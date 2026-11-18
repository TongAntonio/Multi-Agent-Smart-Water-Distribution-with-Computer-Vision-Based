import subprocess
import sys

import pytest


def test_ppo_smoke_train_and_export_parity(tmp_path):
    """Runs in its own process: TensorFlow and PyTorch can crash when loaded together (same as in real use, where the
    forecaster and PPO trainers are separate scripts). train_ppo asserts 0/500 action mismatches between SB3 and NumPy."""
    pytest.importorskip("torch"); pytest.importorskip("stable_baselines3")
    r = subprocess.run([sys.executable, "-m", "train.train_ppo", "--timesteps", "1024", "--n-envs", "1", "--out", str(tmp_path)],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    assert "0/500 mismatching actions" in r.stdout and (tmp_path / "policy.npz").exists()
