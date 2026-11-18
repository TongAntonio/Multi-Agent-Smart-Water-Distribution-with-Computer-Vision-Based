import json

import pytest

from agent import comms as c
from tests.helpers import FakeModem, FakeSpi


def test_binary_roundtrip_and_sizes():
    msgs = [c.State(3, 7, 2, 1230.0, 3.4, True, 31.0, 62.0), c.Forward(1, 2, 9, 70000, 500, 1, 12), c.Ack(2, 1, 9, 70000)]
    for m, size in zip(msgs, (11, 14, 9)):
        b = c.encode(m)
        assert len(b) == size
        assert c.decode(b) == m


def test_binary_decode_rejects_garbage():
    assert c.decode(b"") is None
    assert c.decode(b"\x09abc") is None
    assert c.decode(b"\x02\x01") is None          # truncated Forward


def test_json_roundtrip():
    for m in (c.State(1, 2, 3, 4000.0, 1.5, False, 30.0, 60.0), c.Forward(1, 2, 3, 4, 500, 1, 7), c.Ack(2, 1, 3, 4)):
        assert c.from_json(c.to_json(m)) == m
    assert c.from_json("not json") is None


def test_memory_bus_broadcast_and_unicast():
    bus = c.MemoryBus()
    a, b, d = (c.MemoryLink(i, bus) for i in (1, 2, 3))
    a.send(c.State(1, 1, 0, 1000.0, 0.0))
    assert len(b.poll()) == 1 and len(d.poll()) == 1 and a.poll() == []
    a.send(c.Forward(1, 2, 1, 5, 500, 1))
    assert len(b.poll()) == 1 and d.poll() == []


def test_memory_bus_drop_all():
    bus = c.MemoryBus(drop=1.0)
    a, b = c.MemoryLink(1, bus), c.MemoryLink(2, bus)
    a.send(c.State(1, 1, 0, 1000.0, 0.0))
    assert b.poll() == []


# ------------------------------------------------------------------ SX1278 against a fake register file
def test_sx1278_begin_programs_registers():
    spi = FakeSpi()
    r = c.SX1278(spi=spi)
    r.begin(freq_hz=433_175_000, sf=9, bw_hz=125_000, cr=5, power_dbm=14, sync_word=0x12)
    frf = int(433_175_000 * (1 << 19) / 32_000_000)
    assert [spi.regs[0x06], spi.regs[0x07], spi.regs[0x08]] == [(frf >> 16) & 255, (frf >> 8) & 255, frf & 255]
    assert spi.regs[0x1D] == (7 << 4) | (1 << 1)          # BW 125k, CR 4/5
    assert spi.regs[0x1E] >> 4 == 9 and spi.regs[0x1E] & 0x04   # SF9, CRC on
    assert spi.regs[0x39] == 0x12
    assert spi.regs[0x09] == 0x80 | 12                     # PA_BOOST, 14 dBm
    assert spi.regs[0x01] == 0x85                          # LoRa + continuous RX
    assert spi.regs[0x26] & 0x08 == 0                      # SF9/125k: no low-data-rate optimisation


def test_sx1278_low_data_rate_optimisation_for_sf12():
    spi = FakeSpi(); c.SX1278(spi=spi).begin(sf=12)
    assert spi.regs[0x26] & 0x08


def test_sx1278_rejects_wrong_chip_and_band():
    with pytest.raises(RuntimeError):
        c.SX1278(spi=FakeSpi(version=0x00)).begin()
    with pytest.raises(ValueError, match="137-525"):
        c.SX1278(spi=FakeSpi()).begin(freq_hz=923_200_000)


def test_sx1278_send_and_receive():
    spi = FakeSpi(); r = c.SX1278(spi=spi); r.begin()
    payload = c.encode(c.Forward(1, 2, 9, 70000, 500, 1, 12))
    assert r.send(payload) is True
    assert spi.sent == [payload]
    assert spi.regs[0x01] == 0x85                          # back to RX after TX
    assert r.recv() is None
    spi.inject_rx(payload, rssi_raw=100)
    data, rssi = r.recv()
    assert data == payload and rssi == 100 - 164
    spi.inject_rx(payload, crc_error=True)
    assert r.recv() is None                                # CRC errors are dropped


def test_lora_link_filters_own_and_foreign_messages():
    spi = FakeSpi(); radio = c.SX1278(spi=spi); link = c.LoraLink(2, radio, jitter_s=0.0)
    link.start()
    link.send(c.State(2, 1, 0, 1000.0, 0.0))
    assert c.decode(spi.sent[-1]).agent_id == 2
    for m in (c.State(2, 1, 0, 1.0, 0.0),                  # own echo
              c.Forward(1, 3, 1, 1, 500, 1),               # addressed to someone else
              c.State(1, 1, 4, 1000.0, 0.0),               # valid
              c.Forward(1, 2, 2, 2, 500, 1)):              # valid
        spi.inject_rx(c.encode(m)); got = link.poll()
        if m.__class__ is c.State and m.agent_id == 1 or (isinstance(m, c.Forward) and m.dst == 2):
            assert got == [c.decode(c.encode(m))]
        else:
            assert got == []


# ------------------------------------------------------------------ SIM7000 against a scripted modem
def test_nbiot_start_sequence_and_publish():
    m = FakeModem()
    link = c.NbIotLink(2, ser=m, apn="internet", host="broker.example", mqtt_port=1883)
    link.start()
    cmds = m.commands
    assert cmds[0] == "AT" and 'AT+CGDCONT=1,"IP","internet"' in cmds
    assert 'AT+SMCONF="URL","broker.example","1883"' in cmds and "AT+SMCONN" in cmds
    assert 'AT+SMSUB="water/agents/2/forward",1' in cmds and 'AT+SMSUB="water/agents/+/state",1' in cmds
    link.send(c.State(2, 1, 3, 1500.0, 2.0))
    topic, payload = m.published[-1]
    assert topic == "water/agents/2/state" and c.from_json(payload).queue_len == 3
    link.send(c.Forward(2, 5, 1, 9, 500, 1))
    assert m.published[-1][0] == "water/agents/5/forward"


def test_nbiot_receives_urc():
    m = FakeModem(); link = c.NbIotLink(2, ser=m)
    fwd = c.Forward(1, 2, 4, 77, 500, 1, 3)
    m.push(f'\r\n+SMSUB: "water/agents/2/forward","{c.to_json(fwd)}"\r\n')
    m.push(f'+SMSUB: "water/agents/2/state","{c.to_json(c.State(2, 1, 0, 1.0, 0.0))}"\r\n')   # own echo -> ignored
    got = link.poll()
    assert got == [fwd]


def test_nbiot_error_and_timeout():
    with pytest.raises(RuntimeError):
        c.NbIotLink(1, ser=FakeModem(fail_on="AT+SMCONN")).start()
    with pytest.raises(TimeoutError):
        c.NbIotLink(1, ser=FakeModem(silent=True)).at("AT", timeout=0.05)
