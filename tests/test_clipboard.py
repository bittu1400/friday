"""Wayland clipboard helper: text goes to wl-copy on STDIN, never argv."""

import subprocess

import friday.tools.clipboard as clip


def test_set_clipboard_passes_text_on_stdin(monkeypatch):
    seen = {}

    def fake_which(name):
        return "/usr/bin/wl-copy" if name == "wl-copy" else None

    class _Res:
        returncode = 0

    def fake_run(argv, **kw):
        seen["argv"] = argv
        seen["input"] = kw.get("input")
        return _Res()

    monkeypatch.setattr(clip.shutil, "which", fake_which)
    monkeypatch.setattr(clip.subprocess, "run", fake_run)

    assert clip.set_clipboard("a && b | c") is True
    # The (dangerous-looking) text is NEVER an argv element — only stdin bytes.
    assert seen["argv"] == ["/usr/bin/wl-copy"]
    assert seen["input"] == b"a && b | c"


def test_set_clipboard_missing_tool_returns_false(monkeypatch):
    monkeypatch.setattr(clip.shutil, "which", lambda name: None)
    assert clip.set_clipboard("x") is False


def test_read_clipboard_returns_stdout(monkeypatch):
    monkeypatch.setattr(clip.shutil, "which", lambda name: "/usr/bin/wl-paste")

    class _Res:
        stdout = "clipboard body"

    monkeypatch.setattr(clip.subprocess, "run", lambda argv, **kw: _Res())
    assert clip.read_clipboard() == "clipboard body"


def test_read_clipboard_missing_tool_returns_none(monkeypatch):
    monkeypatch.setattr(clip.shutil, "which", lambda name: None)
    assert clip.read_clipboard() is None
