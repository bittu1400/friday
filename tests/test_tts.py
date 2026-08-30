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
    assert len(sp.said) == 1 and sp.said[0].startswith("Launching Brave")  # ADR-073


def test_run_turn_speaks_none_out_of_scope_line() -> None:
    # G8 (design open-item #4): `none` now SPEAKS a distinct out-of-scope line
    # so the operator can tell live that the model chose no action.
    from friday.ui import templates

    sp = RecordingSpeaker()
    _turn('{"action":{"name":"none","params":{}}}', sp)
    assert sp.said == [templates.OUT_OF_SCOPE]


def test_run_turn_speaks_error_line() -> None:
    sp = RecordingSpeaker()
    _turn("not json", sp)  # SchemaError -> "I didn't understand."
    assert sp.said == ["I didn't understand."]


# --- engine-level fallback (2026-08-30) --------------------------------------
# These exist because this project has shipped four decisions that were never
# actually implemented (ADR-070, ADR-074, ADR-058, ADR-019). A fallback nobody
# has watched fail is the same bug. Each test FORCES the failure.

def test_supertonic_not_attempted_without_a_dir(tmp_path) -> None:
    """The dependency is optional: no dir, no attempt, same behaviour as before."""
    assert Speaker.create(
        tmp_path / "nope.onnx", tmp_path / "nope.bin",
        voice="af_bella", fallback="af_heart",
    ) is None


def test_supertonic_takes_over_when_kokoro_model_is_missing(tmp_path, monkeypatch) -> None:
    """The failure af_heart CANNOT cover: both Kokoro voices live in the one
    model file, so losing it loses both."""
    from friday.audio import tts as tts_mod

    made = {}

    class FakeEngine:
        def get_voices(self):
            return ["F1"]

        def create(self, text, voice=None, speed=None, lang=None):
            import numpy as np
            made["text"] = text
            return np.zeros(4, dtype="float32"), 44100

    monkeypatch.setattr(tts_mod._Supertonic, "load",
                        classmethod(lambda cls, *a, **k: FakeEngine()))
    sp = Speaker.create(
        tmp_path / "nope.onnx", tmp_path / "nope.bin",
        voice="af_bella", fallback="af_heart",
        supertonic_dir=tmp_path,
    )
    assert sp is not None
    assert sp.voice == "F1"


def test_supertonic_load_returns_none_without_models(tmp_path) -> None:
    """An absent model set is not an error — it degrades, it does not raise."""
    from friday.audio import tts as tts_mod

    assert tts_mod._Supertonic.load(tmp_path, "F1", 8, 1.05, 8) is None


def test_supertonic_ignores_the_callers_speed() -> None:
    """`say()` passes Kokoro's 1.0, which means 'normal' for Kokoro. Supertonic's
    normal is 1.05, so obeying the caller would slow the fallback for nothing."""
    from friday.audio import tts as tts_mod

    seen = {}

    class FakeTTS:
        def synthesize(self, text, style, total_steps=None, speed=None):
            import numpy as np
            seen.update(steps=total_steps, speed=speed)
            return np.zeros(4, dtype="float32"), 0.1

    eng = tts_mod._Supertonic(FakeTTS(), object(), "F1", steps=8, speed=1.05)
    samples, sr = eng.create("hello", voice="af_bella", speed=1.0, lang="en-us")
    assert sr == 44100
    assert seen == {"steps": 8, "speed": 1.05}
