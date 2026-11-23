"""Software-in-the-loop (SIL) deployment: real agent code, real Mosquitto, the repository's real gateway scripts, simulated peripherals.

What is real: `agent.main.Agent`, `agent.comms.MqttLink` / `LoraLink`, the Mosquitto broker (an OS process), `gateway/firebase_bridge.py`
and `gateway/lora_gateway.py` (separate OS processes). What is simulated: the pump, sensors and camera (`SimHardware`), the container
detector (always valid, 500 ml), the SX1278 radio (`UdpRadio`), the Firebase database (`FirebaseStub`), the users, and the clock
(simulated seconds = real seconds x `--k`). Node-RED and the Angular Admin-Web are NOT run. NB-IoT is NOT covered.

This is not the laboratory or the field deployment, and it cannot say where the broker ran in those trials.

    python -m sim.sil.deployment --link mqtt --scenario broker_window --seed 1 --out results/sil/runs/mqtt_broker_window_s1
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import random
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from agent.comms import LoraLink, MqttLink  # noqa: E402
from agent.config import load_config  # noqa: E402
from agent.hardware import SimHardware  # noqa: E402
from agent.main import Agent  # noqa: E402
from agent.perception import Detection  # noqa: E402
from agent.policy import HeuristicPolicy  # noqa: E402
from agent.spec import ACTIONS, FORWARD  # noqa: E402
from sim.sil.firebase_stub import FirebaseStub  # noqa: E402
from sim.sil.radio import UdpRadio  # noqa: E402

N_AGENTS, VOLUME_ML = 10, 500
HIGH_ML, LOW_ML = 15000.0, 700.0         # agents 1-5 have a full tank; agents 6-10 can serve exactly one 500 ml request
MEAN_GAP_S, ARRIVALS_UNTIL_S, DURATION_S = 25.0, 270.0, 300.0
WINDOW_S = (90.0, 180.0)
PATIENCE_S, WALK_S, LORA_LOSS = 120.0, 5.0, 0.05
SCENARIOS = {"mqtt": ("baseline", "broker_window", "broker_whole", "bridge_window"),
             "lora": ("baseline", "broker_window", "broker_whole", "gateway_window")}


def free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class Proc:
    def __init__(self, cmd, env=None, log=None):
        self.cmd, self.env, self.log, self.p = cmd, env, log, None

    def start(self):
        out = open(self.log, "ab") if self.log else subprocess.DEVNULL
        self.p = subprocess.Popen(self.cmd, env=self.env, stdout=out, stderr=subprocess.STDOUT, cwd=ROOT)

    def alive(self) -> bool:
        return self.p is not None and self.p.poll() is None

    def stop(self):
        if self.p and self.p.poll() is None:
            self.p.kill(); self.p.wait()


class Mosquitto(Proc):
    def __init__(self, port: int, workdir: str):
        conf = os.path.join(workdir, "mosquitto.conf")
        with open(os.path.join(ROOT, "deploy", "mosquitto.sil.conf")) as f:
            open(conf, "w").write(f.read().replace("@PORT@", str(port)))
        super().__init__(["mosquitto", "-c", conf], log=os.path.join(workdir, "mosquitto.log"))
        self.port = port

    def start(self):
        super().start()
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", self.port), 0.2).close(); return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("mosquitto did not start")


class SilHardware(SimHardware):
    def __init__(self, level_ml: float):
        super().__init__(level_ml=level_ml)
        self.served_ml = 0.0

    def dispense(self, ml, keep_going):
        out = super().dispense(ml, keep_going)
        self.served_ml += out
        return out


class FixedDetector:
    def detect(self, frame):
        return Detection(True, 0.95, (0.2, 0.2, 0.8, 0.8), VOLUME_ML, "x")


@dataclass
class User:
    uid: int
    home: int
    t_arr: float
    hops: int = 0
    t_served: Optional[float] = None
    served_at: Optional[int] = None
    outcome: str = "pending"


@dataclass
class Station:
    agent: Agent
    hw: SilHardware
    line: collections.deque = field(default_factory=collections.deque)
    occupant: Optional[User] = None
    free_at: float = 0.0


def run(link: str, scenario: str, seed: int, k: float, out: str) -> dict:
    assert scenario in SCENARIOS[link], f"{scenario} is not defined for the {link} link"
    os.makedirs(out, exist_ok=True)
    rng = random.Random(seed)
    t0 = time.monotonic()
    sim = lambda: (time.monotonic() - t0) * k            # noqa: E731  simulated seconds
    mq_port = free_port()
    udp = {i: free_port() for i in range(1, N_AGENTS + 1)}; udp["gw"] = free_port()
    stub = FirebaseStub()
    env = dict(os.environ, FIREBASE_DB_URL=stub.url, FIREBASE_AUTH="x", SIL_PORTS=json.dumps(udp), PYTHONPATH=ROOT)
    broker = Mosquitto(mq_port, out)
    bridge = Proc([sys.executable, "-m", "gateway.firebase_bridge", "--mqtt-host", "127.0.0.1", "--mqtt-port", str(mq_port)],
                  env=env, log=os.path.join(out, "bridge.log"))
    gateway = Proc([sys.executable, os.path.join(ROOT, "sim", "sil", "lora_gateway_launcher.py"), str(mq_port)],
                   env=env, log=os.path.join(out, "gateway.log")) if link == "lora" else None
    events, facts = [], {}

    # --- infrastructure up (the broker is never started in broker_whole)
    if scenario != "broker_whole":
        broker.start(); events.append((0.0, "broker_up"))
    bridge.start()
    if gateway:
        gateway.start()
    time.sleep(1.5)
    facts["bridge_alive_after_start"], facts["gateway_alive_after_start"] = bridge.alive(), (gateway.alive() if gateway else None)

    # --- agents
    stations: dict[int, Station] = {}
    first_msg_after: dict[int, float] = {}
    restart_t = {"t": None}
    for i in range(1, N_AGENTS + 1):
        cfg = load_config(); cfg.update(agent_id=i, simulate_hardware=True, log_dir=os.path.join(out, "agents"))
        hw = SilHardware(HIGH_ML if i <= 5 else LOW_ML)
        lk = (MqttLink(i, host="127.0.0.1", port=mq_port) if link == "mqtt"
              else LoraLink(i, UdpRadio(i, udp, loss=LORA_LOSS, seed=seed * 100 + i), jitter_s=0.0, freq_hz=433_175_000, sf=9))
        real_poll = lk.poll

        def poll(real_poll=real_poll, i=i):
            m = real_poll()
            if m and restart_t["t"] is not None and i not in first_msg_after and sim() >= restart_t["t"]:
                first_msg_after[i] = sim()
            return m
        lk.poll = poll
        ag = Agent(cfg, hw, lk, None, FixedDetector(), policy=HeuristicPolicy(), clock=sim)
        stations[i] = Station(ag, hw)
    for st in stations.values():
        st.agent.link.start()

    # --- users
    users, pending_arrivals, walking = [], [], []
    uid = 0
    for i in stations:
        t = rng.expovariate(1 / MEAN_GAP_S)
        while t < ARRIVALS_UNTIL_S:
            uid += 1; pending_arrivals.append(User(uid, i, t)); t += rng.expovariate(1 / MEAN_GAP_S)
    pending_arrivals.sort(key=lambda u: u.t_arr)
    users = list(pending_arrivals)
    pending_arrivals = collections.deque(pending_arrivals)
    inject = {"broker_window": ("broker", ), "bridge_window": ("bridge", ), "gateway_window": ("gateway", )}.get(scenario)
    down = False

    try:
        while sim() < DURATION_S:
            now = sim()
            # outage injection
            if inject and not down and now >= WINDOW_S[0]:
                {"broker": broker, "bridge": bridge, "gateway": gateway}[inject[0]].stop(); down = True; events.append((now, inject[0] + "_down"))
            if inject and down and WINDOW_S[1] is not None and now >= WINDOW_S[1] and not any(e[1].endswith("_up2") for e in events):
                {"broker": broker, "bridge": bridge, "gateway": gateway}[inject[0]].start()
                events.append((now, inject[0] + "_up2")); restart_t["t"] = now
                if inject[0] == "broker":
                    time.sleep(0.5)
            # arrivals and walking users join lines
            while pending_arrivals and pending_arrivals[0].t_arr <= now:
                u = pending_arrivals.popleft(); stations[u.home].line.append(u)
            for w in [w for w in walking if w[0] <= now]:
                walking.remove(w); stations[w[2]].line.appendleft(w[1])
            for sid, st in stations.items():
                if st.occupant is None and st.line and now >= st.free_at:
                    u = st.line.popleft()
                    if now - u.t_arr > PATIENCE_S:
                        u.outcome = "gave_up"; continue
                    st.occupant = u; st.hw.served_ml = 0.0; st.hw.set_present(True)
                elif st.occupant is not None and now - st.occupant.t_arr > PATIENCE_S:
                    st.occupant.outcome = "gave_up"; st.occupant = None; st.hw.set_present(False); st.free_at = now + 1.0
            for sid, st in stations.items():
                info = st.agent.step()
                u = st.occupant
                if u is None:
                    continue
                if st.hw.served_ml > 0:
                    u.outcome, u.t_served, u.served_at = "served", now, sid
                    st.occupant = None; st.hw.set_present(False); st.free_at = now + 1.0
                elif info and info["action"] == ACTIONS[FORWARD]:
                    dst = st.agent.pending[info["request_id"]]["dst"]
                    u.hops += 1; st.occupant = None; st.hw.set_present(False); st.free_at = now + 1.0
                    walking.append((now + WALK_S, u, dst))
            time.sleep(0.03)
        facts["bridge_alive_end"], facts["gateway_alive_end"] = bridge.alive(), (gateway.alive() if gateway else None)
    finally:
        for st in stations.values():
            try:
                st.agent.link.stop()
            except Exception:
                pass
        for p in (bridge, gateway, broker):
            if p:
                p.stop()
        stub.close()

    for u in users:
        if u.outcome == "pending":
            u.outcome = "unfinished"
    puts = [(t - t0) * k for t, _ in stub.puts]
    phases = {"before": (0, WINDOW_S[0]), "during": WINDOW_S, "after": (WINDOW_S[1], 1e9)}
    res = {"link": link, "scenario": scenario, "seed": seed, "k": k, "events": events, "facts": facts,
           "reconnect_delay_sim_s": sorted(round(v - restart_t["t"], 1) for v in first_msg_after.values()) if restart_t["t"] else None,
           "phases": {}}
    for ph, (a, b) in phases.items():
        us = [u for u in users if a <= u.t_arr < b]
        sv = [u for u in us if u.outcome == "served"]
        res["phases"][ph] = {"users": len(us), "served": len(sv), "served_via_forward": sum(1 for u in sv if u.hops > 0),
                             "mean_latency_s": round(sum(u.t_served - u.t_arr for u in sv) / len(sv), 2) if sv else None,
                             "dashboard_puts_per_min": round(sum(1 for t in puts if a <= t < b) / ((min(b, DURATION_S) - a) / 60), 1)}
        for grp, rng_ in (("high_tank", range(1, 6)), ("low_tank", range(6, 11))):
            g = [u for u in us if u.home in rng_]
            res["phases"][ph][grp] = {"users": len(g), "served": sum(1 for u in g if u.outcome == "served")}
    with open(os.path.join(out, "result.json"), "w") as f:
        json.dump(res, f, indent=1)
    with open(os.path.join(out, "users.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["uid", "home", "t_arrival_s", "outcome", "hops", "served_at", "t_served_s"])
        for u in users:
            w.writerow([u.uid, u.home, round(u.t_arr, 2), u.outcome, u.hops, u.served_at, None if u.t_served is None else round(u.t_served, 2)])
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--link", choices=("mqtt", "lora"), required=True)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--k", type=float, default=3.0, help="simulated seconds per real second")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    r = run(a.link, a.scenario, a.seed, a.k, a.out)
    print(json.dumps(r["phases"]))


if __name__ == "__main__":
    main()
