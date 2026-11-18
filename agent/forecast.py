"""Short-term demand forecasting (paper Sec. III-C): LSTM on edge (TFLite), 5-10 min horizon.

Input window: last `window` bins of [request count, volume, temperature, humidity, time-of-day sin/cos].
Output: expected number of requests in the next `horizon_bins` bins. Falls back to an EMA predictor until the
window is full or when no trained model is deployed.
"""
from __future__ import annotations

import json
import logging
import math
import os
from collections import deque
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)
N_FEATURES = 6
DEFAULT_STATS = {"count_scale": 5.0, "vol_scale_ml": 2500.0, "target_scale": 10.0, "tz_offset_s": 25200}  # Asia/Bangkok


def make_features(rows, stats: dict) -> np.ndarray:
    """rows: sequence of (count, volume_ml, temp_c, humidity, bin_start_ts) -> float32 [len(rows), N_FEATURES]."""
    out = np.zeros((len(rows), N_FEATURES), dtype=np.float32)
    for i, (c, v, t, h, ts) in enumerate(rows):
        tod = ((ts + stats["tz_offset_s"]) % 86400) / 86400.0
        out[i] = [c / stats["count_scale"], v / stats["vol_scale_ml"], (t if t is not None else 30.0) / 40.0,
                  (h if h is not None else 60.0) / 100.0, math.sin(2 * math.pi * tod), math.cos(2 * math.pi * tod)]
    return out


def _load_tflite(path: str):
    """TFLite interpreter, or None (-> EMA fallback) if no runtime is installed or the model file is unusable."""
    from .tflite import load_interpreter
    try:
        it = load_interpreter(path)
        it.allocate_tensors()
        return it
    except Exception as e:
        log.warning("Forecaster model %s unusable (%s) -> EMA fallback", path, e)
        return None


class DemandForecaster:
    def __init__(self, model_path: Optional[str] = None, stats_path: Optional[str] = None,
                 bin_s: float = 60.0, window: int = 12, horizon_bins: int = 5, ema_alpha: float = 0.3):
        self.bin_s, self.window, self.h, self.alpha = bin_s, window, horizon_bins, ema_alpha
        self.stats = dict(DEFAULT_STATS)
        if stats_path and os.path.exists(stats_path):
            self.stats.update(json.load(open(stats_path)))
        self.interp = _load_tflite(model_path) if model_path and os.path.exists(model_path) else None
        self.bins: deque = deque(maxlen=window)   # finished bins
        self.cur: Optional[list] = None           # [count, volume_ml, temp, hum, start_ts]
        self.ema = 0.0

    @classmethod
    def from_config(cls, cfg: dict) -> "DemandForecaster":
        f = cfg["forecast"]
        return cls(f["model"], f["stats"], f["bin_s"], f["window"], f["horizon_bins"])

    def record_request(self, now: float, volume_ml: float) -> None:
        self._roll(now, None, None)
        self.cur[0] += 1
        self.cur[1] += volume_ml

    def tick(self, now: float, temp_c: Optional[float], humidity: Optional[float]) -> None:
        self._roll(now, temp_c, humidity)
        if temp_c is not None:
            self.cur[2], self.cur[3] = temp_c, humidity

    def _roll(self, now: float, temp_c, hum) -> None:
        if self.cur is None:
            self.cur = [0, 0.0, temp_c, hum, now - (now % self.bin_s)]
        while now >= self.cur[4] + self.bin_s:
            self.bins.append(tuple(self.cur))
            self.ema = self.alpha * self.cur[0] + (1 - self.alpha) * self.ema
            self.cur = [0, 0.0, self.cur[2], self.cur[3], self.cur[4] + self.bin_s]

    def predict(self) -> float:
        """Expected number of requests in the next `horizon_bins` bins."""
        if self.interp is None or len(self.bins) < self.window:
            return float(self.ema * self.h)
        x = make_features(list(self.bins), self.stats)[None]
        inp, out = self.interp.get_input_details()[0], self.interp.get_output_details()[0]
        self.interp.set_tensor(inp["index"], x.astype(np.float32))
        self.interp.invoke()
        return float(max(0.0, self.interp.get_tensor(out["index"])[0][0]) * self.stats["target_scale"])
