"""Success rate / latency / fairness from agent JSONL logs or simulator output.

The paper does not define its fairness index. Here: Jain's index over per-request service quality
q = 1 - latency/timeout for served requests and q = 0 for failed ones. Replace `quality()` if your
definition differs, and re-run on the same logs.
"""
from __future__ import annotations

import argparse
import glob
import json
import math

import numpy as np


def jain(x) -> float:
    x = np.asarray(x, dtype=float)
    s2 = float((x ** 2).sum())
    return 1.0 if x.size == 0 else (0.0 if s2 == 0 else float(x.sum() ** 2 / (x.size * s2)))


def quality(latency_s: float, served: bool, timeout_s: float) -> float:
    return max(0.0, 1.0 - latency_s / timeout_s) if served else 0.0


def summarize(records: list[dict], timeout_s: float = 120.0) -> dict:
    records = [r for r in records if r.get("outcome") != "forwarded"]   # hand-overs are not final outcomes
    served = [r for r in records if r.get("outcome") == "served"]
    lat = [float(r["latency_s"]) for r in served]
    q = [quality(float(r["latency_s"]), True, timeout_s) for r in served] + [0.0] * (len(records) - len(served))
    return {
        "n_requests": len(records),
        "success_rate": len(served) / len(records) if records else math.nan,
        "mean_latency_s": float(np.mean(lat)) if lat else math.nan,
        "p95_latency_s": float(np.percentile(lat, 95)) if lat else math.nan,
        "fairness_jain": jain(q),
    }


def load_jsonl(patterns: list[str]) -> list[dict]:
    out = []
    for pat in patterns:
        for path in sorted(glob.glob(pat)):
            with open(path) as f:
                out += [json.loads(line) for line in f if line.strip()]
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Summarise agent logs (logs/agent-*.jsonl)")
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--timeout", type=float, default=120.0)
    a = ap.parse_args()
    print(json.dumps(summarize(load_jsonl(a.logs), a.timeout), indent=2))
