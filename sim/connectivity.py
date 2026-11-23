"""Connectivity-loss scenarios and ablation variants for the simulator (paper Sec. V).

WHAT THIS MODELS
  A *broker / gateway outage*: during the outage window every agent-to-agent message (state broadcasts, forward
  requests and, for the centralised baseline, telemetry/commands) is lost. Perception, forecasting and the policy
  run on the dispenser, so an agent can still dispense from its own tank; it just receives no neighbour
  information and every forward_request fails.

WHAT THIS DOES NOT MODEL (so do not present it as a hardware test)
  * the real agent code, MQTT client, radio or gateway - only the abstract dynamics in sim/env.py;
  * whether the deployed system really keeps dispensing when the broker is down (that needs a bench test:
    stop mosquitto, or power off the gateway, and read logs/agent-*.jsonl with agent/metrics.py);
  * an internet outage: nothing in the control loop talks to the internet (the Firebase bridge only feeds the
    dashboard), so that scenario is a no-op by construction and is not simulated.
"""
from __future__ import annotations

import numpy as np

from agent.spec import MAX_VOLUME_ML

from .env import WaterGridEnv

DEFAULT_VOLUME_ML = 500.0     # agent/config.py: default_volume_ml, used when the CV volume estimate is missing


class OutageEnv(WaterGridEnv):
    """WaterGridEnv whose packet-drop probability is 1.0 inside `outage=(t_start, t_end)` (simulated seconds)."""

    def __init__(self, *args, outage=None, window=None, **kw):
        self.t = 0.0
        self._outage = outage
        self._window = window          # measurement window; defaults to the outage window (lets a no-outage run be
                                       # measured over the same seconds, for a like-for-like comparison)
        self._drop_base = 0.0
        self.fin: list = []
        super().__init__(*args, **kw)

    @property
    def drop(self):
        o = self._outage
        return 1.0 if (o is not None and o[0] <= self.t < o[1]) else self._drop_base

    @drop.setter
    def drop(self, v):
        self._drop_base = float(v)

    def reset(self, **kw):
        self.fin = []
        return super().reset(**kw)

    def _finish(self, rq, served: bool, latency: float = 0.0):
        self.fin.append((rq["id"], rq["t_arr"], self.t, bool(served)))
        super()._finish(rq, served, latency)

    def outage_metrics(self) -> dict:
        """Success of requests that arrived during the outage, and how long the backlog took to clear afterwards."""
        win = self._window or self._outage
        t0, t1 = win if win else (0.0, 0.0)
        done = {rid: (ta, tf, ok) for rid, ta, tf, ok in self.fin}
        during = [r for r in self.reqs if t0 <= r["t_arr"] < t1]
        ok_during = sum(1 for r in during if r["id"] in done and done[r["id"]][2])
        # backlog = requests that had arrived before the outage ended but were not finished by then
        backlog = [r for r in self.reqs if r["t_arr"] < t1 and (r["id"] not in done or done[r["id"]][1] > t1)]
        if not win or not backlog:
            rec = 0.0
        else:
            ends = [done[r["id"]][1] if r["id"] in done else self.t for r in backlog]   # unfinished -> episode end
            rec = max(ends) - t1
        return dict(n_during=len(during), success_during=(ok_during / len(during)) if during else float("nan"),
                    backlog=len(backlog), recovery_s=rec)


class NoForecastEnv(OutageEnv):
    """Ablation: the policy gets no demand forecast (forecast input fixed at 0)."""

    def _forecast(self, i):
        return 0.0


class NoVolumeEnv(OutageEnv):
    """Ablation: no container-volume estimate. The policy sees the agent's default volume (500 ml) for every
    request; the physical volume still decides how much water is used."""

    def _obs(self):
        o = super()._obs()
        if self.cur is not None:
            o[2] = np.float32(DEFAULT_VOLUME_ML / MAX_VOLUME_ML)
        return o


ENV_VARIANTS = {"full": OutageEnv, "no_forecast": NoForecastEnv, "no_volume": NoVolumeEnv, "no_fairness": OutageEnv}
# no_fairness differs only in the training reward (fair_coef=0.0), not in the dynamics.


def run_episode(policy, seed: int, drop: float = 0.0, outage=None, env_cls=OutageEnv, window=None, **env_kw) -> dict:
    env = env_cls(outage=outage, window=window, **env_kw)
    obs, _ = env.reset(seed=seed, options={"packet_drop": drop})
    done, info = False, {}
    while not done:
        obs, _, done, _, info = env.step(policy.act(env, obs))
    out = dict(info)
    out.update(env.outage_metrics())
    return out
