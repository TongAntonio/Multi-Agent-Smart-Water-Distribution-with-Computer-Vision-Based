"""Train the LSTM demand forecaster and export TFLite for the edge agent.

Data: real usage logs (CSV with columns timestamp[epoch s], volume_ml, optional temp_c, humidity) written by the
agents / exported from your pilot - or --synthetic for a pipeline smoke test. Synthetic numbers say nothing about
real-world accuracy.

  python -m train.train_forecaster --csv logs/usage.csv
  python -m train.train_forecaster --synthetic --days 14
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np

from agent.forecast import DEFAULT_STATS, N_FEATURES, make_features


def synth_bins(days: int, bin_s: int, seed: int, tz: int):
    rng = np.random.default_rng(seed)
    n = days * 86400 // bin_s
    ts = 1_700_000_000 - (1_700_000_000 % 86400) + np.arange(n) * bin_s
    hod = ((ts + tz) % 86400) / 3600.0
    temp = 29 + 6 * np.sin(2 * np.pi * (hod - 9) / 24) + rng.normal(0, 0.7, n)
    hum = 70 - 15 * np.sin(2 * np.pi * (hod - 9) / 24) + rng.normal(0, 2, n)
    lam = 0.25 + 0.7 * np.exp(-0.5 * ((hod - 8) / 1.2) ** 2) + 0.6 * np.exp(-0.5 * ((hod - 18) / 1.5) ** 2)
    lam *= 1 + 0.05 * (temp - 30)
    for _ in range(max(1, days // 3)):                      # emergency surges (x2.5-4 for 2-4 h)
        s = rng.integers(0, max(1, n - 300)); lam[s:s + int(rng.integers(120, 240)) * 60 // bin_s] *= rng.uniform(2.5, 4.0)
    counts = rng.poisson(np.clip(lam, 0.01, None))
    vols = counts * rng.choice([200, 500, 600], n)
    return counts.astype(float), vols.astype(float), temp, hum, ts.astype(float)


def csv_bins(path: str, bin_s: int):
    import pandas as pd
    df = pd.read_csv(path)
    df["bin"] = (df["timestamp"] // bin_s).astype(int)
    agg = {"count": ("volume_ml", "size"), "vol": ("volume_ml", "sum")}
    if "temp_c" in df:
        agg["temp"] = ("temp_c", "mean")
    if "humidity" in df:
        agg["hum"] = ("humidity", "mean")
    g = df.groupby("bin").agg(**agg)
    full = np.arange(g.index.min(), g.index.max() + 1)
    g = g.reindex(full)
    counts, vols = g["count"].fillna(0).to_numpy(float), g["vol"].fillna(0).to_numpy(float)
    temp = g["temp"].ffill().bfill().to_numpy(float) if "temp" in g else np.full(len(g), 30.0)
    hum = g["hum"].ffill().bfill().to_numpy(float) if "hum" in g else np.full(len(g), 60.0)
    return counts, vols, temp, hum, full.astype(float) * bin_s


def windows(counts, vols, temp, hum, ts, W, H, stats):
    rows = list(zip(counts, vols, temp, hum, ts))
    X, y, last = [], [], []
    for i in range(W, len(rows) - H + 1):
        X.append(make_features(rows[i - W:i], stats))
        y.append(counts[i:i + H].sum())
        last.append(counts[i - H:i].sum())            # persistence baseline
    return np.stack(X), np.asarray(y, np.float32), np.asarray(last, np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv"); ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--days", type=int, default=14); ap.add_argument("--bin-s", type=int, default=60)
    ap.add_argument("--window", type=int, default=12); ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--epochs", type=int, default=30); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tz-offset-s", type=int, default=DEFAULT_STATS["tz_offset_s"])
    ap.add_argument("--out", default="models")
    a = ap.parse_args()
    if not (a.csv or a.synthetic):
        ap.error("give --csv or --synthetic")
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    import tensorflow as tf
    from tensorflow import keras
    tf.keras.utils.set_random_seed(a.seed)

    counts, vols, temp, hum, ts = synth_bins(a.days, a.bin_s, a.seed, a.tz_offset_s) if a.synthetic else csv_bins(a.csv, a.bin_s)
    split = int(len(counts) * 0.8)                                  # chronological split, no shuffling
    stats = dict(DEFAULT_STATS, tz_offset_s=a.tz_offset_s,
                 count_scale=float(max(1.0, np.percentile(counts[:split], 95))),
                 vol_scale_ml=float(max(1.0, np.percentile(vols[:split], 95))))
    X, y, last = windows(counts, vols, temp, hum, ts, a.window, a.horizon, stats)
    stats["target_scale"] = float(max(1.0, np.percentile(y[:split], 95)))
    ntr = split - a.window
    Xtr, ytr, Xte, yte, lte = X[:ntr], y[:ntr] / stats["target_scale"], X[ntr:], y[ntr:], last[ntr:]

    inp = keras.Input((a.window, N_FEATURES))
    out = keras.layers.Dense(1)(keras.layers.Dense(16, activation="relu")(keras.layers.LSTM(32)(inp)))
    model = keras.Model(inp, out)
    model.compile(keras.optimizers.Adam(1e-3), loss="mse")
    model.fit(Xtr, ytr, validation_split=0.15, epochs=a.epochs, batch_size=128, verbose=2, shuffle=True,
              callbacks=[keras.callbacks.EarlyStopping(patience=5, restore_best_weights=True)])

    pred = np.maximum(model.predict(Xte, verbose=0)[:, 0] * stats["target_scale"], 0)
    ema = np.zeros(len(yte)); al = 0.3                                # EMA baseline over the same bins
    e = 0.0
    for i, c in enumerate(counts[split:split + len(yte)]):
        e = al * c + (1 - al) * e; ema[i] = e * a.horizon
    print(f"\nHeld-out MAE (requests / {a.horizon} bins):  LSTM {np.abs(pred - yte).mean():.3f} | "
          f"persistence {np.abs(lte - yte).mean():.3f} | EMA {np.abs(ema - yte).mean():.3f} | mean target {yte.mean():.3f}")

    os.makedirs(a.out, exist_ok=True)
    stats.update(window=a.window, horizon_bins=a.horizon, bin_s=a.bin_s)
    json.dump(stats, open(os.path.join(a.out, "forecaster_stats.json"), "w"), indent=2)
    inf_in = keras.Input(batch_shape=(1, a.window, N_FEATURES))
    infer = keras.Model(inf_in, model(inf_in))
    tfl = tf.lite.TFLiteConverter.from_keras_model(infer).convert()
    path = os.path.join(a.out, "forecaster.tflite")
    open(path, "wb").write(tfl)
    it = tf.lite.Interpreter(model_path=path); it.allocate_tensors()          # parity check Keras vs TFLite
    d_in, d_out = it.get_input_details()[0], it.get_output_details()[0]
    err = 0.0
    for k in range(20):
        it.set_tensor(d_in["index"], Xte[k:k + 1]); it.invoke()
        err = max(err, abs(float(it.get_tensor(d_out["index"])[0][0]) - float(model.predict(Xte[k:k + 1], verbose=0)[0][0])))
    print(f"TFLite saved -> {path} ({len(tfl)/1024:.1f} KiB); max |Keras - TFLite| = {err:.2e}")


if __name__ == "__main__":
    main()
