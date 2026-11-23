"""Smoke test of the software-in-the-loop deployment: real Mosquitto + real agents + the real Firebase bridge, 10 simulated seconds.
Skipped when `mosquitto` is not installed. It checks that the harness runs; the experiment itself is sim/run_sil.py."""
import shutil

import pytest

pytestmark = pytest.mark.skipif(shutil.which("mosquitto") is None, reason="mosquitto not installed")


def test_sil_mqtt_baseline_short(tmp_path, monkeypatch):
    import sim.sil.deployment as d
    for name, v in ("DURATION_S", 40.0), ("ARRIVALS_UNTIL_S", 30.0), ("WINDOW_S", (20.0, 30.0)):
        monkeypatch.setattr(d, name, v)
    r = d.run("mqtt", "baseline", 1, 8.0, str(tmp_path / "run"))
    tot = sum(p["users"] for p in r["phases"].values())
    served = sum(p["served"] for p in r["phases"].values())
    assert tot > 0 and served == tot                                   # nothing fails without an outage
    assert r["facts"]["bridge_alive_after_start"] is True
    assert sum(p["dashboard_puts_per_min"] for p in r["phases"].values()) > 0   # the real bridge fed the Firebase stub
