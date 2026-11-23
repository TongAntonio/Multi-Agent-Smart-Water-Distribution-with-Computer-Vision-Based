"""Tests for the stage timer (agent/timing.py) and the benchmark workload (tools/bench_stages.py).

Most tests use an injected clock, so they are exact and do not depend on the machine. The tests marked `timing` compare real
wall-clock times with generous budgets. They are tripwires for a slow regression on a development machine, not performance
claims: on a Raspberry Pi set TIMING_BUDGET_SCALE (for example 10) or deselect them with  -m "not timing".
"""
import os
import shutil
import socket
import subprocess
import time

import numpy as np
import pytest

from agent.comms import Ack, Forward, MemoryBus, MemoryLink, State
from agent.timing import StageTimer, instrument_agent, measure_roundtrip
from tests.test_agent import Clock, Det, make_agent
from tools.bench_stages import CYCLE, drive, enable_nodelay

SCALE = float(os.environ.get("TIMING_BUDGET_SCALE", "1"))
timing = pytest.mark.timing


class FakeClock:
    """perf_counter_ns stand-in: every call returns the next value of a script."""

    def __init__(self, *values):
        self.values = list(values)

    def __call__(self):
        return self.values.pop(0)


# ---------------------------------------------------------------- the stopwatch itself (exact, no real time)
def test_wrapped_method_records_exact_duration_and_returns_value():
    class Thing:
        def work(self, x):
            return x * 2
    th, t = Thing(), StageTimer(FakeClock(1_000, 6_000_000 + 1_000))
    assert t.wrap(th, "work", "thing.work")
    assert th.work(21) == 42
    assert t.samples["thing.work"] == [6_000_000]
    assert t.summary()["thing.work"]["mean_ms"] == pytest.approx(6.0)


def test_exception_is_recorded_and_propagates():
    class Thing:
        def boom(self):
            raise RuntimeError("modem")
    th, t = Thing(), StageTimer(FakeClock(0, 2_000_000))
    t.wrap(th, "boom", "thing.boom")
    with pytest.raises(RuntimeError):
        th.boom()
    assert t.samples["thing.boom"] == [2_000_000]


def test_restore_puts_the_original_back():
    class Thing:
        def work(self):
            return "orig"
    th = Thing()
    with StageTimer() as t:
        t.wrap(th, "work", "w")
        assert "work" in th.__dict__
        th.work()
    assert "work" not in th.__dict__ and th.work() == "orig" and len(t.samples["w"]) == 1


def test_wrap_skips_missing_objects_and_methods():
    t = StageTimer()
    assert t.wrap(None, "x") is False
    assert t.wrap(object(), "nope") is False


def test_summary_statistics_of_known_samples():
    t = StageTimer()
    for ms in range(1, 101):
        t.record("s", ms * 1_000_000)
    s = t.summary()["s"]
    assert (s["n"], s["mean_ms"], s["min_ms"], s["max_ms"]) == (100, pytest.approx(50.5), 1.0, 100.0)
    assert s["p50_ms"] == pytest.approx(50.5) and s["p95_ms"] == pytest.approx(95.05) and s["total_ms"] == pytest.approx(5050.0)
    assert s["min_ms"] <= s["p50_ms"] <= s["p95_ms"] <= s["p99_ms"] <= s["max_ms"]


def test_span_context_manager():
    t = StageTimer(FakeClock(10, 4_000_010))
    with t.span("block"):
        pass
    assert t.samples["block"] == [4_000_000]


def test_stopwatch_overhead_is_small():
    assert StageTimer().overhead_ns(2000) < 200_000          # well below 0.2 ms even on a slow board


@timing
def test_real_sleep_is_measured_not_less_than_requested():
    class Thing:
        def work(self):
            time.sleep(0.01)
    th, t = Thing(), StageTimer()
    t.wrap(th, "work", "w")
    for _ in range(5):
        th.work()
    s = t.summary()["w"]
    assert s["min_ms"] >= 9.0                                # sleep never returns early; no upper bound (loaded machines)


# ---------------------------------------------------------------- instrumenting a real Agent
EXPECTED = {"agent.step", "agent.decide", "agent.on_arrival", "link.poll", "link.send", "hw.read", "hw.dispense",
            "perception.detect", "forecast.tick", "forecast.predict", "forecast.record_request", "policy.act",
            "spec.build_observation", "spec.best_neighbor"}


def _run_agent(tmp_path, steps=CYCLE * 5):
    bus, clock = MemoryBus(), Clock()
    agent, hw = make_agent(tmp_path, 1, bus, clock, det=Det())
    peer = MemoryLink(2, bus)
    timer = StageTimer()
    wrapped = instrument_agent(agent, timer)
    drive(agent, hw, peer, clock, steps, 0.25)
    return agent, timer, wrapped, peer


def test_instrument_agent_times_every_stage_of_the_control_loop(tmp_path):
    agent, timer, wrapped, _ = _run_agent(tmp_path)
    try:
        assert EXPECTED <= set(wrapped)
        missing = {s for s in EXPECTED if not timer.samples[s]}
        assert not missing, f"stages never executed by the workload: {missing}"
        assert len(timer.samples["agent.step"]) == CYCLE * 5
        assert "camera.read" not in wrapped                 # this agent has no camera object
    finally:
        timer.restore()


def test_workload_reaches_the_forward_path(tmp_path):
    """Every 4th simulated user finds a tank below the request; the peer must then receive a Forward (and ACK it)."""
    bus, clock = MemoryBus(), Clock()
    agent, hw = make_agent(tmp_path, 1, bus, clock, det=Det())
    peer = MemoryLink(2, bus)
    seen = []
    orig_poll = peer.poll
    peer.poll = lambda: (lambda m: (seen.extend(m), m)[1])(orig_poll())
    drive(agent, hw, peer, clock, CYCLE * 4, 0.25)
    assert any(isinstance(m, Forward) for m in seen)
    assert not agent.pending                                # the peer ACKed every Forward
    assert [r for r in open(agent.log_path)]                # and requests were served and logged


def test_stage_times_are_inclusive(tmp_path):
    agent, timer, _, _ = _run_agent(tmp_path)
    try:
        s = timer.summary()
        inner = s["hw.read"]["total_ms"] + s["link.poll"]["total_ms"]
        assert s["agent.step"]["total_ms"] >= inner
        assert s["agent.decide"]["total_ms"] >= s["policy.act"]["total_ms"] + s["spec.build_observation"]["total_ms"]
    finally:
        timer.restore()


def test_restore_undoes_every_patch(tmp_path):
    import agent.main as main_mod
    import agent.spec as spec
    agent, timer, _, _ = _run_agent(tmp_path, steps=CYCLE)
    assert main_mod.build_observation is not spec.build_observation       # patched
    timer.restore()
    assert main_mod.build_observation is spec.build_observation and main_mod.best_neighbor is spec.best_neighbor
    for obj, name in ((agent, "step"), (agent.hw, "read"), (agent.link, "poll"), (agent.policy, "act")):
        assert name not in vars(obj) or getattr(obj, name).__func__ is getattr(type(obj), name)


# ---------------------------------------------------------------- budgets (wall clock; scale with TIMING_BUDGET_SCALE)
@timing
def test_stage_budgets_on_a_development_machine(tmp_path):
    agent, timer, _, _ = _run_agent(tmp_path, steps=CYCLE * 25)
    try:
        s = timer.summary()
        assert s["policy.act"]["mean_ms"] < 5 * SCALE
        assert s["forecast.predict"]["mean_ms"] < 5 * SCALE
        assert s["spec.build_observation"]["mean_ms"] < 5 * SCALE
        assert s["agent.step"]["p99_ms"] < 50 * SCALE        # the control tick is 250 ms; the compute must be a small part of it
    finally:
        timer.restore()


@timing
def test_detector_preprocessing_time_with_a_fake_model(tmp_path):
    pytest.importorskip("cv2")
    from agent.perception import ContainerDetector
    from tests.helpers import FakeInterpreter
    labels = tmp_path / "labels.txt"
    labels.write_text("The cup is able to supply water\nThe cup is not able to supply water\n")
    det = ContainerDetector("unused.tflite", str(labels), "The cup is able to supply water", None,
                            interpreter=FakeInterpreter(box=(0.2, 0.2, 0.8, 0.8), cls=0, score=0.9))
    frame = np.random.default_rng(0).integers(0, 256, (480, 640, 3), dtype=np.uint8)
    t = StageTimer()
    t.wrap(det, "detect", "perception.detect")
    for _ in range(30):
        assert det.detect(frame).valid
    s = t.summary()["perception.detect"]
    assert s["n"] == 30 and s["mean_ms"] < 100 * SCALE       # resize + colour + normalise of a 640x480 frame, fake inference


# ---------------------------------------------------------------- link round trip
def test_roundtrip_through_the_memory_link():
    bus = MemoryBus()
    a, b = MemoryLink(11, bus), MemoryLink(12, bus)
    r = measure_roundtrip(a, b, n=20, timeout_s=1.0)
    assert r["n_sent"] == 20 and r["n_lost"] <= 1 and len(r["rtt_ms"]) >= 19
    assert 0 < r["p50_ms"] < 100


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@timing
@pytest.mark.skipif(shutil.which("mosquitto") is None, reason="mosquitto not installed")
def test_roundtrip_through_mosquitto_with_nodelay(tmp_path):
    """With TCP_NODELAY on the clients and `set_tcp_nodelay true` on the broker the loopback round trip is about 1 ms; with the
    defaults (Nagle plus delayed ACK) it was about 90 ms in our runs (see README). Budget here is loose on purpose."""
    from agent.comms import MqttLink
    port = _free_port()
    conf = tmp_path / "m.conf"
    conf.write_text(f"listener {port} 127.0.0.1\nallow_anonymous true\npersistence false\nset_tcp_nodelay true\n")
    proc = subprocess.Popen(["mosquitto", "-c", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    a = b = None
    try:
        time.sleep(1.0)
        a, b = enable_nodelay(MqttLink(11, port=port)), enable_nodelay(MqttLink(12, port=port))
        a.start(); b.start(); time.sleep(1.5)
        r = measure_roundtrip(a, b, n=50, timeout_s=2.0)
        assert r["n_lost"] == 0
        assert r["mean_ms"] < 20 * SCALE
    finally:
        for link in (a, b):
            if link is not None:
                link.stop()
        proc.terminate(); proc.wait(5)
