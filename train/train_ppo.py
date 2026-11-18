"""Train the decentralised dispatch policy with Stable-Baselines3 PPO (parameter sharing: one policy, executed
independently by every agent on its local observation) and export it for the edge agent.

  pip install -r requirements/train.txt
  python -m train.train_ppo --timesteps 300000

Train on a workstation (not on the Pi/Jetson); only models/policy.npz is copied to the dispensers.
"""
from __future__ import annotations

import argparse
import os

import numpy as np

from agent.policy import NumpyPolicy
from agent.spec import OBS_DIM
from sim.env import WaterGridEnv


def export_sb3_policy(model, path: str) -> NumpyPolicy:
    """Extract the tanh-MLP actor from an SB3 PPO MlpPolicy into a NumPy-only policy."""
    import torch.nn as nn
    pi = model.policy
    to = lambda t: t.detach().cpu().numpy().astype(np.float32)
    hidden = [(to(m.weight), to(m.bias)) for m in pi.mlp_extractor.policy_net if isinstance(m, nn.Linear)]
    acts = [m for m in pi.mlp_extractor.policy_net if not isinstance(m, nn.Linear)]
    assert all(isinstance(m, nn.Tanh) for m in acts), "exporter assumes tanh activations"
    p = NumpyPolicy(hidden, (to(pi.action_net.weight), to(pi.action_net.bias)))
    p.save(path)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timesteps", type=int, default=300_000)
    ap.add_argument("--n-envs", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--drop-max", type=float, default=0.4, help="train with packet loss sampled in [0, drop-max]")
    ap.add_argument("--out", default="models")
    a = ap.parse_args()
    import torch.nn as nn
    from stable_baselines3 import PPO
    from stable_baselines3.common.env_util import make_vec_env

    env = make_vec_env(lambda: WaterGridEnv(drop_range=(0.0, a.drop_max)), n_envs=a.n_envs, seed=a.seed)
    model = PPO("MlpPolicy", env, n_steps=512, batch_size=256, learning_rate=3e-4, gamma=0.99, gae_lambda=0.95,
                ent_coef=0.01, seed=a.seed, verbose=1,
                policy_kwargs=dict(net_arch=dict(pi=[64, 64], vf=[64, 64]), activation_fn=nn.Tanh))
    model.learn(total_timesteps=a.timesteps)
    os.makedirs(a.out, exist_ok=True)
    model.save(os.path.join(a.out, "ppo_sb3"))
    pol = export_sb3_policy(model, os.path.join(a.out, "policy.npz"))

    rng = np.random.default_rng(0)                       # self-check: exported NumPy policy == SB3 policy
    obs = rng.random((500, OBS_DIM)).astype(np.float32)
    ref, _ = model.predict(obs, deterministic=True)
    mism = int(sum(pol.act(o) != r for o, r in zip(obs, ref)))
    print(f"export parity check: {mism}/500 mismatching actions")
    assert mism == 0, "NumPy export does not match the SB3 policy"
    print("Saved", os.path.join(a.out, "policy.npz"), "- now run: python -m sim.run_experiment")


if __name__ == "__main__":
    main()
