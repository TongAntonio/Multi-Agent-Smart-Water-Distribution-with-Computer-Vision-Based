"""Train the PPO policy variants used in the ablation study (same recipe as train/train_ppo.py).

    python -m sim.train_variants --variant full --seeds 0 1 2 --timesteps 300000
    variants: full | no_forecast | no_volume | no_fairness

Each (variant, seed) writes models/ablation/<variant>_seed<k>.npz (NumPy actor, same format as models/policy.npz).
Only the training environment/reward differs between variants; all other settings are identical.
"""
from __future__ import annotations

import argparse
import os
import time

import numpy as np


def make_env_fn(variant: str):
    from .connectivity import ENV_VARIANTS
    cls = ENV_VARIANTS[variant]
    kw = dict(drop_range=(0.0, 0.4))
    if variant == "no_fairness":
        kw["fair_coef"] = 0.0           # remove the fairness term from the reward
    return lambda: cls(**kw)


def train_one(variant: str, seed: int, timesteps: int, out_dir: str, n_envs: int = 4) -> str:
    import torch
    import torch.nn as nn
    from stable_baselines3 import PPO
    from stable_baselines3.common.env_util import make_vec_env

    from train.train_ppo import export_sb3_policy

    torch.set_num_threads(1)
    env = make_vec_env(make_env_fn(variant), n_envs=n_envs, seed=seed)
    model = PPO("MlpPolicy", env, n_steps=512, batch_size=256, learning_rate=3e-4, gamma=0.99, gae_lambda=0.95,
                ent_coef=0.01, seed=seed, verbose=0,
                policy_kwargs=dict(net_arch=dict(pi=[64, 64], vf=[64, 64]), activation_fn=nn.Tanh))
    t0 = time.time()
    model.learn(total_timesteps=timesteps)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{variant}_seed{seed}.npz")
    pol = export_sb3_policy(model, path)
    rng = np.random.default_rng(0)
    obs = rng.random((200, 9)).astype(np.float32)
    ref, _ = model.predict(obs, deterministic=True)
    assert all(pol.act(o) == r for o, r in zip(obs, ref)), "NumPy export does not match the SB3 policy"
    print(f"{variant} seed {seed}: {timesteps} steps in {time.time() - t0:.0f}s -> {path}", flush=True)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True, choices=["full", "no_forecast", "no_volume", "no_fairness"])
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--timesteps", type=int, default=300_000)
    ap.add_argument("--out", default="models/ablation")
    a = ap.parse_args()
    for s in a.seeds:
        train_one(a.variant, s, a.timesteps, a.out)


if __name__ == "__main__":
    main()
