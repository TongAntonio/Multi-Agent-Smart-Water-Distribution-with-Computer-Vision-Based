"""Autonomous dispenser agent: perceive -> forecast -> decide (PPO policy) -> act -> coordinate (paper Sec. III).

    python -m agent.main --config config/agent.yaml            # real hardware
    python -m agent.main --config config/agent.yaml --simulate # no GPIO/camera (development)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from collections import deque
from typing import Optional

from .comms import Ack, Forward, State, make_link
from .config import load_config
from .forecast import DemandForecaster
from .perception import Detection
from .policy import HeuristicPolicy, NumpyPolicy
from .spec import ACTIONS, DISPENSE, FORWARD, MAX_HOPS, WAIT, best_neighbor, build_observation

log = logging.getLogger("agent")


class StubDetector:
    """Always-valid detector for --simulate. Never use on a real dispenser."""

    def detect(self, frame):
        return Detection(True, 1.0, (0.2, 0.2, 0.8, 0.8), 500, "stub")


class Agent:
    def __init__(self, cfg: dict, hw, link, camera=None, detector=None, forecaster=None, policy=None, clock=time.time):
        self.cfg, self.hw, self.link, self.cam, self.det, self.clock = cfg, hw, link, camera, detector, clock
        self.id = cfg["agent_id"]
        self.fc = forecaster or DemandForecaster.from_config(cfg)
        self.policy = policy or HeuristicPolicy()
        self.queue: deque = deque()          # waiting requests (dicts)
        self.nbr: dict = {}                  # neighbour id -> (queue_len, water_ml, t_updated)
        self.pending: dict = {}              # request_id -> forward awaiting ACK
        self.seen: set = set()               # forwarded request ids already accepted (de-duplication)
        self.seq = self._ctr = 0
        self.busy_until, self._present_prev, self._last_state = 0.0, False, -1e9
        os.makedirs(cfg["log_dir"], exist_ok=True)
        self.log_path = os.path.join(cfg["log_dir"], f"agent-{self.id}.jsonl")

    # ---------------------------------------------------------------- helpers
    def _record(self, req: dict, outcome: str, now: float, **extra) -> None:
        rec = {"request_id": req["id"], "agent_id": self.id, "origin": req.get("origin", self.id), "volume_ml": req["volume_ml"],
               "outcome": outcome, "t_request": req["t_req"], "t_dispense": now, "latency_s": round(now - req["t_req"], 3),
               "hops": req.get("hops", 0), **extra}
        with open(self.log_path, "a") as f:
            f.write(json.dumps(rec) + "\n")

    def _detect(self) -> Optional[Detection]:
        if self.det is None:
            return None
        try:
            return self.det.detect(self.cam.read() if self.cam else None)
        except Exception as e:  # camera/model errors must never crash the agent
            log.warning("detection failed: %s", e)
            return None

    def _notify(self, text: str) -> None:
        log.info("USER NOTICE: %s", text)   # hook for the 16x2 LCD / app push

    def _next_seq(self) -> int:
        self.seq = (self.seq + 1) & 0xFFFF
        return self.seq

    # ---------------------------------------------------------------- inbound
    def _on_msg(self, m, now: float) -> None:
        if isinstance(m, State):
            self.nbr[m.agent_id] = (m.queue_len, m.water_ml, now)
        elif isinstance(m, Forward) and m.dst == self.id:
            if m.request_id not in self.seen:
                self.seen.add(m.request_id)
                # reservation for a user who was redirected here; claimed when someone arrives at the IR sensor
                self.queue.append({"id": m.request_id, "origin": m.src, "volume_ml": m.volume_ml, "t_req": now - m.waited_s,
                                   "hops": m.hops, "forwarded": True, "claimed": False})
                self.fc.record_request(now, m.volume_ml)
            self.link.send(Ack(self.id, m.src, m.seq, m.request_id))      # always (re-)ACK, even duplicates
        elif isinstance(m, Ack) and m.dst == self.id:
            p = self.pending.pop(m.request_id, None)
            if p:
                self._record(p["req"], "forwarded", now, to=p["dst"])

    def _on_arrival(self, now: float) -> None:
        for r in self.queue:                       # a redirected user arriving here is NOT a new request
            if r.get("forwarded") and not r.get("claimed"):
                r["claimed"] = True
                return
        det = self._detect()
        vol = det.volume_ml if det and det.volume_ml else self.cfg["default_volume_ml"]
        self._ctr = (self._ctr + 1) & 0xFFFFFF
        self.queue.append({"id": (self.id << 24) | self._ctr, "origin": self.id, "volume_ml": int(vol), "t_req": now, "hops": 0})
        self.fc.record_request(now, vol)

    def _send_forward(self, p: dict, now: float) -> None:
        r = p["req"]
        self.link.send(Forward(self.id, p["dst"], p["seq"], r["id"], int(r["volume_ml"]), r.get("hops", 0) + 1, int(now - r["t_req"])))

    def _service_pending(self, now: float) -> None:
        for rid, p in list(self.pending.items()):
            if now - p["t"] < self.cfg["forward_ack_timeout_s"]:
                continue
            if p["tries"] <= self.cfg["forward_retries"]:
                p["tries"] += 1; p["t"] = now
                self._send_forward(p, now)
            else:                                                         # give up: keep the request locally
                del self.pending[rid]
                self.queue.appendleft(p["req"])
                self.nbr.pop(p["dst"], None)
                log.warning("forward of %s to #%s failed after retries; request returned to local queue", rid, p["dst"])

    def _expire(self, now: float) -> None:
        for r in [r for r in self.queue if now - r["t_req"] > self.cfg["request_timeout_s"]]:
            self.queue.remove(r)
            self._record(r, "timeout", now)

    # ---------------------------------------------------------------- one control tick
    def step(self) -> Optional[dict]:
        now = self.clock()
        for m in self.link.poll():
            self._on_msg(m, now)
        rd = self.hw.read()
        self.fc.tick(now, rd.temp_c, rd.humidity)
        if rd.present and not self._present_prev:
            self._on_arrival(now)
        self._present_prev = rd.present
        self._expire(now)
        self._service_pending(now)
        if now - self._last_state >= self.cfg["state_period_s"]:
            self._last_state = now
            self.link.send(State(self.id, self._next_seq(), len(self.queue), rd.level_ml, self.fc.predict(),
                                 now < self.busy_until, rd.temp_c or 0.0, rd.humidity or 0.0))
        if self.queue and now >= self.busy_until and rd.present:
            return self._decide(now, rd)
        return None

    def _decide(self, now: float, rd) -> dict:
        head = self.queue[0]
        det = self._detect()
        cv_valid = True if (self.det is None and self.cfg["cv"]["allow_without_model"]) else bool(det and det.valid)
        vol = det.volume_ml if (det and det.volume_ml) else head["volume_ml"]
        nbr = best_neighbor(self.nbr, vol, now)
        obs = build_observation(water_ml=rd.level_ml, cv_valid=cv_valid, volume_ml=vol, forecast_requests=self.fc.predict(),
                                queue_len=len(self.queue), head_wait_s=now - head["t_req"], nbr=nbr, busy=False)
        a, override = self.policy.act(obs), None
        if a == DISPENSE and not (cv_valid and rd.level_ml - vol >= self.cfg["reserve_ml"]):
            a, override = WAIT, "dispense blocked: container not verified or tank below reserve"
        elif a == FORWARD and (nbr is None or head.get("hops", 0) >= MAX_HOPS):
            a, override = WAIT, "forward blocked: no usable neighbour or hop limit"
        info = {"action": ACTIONS[a], "override": override, "request_id": head["id"]}
        if a == DISPENSE:
            got = self.hw.dispense(vol, keep_going=self.hw.present)
            self.queue.popleft()
            ok = got >= 0.9 * vol
            self._record(head, "served" if ok else "failed", now, dispensed_ml=round(got, 1), cv_score=det.score if det else None)
            self.busy_until = self.clock()
        elif a == FORWARD:
            self.queue.popleft()
            p = {"req": head, "dst": nbr[0], "seq": self._next_seq(), "t": now, "tries": 1}
            self.pending[head["id"]] = p
            self._send_forward(p, now)
            self.nbr[nbr[0]] = (nbr[1] + 1, nbr[2], now)
            self._notify(f"Please go to dispenser #{nbr[0]}")
        if override:
            log.info("%s", override)
        return info

    def run(self) -> None:
        self.link.start()
        try:
            while True:
                self.step()
                time.sleep(self.cfg["tick_s"])
        except KeyboardInterrupt:
            pass
        finally:
            self.link.stop()
            self.hw.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--simulate", action="store_true", help="no GPIO/camera: simulated hardware and stub detector")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = load_config(a.config)
    if a.simulate:
        cfg["simulate_hardware"] = True
    from .hardware import make_hardware
    hw = make_hardware(cfg)
    cam = det = None
    if cfg["simulate_hardware"]:
        det = StubDetector()
    else:
        try:
            from .perception import Camera, ContainerDetector
            cam = Camera(**{k: cfg["camera"][k] for k in ("backend", "index", "width", "height")})
            det = ContainerDetector.from_config(cfg)
        except Exception as e:
            log.error("CV unavailable (%s). The agent will NOT dispense unless cv.allow_without_model=true.", e)
    pp = cfg["policy"]["path"]
    if os.path.exists(pp):
        policy = NumpyPolicy.load(pp)
    else:
        log.warning("%s not found -> using rule-based heuristic policy (train with train/train_ppo.py)", pp)
        policy = HeuristicPolicy()
    Agent(cfg, hw, make_link(cfg), cam, det, policy=policy).run()


if __name__ == "__main__":
    main()
