import numpy as np

from agent.spec import MAX_VOLUME_ML
from sim.baselines import CentralizedPolicy, HeuristicPolicy
from sim.connectivity import DEFAULT_VOLUME_ML, NoForecastEnv, NoVolumeEnv, OutageEnv, run_episode


def test_outage_window_sets_drop_to_one_only_inside_window():
    env = OutageEnv(outage=(100.0, 200.0))
    env.reset(seed=0, options={"packet_drop": 0.0})
    env.t = 50.0
    assert env.drop == 0.0
    env.t = 150.0
    assert env.drop == 1.0
    env.t = 200.0
    assert env.drop == 0.0


def test_no_outage_matches_plain_env_results():
    from sim.run_experiment import run_episode as plain
    a = run_episode(HeuristicPolicy(), 3, 0.2)
    b = plain(HeuristicPolicy(), 3, 0.2)
    for k in ("success_rate", "mean_latency_s", "fairness_jain"):
        assert np.isclose(a[k], b[k], equal_nan=True)


def test_centralized_cannot_act_during_whole_run_outage_but_local_policy_can():
    kw = dict(outage=(0.0, 1e9))
    cen = run_episode(CentralizedPolicy(3.0), 0, **kw)
    loc = run_episode(HeuristicPolicy(), 0, **kw)
    assert cen["success_rate"] == 0.0
    assert loc["success_rate"] > 0.3          # serves from its own tank without any neighbour information
    assert loc["forwards"] == 0               # forwarding is impossible without neighbour views


def test_outage_metrics_count_requests_in_window():
    r = run_episode(HeuristicPolicy(), 1, outage=(100.0, 200.0))
    assert r["n_during"] > 0
    assert 0.0 <= r["success_during"] <= 1.0
    assert r["recovery_s"] >= 0.0


def test_ablation_envs_change_only_the_observation():
    e = NoForecastEnv(); e.reset(seed=0); assert e._forecast(e.cur) == 0.0
    v = NoVolumeEnv(); o, _ = v.reset(seed=0)
    assert np.isclose(o[2], DEFAULT_VOLUME_ML / MAX_VOLUME_ML)
