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

from __future__ import annotations

import asyncio
import logging

from . import config
from .audio import ptt
from .audio.capture import Recorder
from .audio.state import State, TurnState
from .audio.stt import Transcriber
from .llm.client import LlamaClient
from .store.audit import AuditLog
from .store.prefs import PendingPreference, PrefStore
from .turn import confirm_preference, is_affirmation, run_turn

log = logging.getLogger("friday.daemon")

# Per-stage timeouts (diagram 01). Latency targets live in diagram 05; these
# are the hard aborts, deliberately larger — a slow turn should finish late,
# not fail.
_TRANSCRIBE_TIMEOUT = 5.0
_PLANNING_TIMEOUT = 12.0
_CONFIRM_WINDOW = 30.0


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
    ) -> None:
        self.state = TurnState()
        self._client = client
        self._recorder = recorder
        self._transcriber = transcriber
        self._speaker = speaker
        self._prefs = prefs
        self._audit = audit
        self._dry_run = dry_run
        self._turn_task: asyncio.Task | None = None
        self._speak_task: asyncio.Task | None = None
        self._pending: PendingPreference | None = None  # awaiting voice confirm
        self._cap_timer: asyncio.TimerHandle | None = None
        self._confirm_timer: asyncio.TimerHandle | None = None
        self._last_toggle = 0.0  # debounce clock for the tap-only trigger (ADR-044)
        self._seq = 0
        self.rejected = 0  # FR-5 counter (observable in tests)

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
                self._start_capture()
            return
        if self.state.begin_capture():
            self._start_capture()
        else:
            self.rejected += 1  # FR-5: busy, rejected not queued
            log.info("E_BUSY: press ignored in %s", self.state.state.value)

    def _start_capture(self) -> None:
        self._recorder.reset()
        self._arm_capture_cap()

    async def _on_release(self) -> None:
        if self.state.state is not State.CAPTURING:
            return  # release without a capture — ignore
        self._disarm_capture_cap()
        self.state.end_capture()
        pcm = self._recorder.collect()
        self._turn_task = asyncio.create_task(self._run_turn(pcm))

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
                log.info("[debug] %s heard=%r", rid, text)
            if not text:  # FR-12 empty / FR-13 over-limit -> IDLE, silent
                return

            # If we were waiting on a spoken yes/no, this utterance is it.
            if self._pending is not None:
                await self._resolve_confirm(text, rid)
                return

            # PLANNING + EXECUTING (execute-first inside run_turn; no speech).
            result = await asyncio.wait_for(
                run_turn(
                    text, self._client, request_id=rid, dry_run=self._dry_run,
                    prefs=self._prefs, audit=self._audit, speaker=None,
                ),
                timeout=_PLANNING_TIMEOUT,
            )

            if result.pending is not None:  # confirm-first (ADR-037)
                self._pending = result.pending
                self.state.got_plan(will_speak=True)
                await self._speak(result.spoken)  # the question
                self._open_confirm_window()
                return

            if config.DEBUG:
                log.info(
                    "[debug] %s action=%s dispatched=%s spoken=%r",
                    rid, result.plan_name, result.dispatched, result.spoken,
                )
            will_speak = bool(result.spoken) and result.spoken != "(no action)"
            self.state.got_plan(will_speak=will_speak)
            if will_speak:
                await self._speak(result.spoken)
        except asyncio.TimeoutError:
            await self._fail_speak("That took too long.")  # E_LLM_TIMEOUT
        except asyncio.CancelledError:
            raise
        except Exception:  # never leak a raw exception (FR-26)
            log.exception("turn failed")
            await self._fail_speak("Something went wrong.")

    async def _transcribe(self, pcm) -> str | None:  # noqa: ANN001
        if self._transcriber is None:
            self.state.got_transcript(nonempty=False)
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
        # 30 s with no answer -> cancel silently (diagram 01).
        self._confirm_timer = None
        self._pending = None
        if self.state.state is not State.IDLE:
            self.state.reset()

    async def _resolve_confirm(self, text: str, rid: str) -> None:
        pending, self._pending = self._pending, None
        self._disarm_confirm()
        self._disarm_capture_cap()
        if is_affirmation(text):
            spoken = await confirm_preference(
                pending, self._prefs, self._audit, request_id=rid
            )
        else:
            spoken = "Okay, I won't."  # anything but yes cancels the write
        self.state.got_plan(will_speak=True)
        await self._speak(spoken)

    # --- speaking (cancellable) -------------------------------------------

    async def _speak(self, text: str) -> None:
        if self._speaker is None:
            if self.state.state is State.SPEAKING:
                self.state.done_speaking()
            return
        self._speak_task = asyncio.create_task(asyncio.to_thread(self._speaker.say, text))
        try:
            await self._speak_task
        except asyncio.CancelledError:
            return  # barge-in cancelled us; state already moved on
        finally:
            self._speak_task = None
        if self.state.state is State.SPEAKING:
            self.state.done_speaking()

    async def _say_now(self, text: str) -> None:
        """Speak a line that is not tied to SPEAKING-state bookkeeping (errors
        during TRANSCRIBING)."""
        if self._speaker is not None:
            await asyncio.to_thread(self._speaker.say, text)

    async def _fail_speak(self, text: str) -> None:
        self.state.fail()
        await self._say_now(text)
        self.state.reset()

    def _cancel_speak(self) -> None:
        if self._speaker is not None:
            self._speaker.stop()
        if self._speak_task is not None and not self._speak_task.done():
            self._speak_task.cancel()

    async def _abort(self) -> None:
        self._cancel_speak()
        self._disarm_capture_cap()
        self._disarm_confirm()
        self._pending = None
        self.state.reset()

    # --- lifecycle --------------------------------------------------------

    async def run(self) -> None:
        self._recorder.open()  # fail-soft; text-only if no device
        server = await ptt.serve(config.PTT_SOCKET, self.on_ptt)
        log.info("friday daemon listening on %s", config.PTT_SOCKET)
        try:
            await asyncio.Event().wait()  # run until cancelled
        finally:
            server.close()
            await server.wait_closed()
            self._recorder.close()
