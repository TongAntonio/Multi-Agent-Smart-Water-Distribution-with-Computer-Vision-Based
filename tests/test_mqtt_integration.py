"""MqttLink against a real (pure-Python) MQTT broker: end-to-end state broadcast, forward + ACK over the wire.
Skipped when `amqtt` is not installed. This is NOT a Mosquitto test - rerun against your Mosquitto before deploying."""
import asyncio
import socket
import threading
import time

import pytest

pytest.importorskip("amqtt")

from agent.comms import Ack, Forward, MqttLink, State  # noqa: E402


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture()
def broker():
    from amqtt.broker import Broker
    port = _free_port()
    cfg = {"listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{port}"}}, "sys_interval": 0,
           "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]}, "topic-check": {"enabled": False}}
    loop = asyncio.new_event_loop(); b = Broker(cfg, loop=loop); ready = threading.Event()

    def run():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(b.start()); ready.set(); loop.run_forever()
    t = threading.Thread(target=run, daemon=True); t.start()
    assert ready.wait(10), "broker did not start"
    yield port
    asyncio.run_coroutine_threadsafe(b.shutdown(), loop).result(10)
    loop.call_soon_threadsafe(loop.stop)


def _wait(cond, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_state_forward_ack_over_mqtt(broker):
    a, b = MqttLink(1, port=broker), MqttLink(2, port=broker)
    got_a, got_b = [], []
    a.start(); b.start()
    try:
        time.sleep(1.0)                                          # let both subscribe
        a.send(State(1, 1, 4, 1500.0, 2.5, False, 31.0, 62.0))
        assert _wait(lambda: got_b.extend(b.poll()) or any(isinstance(m, State) for m in got_b))
        st = [m for m in got_b if isinstance(m, State)][0]
        assert st.agent_id == 1 and st.queue_len == 4 and st.water_ml == 1500.0
        assert a.poll() == []                                    # a never sees its own state
        a.send(Forward(1, 2, 7, 424242, 500, 1, 3))
        assert _wait(lambda: got_b.extend(b.poll()) or any(isinstance(m, Forward) for m in got_b))
        f = [m for m in got_b if isinstance(m, Forward)][0]
        b.send(Ack(2, f.src, f.seq, f.request_id))
        assert _wait(lambda: got_a.extend(a.poll()) or any(isinstance(m, Ack) for m in got_a))
        assert [m for m in got_a if isinstance(m, Ack)][0].request_id == 424242
    finally:
        a.stop(); b.stop()
