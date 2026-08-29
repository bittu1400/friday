"""Wake word detection and always-on audio orchestration (G10, ADR-055/061).

Owns the always-on background microphone stream, passes frames through AEC,
and coordinates wake detection, VAD end-of-utterance, and voice barge-in.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import threading
import time
from typing import Any, Callable, Protocol

import numpy as np

from friday import config
from friday.audio.aec import AecProcessor, NullAec
from friday.audio.guard import CallbackGuard
from friday.audio.vad import SpeechGate, Vad

log = logging.getLogger(__name__)


class FarEndRef:
    """Thread-safe lock-free ring/queue for played TTS PCM frames (AEC reference)."""

    def __init__(self, max_samples: int = 16000 * 5) -> None:
        self._lock = threading.Lock()
        self._buffer = np.zeros(0, dtype=np.float32)
        self._max_samples = max_samples

    def write(self, pcm: np.ndarray) -> None:
        """Append played mono float32 PCM samples."""
        pcm_f = np.asarray(pcm, dtype=np.float32)
        with self._lock:
            self._buffer = np.concatenate((self._buffer, pcm_f))
            if len(self._buffer) > self._max_samples:
                self._buffer = self._buffer[-self._max_samples :]

    def read(self, n_samples: int) -> np.ndarray | None:
        """Consume and return n_samples from the front, or None if empty."""
        with self._lock:
            if len(self._buffer) == 0:
                return None
            if len(self._buffer) <= n_samples:
                out = self._buffer
                self._buffer = np.zeros(0, dtype=np.float32)
                if len(out) < n_samples:
                    out = np.pad(out, (0, n_samples - len(out)))
                return out
            out = self._buffer[:n_samples]
            self._buffer = self._buffer[n_samples:]
            return out

    def clear(self) -> None:
        """Clear reference buffer."""
        with self._lock:
            self._buffer = np.zeros(0, dtype=np.float32)


class WakeDetector(Protocol):
    """Protocol for wake word detectors."""

    def score(self, frame: np.ndarray) -> float:
        """Score incoming audio frame. Returns probability in [0.0, 1.0]."""
        ...


class OpenWakeWordDetector:
    """Wake word detector wrapping openWakeWord."""

    def __init__(self, model_path: Path | str, chunk_size: int = 1280) -> None:
        from openwakeword.model import Model

        p = str(model_path)
        self._model = Model(wakeword_model_paths=[p])

        # Invariant #6: only llama-server (a separate process) touches CUDA;
        # everything in this process — STT, TTS, and wake — is CPU. openWakeWord
        # hardcodes ["CUDAExecutionProvider", "CPUExecutionProvider"] for its
        # melspec/embedding sessions (utils.py), so on a machine with
        # onnxruntime-gpu installed it would silently grab the GPU. Fail closed
        # instead: create_detector() catches this and disables wake (PTT still
        # works) rather than let the invariant break unnoticed.
        provider = getattr(self._model.preprocessor, "onnx_execution_provider", "")
        if "CUDA" in str(provider):
            raise RuntimeError(
                f"wake models loaded on {provider}; invariant #6 requires CPU. "
                "Ensure onnxruntime (CPU), not onnxruntime-gpu, is installed."
            )

        self._model_key = list(self._model.models.keys())[0]
        self._chunk_size = chunk_size
        self._buffer = np.zeros(0, dtype=np.int16)
        self._last_score: float = 0.0

    def score(self, frame: np.ndarray) -> float:
        frame_f = np.asarray(frame, dtype=np.float32)
        pcm_i16 = (np.clip(frame_f, -1.0, 1.0) * 32767.0).astype(np.int16)
        self._buffer = np.concatenate((self._buffer, pcm_i16))

        while len(self._buffer) >= self._chunk_size:
            chunk = self._buffer[: self._chunk_size]
            self._buffer = self._buffer[self._chunk_size :]
            preds = self._model.predict(chunk)
            if self._model_key in preds:
                self._last_score = float(preds[self._model_key])
            elif preds:
                self._last_score = float(max(preds.values()))

        return self._last_score



def create_detector(
    model_path: Path | str | None = None,
    *,
    threshold: float = 0.5,
) -> WakeDetector | None:
    """Factory for wake word detector, fail-soft to None."""
    target_path = Path(model_path or config.WAKE_MODEL)
    if not target_path.exists():
        # Fallback to package model if local share doesn't exist
        try:
            import openwakeword
            import os

            pkg_dir = os.path.dirname(openwakeword.__file__)
            fallback = Path(pkg_dir) / "resources" / "models" / "hey_jarvis_v0.1.onnx"
            if fallback.exists():
                target_path = fallback
        except Exception:
            pass

    if not target_path.exists():
        log.warning("Wake word model not found at %s", target_path)
        return None

    try:
        return OpenWakeWordDetector(target_path)
    except Exception as exc:
        log.warning("Failed to load wake word model (%s)", exc)
        return None


@dataclass(frozen=True)
class WakeCallbacks:
    """Synchronous callbacks emitted by the WakeListener audio thread."""

    on_wake: Callable[[], None]
    on_speech_end: Callable[[], None]
    on_barge: Callable[[], None]


def _run_now(cb: Callable[[], None]) -> None:
    cb()


class WakeListener:
    """Always-on audio listener orchestrator.

    Owns continuous mic stream, cleans via AEC, and triggers wake, VAD end,
    and barge-in events based on FSM state predicates.
    """

    def __init__(
        self,
        *,
        detector: Any,
        vad: Any,
        aec: AecProcessor | None = None,
        callbacks: WakeCallbacks,
        far_ref: FarEndRef | None = None,
        threshold: float = 0.5,
        frame_len: int = 320,  # 20ms at 16kHz
        refractory_s: float = 1.5,
        is_idle: Callable[[], bool],
        is_speaking: Callable[[], bool],
        schedule: Callable[[Callable[[], None]], None] = _run_now,
    ) -> None:
        self.detector = detector
        self.vad = vad
        self.aec = aec or NullAec()
        self.callbacks = callbacks
        self.far_ref = far_ref or FarEndRef()
        self.threshold = threshold
        self.frame_len = frame_len
        self.refractory_s = refractory_s
        self.is_idle = is_idle
        self.is_speaking = is_speaking
        self.schedule = schedule

        self._last_wake_time: float = 0.0
        self._awaiting_end: bool = False
        self._warned_no_vad = False  # M-A3: warn once, not once per capture
        self._heard_speech = False   # any speech at all in the current capture
        self._silent_frames = 0      # frames since the capture began
        self._stream: Any = None
        # M-A1: an exception out of here does not crash anything — sounddevice
        # eats it and quietly stops calling back, so wake and VAD die while the
        # service still looks healthy. Swallow, count, and degrade out loud.
        self._guard = CallbackGuard("wake", on_disable=self._disable_detector)

        frame_ms = (frame_len * 1000) // 16000
        self.frame_ms = frame_ms
        self._no_speech_frames = max(
            1, int(round(config.VAD_NO_SPEECH_TIMEOUT_S * 1000 / frame_ms))
        )
        self._capture_gate = SpeechGate(
            frame_ms=frame_ms,
            end_silence_s=config.VAD_END_SILENCE_S,
            min_speech_s=config.VAD_MIN_SPEECH_S,
        )
        self._barge_gate = SpeechGate(
            frame_ms=frame_ms,
            end_silence_s=0.5,
            min_speech_s=config.VAD_MIN_SPEECH_S,
        )

    def _arm(self) -> None:
        self._awaiting_end = True
        self._capture_gate.reset()
        self._heard_speech = False
        self._silent_frames = 0

    def arm_end_of_speech(self) -> None:
        """Arm VAD end-of-utterance for a hands-free capture the FSM ACCEPTED.

        ADR-062: a capture with no physical key release needs VAD to end it.
        PTT is deliberately excluded: a tap-toggle capture ends on the user's
        second tap (ADR-044).

        Called by the daemon from `_start_capture`, i.e. only after
        `begin_capture()`/`barge_in()` returned True. Arming inside `_on_frame`
        at wake-detection time was a TOCTOU (audit H5): the audio thread armed
        first and the loop could then REJECT the trigger as busy, leaving the
        listener armed so VAD end-of-speech terminated whatever capture was
        actually running — including a PTT one, contradicting ADR-044.
        """
        if self.vad is None:
            # Without a VAD there is no end-of-speech and no ADR-066 bail-out,
            # so an "armed" hands-free capture would just run the full 15 s cap
            # with Friday deaf throughout — the pre-ADR-066 behaviour, silently
            # back (M-A3). Refuse, and say so rather than pretend.
            if not self._warned_no_vad:
                self._warned_no_vad = True
                log.warning(
                    "no VAD: hands-free captures cannot end on silence and will "
                    "run to the %.0fs cap. Use PTT until webrtcvad loads.",
                    config.MAX_CAPTURE_S,
                )
            return
        self._arm()

    def _on_frame(self, frame: np.ndarray) -> None:
        """Route one 16 kHz mono frame from audio thread."""
        far = self.far_ref.read(len(frame))
        cleaned = self.aec.process(frame, far)

        # openWakeWord is a STREAMING model: it holds rolling melspectrogram and
        # embedding buffers and expects an unbroken feed. Scoring it only while
        # idle starved it for the whole 15 s of a capture, and since one frame
        # (320 samples) is smaller than a prediction chunk (1280), the first
        # frame after the capture could not run a new prediction and returned
        # the very score that STARTED that capture — re-firing the wake at once,
        # forever (OQ-29). Flushing is not an option: openWakeWord's reset()
        # clears only its score deque, not the feature buffers. So score every
        # frame to keep the stream continuous, and merely ignore the result
        # unless we are idle.
        score = self.detector.score(cleaned) if self.detector is not None else 0.0

        if self.is_speaking():
            self._awaiting_end = False
            self._capture_gate.reset()
            # ADR-064: voice barge-in is off until an echo canceller that works
            # on this hardware is chosen. PTT barge-in (daemon._on_press) is
            # unaffected — it comes from the socket, not from this VAD.
            if self.vad is not None and config.BARGE_VAD_ENABLED:
                voiced = self.vad.is_speech(cleaned)
                ev = self._barge_gate.push(voiced)
                if ev == "start":
                    self._barge_gate.reset()
                    self.schedule(self.callbacks.on_barge)
            return

        self._barge_gate.reset()

        if self._awaiting_end:
            if not self.is_idle():
                if self.vad is not None:
                    voiced = self.vad.is_speech(cleaned)
                    ev = self._capture_gate.push(voiced)
                    if voiced:
                        self._heard_speech = True
                    self._silent_frames += 1
                    if ev == "end":
                        self._awaiting_end = False
                        self._capture_gate.reset()
                        self.schedule(self.callbacks.on_speech_end)
                    elif (
                        not self._heard_speech
                        and self._silent_frames >= self._no_speech_frames
                    ):
                        # ADR-066: a false wake. Nothing was ever said, so the
                        # end-of-speech timer can never arm and this capture
                        # would run to the 15 s cap with Friday deaf the whole
                        # time (FR-5). Give it back now.
                        log.info("capture abandoned: no speech within %.1fs",
                                 self._no_speech_frames * self.frame_ms / 1000)
                        self._awaiting_end = False
                        self._capture_gate.reset()
                        self.schedule(self.callbacks.on_speech_end)
            else:
                # Capture finished or was interrupted
                self._awaiting_end = False
                self._capture_gate.reset()
            return

        if self.is_idle() and score >= self.threshold:
            now = time.monotonic()
            if now - self._last_wake_time >= self.refractory_s:
                self._last_wake_time = now
                # Score is logged so a threshold can be chosen from data rather
                # than guessed: a false wake is invisible in the logs otherwise.
                log.info("wake fired score=%.3f threshold=%.2f", score, self.threshold)
                # NOT armed here (H5). The FSM may reject this trigger as busy,
                # and an armed listener would then end somebody else's capture.
                # The daemon arms from `_start_capture`, after acceptance.
                self.schedule(self.callbacks.on_wake)

    def _disable_detector(self) -> None:
        """Give up on wake detection for the rest of the process (M-A1).

        The stream stays open — PTT still works, and so does a capture already
        running — but nothing pretends the wake word is being listened for.
        """
        self.detector = None

    def _sd_callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        if status:
            log.debug("WakeListener input stream status: %s", status)
        mono = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
        self._guard.run(self._on_frame, mono)

    def start(self) -> bool:
        """Start always-on audio stream; fail-soft returning False on error."""
        if self._stream is not None:
            return True

        try:
            import sounddevice as sd

            self._stream = sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype="float32",
                blocksize=self.frame_len,
                callback=self._sd_callback,
            )
            self._stream.start()
            log.info("WakeListener background audio stream active")
            return True
        except Exception as exc:
            log.warning("Failed to start WakeListener audio stream (%s); wake disabled", exc)
            self._stream = None
            return False

    def stop(self) -> None:
        """Stop and close audio stream."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
