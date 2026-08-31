import wave
from pathlib import Path

import numpy as np
import pytest

from friday.audio.vad import SileroVad, SpeechGate, WebRtcVad, create

CLIPS = sorted((Path.home() / ".cache/whisper-bench/clips").glob("clip_*.wav"))


def _read_pcm(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def _with_room_tail(pcm: np.ndarray, sr: int = 16000, tail_s: float = 2.0) -> np.ndarray:
    """Append this clip's own quietest half-second, tiled (scripts/vad_bench.py)."""
    win = sr // 2
    if len(pcm) <= win:
        quiet = pcm
    else:
        rms = [np.sqrt(np.mean(pcm[i:i + win] ** 2)) for i in range(0, len(pcm) - win, win // 2)]
        quiet = pcm[int(np.argmin(rms)) * (win // 2):][:win]
    tail = np.tile(quiet, int(np.ceil(tail_s * sr / len(quiet))))[: int(tail_s * sr)]
    return np.concatenate([pcm, tail])


def gate():  # 20 ms frames
    return SpeechGate(frame_ms=20, end_silence_s=0.8, min_speech_s=0.3)


def test_start_fires_after_min_speech():
    g = gate()
    events = [g.push(True) for _ in range(15)]  # 15*20ms = 300ms
    assert "start" in events
    assert events.index("start") == 14  # exactly at 300ms (min_speech_s)
    # Subsequent speech frames return None while in speech
    assert g.push(True) is None


def test_end_fires_after_trailing_silence():
    g = gate()
    for _ in range(20):
        g.push(True)  # speaking -> starts
    n_silence = int(0.8 / 0.02)  # 40 frames = 800ms
    events = [g.push(False) for _ in range(n_silence)]
    assert events[-1] == "end"
    assert events.count("end") == 1


def test_short_blip_never_starts():
    g = gate()
    events = [g.push(True) for _ in range(5)]  # 100ms < 300ms
    events += [g.push(False) for _ in range(5)]
    assert "start" not in events
    assert "end" not in events


def test_reset_clears_state():
    g = gate()
    for _ in range(15):
        g.push(True)
    assert g.in_speech
    g.reset()
    assert not g.in_speech
    assert g.push(False) is None


def test_webrtc_vad_smoke():
    vad = create(mode=2, sample_rate=16000)
    assert vad is not None
    silence = np.zeros(320, dtype=np.float32)  # 20ms of silence
    assert not vad.is_speech(silence)


# --- D3 / ADR-095: Silero replaces webrtcvad as the frame classifier ---------
#
# webrtcvad called 83-100% of frames speech on 5 of 20 real DMIC clips, room
# noise included, so trailing silence never accumulated, SpeechGate never
# emitted 'end', and every hands-free capture ran to the 15 s cap (D3).


def test_create_returns_silero_by_default():
    v = create()
    assert type(v).__name__ == "SileroVad"


def test_silero_accepts_20ms_frames_and_holds_verdict():
    """The mic path delivers 320-sample frames; Silero's graph wants 512.

    The adapter must buffer and hold the last verdict in between, or every
    caller in the tree (wake.py, speaker_enroll.py) has to change its frame
    size — and openwakeword's chunking would have to change with it.
    """
    v = SileroVad()
    silence = np.zeros(320, dtype=np.float32)
    verdicts = [v.is_speech(silence) for _ in range(100)]  # 2 s of digital silence
    assert not any(verdicts)
    assert v.inferences == pytest.approx(100 * 320 // 512, abs=1)


def test_silero_reset_clears_stream_state():
    v = SileroVad()
    for _ in range(50):
        v.is_speech(np.zeros(320, dtype=np.float32))
    v.reset()
    assert v.inferences == 0


@pytest.mark.skipif(not CLIPS, reason="real DMIC corpus not on this machine")
def test_silero_ends_every_real_clip():
    """THE D3 test. Drive the real SpeechGate over the real 20-clip corpus.

    Each clip gets 2 s of its own quietest room noise appended — digital
    silence would flatter any detector and prove nothing. webrtcvad mode 2
    ends 15 of 20 here; that gap is D3.
    """
    ended = 0
    for path in CLIPS:
        audio = _with_room_tail(_read_pcm(path))
        v, g = SileroVad(), gate()
        events = [
            g.push(v.is_speech(audio[i:i + 320]))
            for i in range(0, len(audio) - 320, 320)
        ]
        ended += "end" in events
    assert ended == len(CLIPS), f"SpeechGate ended only {ended}/{len(CLIPS)} clips"
