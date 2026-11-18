"""Baselines for the simulator. Every policy has act(env, obs) -> action."""
from __future__ import annotations

from agent.policy import NumpyPolicy, heuristic_act
from agent.spec import DISPENSE, FORWARD, WAIT, best_neighbor


class HeuristicPolicy:
    """Decentralised rule-based baseline (greedy FIFO + simple forwarding)."""
    name = "heuristic"

    def act(self, env, obs):
        return heuristic_act(obs)


class CentralizedPolicy:
    """Central controller with global, up-to-date knowledge. Every decision needs telemetry up + command down; if
    either packet is lost the agent idles for `timeout_s` (assumption - set to your controller's real timeout)."""
    name = "centralized"

    def __init__(self, timeout_s: float = 3.0):
        self.timeout = timeout_s

    def act(self, env, obs):
        i = env.cur
        if env.rng.random() < 1.0 - (1.0 - env.drop) ** 2:
            env.busy_until[i] = env.t + self.timeout
            return WAIT
        head = env.queue[i][0]
        env.refresh_views(i)
        if env.water[i] >= head["vol"]:
            if env._cv:
                return DISPENSE
            return WAIT
        return FORWARD if best_neighbor(env.views[i], head["vol"], env.t) else WAIT


class LearnedPolicy:
    """Decentralised learned policy executed with NumPy (policy.npz exported from SB3 PPO)."""
    name = "ppo"

    def __init__(self, path: str):
        self.pi = NumpyPolicy.load(path)

    def act(self, env, obs):
        return self.pi.act(obs)
