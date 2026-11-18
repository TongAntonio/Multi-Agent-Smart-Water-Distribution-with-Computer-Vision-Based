"""Sensors and actuators of one dispenser (paper Table I).

HC-SR04 ultrasonic (tank level) | DHT22 (temperature/humidity) | IR E18-D80NK (user proximity) | pump relay.
Runs on Raspberry Pi 4 (RPi.GPIO) or Jetson Nano (Jetson.GPIO, same API, BCM numbering).

WIRING WARNINGS (3.3 V GPIO):
  * HC-SR04 ECHO is 5 V -> use a 1k/2k divider or a level shifter.
  * E18-D80NK is an NPN open-collector sensor powered from 5 V -> pull-up to 3.3 V (not 5 V) or level shifter.
  * The pump relay board must be driven from a separate supply; share GND only.
The pump is NOT listed in the paper's Table I but is required to implement the `dispense` action.
"""
from __future__ import annotations

import logging
import random
import statistics
import time
from typing import Callable, NamedTuple, Optional

log = logging.getLogger(__name__)

try:  # Raspberry Pi
    import RPi.GPIO as GPIO
except ImportError:  # Jetson Nano
    try:
        import Jetson.GPIO as GPIO
    except ImportError:
        GPIO = None


class SensorReading(NamedTuple):
    level_ml: float
    temp_c: Optional[float]
    humidity: Optional[float]
    present: bool
    distance_cm: Optional[float]


class Ultrasonic:
    def __init__(self, trig: int, echo: int, empty_cm: float, full_cm: float, capacity_ml: float, samples: int = 5):
        self.trig, self.echo, self.empty_cm, self.full_cm, self.cap, self.n = trig, echo, empty_cm, full_cm, capacity_ml, samples
        GPIO.setup(trig, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(echo, GPIO.IN)

    def _once(self, speed_cm_s: float, timeout: float = 0.03) -> Optional[float]:
        GPIO.output(self.trig, True)
        time.sleep(1e-5)
        GPIO.output(self.trig, False)
        t0 = time.perf_counter()
        while not GPIO.input(self.echo):
            if time.perf_counter() - t0 > timeout:
                return None
        t1 = time.perf_counter()
        while GPIO.input(self.echo):
            if time.perf_counter() - t1 > timeout:
                return None
        return (time.perf_counter() - t1) * speed_cm_s / 2.0

    def distance_cm(self, temp_c: Optional[float] = None) -> Optional[float]:
        speed = (331.3 + 0.606 * (temp_c if temp_c is not None else 25.0)) * 100.0  # cm/s, temperature compensated
        vals = [v for v in (self._once(speed) for _ in range(self.n)) if v is not None]
        return statistics.median(vals) if vals else None

    def level_ml(self, distance_cm: Optional[float]) -> float:
        if distance_cm is None:
            return 0.0  # fail safe: unknown level = empty, so the agent never dispenses blindly
        frac = (self.empty_cm - distance_cm) / (self.empty_cm - self.full_cm)
        return max(0.0, min(1.0, frac)) * self.cap


class ProximityIR:
    def __init__(self, pin: int, active_low: bool = True):
        self.pin, self.active_low = pin, active_low
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP if active_low else GPIO.PUD_DOWN)

    def present(self) -> bool:
        v = GPIO.input(self.pin)
        return (v == 0) if self.active_low else (v == 1)


class DHT22Sensor:
    def __init__(self, pin_name: str):
        import adafruit_dht
        import board
        self.dev = adafruit_dht.DHT22(getattr(board, pin_name), use_pulseio=False)
        self._last: tuple[Optional[float], Optional[float]] = (None, None)

    def read(self):
        try:
            t, h = self.dev.temperature, self.dev.humidity
            if t is not None and h is not None:
                self._last = (float(t), float(h))
        except RuntimeError:  # checksum / timing errors are normal for DHT22
            pass
        return self._last


class Pump:
    def __init__(self, pin: int, active_low: bool, flow_ml_s: float, max_s: float):
        self.pin, self.active_low, self.flow, self.max_s = pin, active_low, flow_ml_s, max_s
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH if active_low else GPIO.LOW)

    def _set(self, on: bool) -> None:
        GPIO.output(self.pin, (not on) if self.active_low else on)

    def dispense(self, ml: float, keep_going: Callable[[], bool]) -> float:
        """Run the pump for ml/flow seconds, stopping early if keep_going() turns False. Returns estimated ml."""
        dur = min(ml / self.flow, self.max_s)
        t0 = time.monotonic()
        self._set(True)
        try:
            while time.monotonic() - t0 < dur and keep_going():
                time.sleep(0.02)
        finally:
            self._set(False)
        return (time.monotonic() - t0) * self.flow


class Hardware:
    def __init__(self, cfg: dict):
        if GPIO is None:
            raise RuntimeError("No GPIO library (RPi.GPIO / Jetson.GPIO). Use simulate_hardware: true for development.")
        h = cfg["hardware"]
        p, t = h["pins"], h["tank"]
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        self.us = Ultrasonic(p["us_trig"], p["us_echo"], t["empty_distance_cm"], t["full_distance_cm"], t["capacity_ml"])
        self.ir = ProximityIR(p["ir"], h["ir_active_low"])
        self.dht = DHT22Sensor(p["dht"])
        self.pump = Pump(p["pump_relay"], h["pump_active_low"], h["flow_ml_per_s"], h["max_dispense_s"])

    def present(self) -> bool:
        return self.ir.present()

    def read(self) -> SensorReading:
        temp, hum = self.dht.read()
        d = self.us.distance_cm(temp)
        return SensorReading(self.us.level_ml(d), temp, hum, self.ir.present(), d)

    def dispense(self, ml: float, keep_going: Callable[[], bool]) -> float:
        return self.pump.dispense(ml, keep_going)

    def close(self) -> None:
        GPIO.cleanup()


class SimHardware:
    """Drop-in replacement for development and tests (no GPIO)."""

    def __init__(self, level_ml: float = 15000.0, flow_ml_s: float = 1e6, seed: int = 0):
        self.level, self.flow, self._present = level_ml, flow_ml_s, False
        self.rng = random.Random(seed)

    def set_present(self, v: bool) -> None:
        self._present = v

    def present(self) -> bool:
        return self._present

    def read(self) -> SensorReading:
        return SensorReading(self.level, 30.0 + self.rng.uniform(-1, 1), 60.0 + self.rng.uniform(-3, 3), self._present, 20.0)

    def dispense(self, ml: float, keep_going: Callable[[], bool]) -> float:
        out = ml if keep_going() else 0.0
        self.level = max(0.0, self.level - out)
        return out

    def close(self) -> None:
        pass


def make_hardware(cfg: dict):
    if cfg.get("simulate_hardware"):
        log.warning("simulate_hardware=true -> using SimHardware (no GPIO access)")
        return SimHardware()
    return Hardware(cfg)
