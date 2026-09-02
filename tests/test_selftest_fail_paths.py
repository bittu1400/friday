"""Every check in here could once return PASS or WARN while the thing it
checks was broken (audit M-L3, M-L4, M-L9).

`gpu_arch` PASSed through an entire GPU outage. That is the pattern: a check
that cannot fail is worthless, so each of these tests drives the FAIL path.
"""

import pytest

from friday import selftest
from friday.selftest import Status


class _Proc:
    def __init__(self, stdout: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


# --- M-L3: gpu_arch on unparsable output -----------------------------------

def test_gpu_arch_does_not_pass_on_unparsable_output(monkeypatch):
    monkeypatch.setattr(selftest.shutil, "which", lambda n: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(
        selftest.subprocess, "run",
        lambda *a, **k: _Proc("NVIDIA GeForce RTX 5070 Laptop GPU, N/A\n"),
    )
    assert selftest.check_gpu_arch().status is not Status.PASS


def test_gpu_arch_still_passes_on_this_machines_real_output(monkeypatch):
    monkeypatch.setattr(selftest.shutil, "which", lambda n: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(
        selftest.subprocess, "run",
        lambda *a, **k: _Proc("NVIDIA GeForce RTX 5070 Laptop GPU, 12.0\n"),
    )
    assert selftest.check_gpu_arch().status is Status.PASS


# --- M-L4: the bind audit's holes -------------------------------------------

_SS_HEADER = "State  Recv-Q Send-Q Local Address:Port  Peer Address:Port\n"


def test_a_lan_ip_bind_is_a_violation_even_though_it_is_not_a_wildcard(monkeypatch):
    """Invariant #8 says loopback only. Binding 192.168.1.5:8080 exposes
    llama-server to the LAN and passed the old wildcard-only check."""
    out = _SS_HEADER + "LISTEN 0 4096 192.168.1.5:8080 0.0.0.0:*\n"
    assert selftest._ss_violations(out)


def test_an_ipv6_wildcard_is_a_violation(monkeypatch):
    out = _SS_HEADER + "LISTEN 0 4096 [::]:8888 [::]:*\n"
    assert selftest._ss_violations(out)


def test_loopback_binds_are_not_violations():
    out = (
        _SS_HEADER
        + "LISTEN 0 4096 127.0.0.1:8080 0.0.0.0:*\n"
        + "LISTEN 0 4096 [::1]:8888 [::]:*\n"
        + "LISTEN 0 4096 0.0.0.0:22 0.0.0.0:*\n"  # sshd is not our business
    )
    assert selftest._ss_violations(out) == []


def test_the_proc_fallback_reads_tcp6_too():
    """`/proc/net/tcp6` was never read, so an IPv6 wildcard bind was invisible
    whenever `ss` was missing — exactly the degraded state the check is for."""
    # 32 hex chars, little-endian words: the IPv6 wildcard, port 8080 (0x1F90)
    v6 = (
        "  sl  local_address remote_address st\n"
        "   0: 00000000000000000000000000000000:1F90 "
        "00000000000000000000000000000000:0000 0A\n"
    )
    assert selftest._proc_net_violations(v6)


def test_the_proc_fallback_accepts_ipv6_loopback():
    v6 = (
        "  sl  local_address remote_address st\n"
        "   0: 00000000000000000000000001000000:1F90 "
        "00000000000000000000000000000000:0000 0A\n"
    )
    assert selftest._proc_net_violations(v6) == []


def test_the_proc_fallback_accepts_ipv4_loopback_and_flags_the_wildcard():
    v4_ok = "  sl local_address rem st\n   0: 0100007F:1F90 00000000:0000 0A\n"
    v4_bad = "  sl local_address rem st\n   0: 00000000:1F90 00000000:0000 0A\n"
    assert selftest._proc_net_violations(v4_ok) == []
    assert selftest._proc_net_violations(v4_bad)


def test_an_unparsable_address_is_treated_as_a_violation():
    """Fail closed: an address this parser does not understand is not evidence
    of loopback-only binding."""
    weird = "  sl local_address rem st\n   0: ZZZZ:1F90 00000000:0000 0A\n"
    assert selftest._proc_net_violations(weird)


# --- M-L9: WARN where the truth is FAIL -------------------------------------

def test_audio_devices_fails_when_enumeration_raises(monkeypatch):
    import sys, types

    fake = types.ModuleType("sounddevice")
    def boom(*a, **k):
        raise OSError("PortAudio not initialized")
    fake.query_devices = boom
    fake.default = types.SimpleNamespace(device=(0, 0))
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    assert selftest.check_audio_devices().status is Status.FAIL


def test_llm_on_gpu_fails_rather_than_warns_on_a_surprise(monkeypatch):
    """It is the one check that caught the CPU-fallback outage. A surprise in
    it must not be softened to WARN — that is how the outage hid for hours."""
    monkeypatch.setattr(selftest.shutil, "which", lambda n: "/usr/bin/nvidia-smi")

    def boom(*a, **k):
        raise RuntimeError("nvidia-smi exploded")

    monkeypatch.setattr(selftest.subprocess, "run", boom)
    assert selftest.check_llm_on_gpu().status is Status.FAIL


def test_check_database_does_not_create_the_database_it_verifies(tmp_path):
    """It opened the DB to read the schema version, which CREATES a missing
    one — then reported PASS on a database that did not exist a moment ago."""
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    db = state / "memory.db"

    res = selftest.check_database(db)

    assert res.status is Status.FAIL
    assert not db.exists(), "the check created the database it claims to verify"


# --- F28: power profile verification ---------------------------------------

def test_power_profile_warns_on_powersave_profile(monkeypatch):
    monkeypatch.setattr(
        selftest.subprocess, "run",
        lambda *a, **k: _Proc("power-saver\n", returncode=0),
    )
    res = selftest.check_power_profile()
    assert res.status is Status.WARN
    assert "power-saver" in res.message


def test_power_profile_warns_on_acpi_quiet_profile(monkeypatch, tmp_path):
    # Simulate powerprofilesctl failing and falling back to platform_profile
    def fake_run(*a, **k):
        raise FileNotFoundError("no powerprofilesctl")

    fake_sysfs = tmp_path / "platform_profile"
    fake_sysfs.write_text("quiet\n")

    monkeypatch.setattr(selftest.subprocess, "run", fake_run)
    monkeypatch.setattr(selftest, "Path", lambda p: fake_sysfs if str(p) == "/sys/firmware/acpi/platform_profile" else Path(p))

    res = selftest.check_power_profile()
    assert res.status is Status.WARN
    assert "quiet" in res.message

