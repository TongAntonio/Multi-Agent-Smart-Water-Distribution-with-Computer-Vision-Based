"""Two documented gaps (README, "Status and known gaps"), pinned so that a fix is noticed.

1. An NB-IoT modem error raises inside `Agent.step()` before the dispense decision, and `Agent.run()` does not catch it.
   The test asserts the CURRENT behaviour; when the gap is fixed it fails and should be rewritten to expect the dispense.
2. A tank holding between `volume` and `volume + reserve_ml` neither dispenses (the reserve guard blocks it) nor forwards
   (the policy only forwards when water < volume), although a neighbour with water is known. Marked xfail(strict) so a fix flips it.
"""
import pytest

from agent.comms import NbIotLink
from agent.comms import MemoryBus
from agent.config import load_config
from agent.hardware import SimHardware
from agent.main import Agent
from agent.policy import HeuristicPolicy

from .helpers import FakeModem
from .test_agent import Clock, Det, make_agent


def test_nbiot_modem_error_currently_ends_the_step_before_dispensing(tmp_path):
    cfg = load_config(); cfg.update(agent_id=1, simulate_hardware=True, log_dir=str(tmp_path))
    hw = SimHardware(level_ml=15000.0); hw.set_present(True)
    agent = Agent(cfg, hw, NbIotLink(1, ser=FakeModem(fail_on="AT+SMPUB")), None, Det(), policy=HeuristicPolicy(), clock=Clock())
    with pytest.raises(RuntimeError):
        agent.step()
    assert hw.level == 15000.0                       # nothing was dispensed


@pytest.mark.xfail(strict=True, reason="known gap: water between volume and volume+reserve neither dispenses nor forwards")
def test_tank_between_volume_and_volume_plus_reserve_forwards_to_neighbour(tmp_path):
    bus, clk = MemoryBus(), Clock()
    a, hw = make_agent(tmp_path, 1, bus, clk, level=700.0, det=Det(vol=600))        # reserve is 200 ml by default
    b, _ = make_agent(tmp_path, 2, bus, clk, level=15000.0)
    b.step(); clk.advance(1); a.step()                                              # a learns that b has water
    hw.set_present(True)
    actions = []
    for _ in range(5):
        actions.append(a.step()["action"]); clk.advance(1)
    assert "forward_request" in actions or hw.level < 700.0
