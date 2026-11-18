import numpy as np
import pytest

from agent.forecast import DEFAULT_STATS, N_FEATURES, DemandForecaster, make_features


def test_make_features_shape_range_and_missing_sensors():
    rows = [(2, 1000.0, 31.0, 65.0, 1_700_000_000.0 + 60 * i) for i in range(12)] + [(0, 0.0, None, None, 0.0)]
    f = make_features(rows, DEFAULT_STATS)
    assert f.shape == (13, N_FEATURES) and f.dtype == np.float32
    assert np.all(np.isfinite(f)) and np.all(np.abs(f[:, 4:]) <= 1.0)   # sin/cos


def test_ema_tracks_load():
    fc = DemandForecaster(bin_s=60, window=12, horizon_bins=5)
    t = 1000.0
    assert fc.predict() == 0.0
    for minute in range(10):                                  # 3 requests per minute
        for _ in range(3):
            fc.record_request(t + minute * 60, 500)
        fc.tick(t + minute * 60 + 59, 30.0, 60.0)
    busy = fc.predict()
    for minute in range(10, 30):                              # then silence
        fc.tick(t + minute * 60 + 59, 30.0, 60.0)
    assert busy > 5.0 and fc.predict() < 0.2 * busy


def test_tflite_model_used_once_window_full(tmp_path):
    tf = pytest.importorskip("tensorflow")
    keras = tf.keras
    inp = keras.Input(batch_shape=(1, 12, N_FEATURES))
    out = keras.layers.Dense(1, kernel_initializer="ones", bias_initializer="zeros")(keras.layers.Flatten()(inp))
    path = tmp_path / "f.tflite"
    path.write_bytes(tf.lite.TFLiteConverter.from_keras_model(keras.Model(inp, out)).convert())
    fc = DemandForecaster(str(path), None, bin_s=60, window=12, horizon_bins=5)
    assert fc.interp is not None
    t0 = 1_700_000_000.0
    for i in range(11):
        fc.tick(t0 + 60 * i, 30.0, 60.0)
        assert fc.predict() == 0.0                            # window not full -> EMA fallback (no demand yet)
    for i in range(11, 14):
        fc.record_request(t0 + 60 * i, 500); fc.tick(t0 + 60 * i + 59, 30.0, 60.0)
    assert len(fc.bins) == 12
    rows = list(fc.bins)
    expected = max(0.0, float(make_features(rows, fc.stats).sum())) * fc.stats["target_scale"]
    assert fc.predict() == pytest.approx(expected, rel=1e-4)


def test_missing_model_file_falls_back(tmp_path):
    fc = DemandForecaster(str(tmp_path / "nope.tflite"), None)
    assert fc.interp is None and fc.predict() == 0.0


def test_corrupt_model_file_falls_back_to_ema(tmp_path):
    bad = tmp_path / "bad.tflite"; bad.write_bytes(b"this is not a flatbuffer")
    fc = DemandForecaster(str(bad), None)
    assert fc.interp is None and fc.predict() == 0.0
