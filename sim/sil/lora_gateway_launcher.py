"""Run the repository's real `gateway/lora_gateway.py` with RPi.GPIO faked and the SX1278 replaced by `UdpRadio`.

Usage (set by sim/sil/deployment.py): SIL_PORTS='{"1": 41001, ..., "gw": 41099}' python sim/sil/lora_gateway_launcher.py <mqtt-port>
"""
import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


def main() -> None:
    ports = {(int(k) if k.isdigit() else k): v for k, v in json.loads(os.environ["SIL_PORTS"]).items()}
    gpio = types.ModuleType("RPi.GPIO")
    gpio.BCM, gpio.OUT = 11, 0
    gpio.setmode = gpio.setup = gpio.output = lambda *a, **k: None
    rpi = types.ModuleType("RPi")
    rpi.GPIO = gpio
    sys.modules["RPi"], sys.modules["RPi.GPIO"] = rpi, gpio
    from sim.sil.radio import UdpRadio
    import gateway.lora_gateway as gw
    gw.SX1278 = lambda gpio=None, reset_pin=0, **kw: UdpRadio("gw", ports)
    sys.argv = ["lora_gateway", "--mqtt-host", "127.0.0.1", "--mqtt-port", sys.argv[1]]
    gw.main()


if __name__ == "__main__":
    main()
