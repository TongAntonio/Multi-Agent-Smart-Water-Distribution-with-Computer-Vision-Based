"""Time every stage of the dispenser agent: the same command runs on a PC and on the Raspberry Pi.

    python -m tools.bench_stages                                   # simulated hardware, in-memory link, stub detector
    python -m tools.bench_stages --detector fake                   # real image pre/post-processing, instant fake model
    python -m tools.bench_stages --detector tflite --model models/container_ssd.tflite --labels models/labels.txt \
                                 --images some_folder_of_jpgs      # real TFLite inference
    python -m tools.bench_stages --link mqtt --mqtt-host 192.168.1.10   # also times the broker (a broker must be running)
    python -m tools.bench_stages --hardware real --config config/agent.yaml   # Pi: real sensor reads, pump NEVER runs

What is timed: the agent's control tick (`agent.step`) and, inside it, the link poll/send, sensor read, camera frame,
detector, forecaster, policy and observation building (see agent/timing.py). Times are inclusive and in milliseconds. A
separate section gives the message round trip through the link. The result is a JSON file (--out) with the machine
description, so a laptop run and a Pi run can never be mixed up.

Nothing here is a measurement of the paper's laboratory or field trials, and a laptop number is not a Pi number.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

from agent.comms import Ack, Forward, MemoryBus, MemoryLink, MqttLink, State
from agent.config import load_config
from agent.forecast import DemandForecaster
from agent.hardware import SimHardware
from agent.main import Agent, StubDetector
from agent.policy import HeuristicPolicy, NumpyPolicy
from agent.timing import StageTimer, instrument_agent, measure_roundtrip

CYCLE = 12            # steps per simulated user cycle: arrival, decision, absence
LOW_EVERY = 4         # every 4th cycle the tank is below the request, so the policy has to consider forwarding


# ---------------------------------------------------------------- frame sources and hardware wrappers
class FrameSource:
    """Stands in for the camera when no real camera is used: cycles through JPEG/PNG files, or random 640x480 frames."""

    def __init__(self, folder: str | None, seed: int = 0, size=(480, 640)):
        self.files = sorted(sum((glob.glob(os.path.join(folder, e)) for e in ("*.jpg", "*.jpeg", "*.png")), [])) if folder else []
        if folder and not self.files:
            raise SystemExit(f"no .jpg/.jpeg/.png files in {folder}")
        self.i, self.rng, self.size = 0, np.random.default_rng(seed), size
        self._cache = [self._load(f) for f in self.files]       # decode once: the timed stage is the detector, not the disk

    @staticmethod
    def _load(path):
        import cv2
        img = cv2.imread(path)
        if img is None:
            raise SystemExit(f"cannot read image {path}")
        return img

    def read(self):
        if self._cache:
            self.i = (self.i + 1) % len(self._cache)
            return self._cache[self.i]
        return self.rng.integers(0, 256, (*self.size, 3), dtype=np.uint8)


class ScheduledHardware:
    """Real sensors for read() (level, temperature, humidity, distance) but the pump never runs and the presence flag follows
    the benchmark's schedule, so no water moves and nobody has to stand in front of the IR sensor."""

    def __init__(self, real):
        self.real, self._present = real, False

    def set_present(self, v: bool) -> None:
        self._present = v

    def present(self) -> bool:
        return self._present

    def read(self):
        return self.real.read()._replace(present=self._present)

    def dispense(self, ml, keep_going):
        return float(ml)                                         # NO pump action

    def close(self) -> None:
        self.real.close()

    @property
    def level(self):
        return 0.0

    @level.setter
    def level(self, v):                                          # the real tank level is what the sensor says
        pass


# ---------------------------------------------------------------- machine description
def _run(cmd: list[str]) -> str | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip() or None
    except Exception:
        return None


def machine_info() -> dict:
    info = {"platform": platform.platform(), "machine": platform.machine(), "processor": platform.processor() or None,
            "python": platform.python_version(), "numpy": np.__version__, "cpu_count": os.cpu_count()}
    try:
        info["device_model"] = open("/proc/device-tree/model", "rb").read().rstrip(b"\0").decode()   # Raspberry Pi / Jetson
    except OSError:
        info["device_model"] = None
    try:
        import cv2
        info["opencv"] = cv2.__version__
    except Exception:
        info["opencv"] = None
    for mod in ("tflite_runtime", "ai_edge_litert", "tensorflow"):
        try:
            m = __import__(mod)
            info["tflite_runtime"] = f"{mod} {getattr(m, '__version__', '?')}"
            break
        except Exception:
            continue
    else:
        info["tflite_runtime"] = None
    info["git_commit"] = _run(["git", "rev-parse", "--short", "HEAD"])
    if shutil.which("vcgencmd"):
        info["temp_start"], info["throttled_start"] = _run(["vcgencmd", "measure_temp"]), _run(["vcgencmd", "get_throttled"])
    return info


# ---------------------------------------------------------------- build the agent under test

def enable_nodelay(link):
    """Set TCP_NODELAY on an MqttLink's socket when it connects (benchmark option only; the agent code is unchanged)."""
    import socket
    original = link.c.on_connect

    def on_connect(client, userdata, flags, rc, *a):
        try:
            client.socket().setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass
        return original(client, userdata, flags, rc, *a)
    link.c.on_connect = on_connect
    return link


def new_mqtt(args, agent_id):
    link = MqttLink(agent_id, host=args.mqtt_host, port=args.mqtt_port)
    return enable_nodelay(link) if args.tcp_nodelay else link

def build_agent(args, cfg, bus, timer_clock):
    cfg["log_dir"] = tempfile.mkdtemp(prefix="bench_logs_")
    cfg["state_period_s"] = args.state_period
    if args.hardware == "real":
        from agent.hardware import Hardware
        hw = ScheduledHardware(Hardware(cfg))
    else:
        hw = SimHardware(level_ml=15000.0, flow_ml_s=1e6)
    cam, comp = None, {"hardware": args.hardware, "link": args.link + (" (TCP_NODELAY on the clients)" if args.link == "mqtt" and args.tcp_nodelay else "")}
    if args.detector == "stub":
        det = StubDetector()
        comp["detector"] = "stub (no image work)"
    else:
        try:
            import cv2  # noqa: F401
        except ImportError:
            raise SystemExit("--detector fake/tflite needs OpenCV (pip install opencv-python-headless)")
        from agent.perception import ContainerDetector
        cam = make_camera(args, cfg)
        if args.detector == "fake":
            from tests.helpers import FakeInterpreter
            labels = os.path.join(cfg["log_dir"], "labels.txt")
            open(labels, "w").write("The cup is able to supply water\nThe cup is not able to supply water\n")
            det = ContainerDetector("unused.tflite", labels, "The cup is able to supply water", None, interpreter=FakeInterpreter(
                box=(0.2, 0.2, 0.8, 0.8), cls=0, score=0.9))
            comp["detector"] = "fake model: real resize/colour/normalise and output decoding, instant inference"
        else:
            if not args.model:
                raise SystemExit("--detector tflite needs --model (and usually --labels)")
            cfg["cv"].update(model=args.model, **({"labels": args.labels} if args.labels else {}))
            det = ContainerDetector.from_config(cfg)
            comp["detector"] = f"TFLite {os.path.basename(args.model)}"
    pp = args.policy or cfg["policy"]["path"]
    policy = NumpyPolicy.load(pp) if os.path.exists(pp) else HeuristicPolicy()
    comp["policy"] = "NumpyPolicy " + os.path.basename(pp) if os.path.exists(pp) else "heuristic"
    if args.link == "mqtt":
        link = new_mqtt(args, 1)
    else:
        link = MemoryLink(1, bus)
    fc = DemandForecaster.from_config(cfg)
    comp["forecaster"] = "LSTM (TFLite)" if getattr(fc, "interp", None) is not None else "moving-average fallback"
    return Agent(cfg, hw, link, cam, det, forecaster=fc, policy=policy, clock=timer_clock), hw, comp


def make_camera(args, cfg):
    if args.camera == "real":
        from agent.perception import Camera
        return Camera(**{k: cfg["camera"][k] for k in ("backend", "index", "width", "height")})
    return FrameSource(args.images)


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


# ---------------------------------------------------------------- workload
def drive(agent, hw, peer, clock, steps: int, tick_s: float, first: int = 0) -> None:
    """Scripted user cycles: arrival -> decision -> absence. Every LOW_EVERY-th cycle the tank is too low, so the forward path
    (best_neighbor, Forward, ACK, pending bookkeeping) runs; the peer answers every Forward with an ACK and sends a State."""
    for k in range(first, first + steps):
        ph, cyc = k % CYCLE, k // CYCLE
        if ph == 0:
            hw.level = 300.0 if cyc % LOW_EVERY == LOW_EVERY - 1 else 15000.0
        hw.set_present(ph < 4)
        if k % 5 == 0:
            peer.send(State(2, k & 0xFFFF, 0, 8000.0, 1.0, False, 30.0, 60.0))
        agent.step()
        for m in peer.poll():
            if isinstance(m, Forward):
                peer.send(Ack(2, m.src, m.seq, m.request_id))
        clock.t += tick_s


# ---------------------------------------------------------------- reporting
def print_table(summary: dict) -> None:
    cols = ("n", "mean_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms")
    w = max([len(s) for s in summary] + [5])
    print(f"{'stage':<{w}}  " + "  ".join(f"{c:>9}" for c in cols))
    for stage, s in summary.items():
        print(f"{stage:<{w}}  " + "  ".join(f"{s[c]:>9.4f}" if c != "n" else f"{s[c]:>9d}" for c in cols))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None)
    ap.add_argument("--steps", type=int, default=2000, help="control ticks to time (default 2000)")
    ap.add_argument("--warmup", type=int, default=100, help="ticks run first and discarded (default 100)")
    ap.add_argument("--hardware", choices=("sim", "real"), default="sim", help="real: sensor reads on a Pi, the pump never runs")
    ap.add_argument("--detector", choices=("stub", "fake", "tflite"), default="stub")
    ap.add_argument("--model", help="TFLite detection model (with --detector tflite)")
    ap.add_argument("--labels", help="labels file for the model")
    ap.add_argument("--images", help="folder of .jpg/.png frames to cycle through (default: random 640x480 frames)")
    ap.add_argument("--camera", choices=("none", "real"), default="none", help="real: grab frames from the camera in the config")
    ap.add_argument("--policy", help="NumPy policy file (default: config path, else heuristic)")
    ap.add_argument("--link", choices=("memory", "mqtt"), default="memory")
    ap.add_argument("--mqtt-host", default="localhost")
    ap.add_argument("--mqtt-port", type=int, default=1883)
    ap.add_argument("--tcp-nodelay", action="store_true",
                    help="set TCP_NODELAY on the MQTT client sockets (also set_tcp_nodelay true in mosquitto.conf; see README)")
    ap.add_argument("--state-period", type=float, default=1.0, help="seconds between state broadcasts in the benchmark (default 1)")
    ap.add_argument("--roundtrips", type=int, default=200, help="link round trips to time (0 = skip)")
    ap.add_argument("--out", default=None, help="JSON result file (default results/timing/<utc>.json)")
    ap.add_argument("--raw", default=None, help="also write every sample (ns) to this CSV file")
    args = ap.parse_args()

    cfg = load_config(args.config)
    cfg["agent_id"], tick_s = 1, float(cfg["tick_s"])
    cfg["simulate_hardware"] = args.hardware == "sim"
    clock, bus = Clock(), MemoryBus()
    agent, hw, comp = build_agent(args, cfg, bus, clock)
    peer = new_mqtt(args, 2) if args.link == "mqtt" else MemoryLink(2, bus)
    agent.link.start()
    if args.link == "mqtt":
        peer.start()
        time.sleep(1.5)                                          # let both clients connect and subscribe
    timer = StageTimer()
    info = machine_info()
    try:
        drive(agent, hw, peer, clock, args.warmup, tick_s)
        wrapped = instrument_agent(agent, timer)
        t0 = time.perf_counter()
        drive(agent, hw, peer, clock, args.steps, tick_s, first=args.warmup)
        wall = time.perf_counter() - t0
        rt = None
        if args.roundtrips:
            if args.link == "mqtt":
                a, b = new_mqtt(args, 11), new_mqtt(args, 12)
                a.start(); b.start(); time.sleep(1.5)
            else:
                a, b = MemoryLink(11, bus), MemoryLink(12, bus)
            try:
                rt = measure_roundtrip(a, b, n=args.roundtrips)
            finally:
                if args.link == "mqtt":
                    a.stop(); b.stop()
    finally:
        timer.restore()
        agent.link.stop()
        peer.stop()
        agent.hw.close()
    if shutil.which("vcgencmd"):
        info["temp_end"], info["throttled_end"] = _run(["vcgencmd", "measure_temp"]), _run(["vcgencmd", "get_throttled"])
    summary = timer.summary()
    result = {"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "machine": info,
              "components": comp, "steps": args.steps, "warmup": args.warmup, "tick_s_simulated": tick_s,
              "state_period_s": args.state_period, "wall_s_for_timed_steps": wall,
              "stopwatch_overhead_ns": timer.overhead_ns(), "stages": summary,
              "link_roundtrip": {k: v for k, v in rt.items() if k != "rtt_ms"} if rt else None}
    print(f"\nMachine: {info['device_model'] or info['platform']} | {info['machine']} | Python {info['python']}")
    print("Components:", "; ".join(f"{k}={v}" for k, v in comp.items()))
    print(f"Timed {args.steps} ticks (+{args.warmup} warm-up), stopwatch overhead {result['stopwatch_overhead_ns']:.0f} ns per call\n")
    print_table(summary)
    if rt:
        print(f"\nLink round trip ({args.link}): n={rt['n_sent']}, lost={rt['n_lost']}, mean {rt['mean_ms']:.3f} ms, "
              f"p50 {rt['p50_ms']:.3f}, p95 {rt['p95_ms']:.3f}, max {rt['max_ms']:.3f}")
    tick_ms = tick_s * 1000
    st = summary.get("agent.step")
    if st:
        print(f"\nControl tick budget: the loop sleeps {tick_ms:.0f} ms between ticks; agent.step p99 = {st['p99_ms']:.2f} ms "
              f"({100 * st['p99_ms'] / tick_ms:.1f} % of the tick).")
    out = args.out or os.path.join("results", "timing", datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(result, open(out, "w"), indent=2)
    print("\nwritten:", out)
    if args.raw:
        with open(args.raw, "w") as f:
            f.write("stage,duration_ns\n")
            for stage, ns in timer.samples.items():
                f.writelines(f"{stage},{v}\n" for v in ns)
        print("raw samples:", args.raw)
    shutil.rmtree(cfg["log_dir"], ignore_errors=True)


if __name__ == "__main__":
    main()
