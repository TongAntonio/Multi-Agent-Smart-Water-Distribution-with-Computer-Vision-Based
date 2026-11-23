"""Real-time test (no time scaling): how long does an `MqttLink` take to reconnect and resubscribe after a Mosquitto outage?

    python -m sim.sil.reconnect_test            # writes results/sil/reconnect.json; takes about four minutes

The scaled-clock runs in sim/sil/deployment.py cannot measure this, because paho's reconnect back-off is in real seconds.
"""
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from agent.comms import MqttLink, State  # noqa: E402
from sim.sil.deployment import Mosquitto, free_port  # noqa: E402


def wait(cond, timeout):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if cond():
            return time.monotonic() - t0
        time.sleep(0.05)
    return None


def main() -> None:
    out = []
    port, wd = free_port(), tempfile.mkdtemp()
    br = Mosquitto(port, wd); br.start()
    a, b = MqttLink(1, host="127.0.0.1", port=port), MqttLink(2, host="127.0.0.1", port=port)
    a.start(); b.start()
    assert wait(lambda: a.c.is_connected() and b.c.is_connected(), 10) is not None
    time.sleep(1.0)
    try:
        for outage in (10, 30, 90):
            br.stop(); time.sleep(0.5)
            assert wait(lambda: not a.c.is_connected(), 5) is not None
            time.sleep(outage)
            br.start(); t0 = time.monotonic()
            d_conn = wait(lambda: a.c.is_connected() and b.c.is_connected(), 200)
            got = []
            d_msg = None
            if d_conn is not None:
                for _ in range(100):                                   # resubscription check: B sends a State, A must receive it
                    b.send(State(2, 1, 0, 1000.0, 0.0, False, 30.0, 60.0)); time.sleep(0.1)
                    got = a.poll()
                    if any(isinstance(m, State) for m in got):
                        d_msg = time.monotonic() - t0; break
            out.append({"outage_s": outage, "reconnect_s": None if d_conn is None else round(d_conn, 1),
                        "first_state_delivered_s": None if d_msg is None else round(d_msg, 1)})
            print(out[-1], flush=True)
    finally:
        a.stop(); b.stop(); br.stop()
    os.makedirs(os.path.join(ROOT, "results", "sil"), exist_ok=True)
    json.dump({"note": "real time, one run per outage length, paho-mqtt default reconnect back-off (1 s doubling to 120 s)", "runs": out},
              open(os.path.join(ROOT, "results", "sil", "reconnect.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
