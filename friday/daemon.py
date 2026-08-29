"""The voice-in daemon (G6): PTT -> capture -> STT -> turn -> speak, with
barge-in. One turn in flight, enforced by the FSM (FR-5), not a lock.

Single asyncio loop (architecture.md §5). CPU-bound work (whisper synth via
faster-whisper, kokoro TTS) runs in worker threads via `asyncio.to_thread`;
the audio callback (a PortAudio thread) only fills the ring (capture.py). The
PTT socket (ptt.py) feeds `on_ptt` from the Hyprland bind.

Execute-first is preserved (ADR-009): the turn runs `run_turn(speaker=None)`,
which plans, validates, and executes *before* returning; the daemon then
enters SPEAKING and voices the outcome as a cancellable job so a PTT press
mid-sentence is barge-in (FR-7): stop playback, drop the turn, start
capturing.

Confirm-first preferences (ADR-037) become a voice handshake here: the
pending preference is spoken as a question and the *next* utterance is read
as the yes/no answer (30 s window, diagram 01 CONFIRMING). Anything not an
affirmation cancels the write — fail safe.
"""

import asyncio
import logging
import time
import uuid

from . import config

from .audio import ptt
from .audio.capture import Recorder
from .audio.state import State, TurnState
from .audio.stt import Transcriber
from .dialogue import Dialogue
from .llm.client import LlamaClient
from .proactive import notifier
from .store.audit import AuditLog
from .store.prefs import PendingPreference, PrefStore
from .tools.search import SearchClient
from .turn import PendingAction, resolve_pending, run_turn

log = logging.getLogger("friday.daemon")

# Per-stage timeouts (diagram 01). Latency targets live in diagram 05; these
# are the hard aborts, deliberately larger — a slow turn should finish late,
# not fail.
_TRANSCRIBE_TIMEOUT = 5.0
# was 12.0; a web_search turn adds SearXNG (≤8 s, SEARCH_TIMEOUT_S) + grounding
# (~1-2 s) on top of planning. Safe: the search stage has its own 8 s cap
# (FR-64), so the turn cannot actually hang to 20 s.
_PLANNING_TIMEOUT = 20.0
_CONFIRM_WINDOW = 30.0
# A proactive alert waits this long for an in-flight turn to finish before it
# gives up speaking (the desktop notification fired regardless).
_PROACTIVE_WAIT_S = 30.0


class Daemon:
    def __init__(
        self,
        *,
        client: LlamaClient,
        recorder: Recorder,
        transcriber: Transcriber | None,
        speaker: object | None,
        prefs: PrefStore | None = None,
        audit: AuditLog | None = None,
        dry_run: bool = False,
        connected: bool = True,
        wake_listener: object | None = None,
        dnd: object | None = None,
        scheduler: object | None = None,
        dictation: object | None = None,
        speaker_verifier: object | None = None,
    ) -> None:
        self.state = TurnState()
        self._client = client
        self._recorder = recorder
        self._transcriber = transcriber
        self._speaker = speaker
        self._prefs = prefs
        self._audit = audit
        self._dry_run = dry_run
        self._connected = connected
        self._wake_listener = wake_listener

        from .proactive.dnd import DndManager
        self._dnd = dnd if dnd is not None else DndManager()
        self._scheduler = scheduler

        from .audio.dictation import DictationManager
        self._dictation = dictation if dictation is not None else DictationManager()

        self._speaker_verifier = speaker_verifier
        if self._speaker_verifier is None and config.SPEAKER_VERIFY_ENABLED:
            from .audio.speaker import SpeakerVerifier
            self._speaker_verifier = SpeakerVerifier()
            # Verify fails OPEN with no enrolled voiceprint (a mic-only check
            # cannot reject an unknown speaker). Say so loudly at startup so an
            # operator who flipped the flag is not lulled into thinking turns
            # are being gated when they are not. Enroll with `just enroll`.
            if getattr(self._speaker_verifier, "_voiceprint", None) is None:
                log.warning(
                    "speaker verification ENABLED but no voiceprint enrolled at %s; "
                    "all turns pass unchecked (fail-open). Run `just enroll-voice`.",
                    config.VOICEPRINT_FILE,
                )

        db = self._audit._db if self._audit else (self._prefs._db if self._prefs else None)
        if self._scheduler is None and db is not None:
            from .store.reminders import ReminderStore
            from .proactive.scheduler import Scheduler
            self._scheduler = Scheduler(
                store=ReminderStore(db),
                dnd=self._dnd,
                is_idle=lambda: self.state.is_idle,
                on_event=self.on_proactive_event,
            )

        self._search = SearchClient(
            base_url=config.SEARXNG_URL, timeout_s=config.SEARCH_TIMEOUT_S
        )
        self._turn_task: asyncio.Task | None = None
        self._speak_task: asyncio.Task | None = None
        # The speak task `_cancel_speak` most recently cut, so `_speak` can tell
        # a barge-in apart from its own turn task being cancelled (ADR-069).
        self._barged_speak_task: asyncio.Task | None = None
        self._sched_task: asyncio.Task | None = None
        self._pending: PendingPreference | PendingAction | None = None  # awaiting voice confirm
        self._cap_timer: asyncio.TimerHandle | None = None
        self._confirm_timer: asyncio.TimerHandle | None = None
        self._session_id = uuid.uuid4().hex
        self._dialogue = Dialogue()  # in-session context, RAM-only (invariant #7)
        self._last_toggle = 0.0  # debounce clock for the tap-only trigger (ADR-044)
        self._capture_end = 0.0  # monotonic mark at end of speech, for TTFA (OQ-09)
        self._seq = 0
        self.rejected = 0  # FR-5 counter (observable in tests)

    # --- Hands-free Wake & Barge events (G10) -----------------------------

    def _reject_busy(self, source: str) -> None:
        """One turn in flight (FR-5): the trigger is rejected, never queued.

        FR-5 says reject; it does not say do it silently. With tap-toggle PTT
        (ADR-044) a silent rejection desyncs the user from the state machine —
        they tap to START, the tap is dropped, and their next tap (meant to
        STOP) starts a capture of an empty room instead. That is exactly what
        the 2026-08-25 14:28 logs show: two dropped presses, then 11-15 s
        captures that STT reported as 100% silence. So say so.
        """
        self.rejected += 1
        log.info("E_BUSY: %s ignored in %s", source, self.state.state.value)
        # Module-qualified so tests can stub notifier.notify (a real notify-send
        # in the suite is how the phantom "pasta" toasts happened).
        notifier.notify(
            "Friday is busy",
            "Still finishing the last request — that one didn't register.",
            urgency="low",
        )

    async def on_wake(self) -> None:
        """Wake word detected from idle: begin capturing."""
        if self.state.begin_capture():
            self._start_capture("wake")
        else:
            self._reject_busy("wake")

    async def on_speech_end(self) -> None:
        """VAD detected trailing silence during capture: finish capture."""
        if self.state.state is State.CAPTURING:
            self._finish_capture()

    async def on_barge(self) -> None:
        """Voice activity detected during playback: barge-in."""
        if self.state.state is State.SPEAKING:
            if self.state.barge_in():
                self._cancel_speak()
                self._start_capture("barge")

    # --- PTT events (from the socket) -------------------------------------

    async def on_ptt(self, cmd: str) -> None:
        if cmd == "press":
            await self._on_press()
        elif cmd == "release":
            await self._on_release()
        elif cmd == "toggle":
            await self._on_toggle()
        elif cmd == "cancel":
            await self._abort()

    async def _on_toggle(self) -> None:
        # One bind on a tap-only key (ADR-044): flip capture on each tap. The
        # key machine-guns press events while held and can double-fire one tap,
        # so collapse anything inside the debounce window into a single flip.
        # Trailing debounce: bump the clock on EVERY event so a sustained burst
        # never advances past one action, however long the key is held.
        loop = asyncio.get_running_loop()
        now = loop.time()
        prev, self._last_toggle = self._last_toggle, now
        if now - prev < config.PTT_DEBOUNCE_S:
            return
        if self.state.state is State.CAPTURING:
            await self._on_release()  # second tap: stop + transcribe
        else:
            await self._on_press()  # first tap: start (or barge-in while SPEAKING)

    async def _on_press(self) -> None:
        # Barge-in: a press while speaking cancels playback and starts a new
        # capture (FR-7) — the user is already holding the key to talk.
        if self.state.state is State.SPEAKING:
            if self.state.barge_in():
                self._cancel_speak()
                self._start_capture("ptt-barge")
            return
        if self.state.begin_capture():
            self._start_capture("ptt")
        else:
            self._reject_busy("press")  # FR-5: busy, rejected not queued

    def _start_capture(self, source: str = "unknown") -> None:
        # Name the trigger. Three sources can open a capture (wake, barge-in,
        # PTT) and the logs could not tell them apart, which is why the OQ-29
        # loop took a whole session to pin down. No transcript content here —
        # invariant #7.
        log.info("capture start source=%s", source)
        # Hands-free captures have no key release to end them (ADR-062). The
        # listener arms itself on wake; barge-in was never armed, so it could
        # only end at the 15 s cap. PTT stays unarmed on purpose (ADR-044:
        # the second tap ends it).
        if source in ("barge", "ptt-barge"):
            # A barge-in is the user starting something NEW over whatever
            # Friday is saying. If a confirm was somehow still armed, the next
            # utterance is a command, never the yes/no answer to a question
            # that got talked over (ADR-069/H3). Ordering makes this hard to
            # reach today — the window only opens after the question finishes —
            # but "currently unreachable" has never been a control here.
            if self._pending is not None:
                self._pending = None
                self._disarm_confirm()
            if self._wake_listener is not None:
                self._wake_listener.arm_end_of_speech()
        if hasattr(self._recorder, "ensure_open"):
            self._recorder.ensure_open()
        self._recorder.reset()
        self._arm_capture_cap()

    def _finish_capture(self) -> None:
        if self.state.state is not State.CAPTURING:
            return
        self._disarm_capture_cap()
        self.state.end_capture()
        self._capture_end = time.monotonic()  # end of speech -> TTFA clock start
        pcm = self._recorder.collect()
        self._turn_task = asyncio.create_task(self._run_turn(pcm))

    async def _on_release(self) -> None:
        self._finish_capture()


    # --- 15 s hard cap (FR-4) ---------------------------------------------

    def _arm_capture_cap(self) -> None:
        loop = asyncio.get_running_loop()
        self._cap_timer = loop.call_later(
            config.MAX_CAPTURE_S, lambda: asyncio.ensure_future(self._on_release())
        )

    def _disarm_capture_cap(self) -> None:
        if self._cap_timer is not None:
            self._cap_timer.cancel()
            self._cap_timer = None

    # --- the turn ---------------------------------------------------------

    async def _run_turn(self, pcm) -> None:  # noqa: ANN001 - numpy array
        self._seq += 1
        rid = f"v{self._seq}"
        try:
            # TRANSCRIBING
            text = await self._transcribe(pcm)
            if text is None:  # timeout already handled
                return
            self.state.got_transcript(nonempty=bool(text))
            if config.DEBUG:
                # no_disk: the transcript may reach the console, never the log
                # file (invariant #7 — the redactor rewrites paths, not bodies).
                log.info("[debug] %s heard=%r", rid, text, extra={"no_disk": True})
            if not text:  # FR-12 empty / FR-13 over-limit -> IDLE, silent
                return

            if self._speaker_verifier is not None:
                matched, score = self._speaker_verifier.verify(pcm)
                if not matched:
                    log.info("Impostor detected (similarity %.3f < threshold); turn dropped", score)
                    self.state.reset()
                    return

            # If we were waiting on a spoken yes/no, this utterance is it.
            if self._pending is not None:
                await self._resolve_confirm(text, rid)
                return

            from .audio.dictation import is_start_dictation, is_stop_dictation
            from .proactive.briefing import is_signoff_phrase, generate_signoff_summary
            from .proactive.dnd import is_hush_phrase, is_resume_phrase

            if is_start_dictation(text):
                self._dictation.start()
                self.state.got_plan(will_speak=True)
                await self._speak("Dictation mode enabled.")
                return

            if is_stop_dictation(text):
                self._dictation.stop()
                self.state.got_plan(will_speak=True)
                await self._speak("Dictation mode disabled.")
                return

            if self._dictation.is_dictating:
                # Verbatim typing directly into focused window; bypasses planner
                self._dictation.handle_transcript(text)
                self.state.reset()
                return

            # Conversational DND: user speech clears DND; explicit resume acknowledged
            if self._dnd.is_dnd:
                if is_resume_phrase(text):
                    self._dnd.clear_dnd()
                    self.state.got_plan(will_speak=True)
                    await self._speak("Quiet mode disabled. How can I help?")
                    return
                self._dnd.clear_dnd()

            # Conversational DND hush phrases
            if is_hush_phrase(text):
                self._dnd.set_dnd()
                self.state.got_plan(will_speak=True)
                await self._speak("Quiet mode enabled. Let me know when you need me.")
                return

            # Voice sign-off close summary ("goodnight", "bye")
            if is_signoff_phrase(text):
                spoken = generate_signoff_summary(self._dialogue.render(), self._client)
                self.state.got_plan(will_speak=True)
                if await self._speak(spoken):  # ADR-069: heard, or not history
                    self._dialogue.add(text, spoken)
                return

            # PLANNING + EXECUTING (execute-first inside run_turn; no speech).
            db = self._audit._db if self._audit else (self._prefs._db if self._prefs else None)
            habits_digest = ""
            summaries_digest = ""
            if db is not None:
                from .store.habits import mine_habits, render_habits_digest
                from .store.summarizer import get_recent_session_summaries, render_summaries_digest
                habits = mine_habits(db)
                habits_digest = render_habits_digest(habits)
                summaries = get_recent_session_summaries(db, limit=2)
                summaries_digest = render_summaries_digest(summaries)

            result = await asyncio.wait_for(
                run_turn(
                    text, self._client, request_id=rid, dry_run=self._dry_run,
                    prefs=self._prefs, audit=self._audit, speaker=None,
                    search_client=self._search, connected=self._connected,
                    history=self._dialogue.render(),
                    habits_digest=habits_digest,
                    summaries_digest=summaries_digest,
                ),
                timeout=_PLANNING_TIMEOUT,
            )

            if result.plan_name == "set_dnd":
                self._dnd.set_dnd()
            elif result.plan_name == "resume_dnd":
                self._dnd.clear_dnd()
            elif result.plan_name == "dictation_mode":
                # The regex pre-intercept above catches most phrasings; this is
                # the fallback for a planner-routed toggle ("dictation on"), so
                # the manager state actually matches what we speak.
                if result.params.get("action", "start").lower() == "stop":
                    self._dictation.stop()
                else:
                    self._dictation.start()




            if result.pending is not None:  # confirm-first (ADR-037)
                self.state.got_plan(will_speak=True)
                # Arm the handshake ONLY if the question was actually delivered
                # (ADR-069). Arming first was two defects at once:
                #   H2 — if `speaker.say` raised (device gone), `_pending` stayed
                #        set with NO confirm timer armed, so a "yeah" opening an
                #        unrelated turn minutes later dispatched a held
                #        `system_wifi{off}` the user never heard proposed;
                #   H3 — on barge-in the user's new COMMAND was read as the
                #        yes/no answer, cancelled ("Okay, cancelled.") and lost.
                # An undelivered question is not a question.
                if await self._speak(result.spoken):
                    self._pending = result.pending
                    self._open_confirm_window()
                return

            if config.DEBUG:
                log.info(
                    "[debug] %s action=%s dispatched=%s spoken=%r",
                    rid, result.plan_name, result.dispatched, result.spoken,
                    extra={"no_disk": True},  # spoken can be raw model output
                )
            will_speak = bool(result.spoken) and result.spoken != "(no action)"
            self.state.got_plan(will_speak=will_speak)
            if will_speak and await self._speak(result.spoken, measure=True):
                # Append after speaking so cross-turn context holds (action and
                # chat turns alike). RAM-only — the buffer is never persisted.
                #
                # Only after speech the user actually RECEIVED (ADR-069). A
                # barged reply used to be recorded as if fully delivered, and
                # history is what ADR-065 resolves anaphora against — so Friday
                # could resolve a later "open it" against a sentence that was
                # cut off before the user heard the noun.
                self._dialogue.add(text, result.spoken)
        except asyncio.TimeoutError:
            await self._fail_speak("That took too long.")  # E_LLM_TIMEOUT
        except asyncio.CancelledError:
            raise
        except Exception:  # never leak a raw exception (FR-26)
            log.exception("turn failed")
            await self._fail_speak("Something went wrong.")

    async def _transcribe(self, pcm) -> str | None:  # noqa: ANN001
        if self._transcriber is None:
            # No transition here: `_run_turn` owns TRANSCRIBING -> IDLE for
            # every empty transcript (:269). Doing it in both places raised
            # IllegalTransition on EVERY capture in the supported no-STT mode,
            # so Friday said "Something went wrong." where FR-12 mandates a
            # silent return to IDLE (audit H4).
            return ""
        try:
            t = await asyncio.wait_for(
                asyncio.to_thread(self._transcriber.run, pcm),
                timeout=_TRANSCRIBE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            self.state.fail()
            await self._say_now("I didn't catch that.")  # E_STT_TIMEOUT
            self.state.reset()
            return None
        return t.text if t.actionable else ""

    # --- confirm-first voice handshake ------------------------------------

    def _open_confirm_window(self) -> None:
        # A DISTINCT timer from the 15 s capture cap: pressing the key to speak
        # the yes/no answer arms the capture cap, and sharing one handle would
        # orphan this 30 s timer (it would then fire mid-future-turn and reset
        # the FSM). Keep them separate.
        loop = asyncio.get_running_loop()
        self._confirm_timer = loop.call_later(_CONFIRM_WINDOW, self._expire_confirm)

    def _disarm_confirm(self) -> None:
        if self._confirm_timer is not None:
            self._confirm_timer.cancel()
            self._confirm_timer = None

    def _expire_confirm(self) -> None:
        # 30 s with no answer -> cancel silently (diagram 01). Dropping the
        # pending IS the cancellation; a later utterance is then simply a fresh
        # command.
        self._confirm_timer = None
        self._pending = None
        # It must NOT touch the FSM. Firing while the user is mid-answer used to
        # slam the mic gate shut (CAPTURING -> IDLE), so the release found the
        # wrong state and the answer vanished with zero feedback (audit M-P1) —
        # and resetting during TRANSCRIBING/PLANNING would break that turn's own
        # transitions the same way H4 did. Every state here is owned by an
        # in-flight turn that ends on its own: the 15 s cap (FR-4) ends a
        # capture, `_fail_speak` clears ERROR.

    async def _resolve_confirm(self, text: str, rid: str) -> None:
        pending, self._pending = self._pending, None
        self._disarm_confirm()
        self._disarm_capture_cap()
        # Shared with the TUI (turn.resolve_pending) so the two UIs cannot
        # drift apart again — audit finding C1 was exactly that drift.
        spoken = await resolve_pending(
            pending, text,
            prefs=self._prefs, audit=self._audit,
            request_id=rid, dry_run=self._dry_run,
        )
        self.state.got_plan(will_speak=True)
        await self._speak(spoken)

    # --- speaking (cancellable) -------------------------------------------

    async def _speak(self, text: str, *, measure: bool = False) -> bool:
        """Speak `text`. Returns True if it was delivered to the end, False if
        barge-in cut it off (ADR-069).

        Callers act on the answer: an interrupted line is not history, and an
        interrupted question does not arm a confirm. Two independent signals
        mean "cut off" — `Speaker.say` returns False when `stop()` beat it, and
        the task is cancelled when `_cancel_speak` got there first — so both
        are checked.
        """
        if self._speaker is None:
            if self.state.state is State.SPEAKING:
                self.state.done_speaking()
            return True
        on_play = self._ttfa_logger() if (measure and config.DEBUG) else None
        task = self._speak_task = asyncio.create_task(
            asyncio.to_thread(self._speaker.say, text, on_play)
        )
        try:
            played = await task
        except asyncio.CancelledError:
            # Only swallow OUR cancellation. If the turn task itself was
            # cancelled, the inner task is collateral and the CancelledError
            # belongs to the caller.
            if self._barged_speak_task is not task:
                raise
            self._barged_speak_task = None
            return False
        finally:
            # Identity-checked: a superseded turn must not blank the handle a
            # newer turn already installed, or the next barge-in would find
            # nothing to cancel.
            if self._speak_task is task:
                self._speak_task = None
        if played is False:  # stop() beat us to it; the task was never cancelled
            self._barged_speak_task = None
            return False
        if self.state.state is State.SPEAKING:
            self.state.done_speaking()
        return True

    def _ttfa_logger(self):  # noqa: ANN202 - returns a thread callback
        """A one-shot callback for `Speaker.say(on_play=...)` that logs TTFA —
        end of speech (`_capture_end`) to the first audio sample. Runs on the
        TTS worker thread; logging is thread-safe and it never raises."""
        start = self._capture_end
        seq = self._seq

        def on_play() -> None:
            log.info("[debug] v%d TTFA %.0f ms", seq, (time.monotonic() - start) * 1000)

        return on_play

    async def _say_now(self, text: str) -> None:
        """Speak a line that is not tied to SPEAKING-state bookkeeping (errors
        during TRANSCRIBING)."""
        if self._speaker is None:
            return
        try:
            await asyncio.to_thread(self._speaker.say, text)
        except Exception:
            # The error path must not be able to fail worse than what it is
            # reporting. `_fail_speak` calls this; a raising speaker (dead audio
            # device) would otherwise raise out of the exception handler, kill
            # the turn task mid-unwind and strand the FSM in ERROR, rejecting
            # every later trigger. Log the code, never the exception (FR-26).
            log.error("E_TTS_FAILED: could not speak")

    async def _fail_speak(self, text: str) -> None:
        self.state.fail()
        await self._say_now(text)
        self.state.reset()

    def _cancel_speak(self) -> None:
        if self._speaker is not None:
            self._speaker.stop()
        task = self._speak_task
        if task is not None and not task.done():
            # Remember WHICH task we cut, so `_speak` can tell our cancellation
            # apart from the turn task being cancelled out from under it.
            self._barged_speak_task = task
            task.cancel()

    async def _abort(self) -> None:
        self._cancel_speak()
        self._disarm_capture_cap()
        self._disarm_confirm()
        self._pending = None
        self.state.reset()

    async def on_proactive_event(self, title: str, message: str) -> None:
        """Deliver a proactive spoken alert when idle without violating FR-5.

        Wait bounded (a busy turn should not block a reminder forever, nor spin
        the scheduler indefinitely). The desktop notification already fired in
        the scheduler, so on timeout we drop the spoken line rather than talk
        over an in-progress turn."""
        deadline = time.monotonic() + _PROACTIVE_WAIT_S
        while not self.state.is_idle:
            if time.monotonic() >= deadline:
                log.info("proactive '%s' not spoken: busy past %.0fs", message, _PROACTIVE_WAIT_S)
                return
            await asyncio.sleep(0.2)
        await self._say_now(f"Reminder: {message}")

    # --- lifecycle --------------------------------------------------------

    async def close(self) -> None:
        """Teardown daemon and distill session memory if meaningful dialogue occurred (ADR-050)."""
        db = self._audit._db if self._audit else (self._prefs._db if self._prefs else None)
        if len(self._dialogue) >= 2 and db is not None:
            try:
                from .store.summarizer import distill_dialogue, save_session_summary
                summary = await asyncio.to_thread(
                    distill_dialogue, self._client, self._dialogue.render()
                )
                if summary:
                    save_session_summary(db, self._session_id, summary)
            except Exception:
                log.exception("session distillation failed on close")

    async def run(self) -> None:
        self._recorder.open()  # fail-soft; text-only if no device
        if self._wake_listener is not None:
            if not self._wake_listener.start():
                log.warning("no wake: PTT only")

        db = self._audit._db if self._audit else (self._prefs._db if self._prefs else None)
        if db is not None and not self._dnd.is_dnd:
            from .proactive.briefing import generate_startup_briefing
            briefing = generate_startup_briefing(db)
            await self._say_now(briefing)

        if self._scheduler is not None:
            self._sched_task = asyncio.create_task(self._scheduler.run())

        server = await ptt.serve(config.PTT_SOCKET, self.on_ptt)
        log.info("friday daemon listening on %s", config.PTT_SOCKET)
        try:
            await asyncio.Event().wait()  # run until cancelled
        finally:
            if self._scheduler is not None:
                self._scheduler.stop()
            if self._sched_task is not None:
                self._sched_task.cancel()
            if self._wake_listener is not None:
                self._wake_listener.stop()
            await self.close()
            server.close()
            await server.wait_closed()
            self._recorder.close()



