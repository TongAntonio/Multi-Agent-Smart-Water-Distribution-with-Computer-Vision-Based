"""On-device container perception (paper Sec. III-B): MobileNet-SSD (TensorFlow Lite) + bounding-box volume calibration.

Model contract: a TFLite SSD with the standard post-processed outputs (boxes [1,N,4] as ymin,xmin,ymax,xmax in 0..1,
classes [1,N], scores [1,N], count [1]). Output order is configurable (cv.output_order). Verify your exported model
before deploying.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from math import log as ln
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class Detection:
    valid: bool                       # "able to supply water"
    score: float
    bbox: tuple                       # (ymin, xmin, ymax, xmax) normalised
    volume_ml: Optional[int]          # 200 / 500 / 600, or None if uncalibrated / out of tolerance
    label: str


class VolumeEstimator:
    """Bounding-box scaling against reference containers (200/500/600 ml) imaged at the fixed camera distance."""

    def __init__(self, ref_area: dict[int, float], tol: float = 1.6):
        self.ref_area, self.tol = ref_area, tol

    @classmethod
    def from_json(cls, path: str) -> "VolumeEstimator":
        d = json.load(open(path))
        return cls({int(k): float(v) for k, v in d["reference_bbox_area"].items()}, float(d.get("tolerance", 1.6)))

    def estimate(self, bbox) -> Optional[int]:
        ymin, xmin, ymax, xmax = bbox
        area = max((ymax - ymin) * (xmax - xmin), 1e-6)
        ml, ref = min(self.ref_area.items(), key=lambda kv: abs(ln(area / kv[1])))
        return ml if abs(ln(area / ref)) <= ln(self.tol) else None


from .tflite import load_interpreter as _load_interpreter  # noqa: E402


class ContainerDetector:
    def __init__(self, model_path: str, labels_path: str, valid_label: str, calibration_path: Optional[str] = None,
                 score_threshold: float = 0.5, class_offset: int = 0,
                 output_order=("boxes", "classes", "scores", "count"), interpreter=None):
        self.interp = interpreter or _load_interpreter(model_path)
        self.interp.allocate_tensors()
        self.inp = self.interp.get_input_details()[0]
        self.outs = self.interp.get_output_details()
        self.labels = [s.strip() for s in open(labels_path) if s.strip()] if os.path.exists(labels_path) else []
        self.valid_label, self.thr, self.off, self.order = valid_label, score_threshold, class_offset, tuple(output_order)
        self.vol = VolumeEstimator.from_json(calibration_path) if calibration_path and os.path.exists(calibration_path) else None
        if self.vol is None:
            log.warning("No volume calibration file: volume_ml will be None (run tools/calibrate_volume.py)")

    @classmethod
    def from_config(cls, cfg: dict) -> "ContainerDetector":
        c = cfg["cv"]
        return cls(c["model"], c["labels"], c["valid_label"], c["calibration"], c["score_threshold"],
                   c["class_offset"], c["output_order"])

    def detect(self, frame_bgr: np.ndarray) -> Optional[Detection]:
        import cv2
        h, w = int(self.inp["shape"][1]), int(self.inp["shape"][2])
        x = cv2.cvtColor(cv2.resize(frame_bgr, (w, h)), cv2.COLOR_BGR2RGB)[None]
        x = (x.astype(np.float32) - 127.5) / 127.5 if self.inp["dtype"] == np.float32 else x.astype(self.inp["dtype"])
        self.interp.set_tensor(self.inp["index"], x)
        self.interp.invoke()
        out = dict(zip(self.order, [self.interp.get_tensor(o["index"]) for o in self.outs]))
        scores = np.asarray(out["scores"])[0]
        if scores.size == 0:
            return None
        k = int(np.argmax(scores))
        if scores[k] < self.thr:
            return None
        cls_id = int(np.asarray(out["classes"])[0][k]) + self.off
        label = self.labels[cls_id] if 0 <= cls_id < len(self.labels) else str(cls_id)
        ymin, xmin, ymax, xmax = (float(v) for v in np.clip(np.asarray(out["boxes"])[0][k], 0.0, 1.0))
        valid = label == self.valid_label
        vol = self.vol.estimate((ymin, xmin, ymax, xmax)) if (valid and self.vol) else None
        return Detection(valid, float(scores[k]), (ymin, xmin, ymax, xmax), vol, label)


class Camera:
    """Returns BGR uint8 frames. Backends: picamera2 (Pi OS Bullseye+), OpenCV/V4L2 (USB or legacy Pi camera)."""

    def __init__(self, backend: str = "auto", index: int = 0, width: int = 640, height: int = 480):
        self._pc2 = self._cap = None
        if backend in ("auto", "picamera2"):
            try:
                from picamera2 import Picamera2
                self._pc2 = Picamera2()
                self._pc2.configure(self._pc2.create_still_configuration(main={"size": (width, height), "format": "RGB888"}))
                self._pc2.start()  # NB: picamera2 "RGB888" arrays are in BGR byte order, which is what OpenCV wants
                return
            except Exception as e:
                if backend == "picamera2":
                    raise
                log.info("picamera2 unavailable (%s), trying OpenCV", e)
        import cv2
        self._cap = cv2.VideoCapture(index)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if not self._cap.isOpened():
            raise RuntimeError("No camera backend could be opened")

    def read(self) -> np.ndarray:
        if self._pc2 is not None:
            return self._pc2.capture_array()
        ok, frame = self._cap.read()
        if not ok:
            raise RuntimeError("Camera read failed")
        return frame
