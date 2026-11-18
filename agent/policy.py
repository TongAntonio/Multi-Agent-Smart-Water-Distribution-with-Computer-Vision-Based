"""Edge-side policy. Training happens off-device with Stable-Baselines3 PPO (train/train_ppo.py); the trained
actor network is exported to a small .npz and executed here with NumPy only (no PyTorch on the Pi/Jetson)."""
from __future__ import annotations

import numpy as np

from .spec import DISPENSE, FORWARD, MAX_VOLUME_ML, TANK_REF_ML, WAIT


class NumpyPolicy:
    """tanh-MLP actor exported from an SB3 PPO MlpPolicy."""

    def __init__(self, hidden: list[tuple[np.ndarray, np.ndarray]], out: tuple[np.ndarray, np.ndarray]):
        self.hidden, self.out = hidden, out

    @classmethod
    def load(cls, path: str) -> "NumpyPolicy":
        z = np.load(path)
        n = int(z["n_hidden"])
        return cls([(z[f"W{i}"], z[f"b{i}"]) for i in range(n)], (z["Wout"], z["bout"]))

    def save(self, path: str) -> None:
        d = {"n_hidden": len(self.hidden), "Wout": self.out[0], "bout": self.out[1]}
        for i, (w, b) in enumerate(self.hidden):
            d[f"W{i}"], d[f"b{i}"] = w, b
        np.savez(path, **d)

    def logits(self, obs: np.ndarray) -> np.ndarray:
        x = np.asarray(obs, dtype=np.float32)
        for w, b in self.hidden:
            x = np.tanh(x @ w.T + b)
        return x @ self.out[0].T + self.out[1]

    def act(self, obs: np.ndarray, deterministic: bool = True, rng: np.random.Generator | None = None) -> int:
        lg = self.logits(obs)
        if deterministic:
            return int(np.argmax(lg))
        p = np.exp(lg - lg.max())
        p /= p.sum()
        return int((rng or np.random.default_rng()).choice(len(p), p=p))


def heuristic_act(obs: np.ndarray) -> int:
    """Rule-based baseline / safe fallback when no trained policy is deployed (obs layout: see spec.OBS_FIELDS)."""
    water, cv, vol = obs[0] * TANK_REF_ML, obs[1] > 0.5, obs[2] * MAX_VOLUME_ML
    queue, head_wait, nbr_q, nbr_level, busy = obs[4], obs[5], obs[6], obs[7], obs[8] > 0.5
    nbr_ok = nbr_level > 0.0
    if busy:
        return WAIT
    if water < vol:                      # cannot serve here
        return FORWARD if nbr_ok else WAIT
    if cv:
        return DISPENSE                  # greedy first-come-first-served
    if head_wait > 0.4 and nbr_ok and nbr_q < queue:
        return FORWARD                   # CV keeps failing and a neighbour is less busy
    return WAIT


class HeuristicPolicy:
    def act(self, obs: np.ndarray, deterministic: bool = True, rng=None) -> int:
        return heuristic_act(obs)
