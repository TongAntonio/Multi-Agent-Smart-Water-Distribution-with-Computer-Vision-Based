"""Per-stage timing for the dispenser agent. Pure Python, no extra dependencies, and the agent code is not edited.

`StageTimer` wraps methods of live objects (hardware read, camera, detector, forecaster, policy, link, the agent's own
`step`) with a `time.perf_counter_ns` stopwatch and keeps every sample. `instrument_agent` wraps all the stages of an
`Agent` in one call and `restore()` puts the original methods back.

Times are INCLUSIVE: `agent.step` contains the time of `hw.read`, `link.poll`, `policy.act` and so on. They are wall-clock
times of the machine they run on, so numbers taken on a laptop say nothing about a Raspberry Pi; run the same tool on the
Pi (tools/bench_stages.py) to get Pi numbers. Never mix the two in a table without naming the machine.
"""
from __future__ import annotations

import functools
import math
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Callable, Optional

import numpy as np


class StageTimer:
    def __init__(self, clock_ns: Callable[[], int] = time.perf_counter_ns):
        self._clock = clock_ns
        self.samples: dict[str, list[int]] = defaultdict(list)     # stage -> durations in ns
        self._undo: list[Callable[[], None]] = []

    # ------------------------------------------------------------- recording
    def record(self, stage: str, ns: int) -> None:
        self.samples[stage].append(int(ns))

    @contextmanager
    def span(self, stage: str):
        t0 = self._clock()
        try:
            yield
        finally:
            self.record(stage, self._clock() - t0)

    def _timed(self, fn: Callable, stage: str) -> Callable:
        clock, rec = self._clock, self.record

        @functools.wraps(fn)
        def wrapper(*a, **k):
            t0 = clock()
            try:
                return fn(*a, **k)
            finally:                                   # an exception still counts as time spent in the stage
                rec(stage, clock() - t0)
        return wrapper

    # ------------------------------------------------------------- wrapping
    def wrap(self, obj, method: str, stage: Optional[str] = None) -> bool:
        """Replace obj.method by a timed wrapper (instance attribute). False if obj or method does not exist."""
        if obj is None or not callable(getattr(obj, method, None)):
            return False
        had_own = method in getattr(obj, "__dict__", {})
        original = getattr(obj, method)
        setattr(obj, method, self._timed(original, stage or f"{type(obj).__name__}.{method}"))

        def undo():
            if had_own:
                setattr(obj, method, original)
            else:
                delattr(obj, method)
        self._undo.append(undo)
        return True

    def wrap_function(self, module, name: str, stage: Optional[str] = None) -> bool:
        """Same for a module-level function that other code looks up by name at call time."""
        original = getattr(module, name, None)
        if not callable(original):
            return False
        setattr(module, name, self._timed(original, stage or f"{module.__name__.split('.')[-1]}.{name}"))
        self._undo.append(lambda: setattr(module, name, original))
        return True

    def restore(self) -> None:
        while self._undo:
            self._undo.pop()()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.restore()

    def reset(self) -> None:
        self.samples.clear()

    # ------------------------------------------------------------- reporting
    def summary(self) -> dict[str, dict]:
        out = {}
        for stage, ns in self.samples.items():
            ms = np.asarray(ns, dtype=float) / 1e6
            out[stage] = {"n": int(ms.size), "mean_ms": float(ms.mean()), "std_ms": float(ms.std(ddof=1)) if ms.size > 1 else 0.0,
                          "min_ms": float(ms.min()), "p50_ms": float(np.percentile(ms, 50)), "p95_ms": float(np.percentile(ms, 95)),
                          "p99_ms": float(np.percentile(ms, 99)), "max_ms": float(ms.max()), "total_ms": float(ms.sum())}
        return dict(sorted(out.items()))

    def overhead_ns(self, n: int = 20000) -> float:
        """Median cost of one timed call of an empty function: the stopwatch's own bias, to quote next to the results."""
        probe = StageTimer(self._clock)
        f = probe._timed(lambda: None, "probe")
        for _ in range(n):
            f()
        return float(np.median(probe.samples["probe"]))


# ---------------------------------------------------------------------------------------------------------------
def instrument_agent(agent, timer: StageTimer, *, include_main_functions: bool = True) -> list[str]:
    """Wrap every stage of a live Agent. Returns the names of the stages that were wrapped.

    Stage names: agent.step, agent.decide, agent.on_arrival, link.poll, link.send, hw.read, hw.dispense, camera.read,
    perception.detect, forecast.tick, forecast.predict, forecast.record_request, policy.act, spec.build_observation,
    spec.best_neighbor.
    """
    wrapped = []

    def w(obj, method, stage):
        if timer.wrap(obj, method, stage):
            wrapped.append(stage)

    w(agent, "step", "agent.step")
    w(agent, "_decide", "agent.decide")
    w(agent, "_on_arrival", "agent.on_arrival")
    w(agent.link, "poll", "link.poll")
    w(agent.link, "send", "link.send")
    w(agent.hw, "read", "hw.read")
    w(agent.hw, "dispense", "hw.dispense")
    w(agent.cam, "read", "camera.read")
    w(agent.det, "detect", "perception.detect")
    w(agent.fc, "tick", "forecast.tick")
    w(agent.fc, "predict", "forecast.predict")
    w(agent.fc, "record_request", "forecast.record_request")
    w(agent.policy, "act", "policy.act")
    if include_main_functions:
        import agent.main as main_mod
        for name, stage in (("build_observation", "spec.build_observation"), ("best_neighbor", "spec.best_neighbor")):
            if timer.wrap_function(main_mod, name, stage):
                wrapped.append(stage)
    return wrapped


# ---------------------------------------------------------------------------------------------------------------
def measure_roundtrip(link_a, link_b, n: int = 200, timeout_s: float = 2.0, poll_s: float = 0.0002) -> dict:
    """Round-trip time of a message through a link: A sends a Forward to B, B answers with an Ack, A receives it.

    Works with any pair of Link objects that are already started (MemoryLink, MqttLink against a broker, ...). Messages that
    do not come back within timeout_s are counted as lost. Returns the samples (ms) and a summary.
    """
    import threading

    from .comms import Ack, Forward

    stop = threading.Event()

    def echo():
        while not stop.is_set():
            for m in link_b.poll():
                if isinstance(m, Forward):
                    link_b.send(Ack(link_b.id, m.src, m.seq, m.request_id))
            time.sleep(poll_s)

    th = threading.Thread(target=echo, daemon=True)
    th.start()
    rtt_ms, lost = [], 0
    try:
        for i in range(n):
            t0 = time.perf_counter()
            link_a.send(Forward(link_a.id, link_b.id, i & 0xFFFF, 1_000_000 + i, 500, 1, 0))
            got = False
            while time.perf_counter() - t0 < timeout_s and not got:
                got = any(isinstance(m, Ack) and m.request_id == 1_000_000 + i for m in link_a.poll())
                if not got:
                    time.sleep(poll_s)
            if got:
                rtt_ms.append((time.perf_counter() - t0) * 1000.0)
            else:
                lost += 1
    finally:
        stop.set()
        th.join(timeout=1.0)
    a = np.asarray(rtt_ms) if rtt_ms else np.asarray([math.nan])
    return {"n_sent": n, "n_lost": lost, "rtt_ms": rtt_ms,
            "mean_ms": float(np.nanmean(a)), "p50_ms": float(np.nanpercentile(a, 50)),
            "p95_ms": float(np.nanpercentile(a, 95)), "max_ms": float(np.nanmax(a))}
