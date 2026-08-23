"""Ring-buffer capture logic (FR-4 cap, FR-6 gate). No audio hardware —
frames are fed to `_write` directly."""

import numpy as np

from friday.audio.capture import Recorder


def _frames(n: float, sr: int = 16000, val: float = 0.5) -> np.ndarray:
    return np.full(int(n * sr), val, dtype=np.float32)


def test_gate_closed_writes_nothing():
    """FR-6: mic closed outside CAPTURING -> nothing captured."""
    r = Recorder(gate=lambda: False)
    r._write(_frames(1.0))
    assert r.seconds == 0.0
    assert r.collect().size == 0


def test_gate_open_captures():
    r = Recorder(gate=lambda: True)
    r._write(_frames(2.0))
    assert r.seconds == 2.0
    assert r.collect().size == 32000


def test_hard_cap_at_15s_drops_overflow():
    """FR-4: a held key past 15 s yields a 15 s clip, not more."""
    r = Recorder(gate=lambda: True, max_seconds=15)
    for _ in range(20):
        r._write(_frames(1.0))  # 20 s fed
    assert r.seconds == 15.0
    assert r.collect().size == 15 * 16000


def test_gate_can_toggle_mid_capture():
    open_flag = {"v": True}
    r = Recorder(gate=lambda: open_flag["v"])
    r._write(_frames(1.0))
    open_flag["v"] = False
    r._write(_frames(1.0))  # dropped
    open_flag["v"] = True
    r._write(_frames(0.5))
    assert r.seconds == 1.5


def test_reset_clears_for_next_turn():
    r = Recorder(gate=lambda: True)
    r._write(_frames(3.0))
    r.reset()
    assert r.seconds == 0.0
    r._write(_frames(1.0))
    assert r.seconds == 1.0


def test_collect_returns_a_copy():
    r = Recorder(gate=lambda: True)
    r._write(_frames(1.0, val=0.5))
    out = r.collect()
    r.reset()
    r._write(_frames(1.0, val=0.9))
    assert out[0] == np.float32(0.5)  # earlier copy untouched
