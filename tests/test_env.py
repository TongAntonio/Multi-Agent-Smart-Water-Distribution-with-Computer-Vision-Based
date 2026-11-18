import warnings

import numpy as np
import pytest

from sim.baselines import CentralizedPolicy, HeuristicPolicy
from sim.env import WaterGridEnv
from sim.run_experiment import run_episode


def test_gymnasium_api_check():
    from gymnasium.utils.env_checker import check_env
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        check_env(WaterGridEnv(), skip_render_check=True)


def test_seed_determinism():
    assert run_episode(HeuristicPolicy(), 3, 0.2) == run_episode(HeuristicPolicy(), 3, 0.2)


def test_random_policy_always_terminates_with_valid_metrics():
    env = WaterGridEnv(drop_range=(0.0, 0.4))
    rng = np.random.default_rng(0)
    for ep in range(5):
        env.reset(seed=ep); done, n = False, 0
        while not done:
            _, r, done, _, info = env.step(int(rng.integers(3))); n += 1
            assert np.isfinite(r) and n < 20000
        assert 0.0 <= info["success_rate"] <= 1.0 and 0.0 <= info["fairness_jain"] <= 1.0


def test_water_is_conserved_and_never_negative():
    env = WaterGridEnv(); env.reset(seed=1); done = False
    cap0 = env.cap.sum()
    while not done:
        _, _, done, _, info = env.step(0)
        assert (env.water >= -1e-9).all()
    assert cap0 - env.water.sum() == pytest.approx(env.st["served_ml"])


def test_total_packet_loss_breaks_centralised_but_not_local_control():
    local = run_episode(HeuristicPolicy(), 0, 1.0)["success_rate"]
    central = run_episode(CentralizedPolicy(3.0), 0, 1.0)["success_rate"]
    assert central == 0.0 and local > 0.5
