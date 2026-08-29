"""Blocking work must not run on the asyncio event loop (audit H6).

The daemon is a single loop (architecture.md §5). While it is blocked, nothing
is read from the PTT socket, no timer fires, and no wake callback is drained —
Friday is deaf for the duration. STT and TTS were correctly threaded from G6;
four later call sites were not, and each is hundreds of milliseconds to seconds.

These assert the work ran on a DIFFERENT thread than the loop, which is the
only observable that distinguishes `await to_thread(f)` from `f()`. Drop a
`to_thread` and the matching test fails.
"""

import asyncio
import threading

import pytest

from friday import daemon as daemon_mod
from friday.audio.stt import Transcript
from friday.daemon import Daemon
from friday.turn import TurnResult


class FakeTranscriber:
    def __init__(self, text="open my browser"):
        self._t = Transcript(text, over_limit=False)

    def run(self, pcm):
        return self._t


class FakeSpeaker:
    def __init__(self):
        self.said = []

    def say(self, text, on_play=None):
        self.said.append(text)
        return True

    def stop(self):
        pass


class FakeRecorder:
    def reset(self):
        pass

    def collect(self):
        return b""

    def open(self):
        return True

    def ensure_open(self):
        return True

    def close(self):
        pass


def _daemon(**kw):
    kw.setdefault("client", object())
    kw.setdefault("recorder", FakeRecorder())
    kw.setdefault("transcriber", FakeTranscriber())
    kw.setdefault("speaker", FakeSpeaker())
    return Daemon(**kw)


def _plan(monkeypatch, result):
    async def fake_run_turn(*a, **k):
        return result

    monkeypatch.setattr(daemon_mod, "run_turn", fake_run_turn)


class _ThreadProbe:
    """Records the thread it was called on."""

    def __init__(self, ret):
        self.thread: int | None = None
        self._ret = ret

    def __call__(self, *a, **k):
        self.thread = threading.get_ident()
        return self._ret


def _run_turn_on(d):
    async def go():
        loop_thread = threading.get_ident()
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task
        return loop_thread

    return asyncio.run(go())


def test_speaker_verification_runs_off_the_loop(monkeypatch):
    """ONNX embedding inference, hundreds of ms, once per turn."""
    _plan(monkeypatch, TurnResult("chat", {}, "Hi.", False))
    probe = _ThreadProbe((True, 0.95))

    class Verifier:
        def verify(self, pcm):
            return probe(pcm)

    d = _daemon(speaker_verifier=Verifier())
    loop_thread = _run_turn_on(d)

    assert probe.thread is not None, "verify was never called"
    assert probe.thread != loop_thread


def test_signoff_summary_runs_off_the_loop(monkeypatch):
    """A full synchronous LLM round-trip."""
    from friday.proactive import briefing

    probe = _ThreadProbe("Goodnight.")
    monkeypatch.setattr(briefing, "generate_signoff_summary", probe)

    d = _daemon(transcriber=FakeTranscriber(text="goodnight friday"))
    loop_thread = _run_turn_on(d)

    assert probe.thread is not None
    assert probe.thread != loop_thread


def test_prompt_digests_run_off_the_loop(monkeypatch, tmp_path):
    """Two SQLite reads per turn, one scanning 30 days of audit rows."""
    import friday.store as store_pkg
    from friday.store.audit import AuditLog
    from friday.store.db import Database

    probe = _ThreadProbe(("", ""))
    monkeypatch.setattr(store_pkg, "prompt_digests", probe)

    _plan(monkeypatch, TurnResult("chat", {}, "Hi.", False))
    d = _daemon(audit=AuditLog(Database(tmp_path / "memory.db")))
    loop_thread = _run_turn_on(d)

    assert probe.thread is not None
    assert probe.thread != loop_thread


def test_busy_rejection_notify_runs_off_the_loop(monkeypatch):
    """`notify-send` blocks up to 2 s, in the one path that fires WHILE a turn
    is already running and can burst (FR-5 rejection)."""
    probe = _ThreadProbe(True)
    monkeypatch.setattr(daemon_mod.notifier, "notify", probe)
    _plan(monkeypatch, TurnResult("none", {}, "(no action)", False))
    d = _daemon()

    async def go():
        loop_thread = threading.get_ident()
        await d.on_ptt("press")  # accepted
        await d.on_ptt("press")  # rejected -> notifies
        return loop_thread

    loop_thread = asyncio.run(go())
    assert d.rejected == 1
    assert probe.thread is not None, "the rejection was silent"
    assert probe.thread != loop_thread


def test_scheduler_notify_runs_off_the_loop(monkeypatch, tmp_path):
    """A burst of due reminders used to pay the blocking notify serially inside
    the poll loop, delaying every later one in the same tick."""
    import friday.proactive.notifier as notifier_mod
    from friday.proactive.dnd import DndManager
    from friday.proactive.scheduler import Scheduler
    from friday.store.db import Database
    from friday.store.reminders import ReminderStore

    probe = _ThreadProbe(True)
    monkeypatch.setattr(notifier_mod, "notify", probe)

    store = ReminderStore(Database(tmp_path / "memory.db"))
    store.create(0.01, "pasta")
    delivered: list[str] = []

    async def on_event(title, message):
        delivered.append(message)

    sched = Scheduler(
        store=store, dnd=DndManager(), is_idle=lambda: True, on_event=on_event,
    )

    async def go():
        loop_thread = threading.get_ident()
        await asyncio.sleep(0.05)  # let the 0.01 s timer come due
        await sched._poll_step()
        return loop_thread

    loop_thread = asyncio.run(go())
    assert delivered == ["pasta"]
    assert probe.thread is not None
    assert probe.thread != loop_thread
