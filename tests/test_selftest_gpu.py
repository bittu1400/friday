"""The GPU-offload check must actually FAIL on CPU fallback.

On 2026-08-25 llama-server ran CPU-only for hours while `gpu_arch` reported
PASS -- that check asks whether a GPU exists, not whether the LLM is using it.
These tests pin the branch that would have caught it.
"""
import subprocess
import types

from friday import selftest
from friday.selftest import Status, check_llm_on_gpu


def _fake_run(pgrep_out: str, smi_out: str):
    def run(argv, **kw):
        out = pgrep_out if argv[0] == "pgrep" else smi_out
        return types.SimpleNamespace(stdout=out, returncode=0)
    return run


def test_fails_when_llama_running_but_holds_no_vram(monkeypatch):
    monkeypatch.setattr(selftest.shutil, "which", lambda n: "/usr/bin/nvidia-smi")
    # llama-server alive (pid 999) but only another process holds VRAM
    monkeypatch.setattr(subprocess, "run", _fake_run("999\n", "1234, 4\n"))
    res = check_llm_on_gpu()
    assert res.status is Status.FAIL
    assert "CPU" in res.message
    assert "restart friday-llm" in (res.details or "")


def test_passes_when_llama_holds_vram(monkeypatch):
    monkeypatch.setattr(selftest.shutil, "which", lambda n: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(subprocess, "run", _fake_run("999\n", "999, 4696\n"))
    res = check_llm_on_gpu()
    assert res.status is Status.PASS
    assert "4696" in res.message


def test_trivial_vram_is_not_enough(monkeypatch):
    """A few MiB means a context/driver allocation, not a loaded 7B model."""
    monkeypatch.setattr(selftest.shutil, "which", lambda n: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(subprocess, "run", _fake_run("999\n", "999, 12\n"))
    assert check_llm_on_gpu().status is Status.FAIL


def test_warns_when_llama_not_running(monkeypatch):
    monkeypatch.setattr(selftest.shutil, "which", lambda n: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(subprocess, "run", _fake_run("", ""))
    assert check_llm_on_gpu().status is Status.WARN
