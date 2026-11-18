"""Lab-trial style evaluation in simulation: 20 agents, 100 requests, packet loss 0/20/30/40 %.

Reports success rate, mean time-to-service (simulated seconds) and fairness (Jain) for each policy.
THESE ARE SIMULATION NUMBERS - they are not the paper's hardware measurements and cannot reproduce them.
"""
from __future__ import annotations

import argparse
import os

import numpy as np

from .baselines import CentralizedPolicy, HeuristicPolicy, LearnedPolicy
from .env import WaterGridEnv


def run_episode(policy, seed: int, drop: float, **env_kw) -> dict:
    env = WaterGridEnv(**env_kw)
    obs, _ = env.reset(seed=seed, options={"packet_drop": drop})
    done, info = False, {}
    while not done:
        obs, _, done, _, info = env.step(policy.act(env, obs))
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy-npz", default="models/policy.npz")
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--agents", type=int, default=20)
    ap.add_argument("--requests", type=int, default=100)
    ap.add_argument("--drops", type=float, nargs="+", default=[0.0, 0.2, 0.3, 0.4])
    ap.add_argument("--central-timeout", type=float, default=3.0)
    ap.add_argument("--csv", default=None)
    a = ap.parse_args()
    pols = [HeuristicPolicy(), CentralizedPolicy(a.central_timeout)]
    if os.path.exists(a.policy_npz):
        pols.append(LearnedPolicy(a.policy_npz))
    else:
        print(f"[info] {a.policy_npz} not found -> PPO row skipped (train with: python -m train.train_ppo)")
    rows = []
    print(f"{'policy':12} {'drop':>5} {'success%':>9} {'latency_s':>10} {'fairness':>9}   (mean over {a.seeds} seeds)")
    for p in pols:
        for d in a.drops:
            res = [run_episode(p, s, d, n_agents=a.agents, n_requests=a.requests) for s in range(a.seeds)]
            m = {k: float(np.nanmean([r[k] for r in res])) for k in ("success_rate", "mean_latency_s", "fairness_jain")}
            sd = float(np.std([r["success_rate"] for r in res]))
            rows.append((p.name, d, m["success_rate"], sd, m["mean_latency_s"], m["fairness_jain"]))
            print(f"{p.name:12} {d:5.0%} {100*m['success_rate']:6.1f}±{100*sd:<3.1f} {m['mean_latency_s']:10.1f} {m['fairness_jain']:9.3f}")
    if a.csv:
        import csv
        with open(a.csv, "w", newline="") as f:
            w = csv.writer(f); w.writerow(["policy", "drop", "success", "success_std", "latency_s", "fairness"]); w.writerows(rows)


if __name__ == "__main__":
    main()
