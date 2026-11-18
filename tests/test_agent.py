import json

import numpy as np
import pytest

from agent.comms import Ack, Forward, MemoryBus, MemoryLink, State
from agent.config import load_config
from agent.hardware import SimHardware
from agent.main import Agent
from agent.perception import Detection
from agent.policy import HeuristicPolicy
from agent.spec import DISPENSE


class Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t
    def advance(self, s): self.t += s


class Det:
    def __init__(self, valid=True, vol=500): self.valid, self.vol = valid, vol
    def detect(self, frame): return Detection(self.valid, 0.95, (0.2, 0.2, 0.8, 0.8), self.vol if self.valid else None, "x")


class AlwaysDispense:
    def act(self, obs, deterministic=True, rng=None): return DISPENSE


def make_agent(tmp_path, aid, bus, clock, level=15000.0, det=None, policy=None, **cfg_over):
    cfg = load_config(); cfg.update(agent_id=aid, simulate_hardware=True, log_dir=str(tmp_path), **cfg_over)
    hw = SimHardware(level_ml=level)
    ag = Agent(cfg, hw, MemoryLink(aid, bus), None, det or Det(), policy=policy or HeuristicPolicy(), clock=clock)
    return ag, hw


def records(tmp_path, aid):
    p = tmp_path / f"agent-{aid}.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def test_serves_a_valid_container(tmp_path):
    clk = Clock(); a, hw = make_agent(tmp_path, 1, MemoryBus(), clk)
    hw.set_present(True)
    info = a.step()
    assert info["action"] == "dispense" and hw.level == pytest.approx(14500.0)
    r = records(tmp_path, 1)
    assert len(r) == 1 and r[0]["outcome"] == "served" and r[0]["volume_ml"] == 500 and r[0]["dispensed_ml"] == 500


def test_no_dispense_without_verified_container(tmp_path):
    clk = Clock()
    for policy in (HeuristicPolicy(), AlwaysDispense()):       # even a policy that insists must be overridden
        a, hw = make_agent(tmp_path, 1, MemoryBus(), clk, det=Det(valid=False), policy=policy)
        hw.set_present(True)
        info = a.step()
        assert info["action"] == "wait" and hw.level == 15000.0 and len(a.queue) == 1


def test_no_dispense_below_reserve(tmp_path):
    a, hw = make_agent(tmp_path, 1, MemoryBus(), Clock(), level=600.0, policy=AlwaysDispense())   # 600-500 < reserve 200
    hw.set_present(True)
    assert a.step()["action"] == "wait" and hw.level == 600.0


def test_user_leaving_aborts_dispense(tmp_path):
    a, hw = make_agent(tmp_path, 1, MemoryBus(), Clock())
    hw.dispense = lambda ml, keep_going: 0.0                    # pump stopped immediately: nobody under the spout
    hw.set_present(True); a.step()
    assert records(tmp_path, 1)[0]["outcome"] == "failed"


def test_expired_requests_are_logged_as_timeouts(tmp_path):
    clk = Clock(); a, hw = make_agent(tmp_path, 1, MemoryBus(), clk, det=Det(valid=False))
    hw.set_present(True); a.step()
    clk.advance(121); a.step()
    assert [r["outcome"] for r in records(tmp_path, 1)] == ["timeout"] and not a.queue


def _pair(tmp_path, bus, clk, a_level=100.0):
    a, ahw = make_agent(tmp_path, 1, bus, clk, level=a_level)
    b, bhw = make_agent(tmp_path, 2, bus, clk)
    b.step(); clk.advance(1)                                     # B announces its state
    return a, ahw, b, bhw


def test_forward_ack_and_service_at_neighbour(tmp_path):
    bus, clk = MemoryBus(), Clock()
    a, ahw, b, bhw = _pair(tmp_path, bus, clk)
    ahw.set_present(True)
    info = a.step()                                              # A's tank is nearly empty -> forwards to B
    assert info["action"] == "forward_request" and a.pending and not a.queue
    clk.advance(0.5); b.step()                                   # B queues the reservation and ACKs
    assert len(b.queue) == 1 and b.queue[0]["forwarded"] and not b.queue[0]["claimed"]
    clk.advance(0.5); a.step()
    assert not a.pending and [r["outcome"] for r in records(tmp_path, 1)] == ["forwarded"]
    bhw.set_present(True); clk.advance(8); b.step()              # the redirected user arrives at B
    r = records(tmp_path, 2)
    assert len(r) == 1 and r[0]["outcome"] == "served" and r[0]["origin"] == 1 and r[0]["hops"] == 1
    # latency is measured from the ORIGINAL request (waited_s travels with the Forward message), not from the arrival
    # at B. One-way radio transit time is not included because agent clocks are not synchronised.
    assert 8.0 <= r[0]["latency_s"] <= 9.0
    assert bhw.level == pytest.approx(14500.0)


def test_arriving_user_claims_reservation_instead_of_duplicating(tmp_path):
    bus, clk = MemoryBus(), Clock()
    a, ahw, b, bhw = _pair(tmp_path, bus, clk)
    ahw.set_present(True); a.step(); b.step()
    assert len(b.queue) == 1
    bhw.set_present(True); b.step()
    assert len(records(tmp_path, 2)) == 1 and not b.queue        # exactly one request, one dispense


def test_duplicate_forward_is_acked_but_queued_once(tmp_path):
    bus, clk = MemoryBus(), Clock()
    b, _ = make_agent(tmp_path, 2, bus, clk); src = MemoryLink(1, bus)
    f = Forward(1, 2, 5, 123, 500, 1, 3)
    src.send(f); src.send(f); b.step()
    acks = [m for m in src.poll() if isinstance(m, Ack)]
    assert len(b.queue) == 1 and len(acks) == 2


def test_lost_forward_is_retried_then_returned_to_local_queue(tmp_path):
    bus, clk = MemoryBus(), Clock()
    a, ahw, b, bhw = _pair(tmp_path, bus, clk)
    sent = []
    real = a.link.send; a.link.send = lambda m: (sent.append(m), real(m))
    bus.drop = 1.0                                               # radio link dies after the state exchange
    ahw.set_present(True); a.step()
    for _ in range(10):
        clk.advance(a.cfg["forward_ack_timeout_s"] + 0.1); a.step()
    forwards = [m for m in sent if isinstance(m, Forward)]
    assert len(forwards) == 1 + a.cfg["forward_retries"]         # initial + retries, then it gives up
    assert not a.pending and not b.queue
    assert len(a.queue) == 1 or records(tmp_path, 1)             # request kept locally (or finally timed out), never lost silently
    assert 2 not in a.nbr                                        # neighbour no longer trusted


def test_ack_for_unknown_request_is_ignored(tmp_path):
    bus, clk = MemoryBus(), Clock(); a, _ = make_agent(tmp_path, 1, bus, clk)
    MemoryLink(2, bus).send(Ack(2, 1, 1, 999)); a.step()
    assert records(tmp_path, 1) == []


def test_state_broadcast_period(tmp_path):
    bus, clk = MemoryBus(), Clock()
    a, _ = make_agent(tmp_path, 1, bus, clk); peer = MemoryLink(2, bus)
    a.step(); assert len([m for m in peer.poll() if isinstance(m, State)]) == 1
    clk.advance(5); a.step(); assert peer.poll() == []
    clk.advance(11); a.step(); assert len([m for m in peer.poll() if isinstance(m, State)]) == 1
