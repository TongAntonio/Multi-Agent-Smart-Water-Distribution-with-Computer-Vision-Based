"""Multi-agent water-distribution simulator (Gymnasium) with parameter-sharing PPO in mind.

One env step = one decision of ONE dispenser that has a waiting request (event-driven); a single shared policy
controls all agents using only their *local* observation (spec.OBS_FIELDS) - i.e. decentralised execution.
Packet loss (`packet_drop`) degrades the neighbour information exchanged between agents (stale views) and makes
forward_request messages fail.

SIMPLIFICATIONS (be explicit about these when reporting results):
  * the LSTM forecast is replaced by a noisy oracle of the true upcoming arrivals (`forecast_noise`);
  * CV is a Bernoulli flag with accuracy `cv_acc`; every container is physically valid;
  * the user is assumed to be present at whichever dispenser holds the request (forward adds `forward_delay_s`);
  * latency is simulated seconds (queueing + decision ticks), NOT the hardware end-to-end latency of the paper.
"""
from __future__ import annotations

from bisect import bisect_right

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from agent.metrics import jain
from agent.spec import (DISPENSE, FORWARD, MAX_HOPS, OBS_DIM, VOLUME_CLASSES_ML, WAIT, best_neighbor, build_observation)


class WaterGridEnv(gym.Env):
    metadata: dict = {}

    def __init__(self, n_agents=20, n_requests=100, window_s=300.0, max_time_s=900.0, drop_range=(0.0, 0.0), nbr_k=2,
                 flow_ml_s=100.0, timeout_s=120.0, cv_acc=0.92, forecast_noise=1.0, bcast_period=5, forward_delay_s=5.0,
                 ack_timeout_s=3.0, wait_cost=0.002, fair_coef=1.0, hot_frac=0.25, hot_mult=4.0):
        super().__init__()
        self.n, self.n_req, self.window, self.max_t = n_agents, n_requests, window_s, max_time_s
        self.drop_range, self.k, self.flow, self.timeout = drop_range, nbr_k, flow_ml_s, timeout_s
        self.cv_acc, self.f_noise, self.bcast, self.fwd_delay, self.ack_to = cv_acc, forecast_noise, bcast_period, forward_delay_s, ack_timeout_s
        self.wait_cost, self.fair_coef, self.hot_frac, self.hot_mult = wait_cost, fair_coef, hot_frac, hot_mult
        self.observation_space = spaces.Box(0.0, 1.0, (OBS_DIM,), np.float32)
        self.action_space = spaces.Discrete(3)
        self.cur = None

    # ------------------------------------------------------------------ episode setup
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        rng, n = self.np_random, self.n
        self.rng = rng
        self.drop = float(options["packet_drop"]) if options and "packet_drop" in options else float(rng.uniform(*self.drop_range))
        self.cap = rng.uniform(1500, 3500, n)
        self.water = self.cap.copy()
        hot = rng.random(n) < self.hot_frac
        w = np.where(hot, self.hot_mult, 1.0)
        agent = rng.choice(n, size=self.n_req, p=w / w.sum())
        surge = rng.random(self.n_req) < 0.3
        t = np.where(surge, rng.uniform(0.4, 0.6, self.n_req), rng.uniform(0, 1, self.n_req)) * self.window
        vols = rng.choice(VOLUME_CLASSES_ML, size=self.n_req, p=[0.4, 0.4, 0.2])
        order = np.argsort(t)
        self.reqs = [dict(id=k, agent=int(agent[o]), t_arr=float(t[o]), vol=int(vols[o]), hops=0, ready=0.0)
                     for k, o in enumerate(order)]
        self.arrivals = [sorted(r["t_arr"] for r in self.reqs if r["agent"] == i) for i in range(n)]
        self.queue = [[] for _ in range(n)]
        self.busy_until = np.zeros(n)
        self.nbrs = [[(i + d) % n for d in range(-self.k, self.k + 1) if d != 0] for i in range(n)]
        self.views = [{} for _ in range(n)]
        self.t, self.idx = 0.0, 0
        self.S1 = self.S2 = 0.0
        self.n_done = 0
        self.st = dict(served=0, lat=[], q=[], forwards=0, lost=0, served_ml=0.0)
        self._r, self.cur, self._cv = 0.0, None, 1
        self._broadcast()
        self._advance()
        return self._obs(), {}

    # ------------------------------------------------------------------ dynamics
    def _broadcast(self):
        for i in range(self.n):
            info = (len(self.queue[i]), float(self.water[i]), self.t)
            for j in self.nbrs[i]:
                if self.rng.random() >= self.drop:
                    self.views[j][i] = info

    def refresh_views(self, i: int):
        """Perfect, fresh neighbour information (used only by the centralised baseline)."""
        self.views[i] = {j: (len(self.queue[j]), float(self.water[j]), self.t) for j in self.nbrs[i]}

    def _jain_now(self):
        return 1.0 if self.n_done == 0 or self.S2 == 0 else self.S1 ** 2 / (self.n_done * self.S2)

    def _finish(self, rq, served: bool, latency: float = 0.0):
        q = max(0.0, 1.0 - latency / self.timeout) if served else 0.0
        j0 = self._jain_now()
        self.S1 += q; self.S2 += q * q; self.n_done += 1
        self._r += self.fair_coef * ((0.0 if self.S2 == 0 else self._jain_now()) - j0)
        self.st["q"].append(q)
        if served:
            self.st["served"] += 1; self.st["lat"].append(latency); self.st["served_ml"] += rq["vol"]
            self._r += 1.0 + 0.5 * q
        else:
            self._r -= 1.0

    def _advance(self):
        n = self.n
        while True:
            self.t += 1.0
            t = self.t
            while self.idx < len(self.reqs) and self.reqs[self.idx]["t_arr"] <= t:
                rq = self.reqs[self.idx]; self.queue[rq["agent"]].append(rq); self.idx += 1
            if int(t) % self.bcast == 0:
                self._broadcast()
            nq = 0
            for i in range(n):
                keep = []
                for rq in self.queue[i]:
                    if t - rq["t_arr"] > self.timeout:
                        self._finish(rq, served=False)
                    else:
                        keep.append(rq)
                self.queue[i] = keep
                nq += len(keep)
            self._r -= self.wait_cost * nq
            if (self.idx >= len(self.reqs) and nq == 0) or t >= self.max_t:
                self.cur = None
                return
            cands = [i for i in range(n) if self.queue[i] and self.busy_until[i] <= t and self.queue[i][0]["ready"] <= t]
            if cands:
                self.cur = max(cands, key=lambda i: t - self.queue[i][0]["t_arr"])
                return

    def _forecast(self, i):
        a = self.arrivals[i]
        true = bisect_right(a, self.t + 300.0) - bisect_right(a, self.t)
        return max(0.0, true + self.rng.normal(0.0, self.f_noise))

    def _obs(self):
        if self.cur is None:
            return np.zeros(OBS_DIM, dtype=np.float32)
        i = self.cur
        head = self.queue[i][0]
        self._cv = int(self.rng.random() < self.cv_acc)
        nbr = best_neighbor(self.views[i], head["vol"], self.t)
        return build_observation(water_ml=self.water[i], cv_valid=self._cv, volume_ml=head["vol"],
                                 forecast_requests=self._forecast(i), queue_len=len(self.queue[i]),
                                 head_wait_s=self.t - head["t_arr"], nbr=nbr, busy=False)

    def step(self, action):
        i, a, t = self.cur, int(action), self.t
        head = self.queue[i][0]
        self._r = 0.0
        if a == DISPENSE:
            if self._cv == 0 or self.water[i] < head["vol"]:
                self._r -= 0.05                       # blocked: container not verified / tank too low
            else:
                self.water[i] -= head["vol"]
                self.busy_until[i] = t + head["vol"] / self.flow
                self.queue[i].pop(0)
                self._finish(head, served=True, latency=t - head["t_arr"])
        elif a == FORWARD:
            nb = best_neighbor(self.views[i], head["vol"], t)
            if nb is None or head["hops"] >= MAX_HOPS:
                self._r -= 0.05
            elif self.rng.random() >= self.drop:      # message delivered (and acknowledged)
                j = nb[0]
                self.queue[i].pop(0)
                head["hops"] += 1; head["ready"] = t + self.fwd_delay; head["agent"] = j
                self.queue[j].append(head)
                self.views[i][j] = (nb[1] + 1, nb[2], t)
                self.st["forwards"] += 1
                self._r -= 0.02
            else:                                     # lost: sender waits for the ACK timeout, keeps the request
                self.busy_until[i] = t + self.ack_to
                self.st["lost"] += 1
                self._r -= 0.1
        self._advance()
        terminated = self.cur is None
        return self._obs(), float(self._r), terminated, False, (self.metrics() if terminated else {})

    def metrics(self) -> dict:
        n = len(self.reqs)
        q = list(self.st["q"]) + [0.0] * (n - len(self.st["q"]))   # unfinished requests count as failures
        lat = self.st["lat"]
        return dict(success_rate=self.st["served"] / n, mean_latency_s=float(np.mean(lat)) if lat else float("nan"),
                    p95_latency_s=float(np.percentile(lat, 95)) if lat else float("nan"), fairness_jain=jain(q),
                    forwards=self.st["forwards"], lost_forwards=self.st["lost"], packet_drop=self.drop)
