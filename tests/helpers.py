"""Fakes shared by the tests: SPI register file for the SX1278, scripted AT modem for the SIM7000, fake TFLite interpreter."""
from __future__ import annotations

import numpy as np


class FakeSpi:
    """Minimal SX127x register model: register file, FIFO with auto-incrementing pointer, TX-done on TX mode."""

    def __init__(self, version: int = 0x12):
        self.regs = [0] * 256
        self.regs[0x42] = version
        self.fifo = bytearray(256)
        self.sent: list[bytes] = []

    def xfer2(self, data):
        reg, addr = data[0], data[0] & 0x7F
        write = bool(reg & 0x80)
        if addr == 0x00:                                   # FIFO burst access
            ptr = self.regs[0x0D]
            if write:
                for b in data[1:]:
                    self.fifo[ptr] = b; ptr += 1
                self.regs[0x0D] = ptr
                return [0] * len(data)
            out = [0]
            for _ in data[1:]:
                out.append(self.fifo[ptr]); ptr += 1
            self.regs[0x0D] = ptr
            return out
        if write:
            v = data[1] & 0xFF
            if addr == 0x12:                               # IRQ flags: write 1 to clear
                self.regs[0x12] &= ~v & 0xFF
            else:
                self.regs[addr] = v
            if addr == 0x01 and (v & 0x07) == 0x03:         # entered TX -> transmit FIFO[0:len], raise TxDone
                self.sent.append(bytes(self.fifo[:self.regs[0x22]]))
                self.regs[0x12] |= 0x08
            return [0, 0]
        return [0, self.regs[addr]]

    def inject_rx(self, payload: bytes, rssi_raw: int = 100, crc_error: bool = False):
        self.fifo[:len(payload)] = payload
        self.regs[0x13], self.regs[0x10], self.regs[0x1A] = len(payload), 0, rssi_raw
        self.regs[0x12] |= 0x40 | (0x20 if crc_error else 0)


class FakeModem:
    """Serial port that answers AT commands like a SIM7000 would (OK / '>' prompt for SMPUB)."""

    def __init__(self, fail_on: str | None = None, silent: bool = False):
        self.rx = bytearray()
        self.commands: list[str] = []
        self.published: list[tuple[str, str]] = []
        self._awaiting_payload = None
        self.fail_on, self.silent = fail_on, silent

    @property
    def in_waiting(self) -> int:
        return len(self.rx)

    def read(self, n: int = 1) -> bytes:
        out = bytes(self.rx[:n]); del self.rx[:n]
        return out

    def push(self, text: str) -> None:
        self.rx += text.encode()

    def write(self, data: bytes) -> int:
        if self.silent:
            return len(data)
        if self._awaiting_payload is not None:
            topic = self._awaiting_payload; self._awaiting_payload = None
            self.published.append((topic, data.decode()))
            self.push("\r\nOK\r\n")
            return len(data)
        cmd = data.decode().strip()
        self.commands.append(cmd)
        if self.fail_on and cmd.startswith(self.fail_on):
            self.push("\r\nERROR\r\n")
        elif cmd.startswith("AT+SMPUB"):
            self._awaiting_payload = cmd.split('"')[1]
            self.push("\r\n>")
        else:
            self.push("\r\nOK\r\n")
        return len(data)


class FakeInterpreter:
    """TFLite SSD stand-in: returns one fixed detection."""

    def __init__(self, box=(0.2, 0.2, 0.8, 0.8), cls=0, score=0.9, shape=(1, 300, 300, 3), dtype=np.uint8):
        self._in = [{"index": 0, "shape": np.array(shape), "dtype": dtype}]
        self._out = [{"index": i} for i in range(1, 5)]
        self._t = {1: np.array([[box, (0, 0, 0, 0)]], np.float32), 2: np.array([[cls, 1]], np.float32),
                   3: np.array([[score, 0.1]], np.float32), 4: np.array([2], np.float32)}
        self.last_input = None

    def allocate_tensors(self): pass
    def get_input_details(self): return self._in
    def get_output_details(self): return self._out
    def set_tensor(self, idx, x): self.last_input = x
    def invoke(self): pass
    def get_tensor(self, idx): return self._t[idx]
