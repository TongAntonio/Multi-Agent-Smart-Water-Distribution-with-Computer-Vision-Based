"""Bounding-box volume calibration: place each reference container (200/500/600 ml) at the normal position,
run this script, and it stores the median detected bbox area in models/volume_calibration.json."""
import argparse
import json

import numpy as np

from agent.config import load_config
from agent.perception import Camera, ContainerDetector

ap = argparse.ArgumentParser()
ap.add_argument("--config", default=None)
ap.add_argument("--out", default="models/volume_calibration.json")
ap.add_argument("--frames", type=int, default=15)
a = ap.parse_args()
cfg = load_config(a.config)
cam = Camera(**{k: cfg["camera"][k] for k in ("backend", "index", "width", "height")})
det = ContainerDetector.from_config(cfg)
refs = {}
for ml in (200, 500, 600):
    input(f"Place the {ml} ml reference container and press Enter...")
    areas = []
    for _ in range(a.frames):
        d = det.detect(cam.read())
        if d and d.valid:
            y0, x0, y1, x1 = d.bbox
            areas.append((y1 - y0) * (x1 - x0))
    if not areas:
        raise SystemExit(f"No valid detection for {ml} ml - check lighting/model")
    refs[str(ml)] = float(np.median(areas))
    print(ml, "ml -> median bbox area", refs[str(ml)], f"({len(areas)}/{a.frames} frames)")
json.dump({"reference_bbox_area": refs, "tolerance": 1.6}, open(a.out, "w"), indent=2)
print("saved", a.out)
