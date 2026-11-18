import numpy as np
import pytest

from agent.perception import ContainerDetector, VolumeEstimator
from tests.helpers import FakeInterpreter

REFS = {200: 0.05, 500: 0.12, 600: 0.16}


def test_volume_estimator_nearest_reference_and_tolerance():
    v = VolumeEstimator(REFS, tol=1.6)
    area_box = lambda a: (0.0, 0.0, 1.0, a)             # area = a
    assert v.estimate(area_box(0.05)) == 200
    assert v.estimate(area_box(0.118)) == 500
    assert v.estimate(area_box(0.14)) == 600             # closer (in log-space) to 0.16 than 0.12
    assert v.estimate(area_box(0.5)) is None             # nothing like any reference -> unknown, not a guess
    assert v.estimate(area_box(0.001)) is None


def _detector(tmp_path, interp, **kw):
    labels = tmp_path / "labels.txt"
    labels.write_text("The cup is able to supply water\nThe cup is not able to supply water\n")
    return ContainerDetector("unused.tflite", str(labels), "The cup is able to supply water", None, interpreter=interp, **kw)


FRAME = np.zeros((480, 640, 3), np.uint8)


def test_detector_valid_container(tmp_path):
    det = _detector(tmp_path, FakeInterpreter(box=(0.2, 0.2, 0.8, 0.8), cls=0, score=0.9))
    det.vol = VolumeEstimator({200: 0.1, 500: 0.36, 600: 0.5})
    d = det.detect(FRAME)
    assert d.valid and d.label == "The cup is able to supply water" and d.volume_ml == 500
    assert d.bbox == pytest.approx((0.2, 0.2, 0.8, 0.8))


def test_detector_not_able_has_no_volume(tmp_path):
    det = _detector(tmp_path, FakeInterpreter(cls=1, score=0.8))
    det.vol = VolumeEstimator(REFS)
    d = det.detect(FRAME)
    assert not d.valid and d.volume_ml is None


def test_detector_below_threshold_returns_none(tmp_path):
    assert _detector(tmp_path, FakeInterpreter(score=0.3)).detect(FRAME) is None


def test_detector_class_offset_and_unknown_class(tmp_path):
    det = _detector(tmp_path, FakeInterpreter(cls=0), class_offset=1)   # SSD models with a background class at 0
    assert det.detect(FRAME).label == "The cup is not able to supply water"
    det = _detector(tmp_path, FakeInterpreter(cls=7))
    d = det.detect(FRAME)
    assert d.label == "7" and not d.valid


def test_detector_feeds_uint8_input_unnormalised(tmp_path):
    it = FakeInterpreter(dtype=np.uint8)
    _detector(tmp_path, it).detect(FRAME)
    assert it.last_input.shape == (1, 300, 300, 3) and it.last_input.dtype == np.uint8


def test_detector_float_input_is_normalised(tmp_path):
    it = FakeInterpreter(dtype=np.float32)
    _detector(tmp_path, it).detect(np.full((480, 640, 3), 255, np.uint8))
    assert it.last_input.dtype == np.float32 and it.last_input.max() == pytest.approx(1.0)
