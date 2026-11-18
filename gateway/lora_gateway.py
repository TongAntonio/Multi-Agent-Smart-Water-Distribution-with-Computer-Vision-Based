"""LoRa (SX1278) -> MQTT gateway for Fig. 9: receives agent frames over the radio and republishes them as JSON on the
Mosquitto broker (water/agents/<id>/state|forward|ack) so Node-RED / the Firebase bridge can consume them.
Run on a Raspberry Pi with its own SX1278 in range of the dispensers.   UNTESTED ON HARDWARE (see README)."""
import argparse
import logging
import time

from agent.comms import Forward, SX1278, State, decode, to_json

log = logging.getLogger("lora-gw")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mqtt-host", default="localhost"); ap.add_argument("--mqtt-port", type=int, default=1883)
    ap.add_argument("--prefix", default="water"); ap.add_argument("--freq-hz", type=int, default=433_175_000)
    ap.add_argument("--sf", type=int, default=9); ap.add_argument("--reset-pin", type=int, default=25)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    import paho.mqtt.client as mqtt
    import RPi.GPIO as G
    G.setmode(G.BCM)
    try:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="lora-gateway")
    except AttributeError:
        c = mqtt.Client(client_id="lora-gateway")
    c.connect(a.mqtt_host, a.mqtt_port, 30); c.loop_start()
    radio = SX1278(gpio=G, reset_pin=a.reset_pin)
    radio.begin(freq_hz=a.freq_hz, sf=a.sf)
    log.info("gateway up: %.3f MHz SF%d -> mqtt://%s", a.freq_hz / 1e6, a.sf, a.mqtt_host)
    while True:
        r = radio.recv()
        if r is None:
            time.sleep(0.02); continue
        m = decode(r[0])
        if m is None:
            continue
        topic = (f"{a.prefix}/agents/{m.agent_id}/state" if isinstance(m, State) else
                 f"{a.prefix}/agents/{m.dst}/{'forward' if isinstance(m, Forward) else 'ack'}")
        c.publish(topic, to_json(m), qos=0)
        if isinstance(m, State):
            c.publish(f"{a.prefix}/agents/{m.agent_id}/rssi", str(r[1]), qos=0)


if __name__ == "__main__":
    main()
