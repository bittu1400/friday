"""Voice out: fail-soft Speaker + speaking wired into the turn loop (ADR-040).

No model file and no audio device are needed — the model is exercised by the
G5 benchmark (ADR-039), not by unit tests. Here we test the wiring: missing
model -> None, blank text -> no synth, synth errors swallowed, and run_turn
speaks real outcomes but not the `none` placeholder."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from friday.audio.tts import Speaker


class FakeKokoro:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_voices(self):
        return ["af_bella", "af_heart"]

    def create(self, text, voice, speed=1.0, lang="en-us"):
        self.calls.append(text)
        import numpy as np

        return np.zeros(10, dtype="float32"), 24000


def test_missing_model_returns_none(tmp_path) -> None:
    sp = Speaker.create(
        tmp_path / "nope.onnx",
        tmp_path / "nope.bin",
        voice="af_bella",
        fallback="af_heart",
    )
    assert sp is None


def test_say_blank_is_noop() -> None:
    fk = FakeKokoro()
    Speaker(fk, "af_bella").say("   ")
    assert fk.calls == []  # never reached synth


def test_say_swallows_synth_errors() -> None:
    class Boom:
        def create(self, *a, **k):
            raise RuntimeError("no audio")

    Speaker(Boom(), "af_bella").say("hello")  # must not raise


# -- speaking wired into the turn loop --------------------------------------


@dataclass
class RecordingSpeaker:
    voice: str = "af_bella"
    said: list[str] = field(default_factory=list)

    def say(self, text: str) -> None:
        self.said.append(text)


@dataclass
class StubClient:
    reply: str

    def complete(self, *, system: str, user: str, grammar: str) -> str:
        return self.reply

    def health(self) -> bool:
        return True


def _turn(reply: str, speaker):
    from friday.turn import run_turn

    return asyncio.run(
        run_turn(
            "x", StubClient(reply), request_id="t", dry_run=True, speaker=speaker
        )
    )


def test_run_turn_speaks_dispatched_outcome() -> None:
    sp = RecordingSpeaker()
    r = _turn('{"action":{"name":"open_app","params":{"app":"browser"}}}', sp)
    assert r.dispatched
    assert len(sp.said) == 1 and sp.said[0].startswith("Opened Brave")


def test_run_turn_does_not_speak_none_placeholder() -> None:
    sp = RecordingSpeaker()
    _turn('{"action":{"name":"none","params":{}}}', sp)
    assert sp.said == []  # "(no action)" is never voiced


def test_run_turn_speaks_error_line() -> None:
    sp = RecordingSpeaker()
    _turn("not json", sp)  # SchemaError -> "I didn't understand."
    assert sp.said == ["I didn't understand."]
