"""Cancellable playback / barge-in (FR-73). No audio hardware: a fake
`sounddevice` module is injected so play/stop/wait are observable."""

import sys
import types

import pytest

from friday.audio.tts import Speaker


class FakeSD:
    def __init__(self):
        self.played = False
        self.stopped = False
        self.waited = False

    def play(self, samples, sr):
        self.played = True

    def wait(self):
        self.waited = True

    def stop(self):
        self.stopped = True


class FakeKokoro:
    def __init__(self, on_create=None):
        self._on_create = on_create

    def create(self, text, voice, speed, lang):
        if self._on_create:
            self._on_create()
        return ([0.0] * 100, 24000)


@pytest.fixture
def fake_sd(monkeypatch):
    sd = FakeSD()
    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(
        play=sd.play, wait=sd.wait, stop=sd.stop))
    return sd


def test_empty_text_plays_nothing(fake_sd):
    assert Speaker(FakeKokoro(), "af_bella").say("") is False
    assert fake_sd.played is False


def test_normal_say_plays_to_end(fake_sd):
    sp = Speaker(FakeKokoro(), "af_bella")
    assert sp.say("hello") is True
    assert fake_sd.played and fake_sd.waited


def test_cancel_during_synthesis_never_starts_audio(fake_sd):
    """stop() called while synth runs -> playback is skipped (FR-73)."""
    sp = Speaker(FakeKokoro(), "af_bella")
    sp._kokoro._on_create = sp.stop  # fire barge-in from inside create()
    assert sp.say("a long sentence") is False
    assert fake_sd.played is False  # cancel landed before play started


def test_stop_sets_flag_and_stops_stream(fake_sd):
    sp = Speaker(FakeKokoro(), "af_bella")
    sp.stop()
    assert fake_sd.stopped is True


def test_say_clears_stale_cancel(fake_sd):
    """A stop() from a previous turn must not suppress the next say()."""
    sp = Speaker(FakeKokoro(), "af_bella")
    sp.stop()  # stale cancel
    assert sp.say("new turn") is True  # say() clears it
    assert fake_sd.played is True
