"""MQTT -> Firebase Realtime Database bridge so the existing Admin-Web (Angular) dashboard keeps working.

It writes the fields that Admin-Web reads: /sensor/waterlevel (litres), /sensor/temperature, /sensor/humidity for the
agent given by --primary-agent, plus /agents/<id> for all agents. /records and /sensor/weight are NOT produced here.
  FIREBASE_DB_URL=https://<project>.firebaseio.com  FIREBASE_AUTH=<database secret or ID token>
"""
import argparse
import json
import os
import urllib.request

import paho.mqtt.client as mqtt

from agent.comms import State, from_json


def fb_put(path: str, obj) -> None:
    url = f"{os.environ['FIREBASE_DB_URL'].rstrip('/')}/{path}.json?auth={os.environ.get('FIREBASE_AUTH', '')}"
    req = urllib.request.Request(url, data=json.dumps(obj).encode(), method="PUT", headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10).read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mqtt-host", default="localhost"); ap.add_argument("--mqtt-port", type=int, default=1883); ap.add_argument("--prefix", default="water")
    ap.add_argument("--primary-agent", type=int, default=1)
    a = ap.parse_args()

    def on_message(c, u, msg):
        m = from_json(msg.payload.decode(errors="ignore"))
        if not isinstance(m, State):
            return
        fb_put(f"agents/{m.agent_id}", {"queue": m.queue_len, "water_l": round(m.water_ml / 1000, 2), "forecast": m.forecast,
                                        "busy": m.busy, "temperature": m.temp_c, "humidity": m.hum})
        if m.agent_id == a.primary_agent:
            fb_put("sensor/waterlevel", round(m.water_ml / 1000, 2)); fb_put("sensor/temperature", m.temp_c); fb_put("sensor/humidity", m.hum)

    try:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="firebase-bridge")
    except AttributeError:
        c = mqtt.Client(client_id="firebase-bridge")
    c.on_connect = lambda cl, u, f, rc, *x: cl.subscribe(f"{a.prefix}/agents/+/state")
    c.on_message = on_message
    c.connect(a.mqtt_host, a.mqtt_port, 30)
    c.loop_forever()


if __name__ == "__main__":
    main()
