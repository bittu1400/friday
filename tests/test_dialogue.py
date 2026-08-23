import os
from pathlib import Path

from friday.dialogue import Dialogue


def test_add_and_render_round_trips():
    d = Dialogue()
    d.add("open brave", "Opening Brave.")
    d.add("thanks", "Anytime.")
    out = d.render()
    assert "open brave" in out and "Opening Brave." in out
    assert "thanks" in out and "Anytime." in out
    # oldest first
    assert out.index("open brave") < out.index("thanks")


def test_bound_trims_oldest():
    d = Dialogue(max_turns=3)
    for i in range(5):
        d.add(f"u{i}", f"f{i}")
    assert len(d) == 3
    out = d.render()
    assert "u0" not in out and "u1" not in out   # trimmed
    assert "u4" in out                            # newest kept


def test_empty_render_is_empty_string():
    assert Dialogue().render() == ""


def test_no_disk_writes(tmp_path, monkeypatch):
    # invariant #7: the buffer is RAM-only. Run a chdir into an empty tmp dir,
    # exercise the buffer heavily, and assert it created no files.
    monkeypatch.chdir(tmp_path)
    d = Dialogue()
    for i in range(50):
        d.add(f"user {i}", f"reply {i}")
    d.render()
    assert list(Path(tmp_path).iterdir()) == []
