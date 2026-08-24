import numpy as np
from friday.audio.vad import SpeechGate, create, WebRtcVad


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
