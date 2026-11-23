"""Stand-in for `agent.comms.SX1278` in the SIL tests: the same begin/send/recv interface over localhost UDP.

It replaces the radio driver only (the driver itself is covered by the register-level tests in tests/test_comms.py).
It is not a propagation model: loss is independent per receiver and there are no collisions, no range limit and no airtime.
"""
from __future__ import annotations

import random
import socket


class UdpRadio:
    def __init__(self, node, ports: dict, loss: float = 0.0, seed: int = 0, **_ignored):
        self.node, self.ports, self.loss = node, dict(ports), loss
        self.rng = random.Random(seed)
        self.sock = None

    def begin(self, **_cfg) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", self.ports[self.node]))
        s.setblocking(False)
        self.sock = s

    def send(self, payload: bytes, timeout: float = 3.0) -> bool:
        for n, p in self.ports.items():
            if n != self.node and self.rng.random() >= self.loss:
                try:
                    self.sock.sendto(payload, ("127.0.0.1", p))
                except OSError:
                    pass
        return True

    def recv(self):
        try:
            data, _ = self.sock.recvfrom(512)
        except (BlockingIOError, OSError):
            return None
        return data, -90

    def close(self) -> None:
        if self.sock:
            self.sock.close()
