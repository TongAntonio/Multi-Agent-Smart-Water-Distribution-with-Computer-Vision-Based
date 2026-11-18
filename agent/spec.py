"""Shared state/action specification (paper Sec. III-D).

One definition used by the simulator, the trainer and the edge agent, so the policy sees exactly the same
observation layout in training and in deployment.
"""
from __future__ import annotations

import numpy as np

ACTIONS = ("dispense", "wait", "forward_request")  # paper: {dispense, wait, forward_request}
DISPENSE, WAIT, FORWARD = 0, 1, 2

# Paper state vector: [sensor readings, CV flag, forecasted demand, queue size]
# + coordination features that arrive from neighbour agents over the radio link.
OBS_FIELDS = (
    "water_level",     # ultrasonic tank level / TANK_REF_ML
    "cv_valid",        # MobileNet-SSD: container able to supply water
    "volume_norm",     # estimated container volume / 600 ml
    "forecast_norm",   # LSTM: expected requests in next horizon / FORECAST_MAX
    "queue_norm",      # local queue length / Q_MAX
    "head_wait_norm",  # waiting time of the head-of-line request / WAIT_MAX_S
    "nbr_queue_norm",  # best neighbour's queue (1.0 when no usable neighbour)
    "nbr_level_norm",  # best neighbour's water level (0.0 when no usable neighbour)
    "busy",            # pump running
)
OBS_DIM = len(OBS_FIELDS)

VOLUME_CLASSES_ML = (200, 500, 600)
MAX_VOLUME_ML = 600.0
TANK_REF_ML = 4000.0
Q_MAX = 10
WAIT_MAX_S = 120.0
FORECAST_MAX = 10.0
STALE_S = 30.0
MAX_HOPS = 2


def _c(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def best_neighbor(views: dict, volume_ml: float, now: float, stale_s: float = STALE_S):
    """views: {nbr_id: (queue_len, water_ml, t_updated)} -> (nbr_id, queue_len, water_ml) or None.

    Only neighbours with fresh info and enough water for this request are candidates; shortest queue wins.
    """
    best = None
    for nid, (q, w, ts) in views.items():
        if now - ts > stale_s or w < volume_ml:
            continue
        if best is None or (q, -w) < (best[1], -best[2]):
            best = (nid, q, w)
    return best


def build_observation(*, water_ml, cv_valid, volume_ml, forecast_requests, queue_len, head_wait_s, nbr, busy):
    nq, nl = (1.0, 0.0) if nbr is None else (_c(nbr[1] / Q_MAX), _c(nbr[2] / TANK_REF_ML))
    return np.array(
        [_c(water_ml / TANK_REF_ML), float(bool(cv_valid)), _c(volume_ml / MAX_VOLUME_ML),
         _c(forecast_requests / FORECAST_MAX), _c(queue_len / Q_MAX), _c(head_wait_s / WAIT_MAX_S),
         nq, nl, float(bool(busy))],
        dtype=np.float32,
    )
