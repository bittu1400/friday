from friday.audio.dictation import DictationManager, format_dictation, is_start_dictation, is_stop_dictation


def test_dictation_phrase_detection():
    assert is_start_dictation("start dictation")
    assert is_start_dictation("begin dictation mode")
    assert not is_start_dictation("start firefox")

    assert is_stop_dictation("stop dictation")
    assert is_stop_dictation("end dictation")
    assert not is_stop_dictation("stop music")


def test_format_dictation_punctuation():
    text = "hello world period how are you question mark new line fine comma thanks exclamation mark"
    formatted = format_dictation(text)
    assert formatted == "hello world. how are you?\nfine, thanks!"


def test_dictation_manager_toggle(monkeypatch):
    dm = DictationManager()
    assert not dm.is_dictating

    typed = []
    monkeypatch.setattr("friday.audio.dictation.type_text", lambda s: typed.append(s) or True)

    dm.start()
    assert dm.is_dictating

    # When dictating, transcript is typed verbatim
    dm.handle_transcript("open brave and search")
    assert typed == ["open brave and search "]

    dm.stop()
    assert not dm.is_dictating


# --- D22: the typer timeout that truncated dictation and stuck a key ---------
#
# ydotool types at a measured ~40 ms/char at its default key-delay/key-hold, so
# the old fixed `timeout=3.0` cut every transcript over ~74 characters — and
# subprocess.run enforces a timeout with SIGKILL, which killed ydotool between
# a key down and its key up and left the key repeating forever. These assert
# the property that was violated, not the constants.


def test_typer_timeout_scales_past_the_74_char_cliff() -> None:
    """The old constant made 74 chars the hard ceiling. Nothing may reimpose one."""
    from friday.tools.typer import _timeout_for

    # The real sentence from the 2026-08-30 live session that got truncated.
    sample = (
        "alright this is your typo like we are trying to check if it's working "
        "or not so write it out"
    )
    assert len(sample) > 74
    # Worst-case observed cost is 40.2 ms/char (ydotool's own defaults). The
    # timeout must clear even that, or a slow run gets killed mid-key again.
    assert _timeout_for(sample) > len(sample) * 0.0402


def test_typer_timeout_is_monotonic_in_length() -> None:
    from friday.tools.typer import _timeout_for

    assert _timeout_for("x" * 1000) > _timeout_for("x" * 100) > _timeout_for("x")


def test_typer_pins_the_key_rate_instead_of_inheriting_it() -> None:
    """A rate left at the tool's default is a decision nobody made — and its
    default is exactly what made the timeout unpayable."""
    from friday.tools import typer

    assert typer._KEY_DELAY_MS < 20 and typer._KEY_HOLD_MS < 20


def test_wtype_gets_a_double_dash_separator(monkeypatch) -> None:
    """D11: a transcript starting with '-' must not be parsed as wtype options."""
    import subprocess as sp

    from friday.tools import typer

    seen: dict[str, list[str]] = {}

    def fake_which(name: str) -> str | None:
        return "/usr/bin/wtype" if name == "wtype" else None

    def fake_run(argv, **kw):
        seen["argv"] = argv
        return sp.CompletedProcess(argv, 0)

    monkeypatch.setattr(typer.shutil, "which", fake_which)
    monkeypatch.setattr(typer.subprocess, "run", fake_run)
    assert typer.type_text("--version") is True
    assert seen["argv"] == ["/usr/bin/wtype", "--", "--version"]


def test_timeout_is_not_reported_as_a_missing_binary(monkeypatch, caplog) -> None:
    """The old code logged 'No working Wayland typer found' for a timeout,
    which sent this investigation looking for an uninstalled package."""
    import subprocess as sp

    from friday.tools import typer

    monkeypatch.setattr(
        typer.shutil, "which", lambda n: "/usr/bin/ydotool" if n == "ydotool" else None
    )

    def fake_run(argv, **kw):
        raise sp.TimeoutExpired(argv, kw.get("timeout", 1.0))

    monkeypatch.setattr(typer.subprocess, "run", fake_run)
    with caplog.at_level("ERROR"):
        assert typer.type_text("hello world") is False
    joined = caplog.text
    assert "timed out" in joined and "stuck" in joined
    assert "No Wayland typer installed" not in joined
