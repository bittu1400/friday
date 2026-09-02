"""Egress verification (FR-60, invariant #8) — audit F9.

Two previous versions of this check could not detect egress, and each one was
cited as an egress proof anyway:

1. `just test-egress` used to run `ss -ltnp` — **listening** sockets. Egress is
   outbound. It inspected the one category that cannot contain an egress event.
   That blindness is why D13 (the STT path resolving huggingface.co at every
   daemon start) survived for the life of the project; `ss -tnp` found it in one
   command. The listening-socket check still exists and is still useful, under
   its honest name: `just test-binds`.
2. The replacement asserted that `config.LLAMA_BASE_URL` and
   `config.SEARXNG_URL` parse to 127.0.0.1. That is a config assertion wearing
   an egress test's name — it reads three constants and observes no connection.
   It would not have caught D13 either, because huggingface.co never appears in
   a config constant.

So this file does not ask what the config says. It installs a guard over the
two stdlib chokepoints every outbound TCP connection passes through —
`socket.getaddrinfo` and `socket.socket.connect` — runs the real code paths,
and asserts that every target is loopback.

`test_guard_detects_a_non_loopback_target` is the FAIL-path proof required by
this project's own rule: a check that cannot fail is worthless.
"""

from __future__ import annotations

import contextlib
import ipaddress
import socket
import subprocess
from urllib.parse import urlparse

import pytest

from friday import config
from friday.llm.client import LlamaClient
from friday.tools.search import SearchClient

_LOOPBACK_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", ""}


def _is_loopback(host: str) -> bool:
    host = str(host).strip("[]")
    if host.lower() in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False  # a name that is not localhost — treat as off-machine


@contextlib.contextmanager
def egress_guard():
    """Record every host this process tries to reach over IP.

    Records BEFORE delegating, so a target counts even when the connection
    fails — the attempt is the leak, not the completion. AF_UNIX is ignored:
    the PTT socket and $NOTIFY_SOCKET never leave the machine.
    """
    seen: list[str] = []
    real_gai = socket.getaddrinfo
    real_connect = socket.socket.connect

    def gai(host, port, *args, **kwargs):  # noqa: ANN001, ANN202
        seen.append(str(host))
        return real_gai(host, port, *args, **kwargs)

    def connect(self, address):  # noqa: ANN001, ANN202
        if self.family in (socket.AF_INET, socket.AF_INET6):
            seen.append(str(address[0]))
        return real_connect(self, address)

    socket.getaddrinfo = gai
    socket.socket.connect = connect
    try:
        yield seen
    finally:
        socket.getaddrinfo = real_gai
        socket.socket.connect = real_connect


def _offenders(seen: list[str]) -> list[str]:
    return sorted({h for h in seen if not _is_loopback(h)})


# --------------------------------------------------------------------------
# The guard must be able to fail.
# --------------------------------------------------------------------------

def test_guard_detects_a_non_loopback_target():
    """FAIL path. 192.0.2.1 is TEST-NET-1 (RFC 5737) — never routed, no DNS."""
    with egress_guard() as seen:
        with contextlib.suppress(OSError):
            socket.getaddrinfo("192.0.2.1", 443)
    assert _offenders(seen) == ["192.0.2.1"]


def test_guard_detects_a_non_loopback_hostname():
    """A name that is not localhost is off-machine, resolved or not."""
    with egress_guard() as seen:
        seen.append("huggingface.co")  # what D13 actually reached
    assert _offenders(seen) == ["huggingface.co"]


def test_guard_ignores_loopback_and_unix_sockets():
    with egress_guard() as seen:
        with contextlib.suppress(OSError):
            socket.getaddrinfo("127.0.0.1", 8080)
        with contextlib.suppress(OSError):
            socket.getaddrinfo("::1", 8888)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        with contextlib.suppress(OSError):
            s.connect("/run/user/1000/friday/does-not-exist.sock")
        s.close()
    assert _offenders(seen) == []


# --------------------------------------------------------------------------
# The real paths.
# --------------------------------------------------------------------------

def test_stt_backend_creation_reaches_no_network():
    """D13 regression: faster-whisper must load from the local cache only.

    `local_files_only=True` (friday/audio/stt.py) is what stops huggingface_hub
    resolving huggingface.co on every daemon start. Drop that argument and this
    test records the hostname and fails.
    """
    from friday.audio.stt import FasterWhisperBackend

    with egress_guard() as seen:
        backend = FasterWhisperBackend.create(
            config.STT_MODEL, compute_type=config.STT_COMPUTE, threads=2
        )
    if backend is None:
        pytest.skip(f"STT model {config.STT_MODEL!r} is not in the local cache")
    assert _offenders(seen) == [], f"STT load reached off-machine: {_offenders(seen)}"


def test_onnxruntime_telemetry_is_disabled_before_import():
    """ADR-112. `import onnxruntime` opens sockets to *.events.data.microsoft.com.

    Only the env var stops it (`disable_telemetry_events()` does not), and only
    if it is set first — so `friday/__init__.py` sets it, and importing anything
    from `friday` must be enough. Five components route through onnxruntime, so
    there is no single call site to guard instead.
    """
    import os
    import friday  # noqa: F401  — the import IS the thing under test

    assert os.environ.get("ORT_DISABLE_TELEMETRY") == "1"


def test_running_daemon_holds_no_non_loopback_connections():
    """Live check on the real process — the query that found D13."""
    pid = subprocess.run(
        ["systemctl", "--user", "show", "friday", "-p", "MainPID", "--value"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    if not pid or pid == "0":
        pytest.skip("friday.service is not running")
    try:
        out = subprocess.run(
            ["ss", "-tnp"], capture_output=True, text=True, timeout=5, check=False
        ).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("ss is unavailable")

    offenders = []
    for line in out.splitlines()[1:]:
        if f"pid={pid}," not in line:
            continue
        fields = line.split()
        if len(fields) < 5:
            continue
        peer = fields[4].rsplit(":", 1)[0]  # strip the port, keep [::1] intact
        if not _is_loopback(peer):
            offenders.append(peer)
    assert offenders == [], f"friday holds off-machine connections: {offenders}"


# --------------------------------------------------------------------------
# Config assertions. Necessary, never sufficient — see the module docstring.
# --------------------------------------------------------------------------

def test_default_endpoints_are_loopback_only():
    assert _is_loopback(urlparse(config.LLAMA_BASE_URL).hostname or "")
    assert _is_loopback(urlparse(config.SEARXNG_URL).hostname or "")


def test_clients_target_loopback():
    assert _is_loopback(urlparse(LlamaClient(base_url=config.LLAMA_BASE_URL).base_url).hostname or "")
    assert _is_loopback(urlparse(SearchClient(base_url=config.SEARXNG_URL).base_url).hostname or "")
