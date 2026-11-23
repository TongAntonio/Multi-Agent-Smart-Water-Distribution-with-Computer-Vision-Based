"""All simulation experiments for the v2 paper (Sec. V): packet loss, broker outage, ablations.

    python -m sim.train_variants --variant full --seeds 0 1 2 3 4        # (and no_forecast / no_volume / no_fairness)
    python -m sim.run_paper_experiments --eval-seeds 30 --out results/

Writes results/sim_episodes.csv (one row per episode), results/sim_summary.csv, results/sim_tables.tex and
results/meta.json (software versions, git commit, parameters).

THESE ARE SIMULATION RESULTS. They describe the abstract model in sim/env.py (noisy-oracle forecast, Bernoulli CV flag,
simulated seconds, the centralised baseline's assumed 3 s timeout). They are not measurements of the physical dispensers.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import platform
import subprocess
from collections import defaultdict

import numpy as np

from .baselines import CentralizedPolicy, HeuristicPolicy, LearnedPolicy
from .connectivity import ENV_VARIANTS, OutageEnv, run_episode

METRICS = ("success_rate", "mean_latency_s", "fairness_jain", "success_during", "recovery_s", "backlog", "forwards", "lost_forwards")
DROPS = (0.0, 0.2, 0.3, 0.4)
OUTAGES = {"none": None, "window_100_200": (100.0, 200.0), "whole_run": (0.0, 1e9)}
VARIANT_LABEL = {"full": "Proposed (PPO, full)", "no_forecast": "No forecast input", "no_volume": "No volume estimate",
                 "no_fairness": "No fairness term in reward"}


def load_ppo(variant: str, model_dir: str, shipped: str):
    """[(train_seed, policy)] for a variant; falls back to the shipped demo policy for 'full' if no retrained ones exist."""
    out = []
    for p in sorted(glob.glob(os.path.join(model_dir, f"{variant}_seed*.npz"))):
        out.append((int(p.rsplit("seed", 1)[1].split(".")[0]), LearnedPolicy(p)))
    if not out and variant == "full" and os.path.exists(shipped):
        out = [(-1, LearnedPolicy(shipped))]
    return out


def ms(x):
    x = np.asarray([v for v in x if not np.isnan(v)], dtype=float)
    return (float(x.mean()), float(x.std(ddof=1)) if x.size > 1 else 0.0, int(x.size)) if x.size else (float("nan"), float("nan"), 0)


def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-seeds", type=int, default=30)
    ap.add_argument("--agents", type=int, default=20)
    ap.add_argument("--requests", type=int, default=100)
    ap.add_argument("--central-timeout", type=float, default=3.0)
    ap.add_argument("--model-dir", default="models/ablation")
    ap.add_argument("--shipped", default="models/policy.npz")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    kw = dict(n_agents=a.agents, n_requests=a.requests)
    rows = []   # one dict per episode

    def record(exp, scen, name, variant, tseed, seed, res):
        rows.append(dict(experiment=exp, scenario=scen, policy=name, variant=variant, train_seed=tseed, eval_seed=seed,
                         **{m: res.get(m, float("nan")) for m in METRICS}))

    base_pols = [("heuristic", HeuristicPolicy()), ("centralized", CentralizedPolicy(a.central_timeout))]
    ppo_full = load_ppo("full", a.model_dir, a.shipped)
    if not ppo_full:
        raise SystemExit("no PPO policy found (train with sim.train_variants or provide models/policy.npz)")

    # ---- A. packet loss (continuous random loss on every message) and B. broker outage -------------------------
    W = OUTAGES["window_100_200"]      # the 'no outage' run is measured over the same window as the outage run
    for exp, scen_items in (("packet_loss", [(f"{d:.0%}", dict(drop=d, outage=None)) for d in DROPS]),
                            ("outage", [(k, dict(drop=0.0, outage=v, window=W if v is None else None)) for k, v in OUTAGES.items()])):
        for scen, sk in scen_items:
            for name, pol in base_pols:
                for s in range(a.eval_seeds):
                    record(exp, scen, name, "-", -1, s, run_episode(pol, s, sk["drop"], sk["outage"], window=sk.get("window"), **kw))
            for ts, pol in ppo_full:
                for s in range(a.eval_seeds):
                    record(exp, scen, "ppo", "full", ts, s, run_episode(pol, s, sk["drop"], sk["outage"], window=sk.get("window"), **kw))
        print(f"done {exp}", flush=True)

    # ---- C. ablations (no loss, and 40 % loss / outage window for robustness) ------------------------------------
    for scen, sk in (("0%", dict(drop=0.0, outage=None)), ("40%", dict(drop=0.4, outage=None)),
                     ("window_100_200", dict(drop=0.0, outage=OUTAGES["window_100_200"]))):
        for name, pol in base_pols:
            for s in range(a.eval_seeds):
                record("ablation", scen, name, "-", -1, s, run_episode(pol, s, sk["drop"], sk["outage"], **kw))
        for var in ("full", "no_forecast", "no_volume", "no_fairness"):
            for ts, pol in load_ppo(var, a.model_dir, a.shipped):
                for s in range(a.eval_seeds):
                    record("ablation", scen, "ppo", var, ts, s,
                           run_episode(pol, s, sk["drop"], sk["outage"], env_cls=ENV_VARIANTS[var], **kw))
    print("done ablation", flush=True)

    # ---- write episodes ------------------------------------------------------------------------------------------
    ep_path = os.path.join(a.out, "sim_episodes.csv")
    with open(ep_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # ---- summary: pooled episodes per (experiment, scenario, policy, variant) -------------------------------------
    groups = defaultdict(list)
    for r in rows:
        groups[(r["experiment"], r["scenario"], r["policy"], r["variant"])].append(r)
    summ = []
    for (exp, scen, pol, var), rs in groups.items():
        row = dict(experiment=exp, scenario=scen, policy=pol, variant=var, n_episodes=len(rs),
                   n_train_seeds=len({r["train_seed"] for r in rs if r["train_seed"] >= 0}))
        for m in METRICS:
            mean, sd, n = ms([r[m] for r in rs])
            row[m + "_mean"], row[m + "_sd"] = mean, sd
        # SD across training seeds of the per-training-seed mean (PPO only)
        if row["n_train_seeds"] > 1:
            for m in ("success_rate", "mean_latency_s", "fairness_jain"):
                per = defaultdict(list)
                for r in rs:
                    per[r["train_seed"]].append(r[m])
                row[m + "_sd_trainseeds"] = float(np.std([np.nanmean(v) for v in per.values()], ddof=1))
        summ.append(row)
    keys = sorted({k for r in summ for k in r})
    with open(os.path.join(a.out, "sim_summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader(); w.writerows(summ)

    # ---- paired comparison: PPO(full, mean over training seeds) vs heuristic, per eval seed -----------------------
    stats = []
    from math import sqrt
    for (exp, scen) in sorted({(r["experiment"], r["scenario"]) for r in rows}):
        for m in ("success_rate", "mean_latency_s", "fairness_jain"):
            h = {r["eval_seed"]: r[m] for r in rows if (r["experiment"], r["scenario"], r["policy"]) == (exp, scen, "heuristic")}
            pv = defaultdict(list)
            for r in rows:
                if (r["experiment"], r["scenario"], r["policy"], r["variant"]) == (exp, scen, "ppo", "full"):
                    pv[r["eval_seed"]].append(r[m])
            d = [np.mean(pv[s]) - h[s] for s in h if s in pv and not np.isnan(h[s]) and not np.isnan(np.mean(pv[s]))]
            if len(d) > 1:
                mu, sd = float(np.mean(d)), float(np.std(d, ddof=1))
                half = 2.045 * sd / sqrt(len(d)) if len(d) == 30 else 1.96 * sd / sqrt(len(d))   # t(29) ~ 2.045
                hm = float(np.nanmean(list(h.values())))
                stats.append(dict(experiment=exp, scenario=scen, metric=m, n=len(d), mean_diff_ppo_minus_heuristic=mu,
                                  ci95_low=mu - half, ci95_high=mu + half, heuristic_mean=hm, relative_diff_pct=100 * mu / hm if hm else float("nan")))
    with open(os.path.join(a.out, "sim_paired_stats.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(stats[0].keys()))
        w.writeheader(); w.writerows(stats)

    # ---- LaTeX tables ----------------------------------------------------------------------------------------------
    S = {(r["experiment"], r["scenario"], r["policy"], r["variant"]): r for r in summ}

    def pm(r, m, pct=False, dec=1):
        mu, sd = r[m + "_mean"], r[m + "_sd"]
        if np.isnan(mu):
            return "n/a"
        return f"{100*mu:.{dec}f}$\\pm${100*sd:.{dec}f}" if pct else f"{mu:.{dec}f}$\\pm${sd:.{dec}f}"

    tex = []
    # Table: ablation at 0 % loss
    tex.append("% ---- ablation, 0% loss (rows of the laboratory-style table, simulated) ----")
    for lab, key in (("Heuristic baseline", ("ablation", "0%", "heuristic", "-")), ("Centralized baseline", ("ablation", "0%", "centralized", "-")),
                     (VARIANT_LABEL["no_forecast"], ("ablation", "0%", "ppo", "no_forecast")), (VARIANT_LABEL["no_volume"], ("ablation", "0%", "ppo", "no_volume")),
                     (VARIANT_LABEL["no_fairness"], ("ablation", "0%", "ppo", "no_fairness")), (VARIANT_LABEL["full"], ("ablation", "0%", "ppo", "full"))):
        if key in S:
            r = S[key]
            tex.append(f"{lab} & {pm(r,'success_rate',True)} & {pm(r,'mean_latency_s')} & {pm(r,'fairness_jain',dec=3)}\\\\")
    tex.append("")
    tex.append("% ---- packet loss: success rate (%) ----")
    for d in DROPS:
        sc = f"{d:.0%}"
        cells = [pm(S[("packet_loss", sc, p, v)], "success_rate", True) for p, v in (("heuristic", "-"), ("centralized", "-"), ("ppo", "full"))]
        tex.append(f"{sc.replace('%', '')}\\% & " + " & ".join(cells) + "\\\\")
    tex.append("")
    tex.append("% ---- broker outage: success of requests arriving during the outage (%), mean latency (s), backlog clearing time (s) ----")
    for sc, lab in (("none", "No outage"), ("window_100_200", "Outage 100--200\\,s"), ("whole_run", "Outage for the whole run")):
        for p, v, pl in (("heuristic", "-", "Heuristic"), ("centralized", "-", "Centralized"), ("ppo", "full", "Proposed")):
            r = S[("outage", sc, p, v)]
            during = pm(r, "success_during", True)       # requests arriving in 100-200 s (whole run for 'whole_run')
            rec = f"{r['recovery_s_mean']:.0f}" if sc in ("none", "window_100_200") else "--"
            tex.append(f"{lab} & {pl} & {during} & {pm(r,'mean_latency_s')} & {rec}\\\\")
    with open(os.path.join(a.out, "sim_tables.tex"), "w") as f:
        f.write("\n".join(tex) + "\n")

    meta = dict(git_commit=git_commit(), python=platform.python_version(), numpy=np.__version__, eval_seeds=a.eval_seeds,
                agents=a.agents, requests=a.requests, central_timeout_s=a.central_timeout, drops=DROPS, outages={k: v for k, v in OUTAGES.items()},
                ppo_train_seeds={v: [t for t, _ in load_ppo(v, a.model_dir, a.shipped)] for v in VARIANT_LABEL})
    try:
        import gymnasium, stable_baselines3, torch
        meta.update(gymnasium=gymnasium.__version__, stable_baselines3=stable_baselines3.__version__, torch=torch.__version__)
    except Exception:
        pass
    with open(os.path.join(a.out, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print("written to", a.out)


if __name__ == "__main__":
    main()
