"""An agent whose MQTT broker is unreachable (nothing listening on the port) must keep serving containers locally.

Uses the real `MqttLink` and `Agent`; only the hardware is simulated. This checks one thing: that an unreachable broker does not
stop a dispense. It says nothing about where the broker ran in any trial. Needs `paho-mqtt`; skipped without it.
"""
import socket

import pytest

pytest.importorskip("paho.mqtt.client")

from agent.comms import MqttLink  # noqa: E402
from agent.config import load_config  # noqa: E402
from agent.hardware import SimHardware  # noqa: E402
from agent.main import Agent  # noqa: E402
from agent.policy import HeuristicPolicy  # noqa: E402

from .test_agent import Clock, Det  # noqa: E402


def _closed_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def test_agent_dispenses_when_broker_is_unreachable(tmp_path):
    link = MqttLink(1, host="127.0.0.1", port=_closed_port())
    cfg = load_config(); cfg.update(agent_id=1, simulate_hardware=True, log_dir=str(tmp_path))
    hw = SimHardware(level_ml=15000.0)
    clk = Clock()
    agent = Agent(cfg, hw, link, None, Det(), policy=HeuristicPolicy(), clock=clk)
    link.start()                                   # connect_async: must not block or raise although nobody is listening
    try:
        hw.set_present(True)
        info = agent.step()                        # also publishes State to the dead broker; must not raise
        assert info["action"] == "dispense"
        assert hw.level == pytest.approx(14500.0)
        clk.advance(cfg["state_period_s"] + 1)
        agent.step()                               # a second tick, still no broker
        assert link.poll() == []                   # nothing arrives from a broker that is not there
    finally:
        link.stop()
