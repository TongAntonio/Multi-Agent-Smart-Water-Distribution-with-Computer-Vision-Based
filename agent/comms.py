"""Agent-to-agent / agent-to-gateway communication (paper Sec. III-D, Fig. 9).

Messages: State (periodic broadcast), Forward (hand a request to a neighbour), Ack.
Transports (same API):  MqttLink (Wi-Fi/Ethernet/LoRaWAN-gateway side) | LoraLink (SX1278 raw LoRa P2P)
                        | NbIotLink (SIM7000 AT-command MQTT) | MemoryLink (tests / simulation).

NOTE: the SX1278 covers only 137-525 MHz, so LoraLink is LoRa point-to-point (default 433 MHz band), NOT LoRaWAN.
LoRaWAN in the AS923 band needs an SX1276-class radio + LoRaWAN stack + gateway. LoraLink and NbIotLink are
validated against simulated peripherals only - bench-test them on real hardware before relying on them.
"""
from __future__ import annotations

import json
import logging
import queue
import random
import re
import struct
import time
from dataclasses import asdict, dataclass
from typing import Optional

log = logging.getLogger(__name__)
BROADCAST = 255


@dataclass
class State:
    agent_id: int
    seq: int
    queue_len: int
    water_ml: float
    forecast: float
    busy: bool = False
    temp_c: float = 0.0
    hum: float = 0.0
    kind = 1


@dataclass
class Forward:
    src: int
    dst: int
    seq: int
    request_id: int
    volume_ml: int
    hops: int
    waited_s: int = 0
    kind = 2


@dataclass
class Ack:
    src: int
    dst: int
    seq: int
    request_id: int
    kind = 3


_KIND = {1: State, 2: Forward, 3: Ack}
_CLS_KIND = {State: 1, Forward: 2, Ack: 3}
_FMT = {1: ">BBHBHBbBB", 2: ">BBBHIHBH", 3: ">BBBHI"}   # State 11 B, Forward 14 B, Ack 9 B (fits any LoRa SF/BW)


def encode(m) -> bytes:
    if isinstance(m, State):
        return struct.pack(_FMT[1], 1, m.agent_id, m.seq & 0xFFFF, min(m.queue_len, 255), min(int(m.water_ml / 10), 65535),
                           min(int(m.forecast * 10), 255), max(-128, min(127, int(round(m.temp_c)))), min(int(m.hum), 255), int(m.busy))
    if isinstance(m, Forward):
        return struct.pack(_FMT[2], 2, m.src, m.dst, m.seq & 0xFFFF, m.request_id, min(m.volume_ml, 65535), m.hops, min(m.waited_s, 65535))
    return struct.pack(_FMT[3], 3, m.src, m.dst, m.seq & 0xFFFF, m.request_id)


def decode(b: bytes):
    if not b or b[0] not in _FMT or len(b) < struct.calcsize(_FMT[b[0]]):
        return None
    k = b[0]
    v = struct.unpack(_FMT[k], b[:struct.calcsize(_FMT[k])])
    if k == 1:
        return State(v[1], v[2], v[3], v[4] * 10.0, v[5] / 10.0, bool(v[8]), float(v[6]), float(v[7]))
    if k == 2:
        return Forward(v[1], v[2], v[3], v[4], v[5], v[6], v[7])
    return Ack(v[1], v[2], v[3], v[4])


def to_json(m) -> str:
    return json.dumps({"kind": _CLS_KIND[type(m)], **asdict(m)}, separators=(",", ":"))


def from_json(s) -> Optional[object]:
    try:
        d = json.loads(s)
        cls = _KIND[d.pop("kind")]
        return cls(**d)
    except Exception:
        return None


class Link:
    def start(self): ...
    def stop(self): ...
    def send(self, msg) -> None: ...
    def poll(self) -> list: ...


# ---------------------------------------------------------------- MQTT
class MqttLink(Link):
    def __init__(self, agent_id: int, host="localhost", port=1883, prefix="water", username=None, password=None):
        import paho.mqtt.client as mqtt
        self.id, self.prefix, self.host, self.port = agent_id, prefix, host, port
        self.q: "queue.Queue" = queue.Queue()
        cid = f"dispenser-{agent_id}"
        try:
            self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)   # paho-mqtt >= 2.0
        except AttributeError:
            self.c = mqtt.Client(client_id=cid)                                      # paho-mqtt 1.x
        if username:
            self.c.username_pw_set(username, password)
        self.c.will_set(f"{prefix}/agents/{agent_id}/status", "offline", qos=1, retain=True)
        self.c.on_connect = self._on_connect
        self.c.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc, *a):
        p = self.prefix
        client.subscribe([(f"{p}/agents/+/state", 0), (f"{p}/agents/{self.id}/forward", 1), (f"{p}/agents/{self.id}/ack", 1)])
        client.publish(f"{p}/agents/{self.id}/status", "online", qos=1, retain=True)

    def _on_message(self, client, userdata, msg):
        m = from_json(msg.payload.decode(errors="ignore"))
        if m is not None:
            self.q.put(m)

    def start(self):
        self.c.connect_async(self.host, self.port, keepalive=30)   # non-blocking: agent keeps working offline
        self.c.loop_start()

    def stop(self):
        self.c.publish(f"{self.prefix}/agents/{self.id}/status", "offline", qos=1, retain=True)
        self.c.loop_stop()
        self.c.disconnect()

    def send(self, msg):
        p = self.prefix
        if isinstance(msg, State):
            self.c.publish(f"{p}/agents/{msg.agent_id}/state", to_json(msg), qos=0)
        elif isinstance(msg, Forward):
            self.c.publish(f"{p}/agents/{msg.dst}/forward", to_json(msg), qos=1)
        else:
            self.c.publish(f"{p}/agents/{msg.dst}/ack", to_json(msg), qos=1)

    def poll(self):
        out = []
        while not self.q.empty():
            m = self.q.get_nowait()
            if not (isinstance(m, State) and m.agent_id == self.id):
                out.append(m)
        return out


# ---------------------------------------------------------------- in-memory bus (tests / simulation)
class MemoryBus:
    def __init__(self, drop: float = 0.0, seed: int = 0):
        self.links: dict[int, "MemoryLink"] = {}
        self.drop, self.rng = drop, random.Random(seed)


class MemoryLink(Link):
    def __init__(self, agent_id: int, bus: MemoryBus):
        self.id, self.bus, self.inbox = agent_id, bus, []
        bus.links[agent_id] = self

    def send(self, msg):
        dsts = [i for i in self.bus.links if i != self.id] if isinstance(msg, State) else [msg.dst]
        for d in dsts:
            if d in self.bus.links and self.bus.rng.random() >= self.bus.drop:
                self.bus.links[d].inbox.append(msg)

    def poll(self):
        out, self.inbox = self.inbox, []
        return out


# ---------------------------------------------------------------- SX1278 raw LoRa
class SX1278:
    REG_FIFO, REG_OP_MODE, REG_FRF_MSB, REG_PA_CONFIG, REG_FIFO_PTR = 0x00, 0x01, 0x06, 0x09, 0x0D
    REG_TX_BASE, REG_RX_BASE, REG_RX_CUR, REG_IRQ, REG_RX_N = 0x0E, 0x0F, 0x10, 0x12, 0x13
    REG_PKT_SNR, REG_PKT_RSSI, REG_MC1, REG_MC2, REG_PRE_MSB = 0x19, 0x1A, 0x1D, 0x1E, 0x20
    REG_PAYLOAD_LEN, REG_MC3, REG_SYNC, REG_VERSION = 0x22, 0x26, 0x39, 0x42
    LORA, SLEEP, STDBY, TX, RX = 0x80, 0x00, 0x01, 0x03, 0x05
    IRQ_TX_DONE, IRQ_RX_DONE, IRQ_CRC_ERR = 0x08, 0x40, 0x20
    BW = {7800: 0, 10400: 1, 15600: 2, 20800: 3, 31250: 4, 41700: 5, 62500: 6, 125000: 7, 250000: 8, 500000: 9}

    def __init__(self, spi=None, gpio=None, reset_pin: int = 25, bus: int = 0, cs: int = 0):
        if spi is None:
            import spidev
            spi = spidev.SpiDev()
            spi.open(bus, cs)
            spi.max_speed_hz = 5_000_000
        self.spi, self.gpio, self.reset_pin = spi, gpio, reset_pin

    def _w(self, reg, val):
        self.spi.xfer2([reg | 0x80, val & 0xFF])

    def _r(self, reg):
        return self.spi.xfer2([reg & 0x7F, 0])[1]

    def begin(self, freq_hz=433_175_000, sf=9, bw_hz=125_000, cr=5, power_dbm=14, sync_word=0x12) -> None:
        if self.gpio is not None:
            self.gpio.setup(self.reset_pin, self.gpio.OUT)
            self.gpio.output(self.reset_pin, 0); time.sleep(0.01)
            self.gpio.output(self.reset_pin, 1); time.sleep(0.01)
        if self._r(self.REG_VERSION) != 0x12:
            raise RuntimeError("SX127x not found on SPI (RegVersion != 0x12) - check wiring/CS/reset")
        if not (137_000_000 <= freq_hz <= 525_000_000):
            raise ValueError("SX1278 supports only 137-525 MHz; use an SX1276-class module for 868/915/923 MHz")
        self._w(self.REG_OP_MODE, self.SLEEP); self._w(self.REG_OP_MODE, self.LORA | self.SLEEP)
        frf = int(freq_hz * (1 << 19) / 32_000_000)
        for i, sh in enumerate((16, 8, 0)):
            self._w(self.REG_FRF_MSB + i, (frf >> sh) & 0xFF)
        self._w(self.REG_PA_CONFIG, 0x80 | (max(2, min(17, power_dbm)) - 2))      # PA_BOOST
        self._w(self.REG_MC1, (self.BW[bw_hz] << 4) | ((cr - 4) << 1))             # explicit header
        self._w(self.REG_MC2, (sf << 4) | 0x04)                                    # CRC on
        ldro = (2 ** sf) / (bw_hz / 1000.0) > 16.0                                 # symbol time > 16 ms
        self._w(self.REG_MC3, 0x04 | (0x08 if ldro else 0))                        # AGC auto, low-data-rate opt.
        self._w(self.REG_PRE_MSB, 0); self._w(self.REG_PRE_MSB + 1, 8)
        self._w(self.REG_SYNC, sync_word)
        self._w(self.REG_TX_BASE, 0); self._w(self.REG_RX_BASE, 0)
        self._w(self.REG_OP_MODE, self.LORA | self.RX)

    def send(self, payload: bytes, timeout: float = 3.0) -> bool:
        self._w(self.REG_OP_MODE, self.LORA | self.STDBY)
        self._w(self.REG_FIFO_PTR, 0)
        self.spi.xfer2([self.REG_FIFO | 0x80] + list(payload))
        self._w(self.REG_PAYLOAD_LEN, len(payload))
        self._w(self.REG_IRQ, 0xFF)
        self._w(self.REG_OP_MODE, self.LORA | self.TX)
        t0, ok = time.monotonic(), False
        while time.monotonic() - t0 < timeout:
            if self._r(self.REG_IRQ) & self.IRQ_TX_DONE:
                ok = True
                break
            time.sleep(0.005)
        self._w(self.REG_IRQ, 0xFF)
        self._w(self.REG_OP_MODE, self.LORA | self.RX)
        return ok

    def recv(self):
        irq = self._r(self.REG_IRQ)
        if not irq & self.IRQ_RX_DONE:
            return None
        self._w(self.REG_IRQ, 0xFF)
        if irq & self.IRQ_CRC_ERR:
            return None
        n = self._r(self.REG_RX_N)
        self._w(self.REG_FIFO_PTR, self._r(self.REG_RX_CUR))
        data = bytes(self.spi.xfer2([self.REG_FIFO & 0x7F] + [0] * n)[1:])
        return data, self._r(self.REG_PKT_RSSI) - 164        # -164 offset: low-frequency port (< 525 MHz)


class LoraLink(Link):
    def __init__(self, agent_id: int, radio: SX1278, jitter_s: float = 0.2, **radio_cfg):
        self.id, self.radio, self.jitter, self.cfg = agent_id, radio, jitter_s, radio_cfg

    def start(self):
        self.radio.begin(**self.cfg)

    def send(self, msg):
        time.sleep(random.uniform(0, self.jitter))   # crude collision avoidance between neighbours
        self.radio.send(encode(msg))

    def poll(self):
        out = []
        while (r := self.radio.recv()) is not None:
            m = decode(r[0])
            if m is None or (isinstance(m, State) and m.agent_id == self.id):
                continue
            if isinstance(m, (Forward, Ack)) and m.dst != self.id:
                continue
            out.append(m)
        return out


# ---------------------------------------------------------------- SIM7000 NB-IoT (AT-command MQTT)
class NbIotLink(Link):
    """SIM7000 MQTT over NB-IoT/LTE-M via AT commands. Activation syntax differs between firmware versions:
    set link.nbiot.activate_cmd accordingly (e.g. 'AT+CNACT=0,1' or 'AT+CNACT=1,"<apn>"')."""

    URC = re.compile(r'^\+SMSUB:\s*"([^"]+)","(.*)"\s*$')

    def __init__(self, agent_id: int, ser=None, port="/dev/serial0", baud=115200, apn="", activate_cmd="AT+CNACT=0,1",
                 host="localhost", mqtt_port=1883, prefix="water"):
        if ser is None:
            import serial
            ser = serial.Serial(port, baud, timeout=0.1)
        self.ser, self.id, self.apn, self.act = ser, agent_id, apn, activate_cmd
        self.host, self.mport, self.prefix, self._rx = host, mqtt_port, prefix, ""

    def _txrx(self, data: bytes, expect=("OK",), timeout=3.0) -> str:
        self.ser.write(data)
        t0, buf = time.monotonic(), b""
        while time.monotonic() - t0 < timeout:
            buf += self.ser.read(getattr(self.ser, "in_waiting", 0) or 1)
            text = buf.decode(errors="ignore")
            if "ERROR" in text:
                raise RuntimeError(f"{data[:40]!r} -> {text.strip()}")
            if any(e in text for e in expect):
                return text
        raise TimeoutError(f"AT timeout: {data[:40]!r}")

    def at(self, cmd: str, expect=("OK",), timeout=3.0) -> str:
        return self._txrx((cmd + "\r\n").encode(), expect, timeout)

    def start(self):
        p = self.prefix
        self.at("AT"); self.at("ATE0")
        if self.apn:
            self.at(f'AT+CGDCONT=1,"IP","{self.apn}"')
        self.at("AT+CMNB=2"); self.at("AT+CNMP=38")           # NB-IoT only (use CMNB=1 for LTE-M)
        self.at("AT+CGATT=1", timeout=15)
        self.at(self.act, timeout=15)
        self.at(f'AT+SMCONF="URL","{self.host}","{self.mport}"')
        self.at(f'AT+SMCONF="CLIENTID","dispenser-{self.id}"')
        self.at('AT+SMCONF="KEEPTIME",60'); self.at('AT+SMCONF="CLEANSS",1')
        self.at("AT+SMCONN", timeout=30)
        for t in (f"{p}/agents/+/state", f"{p}/agents/{self.id}/forward", f"{p}/agents/{self.id}/ack"):
            self.at(f'AT+SMSUB="{t}",1')

    def stop(self):
        try:
            self.at("AT+SMDISC")
        except Exception:
            pass

    def _publish(self, topic: str, payload: str, qos: int = 0):
        b = payload.encode()
        self._txrx(f'AT+SMPUB="{topic}",{len(b)},{qos},0\r\n'.encode(), expect=(">",))
        self._txrx(b, expect=("OK",), timeout=10)

    def send(self, msg):
        p = self.prefix
        if isinstance(msg, State):
            self._publish(f"{p}/agents/{msg.agent_id}/state", to_json(msg), 0)
        elif isinstance(msg, Forward):
            self._publish(f"{p}/agents/{msg.dst}/forward", to_json(msg), 1)
        else:
            self._publish(f"{p}/agents/{msg.dst}/ack", to_json(msg), 1)

    def poll(self):
        n = getattr(self.ser, "in_waiting", 0)
        if n:
            self._rx += self.ser.read(n).decode(errors="ignore")
        out = []
        while "\n" in self._rx:
            line, self._rx = self._rx.split("\n", 1)
            mt = self.URC.match(line.strip())
            if mt:
                m = from_json(mt.group(2))
                if m is not None and not (isinstance(m, State) and m.agent_id == self.id):
                    out.append(m)
        return out


def make_link(cfg: dict, bus: Optional[MemoryBus] = None) -> Link:
    t, aid, lc = cfg["link"]["type"], cfg["agent_id"], cfg["link"]
    if t == "mqtt":
        return MqttLink(aid, **lc["mqtt"])
    if t == "lora":
        l = lc["lora"]
        import RPi.GPIO as G
        radio = SX1278(gpio=G, reset_pin=l["reset_pin"], bus=l["spi_bus"], cs=l["spi_cs"])
        return LoraLink(aid, radio, freq_hz=l["freq_hz"], sf=l["sf"], bw_hz=l["bw_hz"], cr=l["cr"],
                        power_dbm=l["tx_power_dbm"], sync_word=l["sync_word"])
    if t == "nbiot":
        n = lc["nbiot"]
        return NbIotLink(aid, port=n["port"], baud=n["baud"], apn=n["apn"], activate_cmd=n["activate_cmd"],
                         host=n["host"], mqtt_port=n["mqtt_port"], prefix=n["prefix"])
    if t == "memory":
        return MemoryLink(aid, bus or MemoryBus())
    raise ValueError(f"unknown link type {t}")
