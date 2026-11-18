import numpy as np
import pytest

from agent.metrics import jain, quality, summarize
from agent.policy import NumpyPolicy, heuristic_act
from agent.spec import DISPENSE, FORWARD, OBS_DIM, WAIT, best_neighbor, build_observation


def obs(**kw):
    d = dict(water_ml=2000.0, cv_valid=True, volume_ml=500.0, forecast_requests=1.0, queue_len=1, head_wait_s=5.0, nbr=None, busy=False)
    d.update(kw)
    return build_observation(**d)


def test_observation_layout_and_bounds():
    o = obs(water_ml=1e9, queue_len=99, head_wait_s=1e9, forecast_requests=1e9)
    assert o.shape == (OBS_DIM,) and o.dtype == np.float32 and o.min() >= 0.0 and o.max() <= 1.0
    assert obs(nbr=None)[6] == 1.0 and obs(nbr=None)[7] == 0.0           # no neighbour => "worst" values
    assert obs(nbr=(2, 3, 2000.0))[7] == pytest.approx(0.5)


def test_best_neighbor_filters_stale_and_insufficient_water():
    views = {1: (0, 100.0, 95.0), 2: (3, 2000.0, 95.0), 3: (1, 2000.0, 10.0), 4: (2, 2500.0, 99.0)}
    assert best_neighbor(views, 500.0, now=100.0) == (4, 2, 2500.0)       # 1: too little water, 3: stale, 2: longer queue
    assert best_neighbor({}, 500.0, 0.0) is None


def test_heuristic_rules():
    assert heuristic_act(obs(busy=True)) == WAIT
    assert heuristic_act(obs()) == DISPENSE
    assert heuristic_act(obs(cv_valid=False)) == WAIT
    assert heuristic_act(obs(water_ml=100.0, nbr=(0, 1, 3000.0))) == FORWARD
    assert heuristic_act(obs(water_ml=100.0)) == WAIT


def test_numpy_policy_roundtrip_and_sampling(tmp_path):
    rng = np.random.default_rng(0)
    pol = NumpyPolicy([(rng.normal(size=(8, OBS_DIM)).astype(np.float32), np.zeros(8, np.float32))],
                      (rng.normal(size=(3, 8)).astype(np.float32), np.zeros(3, np.float32)))
    p = tmp_path / "p.npz"; pol.save(str(p))
    pol2 = NumpyPolicy.load(str(p))
    x = rng.random((50, OBS_DIM)).astype(np.float32)
    assert [pol.act(o) for o in x] == [pol2.act(o) for o in x]
    assert {pol.act(o, deterministic=False, rng=np.random.default_rng(1)) for o in x} <= {0, 1, 2}


def test_jain_and_summary():
    assert jain([1, 1, 1]) == pytest.approx(1.0) and jain([1, 0, 0, 0]) == pytest.approx(0.25) and jain([]) == 1.0
    assert quality(30, True, 120) == pytest.approx(0.75) and quality(30, False, 120) == 0.0
    recs = [{"outcome": "served", "latency_s": 10}, {"outcome": "served", "latency_s": 30},
            {"outcome": "timeout", "latency_s": 120}, {"outcome": "forwarded", "latency_s": 2}]
    s = summarize(recs)
    assert s["n_requests"] == 3 and s["success_rate"] == pytest.approx(2 / 3) and s["mean_latency_s"] == pytest.approx(20.0)
