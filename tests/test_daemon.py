"""Daemon orchestration: PTT flow, one-turn-in-flight (FR-5), empty-transcript
silence (FR-12), barge-in (FR-7), and the confirm-first voice handshake.

No audio, no model: the transcriber and speaker are fakes, and `run_turn` is
monkeypatched so these tests exercise the daemon's own logic, not the turn
pipeline (which has its own tests)."""

import asyncio
import threading

import pytest

from friday import daemon as daemon_mod
from friday import turn as turn_mod
from friday.audio.state import State
from friday.audio.stt import Transcript
from friday.daemon import Daemon
from friday.turn import TurnResult


class FakeTranscriber:
    def __init__(self, text="open my browser", over_limit=False):
        self._t = Transcript(text, over_limit=over_limit)

    def run(self, pcm):
        return self._t


class FakeSpeaker:
    def __init__(self, block=False):
        self.said = []
        self.stopped = 0
        self._block = block
        self._gate = threading.Event()

    def say(self, text, on_play=None):
        self.said.append(text)
        if on_play is not None:
            on_play()  # mirror the real Speaker: fire at audio start
        if self._block:
            self._gate.wait(timeout=2.0)
            return False  # cancelled
        return True

    def stop(self):
        self.stopped += 1
        self._gate.set()


class FakeRecorder:
    def __init__(self):
        self.resets = 0

    def reset(self):
        self.resets += 1

    def collect(self):
        return b""  # daemon passes it straight to the (fake) transcriber

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


def test_happy_path_press_release_speaks_outcome(monkeypatch):
    _plan(monkeypatch, TurnResult("open_app", {"app": "browser"}, "Opened Brave.", True))
    d = _daemon()

    async def go():
        await d.on_ptt("press")
        assert d.state.state is State.CAPTURING
        await d.on_ptt("release")
        await d._turn_task  # let the turn finish

    asyncio.run(go())
    assert d._speaker.said == ["Opened Brave."]
    assert d.state.state is State.IDLE


def test_five_rapid_presses_one_turn_four_rejections(monkeypatch):
    """FR-5: 5 presses while busy -> 1 accepted + 4 rejected, never queued."""
    _plan(monkeypatch, TurnResult("none", {}, "(no action)", False))
    d = _daemon()

    async def go():
        for _ in range(5):
            await d.on_ptt("press")

    asyncio.run(go())
    assert d.state.state is State.CAPTURING  # still the one capture
    assert d.rejected == 4


def test_empty_transcript_is_silent_and_idle(monkeypatch):
    _plan(monkeypatch, TurnResult("open_app", {}, "should not be spoken", True))
    d = _daemon(transcriber=FakeTranscriber(text=""))

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task

    asyncio.run(go())
    assert d._speaker.said == []  # FR-12: nothing spoken
    assert d.state.state is State.IDLE


def test_over_limit_transcript_is_refused(monkeypatch):
    """FR-13: an over-limit transcript acts like empty -> silent IDLE."""
    _plan(monkeypatch, TurnResult("open_app", {}, "nope", True))
    d = _daemon(transcriber=FakeTranscriber(text="", over_limit=True))

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task

    asyncio.run(go())
    assert d._speaker.said == []
    assert d.state.state is State.IDLE


def test_barge_in_cancels_playback_and_recaptures(monkeypatch):
    """FR-7: PTT press during SPEAKING stops playback and goes to CAPTURING."""
    _plan(monkeypatch, TurnResult("open_app", {}, "A long spoken line.", True))
    speaker = FakeSpeaker(block=True)  # say() blocks until stop()
    d = _daemon(speaker=speaker)

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        # wait until the turn is in SPEAKING (say() is blocking in a thread)
        for _ in range(200):
            if d.state.state is State.SPEAKING and speaker.said:
                break
            await asyncio.sleep(0.01)
        assert d.state.state is State.SPEAKING
        await d.on_ptt("press")  # barge-in
        assert d.state.state is State.CAPTURING
        assert speaker.stopped == 1
        await d._turn_task  # the cancelled turn unwinds cleanly

    asyncio.run(go())


def test_confirm_handshake_yes_writes(monkeypatch):
    """Spoken pref -> question spoken; next 'yes' -> confirm_preference."""
    from friday.store.prefs import PendingPreference

    pending = PendingPreference(key="name", value="Subham")
    _plan(monkeypatch, TurnResult(
        "remember_preference", {}, "Remember your name is Subham?", False, pending=pending))

    confirmed = {}

    async def fake_confirm(p, prefs, audit, *, request_id):
        confirmed["key"] = p.key
        return "Okay, I'll remember that."
    # Both UIs resolve a confirm through turn.resolve_pending (audit C1 fix),
    # so the preference write is patched where it is now looked up.
    monkeypatch.setattr(turn_mod, "confirm_preference", fake_confirm)

    d = _daemon()

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task
        assert d._pending is pending  # awaiting the yes/no
        # answer "yes"
        d._transcriber = FakeTranscriber(text="yes")
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task

    asyncio.run(go())
    assert confirmed["key"] == "name"
    assert "Okay, I'll remember that." in d._speaker.said
    assert d.state.state is State.IDLE


def test_confirm_timer_not_orphaned_by_answer_press(monkeypatch):
    """BUG-3 regression: the 30 s confirm window uses its OWN timer handle, so
    pressing the key to speak the answer (which arms the 15 s capture cap) does
    not orphan it, and resolving the confirm cancels it — no stray timer is
    left to reset the FSM mid-future-turn."""
    from friday.store.prefs import PendingPreference

    pending = PendingPreference(key="name", value="Subham")
    _plan(monkeypatch, TurnResult(
        "remember_preference", {}, "Remember your name is Subham?", False, pending=pending))

    async def fake_confirm(p, prefs, audit, *, request_id):
        return "Okay."
    # Both UIs resolve a confirm through turn.resolve_pending (audit C1 fix),
    # so the preference write is patched where it is now looked up.
    monkeypatch.setattr(turn_mod, "confirm_preference", fake_confirm)

    d = _daemon()

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task
        # Confirm window open on its own handle, separate from the cap timer.
        confirm_timer = d._confirm_timer
        assert confirm_timer is not None
        assert confirm_timer is not d._cap_timer

        # Press to answer: arms the capture cap. The confirm timer must survive
        # unchanged (old bug overwrote the shared handle here).
        d._transcriber = FakeTranscriber(text="yes")
        await d.on_ptt("press")
        assert d._confirm_timer is confirm_timer  # not clobbered
        assert d._cap_timer is not None and d._cap_timer is not confirm_timer

        await d.on_ptt("release")
        await d._turn_task
        # Resolved: the confirm timer is cancelled, not left to fire later.
        assert d._confirm_timer is None
        assert confirm_timer.cancelled()
        assert d.state.state is State.IDLE

    asyncio.run(go())


def test_toggle_start_then_stop_speaks_outcome(monkeypatch):
    """ADR-044: tap to start (CAPTURING), tap again to stop -> transcribe+speak.
    Debounce off here so both taps register (they'd otherwise be same-instant)."""
    monkeypatch.setattr(daemon_mod.config, "PTT_DEBOUNCE_S", 0.0)
    _plan(monkeypatch, TurnResult("open_app", {"app": "browser"}, "Opened Brave.", True))
    d = _daemon()

    async def go():
        await d.on_ptt("toggle")
        assert d.state.state is State.CAPTURING
        await d.on_ptt("toggle")
        await d._turn_task

    asyncio.run(go())
    assert d._speaker.said == ["Opened Brave."]
    assert d.state.state is State.IDLE


def test_toggle_debounce_collapses_burst(monkeypatch):
    """ADR-044: the tap-only trigger machine-guns press events while held; a
    burst inside the debounce window is one flip, not start-then-stop."""
    _plan(monkeypatch, TurnResult("none", {}, "(no action)", False))
    d = _daemon()  # default 0.4 s debounce

    async def go():
        await d.on_ptt("toggle")  # first tap: start
        assert d.state.state is State.CAPTURING
        for _ in range(10):  # machine-gun burst, all within the window
            await d.on_ptt("toggle")
        assert d.state.state is State.CAPTURING  # still capturing, not stopped
        assert d._turn_task is None

    asyncio.run(go())


def test_toggle_barge_in_during_speaking(monkeypatch):
    """A toggle mid-playback is barge-in: stop speaking, go to CAPTURING (FR-7)."""
    monkeypatch.setattr(daemon_mod.config, "PTT_DEBOUNCE_S", 0.0)
    _plan(monkeypatch, TurnResult("open_app", {}, "A long spoken line.", True))
    speaker = FakeSpeaker(block=True)
    d = _daemon(speaker=speaker)

    async def go():
        await d.on_ptt("toggle")
        await d.on_ptt("toggle")
        for _ in range(200):
            if d.state.state is State.SPEAKING and speaker.said:
                break
            await asyncio.sleep(0.01)
        assert d.state.state is State.SPEAKING
        await d.on_ptt("toggle")  # barge-in
        assert d.state.state is State.CAPTURING
        assert speaker.stopped == 1
        await d._turn_task

    asyncio.run(go())


def test_no_stt_mode_returns_to_idle_silently(monkeypatch):
    """H4 (audit 2026-08-26): `--no-voice` / no-STT is a SUPPORTED degraded mode.

    `_transcribe` used to perform TRANSCRIBING -> IDLE itself and `_run_turn`
    did it again at :269, so `_require(TRANSCRIBING)` raised IllegalTransition
    on EVERY capture and Friday spoke "Something went wrong." for what FR-12
    mandates be a silent return to IDLE. No fixture drove `transcriber=None`
    end to end, so 328 green tests never saw it.
    """
    _plan(monkeypatch, TurnResult("open_app", {}, "must not be spoken", True))
    d = _daemon(transcriber=None)

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task

    asyncio.run(go())
    assert d._speaker.said == []  # FR-12: silent, and NOT the error line
    assert d.state.state is State.IDLE


def test_release_without_capture_is_ignored():
    d = _daemon()

    async def go():
        await d.on_ptt("release")  # no press first

    asyncio.run(go())
    assert d.state.state is State.IDLE
    assert d._turn_task is None


def test_chat_turn_appends_to_dialogue(monkeypatch):
    _plan(monkeypatch, TurnResult("chat", {}, "Hello there!", False))
    d = _daemon()

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task

    asyncio.run(go())
    assert len(d._dialogue) == 1
    assert "Hello there!" in d._dialogue.render()


def test_daemon_close_distills_session_summary(tmp_path, monkeypatch):
    from friday.store.db import Database
    from friday.store.audit import AuditLog

    db = Database(tmp_path / "memory.db")
    audit = AuditLog(db)

    class _MockClient:
        def complete(self, *, system, user, grammar="", **kw):
            return "User chatted with Friday and asked for help."

    d = _daemon(client=_MockClient(), audit=audit)
    d._dialogue.add("hi", "Hello!")
    d._dialogue.add("what can you do?", "I can help you with tasks.")

    asyncio.run(d.close())

    rows = db.query("SELECT * FROM session_summaries")
    assert len(rows) == 1
    assert rows[0]["summary"] == "User chatted with Friday and asked for help."
    assert rows[0]["session_id"] == d._session_id


def test_on_wake_begins_capture_when_idle(monkeypatch):
    _plan(monkeypatch, TurnResult("none", {}, "(no action)", False))
    d = _daemon()

    async def go():
        assert d.state.is_idle
        await d.on_wake()
        assert d.state.state is State.CAPTURING

    asyncio.run(go())


def test_on_wake_rejected_when_busy(monkeypatch):
    d = _daemon()

    async def go():
        d.state.begin_capture()  # already CAPTURING
        before = d.rejected
        await d.on_wake()
        assert d.rejected == before + 1  # FR-5: not queued, rejected

    asyncio.run(go())


def test_on_speech_end_runs_the_turn(monkeypatch):
    _plan(monkeypatch, TurnResult("open_app", {"app": "browser"}, "Opened Brave.", True))
    d = _daemon()

    async def go():
        d.state.begin_capture()  # wake already began the capture
        await d.on_speech_end()  # VAD end-of-utterance stands in for release
        await d._turn_task
        assert d._speaker.said == ["Opened Brave."]
        assert d.state.state is State.IDLE

    asyncio.run(go())


def test_on_barge_from_speaking_starts_capture(monkeypatch):
    d = _daemon()

    async def go():
        d.state._state = State.SPEAKING  # arrange: mid-playback
        await d.on_barge()
        assert d.state.state is State.CAPTURING
        assert d._speaker.stopped == 1  # playback was cut

    asyncio.run(go())


def test_dnd_hush_phrase_enters_dnd(monkeypatch):
    d = _daemon(transcriber=FakeTranscriber(text="let's talk later"))

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task
        assert d._dnd.is_dnd
        assert any("Quiet mode enabled" in s for s in d._speaker.said)

    asyncio.run(go())


def test_dnd_resume_phrase_exits_dnd(monkeypatch):
    d = _daemon(transcriber=FakeTranscriber(text="resume"))
    d._dnd.set_dnd()

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task
        assert not d._dnd.is_dnd
        assert any("Quiet mode disabled" in s for s in d._speaker.said)

    asyncio.run(go())


def test_signoff_phrase_speaks_summary(monkeypatch):
    d = _daemon(transcriber=FakeTranscriber(text="goodnight friday"))
    d._dialogue.add("open brave", "Opened Brave.")

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task
        assert any("Goodnight" in s for s in d._speaker.said)

    asyncio.run(go())


class MockSpeakerVerifier:
    def __init__(self, allowed: bool):
        self.allowed = allowed

    def verify(self, pcm):
        return self.allowed, (0.95 if self.allowed else 0.2)


def test_speaker_verification_blocks_impostor(monkeypatch):
    _plan(monkeypatch, TurnResult("open_app", {"app": "browser"}, "Opened Brave.", True))
    verifier = MockSpeakerVerifier(allowed=False)
    d = _daemon(transcriber=FakeTranscriber(text="open my browser"), speaker_verifier=verifier)

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task
        # Impostor blocked: nothing spoken, state back to IDLE
        assert d._speaker.said == []
        assert d.state.state is State.IDLE

    asyncio.run(go())


def test_speaker_verification_allows_enrolled_user(monkeypatch):
    _plan(monkeypatch, TurnResult("open_app", {"app": "browser"}, "Opened Brave.", True))
    verifier = MockSpeakerVerifier(allowed=True)
    d = _daemon(transcriber=FakeTranscriber(text="open my browser"), speaker_verifier=verifier)

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task
        assert d._speaker.said == ["Opened Brave."]
        assert d.state.state is State.IDLE

    asyncio.run(go())


def test_clipboard_set_confirm_yes_actually_writes(monkeypatch):
    """clipboard_set has no registry entry; the confirm path must run wl-copy
    and speak the REAL outcome, never a blanket 'Action completed.' (ADR-009)."""
    from friday.turn import PendingAction
    import friday.tools.clipboard as clip

    calls = []
    monkeypatch.setattr(clip, "set_clipboard", lambda text, **kw: calls.append(text) or True)

    pending = PendingAction("clipboard_set", {"text": "hello world"}, "overwrite clipboard")
    _plan(monkeypatch, TurnResult(
        "clipboard_set", {"text": "hello world"},
        "Are you sure you want to overwrite your clipboard?", False, pending=pending))

    d = _daemon()

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task
        assert d._pending is pending
        d._transcriber = FakeTranscriber(text="yes")
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task

    asyncio.run(go())
    assert calls == ["hello world"]  # wl-copy really ran with the text
    assert any("Copied to your clipboard." in s for s in d._speaker.said)
    assert d.state.state is State.IDLE


def test_clipboard_set_confirm_no_does_not_write(monkeypatch):
    from friday.turn import PendingAction
    import friday.tools.clipboard as clip

    calls = []
    monkeypatch.setattr(clip, "set_clipboard", lambda text, **kw: calls.append(text) or True)

    pending = PendingAction("clipboard_set", {"text": "secret"}, "overwrite clipboard")
    _plan(monkeypatch, TurnResult(
        "clipboard_set", {"text": "secret"}, "Are you sure?", False, pending=pending))

    d = _daemon()

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task
        d._transcriber = FakeTranscriber(text="no")
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task

    asyncio.run(go())
    assert calls == []  # nothing copied when declined
    assert any("cancelled" in s.lower() for s in d._speaker.said)


def test_planner_dictation_mode_toggles_manager(monkeypatch):
    """A planner-routed dictation_mode (phrasing the regex misses) must flip the
    DictationManager, not just speak — otherwise state and speech disagree."""
    _plan(monkeypatch, TurnResult(
        "dictation_mode", {"action": "start"}, "Dictation mode enabled.", False))
    # A transcript the dictation regex does NOT match, forcing the planner path.
    d = _daemon(transcriber=FakeTranscriber(text="dictation on"))

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task

    asyncio.run(go())
    assert d._dictation.is_dictating  # actually activated
    assert any("Dictation mode enabled." in s for s in d._speaker.said)






def test_rejected_trigger_tells_the_user(monkeypatch):
    """FR-5 rejects a busy trigger; it must not do so silently.

    With tap-toggle PTT (ADR-044) a dropped press desyncs the user from the
    state machine: the tap meant to START is swallowed, so their next tap —
    meant to STOP — starts a capture of an empty room. That produced the 11-15 s
    all-silence captures seen live on 2026-08-25.
    """
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        daemon_mod.notifier, "notify",
        lambda title, message, **k: sent.append((title, message)) or True,
    )
    _plan(monkeypatch, TurnResult("none", {}, "(no action)", False))
    d = _daemon()

    async def go():
        await d.on_ptt("press")   # accepted: starts the capture
        await d.on_ptt("press")   # rejected: busy
        await d.on_wake()         # rejected: busy

    asyncio.run(go())
    assert d.rejected == 2
    assert len(sent) == 2, "every rejected trigger gets user-visible feedback"
    assert all("busy" in title.lower() for title, _ in sent)


def test_accepted_trigger_does_not_notify(monkeypatch):
    """No toast when the trigger actually worked — feedback only on rejection."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        daemon_mod.notifier, "notify",
        lambda title, message, **k: sent.append((title, message)) or True,
    )
    _plan(monkeypatch, TurnResult("none", {}, "(no action)", False))
    d = _daemon()

    asyncio.run(d.on_ptt("press"))
    assert sent == []


class FakeWakeListener:
    """Records end-of-speech arming; that is all these tests need from it."""

    def __init__(self):
        self.armed = 0

    def arm_end_of_speech(self):
        self.armed += 1

    def start(self):
        return True

    def stop(self):
        pass


def test_barge_in_capture_arms_vad_end_of_speech():
    """ADR-062: a hands-free capture has no key release, so VAD must be able to
    end it. Only the wake path armed itself, so a barge-in capture could not end
    before the 15 s FR-4 cap however briefly the user spoke."""
    wl = FakeWakeListener()
    d = _daemon(wake_listener=wl)

    async def go():
        d.state._state = State.SPEAKING
        await d.on_barge()
        assert d.state.state is State.CAPTURING
        assert wl.armed == 1, "barge-in capture was never armed for VAD end-of-speech"

    asyncio.run(go())


def test_ptt_capture_does_not_arm_vad_end_of_speech():
    """ADR-044: a tap-toggle capture is ended by the user's second tap. VAD must
    NOT cut it short, or the second tap would open a fresh capture instead."""
    wl = FakeWakeListener()
    d = _daemon(wake_listener=wl)

    async def go():
        await d.on_ptt("press")
        assert d.state.state is State.CAPTURING
        assert wl.armed == 0

    asyncio.run(go())


def test_history_resolved_action_dispatches_only_after_yes(monkeypatch):
    """ADR-065 end to end: an action that only history could supply is spoken
    as a question, and runs on 'yes' — not before."""
    from friday.turn import PendingAction

    d = _daemon(transcriber=FakeTranscriber(text="open it"))
    _plan(monkeypatch, TurnResult(
        "open_app", {"app": "browser"}, "Did you want me to open Brave?", False,
        pending=PendingAction("open_app", {"app": "browser"}, "Brave"),
    ))
    ran = []

    async def fake_execute(spec, params, request_id, dry_run=False):
        ran.append(params)
        from friday.errors import Outcome
        from friday.tools.executor import ToolResult
        return ToolResult(Outcome.OK, "Brave")

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await asyncio.sleep(0.05)
        assert d._pending is not None, "the action must be held for confirmation"
        assert ran == [], "nothing may run before the user says yes"

        from friday.tools import executor as ex
        monkeypatch.setattr(ex, "execute", fake_execute)

        # anything but yes cancels, and nothing runs
        d._transcriber = FakeTranscriber(text="no")
        await d.on_ptt("press")
        await d.on_ptt("release")
        await asyncio.sleep(0.05)
        assert ran == [], "a declined confirm must not dispatch"

        # ask again, then say yes
        _plan(monkeypatch, TurnResult(
            "open_app", {"app": "browser"}, "Did you want me to open Brave?", False,
            pending=PendingAction("open_app", {"app": "browser"}, "Brave"),
        ))
        d._transcriber = FakeTranscriber(text="open it")
        await d.on_ptt("press")
        await d.on_ptt("release")
        await asyncio.sleep(0.05)
        d._transcriber = FakeTranscriber(text="yes")
        await d.on_ptt("press")
        await d.on_ptt("release")
        await asyncio.sleep(0.05)
        assert ran == [{"app": "browser"}], "yes must dispatch the held action"

    asyncio.run(go())
