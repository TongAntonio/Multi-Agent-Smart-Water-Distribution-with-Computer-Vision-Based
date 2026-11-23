"""Run every software-in-the-loop scenario for several seeds (two at a time) and aggregate the results.

    python -m sim.run_sil --seeds 5 --k 5            # runs and aggregates; needs `mosquitto` on PATH
    python -m sim.run_sil --aggregate-only           # re-aggregate results/sil/runs/*

Outputs: results/sil/runs/<link>_<scenario>_s<seed>/ (result.json, users.csv, agent logs, mosquitto.conf and logs),
results/sil/summary.csv, results/sil/summary.md, results/sil/meta.json. See README ("Software-in-the-loop deployment").
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import platform
import statistics as st
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sim.sil.deployment import ARRIVALS_UNTIL_S, DURATION_S, HIGH_ML, LOW_ML, MEAN_GAP_S, N_AGENTS, SCENARIOS, WINDOW_S  # noqa: E402

OUT = os.path.join(ROOT, "results", "sil")
PHASES = ("before", "during", "after")
K_USED = [None]


def run_all(seeds: int, k: float, jobs: int = 2, subset=None, subdir: str = "runs") -> None:
    todo = [(l, s, sd) for l in SCENARIOS for s in SCENARIOS[l] for sd in range(1, seeds + 1) if subset is None or (l, s) in subset]
    running: list = []
    while todo or running:
        running = [(p, n) for p, n in running if p.poll() is None]
        while todo and len(running) < jobs:
            l, s, sd = todo.pop(0)
            d = os.path.join(OUT, subdir, f"{l}_{s}_s{sd}")
            if os.path.exists(os.path.join(d, "result.json")):
                continue
            p = subprocess.Popen([sys.executable, "-m", "sim.sil.deployment", "--link", l, "--scenario", s, "--seed", str(sd),
                                  "--k", str(k), "--out", d], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            running.append((p, d)); print("started", l, s, sd, flush=True)
        time.sleep(1.0)


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))] if xs else None


def aggregate(subdir: str = "runs", suffix: str = "") -> None:
    runs = {}
    for f in sorted(glob.glob(os.path.join(OUT, subdir, "*", "result.json"))):
        r = json.load(open(f)); d = os.path.dirname(f)
        users = list(csv.DictReader(open(os.path.join(d, "users.csv"))))
        runs.setdefault((r["link"], r["scenario"]), []).append((r, users))
    rows = []
    for (link, scen), lst in sorted(runs.items()):
        for ph in PHASES:
            rates, lows, highs, puts = [], [], [], []
            lat, via, n_users, n_served = [], 0, 0, 0
            a, b = {"before": (0, WINDOW_S[0]), "during": WINDOW_S, "after": (WINDOW_S[1], 1e9)}[ph]
            for r, users in lst:
                p = r["phases"][ph]
                rates.append(p["served"] / p["users"] if p["users"] else float("nan"))
                lo, hi = p["low_tank"], p["high_tank"]
                lows.append(lo["served"] / lo["users"] if lo["users"] else float("nan")); highs.append(hi["served"] / hi["users"] if hi["users"] else float("nan"))
                puts.append(p["dashboard_puts_per_min"])
                for u in users:
                    if a <= float(u["t_arrival_s"]) < b:
                        n_users += 1
                        if u["outcome"] == "served":
                            n_served += 1; lat.append(float(u["t_served_s"]) - float(u["t_arrival_s"])); via += int(int(u["hops"]) > 0)
            sd = lambda x: st.pstdev(x) if len(x) > 1 else 0.0  # noqa: E731
            rows.append({"link": link, "scenario": scen, "phase": ph, "runs": len(lst), "users": n_users, "served": n_served,
                         "success_mean": round(st.mean(rates), 3), "success_std": round(sd(rates), 3),
                         "low_tank_success": round(st.mean(lows), 3), "high_tank_success": round(st.mean(highs), 3),
                         "via_forward_share": round(via / n_served, 3) if n_served else None,
                         "latency_mean_s": round(st.mean(lat), 1) if lat else None, "latency_p50_s": round(pct(lat, .5), 1) if lat else None,
                         "latency_p95_s": round(pct(lat, .95), 1) if lat else None, "dashboard_puts_per_min": round(st.mean(puts), 1)})
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f"summary{suffix}.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    with open(os.path.join(OUT, f"summary{suffix}.md"), "w") as f:
        f.write("| link | scenario | phase | runs | users | success (mean ± std over runs) | low-tank | high-tank | via forward | latency mean / p50 / p95 (s) | dashboard PUT/min |\n"
                "|---|---|---|---|---|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r['link']} | {r['scenario']} | {r['phase']} | {r['runs']} | {r['users']} | {r['success_mean']*100:.1f} ± {r['success_std']*100:.1f} % | "
                    f"{r['low_tank_success']*100:.0f} % | {r['high_tank_success']*100:.0f} % | "
                    f"{'-' if r['via_forward_share'] is None else format(r['via_forward_share']*100, '.0f') + ' %'} | "
                    f"{r['latency_mean_s']} / {r['latency_p50_s']} / {r['latency_p95_s']} | {r['dashboard_puts_per_min']} |\n")
    facts = {f"{l}_{s}": [r["facts"] for r, _ in lst] for (l, s), lst in runs.items() if s in ("broker_whole", "gateway_window", "bridge_window")}
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        commit = None
    mos = subprocess.run(["mosquitto", "-h"], capture_output=True, text=True).stdout.splitlines()[:1]
    import paho
    json.dump({"git_commit": commit, "python": platform.python_version(), "mosquitto": mos, "paho_mqtt": getattr(paho, "__version__", "?"),
               "agents": N_AGENTS, "tank_ml": {"agents_1_5": HIGH_ML, "agents_6_10": LOW_ML}, "container_ml": 500, "mean_gap_s": MEAN_GAP_S,
               "time_scale_k": K_USED[0], "arrivals_until_s": ARRIVALS_UNTIL_S, "duration_s": DURATION_S, "outage_window_s": WINDOW_S,
               "runs_per_scenario": {f"{l}_{s}": len(v) for (l, s), v in runs.items()}, "process_facts": facts},
              open(os.path.join(OUT, f"meta{suffix}.json"), "w"), indent=1)
    print(open(os.path.join(OUT, f"summary{suffix}.md")).read())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5); ap.add_argument("--k", type=float, default=5.0)
    ap.add_argument("--jobs", type=int, default=2); ap.add_argument("--aggregate-only", action="store_true")
    ap.add_argument("--realtime", action="store_true", help="k=1 run of the MQTT broker-window scenario only (about 5 min per run)")
    a = ap.parse_args()
    if a.realtime:
        K_USED[0] = 1.0
        if not a.aggregate_only:
            run_all(a.seeds, 1.0, a.jobs, subset={("mqtt", "broker_window")}, subdir="runs_realtime")
        aggregate("runs_realtime", "_realtime")
    else:
        K_USED[0] = a.k
        if not a.aggregate_only:
            run_all(a.seeds, a.k, a.jobs)
        aggregate()
