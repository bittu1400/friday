"""Friday Self-Test Suite (`friday --selftest` / `just selftest`).

Performs full-system sanity and health verification (architecture.md §7, friday.md G9):
  1. llama-server reachability & health (port 8080 loopback)
  2. SearXNG reachability & health (port 8888 loopback)
  3. GPU architecture check (sm_120 / Blackwell compute capability 12.0)
  4. LLM actually ON the GPU — that llama-server holds VRAM, not merely that a
     GPU exists. Added after llama-server served from CPU for hours while
     `gpu_arch` reported PASS throughout (2026-08-25).
  5. Database permissions & schema version (0700 dir, 0600 file incl. the
     `-wal`/`-shm` sidecars, schema >= 1). Perms are read BEFORE the database
     is opened, because opening it repairs them — a check that measured its own
     repair could never fail.
  6. Audio subsystem (input mic & output playback devices available)
  7. Panic switch status (~/.local/state/friday/DISABLED)
  8. Loopback socket bind audit: ANY non-loopback bind on 8080/8888 fails, not
     just wildcard literals, across `ss` and both `/proc/net/tcp` and `tcp6`.
  9. Power profile verification (F28 / ADR-107): ensures power profile is
     `balanced`/`performance` via `powerprofilesctl get` or sysfs; warns on `power-saver`.
 10. The RUNNING unit matches the committed one (M16 / OQ-66): asks systemd,
     not the file. The installed unit is a SYMLINK to `deploy/systemd/`, so a
     file comparison always matches — which is why one stayed green through the
     weeks systemd reported `Type=simple`, `WatchdogUSec=0`, `NeedDaemonReload=yes`
     and the watchdog had never once fired.

Every check must be able to FAIL (M-L3/L4/L9, 2026-08-29). `gpu_arch` returned
PASS on output it could not parse — and PASSed through a whole GPU outage;
`audio_devices` and `llm_on_gpu` returned WARN for "I could not tell", which is
not the same as "probably fine"; `check_database` opened the database to read
its version, which CREATED a missing one, then reported PASS on the file it had
just conjured. A check that cannot fail is worthless.

Ten checks, and this list says ten. A docstring that miscounts the checks is a
small lie about the one tool whose whole job is telling you the truth about the system.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
import ipaddress
import shutil
import struct
import stat
import subprocess
import urllib.request

from . import config
from .store.db import Database


class Status(Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    message: str
    details: str = ""


def check_llama_server(base_url: str = config.LLAMA_BASE_URL) -> CheckResult:
    """Verify llama-server is reachable and reports healthy status."""
    url = f"{base_url.rstrip('/')}/health"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "friday-selftest/1.0"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                srv_status = data.get("status", "unknown")
                return CheckResult(
                    "llama-server",
                    Status.PASS,
                    f"Reachable at {base_url} (status: {srv_status})",
                )
            return CheckResult(
                "llama-server",
                Status.FAIL,
                f"HTTP status {resp.status} from {url}",
            )
    except urllib.error.HTTPError as exc:
        if exc.code == 503:
            try:
                data = json.loads(exc.read().decode("utf-8"))
                if data.get("status") == "loading model":
                    return CheckResult(
                        "llama-server",
                        Status.PASS,
                        f"Reachable at {base_url} (status: loading model)",
                    )
            except Exception:
                pass
        return CheckResult(
            "llama-server",
            Status.FAIL,
            f"Cannot connect to {url}: HTTP {exc.code} {exc.reason}",
            details="Ensure friday-llm.service is running or run `just serve`",
        )
    except Exception as exc:
        return CheckResult(
            "llama-server",
            Status.FAIL,
            f"Cannot connect to {url}: {exc}",
            details="Ensure friday-llm.service is running or run `just serve`",
        )


def check_searxng(url: str = config.SEARXNG_URL) -> CheckResult:
    """Verify local SearXNG search proxy is reachable."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "friday-selftest/1.0"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status in (200, 302):
                return CheckResult(
                    "searxng",
                    Status.PASS,
                    f"Reachable at {url} (HTTP {resp.status})",
                )
            return CheckResult(
                "searxng",
                Status.FAIL,
                f"HTTP status {resp.status} from {url}",
            )
    except Exception as exc:
        return CheckResult(
            "searxng",
            Status.FAIL,
            f"Cannot connect to {url}: {exc}",
            details="Ensure friday-searxng.service is active (`just searxng start`)",
        )


def check_gpu_arch() -> CheckResult:
    """Verify Blackwell sm_120 architecture via nvidia-smi."""
    if shutil.which("nvidia-smi") is None:
        return CheckResult(
            "gpu_arch",
            Status.WARN,
            "nvidia-smi not found in PATH",
            details="Cannot verify GPU compute capability without nvidia-smi",
        )
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,compute_cap", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=True,
        )
        output = proc.stdout.strip()
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if not lines:
            return CheckResult("gpu_arch", Status.FAIL, "nvidia-smi returned no GPUs")
        
        gpu_info = lines[0]
        # Example: "NVIDIA GeForce RTX 5070 Laptop GPU, 12.0"
        parts = [p.strip() for p in gpu_info.split(",")]
        name = parts[0]
        cap_str = parts[1] if len(parts) > 1 else "unknown"

        try:
            cap_float = float(cap_str)
            if cap_float >= 12.0:
                return CheckResult(
                    "gpu_arch",
                    Status.PASS,
                    f"{name} (compute {cap_str} - sm_120 verified)",
                )
            return CheckResult(
                "gpu_arch",
                Status.WARN,
                f"{name} (compute {cap_str} < 12.0)",
                details="Expected sm_120 / Blackwell architecture",
            )
        except ValueError:
            # M-L3: this used to return PASS. "I could not read the answer" is
            # not "the answer was yes" — and this is the check that reported
            # PASS through an entire GPU outage on 2026-08-25.
            return CheckResult(
                "gpu_arch",
                Status.WARN,
                f"could not parse compute capability from nvidia-smi: {gpu_info!r}",
                details="Expected `<name>, <compute_cap>` — the architecture is UNVERIFIED",
            )
    except Exception as exc:
        return CheckResult(
            "gpu_arch",
            Status.FAIL,
            f"nvidia-smi query failed: {exc}",
        )


def _wal_sidecars(db_path: Path) -> list[Path]:
    """The `-wal`/`-shm` files that exist right now, if any."""
    return [
        p
        for p in (
            db_path.with_name(db_path.name + "-wal"),
            db_path.with_name(db_path.name + "-shm"),
        )
        if p.exists()
    ]


def check_database(db_path: Path = config.MEMORY_DB) -> CheckResult:
    """Verify database existence, permissions (0700 dir, 0600 file), and schema version."""
    state_dir = db_path.parent
    if not state_dir.exists():
        return CheckResult(
            "database",
            Status.FAIL,
            f"State directory {state_dir} does not exist",
        )

    # Check directory permissions (0700)
    dir_mode = state_dir.stat().st_mode & 0o777
    if dir_mode != 0o700:
        return CheckResult(
            "database",
            Status.FAIL,
            f"State directory mode is {oct(dir_mode)}, expected 0700 (FR-50)",
        )

    if not db_path.exists():
        # M-L9: `Database(db_path)` CREATES a missing database, so this check
        # used to conjure the file and then report PASS on it — a check that
        # cannot fail. The daemon creates the DB; this one only inspects.
        return CheckResult(
            "database",
            Status.FAIL,
            f"No database at {db_path} (run the daemon once to create it)",
        )

    # Perms are checked BEFORE the database is opened, because opening it
    # repairs them (`Database._secure_sidecars`). Checking afterwards would
    # report the state this function just created — a check that cannot fail,
    # the exact pattern `gpu_arch` was caught in. Report what is on disk; the
    # daemon repairs it at runtime.
    #
    # The sidecars matter as much as the main file: the WAL holds preferences,
    # notes and reminder text in flight, and only the main file was checked
    # before (M-T2).
    for path in (db_path, *_wal_sidecars(db_path)):
        if not path.exists():
            continue
        file_mode = path.stat().st_mode & 0o777
        if file_mode != 0o600:
            return CheckResult(
                "database",
                Status.FAIL,
                f"{path.name} mode is {oct(file_mode)}, expected 0600 (FR-50)",
            )

    # Initialize/open DB to verify migrations and WAL mode
    try:
        db = Database(db_path)
        version = db.version
        db.close()
    except Exception as exc:
        return CheckResult(
            "database",
            Status.FAIL,
            f"Failed opening SQLite database: {exc}",
        )

    # A DB this check just created still has to come out at 0600.
    for path in (db_path, *_wal_sidecars(db_path)):
        file_mode = path.stat().st_mode & 0o777
        if file_mode != 0o600:
            return CheckResult(
                "database",
                Status.FAIL,
                f"{path.name} mode is {oct(file_mode)}, expected 0600 (FR-50)",
            )

    if version < 1:
        return CheckResult(
            "database",
            Status.FAIL,
            f"Database schema version is {version}, expected >= 1",
        )

    return CheckResult(
        "database",
        Status.PASS,
        f"SQLite at {db_path} (mode 0600, dir 0700, schema v{version})",
    )


def check_audio_devices() -> CheckResult:
    """Verify default audio input and output devices."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        default_in, default_out = sd.default.device
        if default_in is None or default_in < 0:
            return CheckResult(
                "audio_devices",
                Status.WARN,
                "No default audio input device found (voice input unavailable)",
            )
        if default_out is None or default_out < 0:
            return CheckResult(
                "audio_devices",
                Status.WARN,
                "No default audio output device found (voice output unavailable)",
            )
        in_name = devices[default_in]["name"]
        out_name = devices[default_out]["name"]
        return CheckResult(
            "audio_devices",
            Status.PASS,
            f"Input: {in_name} | Output: {out_name}",
        )
    except ImportError as exc:
        return CheckResult(
            "audio_devices",
            Status.WARN,
            f"sounddevice not installed: {exc}",
            details="Text mode still works; voice does not",
        )
    except Exception as exc:
        # M-L9: this was WARN. Enumeration raising means PortAudio is broken —
        # the mic and the speaker are both gone, and a "warning" is the wrong
        # word for an assistant that can no longer hear or speak.
        return CheckResult(
            "audio_devices",
            Status.FAIL,
            f"Audio device enumeration failed: {exc}",
            details="Voice in AND out are unavailable — PortAudio cannot enumerate devices",
        )


def check_panic_switch() -> CheckResult:
    """Check whether emergency panic switch is active."""
    if config.is_disabled():
        reasons = []
        if config.PANIC_FILE.exists():
            reasons.append(f"file present ({config.PANIC_FILE})")
        if os.environ.get(config.PANIC_ENV):
            reasons.append(f"env var {config.PANIC_ENV} set")
        return CheckResult(
            "panic_switch",
            Status.WARN,
            f"PANIC SWITCH ENGAGED ({', '.join(reasons)}) - all tool execution blocked",
        )
    return CheckResult(
        "panic_switch",
        Status.PASS,
        "Disarmed (normal dispatch allowed)",
    )


_FRIDAY_PORTS: tuple[int, ...] = (8080, 8888)


def _is_loopback(host: str) -> bool:
    """True only for an address that cannot be reached from another machine.

    Fails CLOSED: anything unparsable (`*`, an empty field, garbage) is NOT
    loopback. Invariant #8's check exists for the degraded states, so it may
    not give an address the benefit of the doubt.
    """
    h = host.strip().strip("[]")
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def _ss_violations(stdout: str) -> list[str]:
    """Lines from `ss -ltn` that listen on a Friday port off loopback.

    M-L4: this used to match the literal strings `0.0.0.0:`/`*:`/`[::]:` only,
    so a bind to this laptop's LAN address (192.168.x.y:8080) passed the audit
    that exists precisely to catch it.
    """
    out: list[str] = []
    # Every line is parsed, header included: it is skipped because its 4th
    # field ("Local") has no `:port`, not because of its position. A check that
    # must fail closed cannot assume the header is exactly one line.
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        host, _, port = parts[3].rpartition(":")
        if not port.isdigit() or int(port) not in _FRIDAY_PORTS:
            continue
        if not _is_loopback(host):
            out.append(line.strip())
    return out


def _hex_to_ip(ip_hex: str) -> str:
    """Decode a /proc/net/tcp{,6} local address. Empty string if unrecognised."""
    try:
        if len(ip_hex) == 8:  # IPv4, one little-endian word
            return str(ipaddress.IPv4Address(struct.unpack("<I", bytes.fromhex(ip_hex))[0]))
        if len(ip_hex) == 32:  # IPv6, four little-endian words
            raw = b"".join(
                struct.pack(">I", struct.unpack("<I", bytes.fromhex(ip_hex[i : i + 8]))[0])
                for i in range(0, 32, 8)
            )
            return str(ipaddress.IPv6Address(raw))
    except (ValueError, struct.error):
        return ""
    return ""


def _proc_net_violations(text: str) -> list[str]:
    """Listening Friday-port sockets in /proc/net/tcp or tcp6 that are not
    loopback. `tcp6` was never read at all before (M-L4)."""
    out: list[str] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[3] != "0A":  # 0A == TCP_LISTEN (skips the header)
            continue
        ip_hex, _, port_hex = parts[1].partition(":")
        try:
            port = int(port_hex, 16)
        except ValueError:
            continue
        if port not in _FRIDAY_PORTS:
            continue
        ip = _hex_to_ip(ip_hex)
        if not _is_loopback(ip):  # "" (unparsable) lands here too, on purpose
            out.append(f"{ip or ip_hex}:{port}")
    return out


def check_socket_binds() -> CheckResult:
    """Assert nothing listens on 8080/8888 off loopback (invariant #8, T6).

    Not just wildcards: ANY address another machine could reach is a violation.
    """
    if shutil.which("ss") is not None:
        try:
            proc = subprocess.run(
                ["ss", "-ltn"],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=True,
            )
            bad = _ss_violations(proc.stdout)
            if bad:
                return CheckResult(
                    "socket_binds",
                    Status.FAIL,
                    f"Non-loopback bind on a Friday port: {bad[0]}",
                    details="Invariant #8 violated: services must bind to 127.0.0.1 only",
                )
            return CheckResult(
                "socket_binds",
                Status.PASS,
                "Services bound to 127.0.0.1 loopback only (no 0.0.0.0 / wildcard listeners)",
            )
        except Exception:
            pass  # fall through to /proc

    try:
        seen_any = False
        for name in ("/proc/net/tcp", "/proc/net/tcp6"):
            path = Path(name)
            if not path.exists():
                continue
            seen_any = True
            bad = _proc_net_violations(path.read_text())
            if bad:
                return CheckResult(
                    "socket_binds",
                    Status.FAIL,
                    f"Non-loopback bind on a Friday port: {bad[0]} (from {name})",
                    details="Invariant #8 violated: services must bind to 127.0.0.1 only",
                )
        if seen_any:
            return CheckResult(
                "socket_binds", Status.PASS, "Ports 8080/8888 bound strictly to loopback"
            )
    except Exception as exc:
        return CheckResult("socket_binds", Status.WARN, f"Socket audit check error: {exc}")

    # Neither `ss` nor /proc/net answered. That is not evidence of compliance.
    return CheckResult(
        "socket_binds",
        Status.WARN,
        "Could not audit listening sockets (no `ss`, no /proc/net/tcp)",
        details="Invariant #8 is UNVERIFIED on this run",
    )


def check_llm_on_gpu() -> CheckResult:
    """Verify llama-server is actually RUNNING ON the GPU, not just that a GPU
    exists (ADR-018, invariant #6).

    `check_gpu_arch` asks nvidia-smi whether a Blackwell card is present. It
    reported PASS for hours on 2026-08-25 while llama-server was silently
    CPU-only: it had lost the CUDA race at boot with
    `ggml_cuda_init: failed to initialize CUDA: no CUDA-capable device is
    detected` / `no usable GPU found, --gpu-layers option will be ignored`,
    loaded zero layers to VRAM, and still answered /health with "ok". A
    completion took 3.18 s instead of 0.14 s — a 22x regression that every
    existing check called green. The only honest signal is VRAM actually held
    by the llama-server process, so that is what this asserts.
    """
    if shutil.which("nvidia-smi") is None:
        return CheckResult("llm_on_gpu", Status.WARN, "nvidia-smi not found in PATH")
    try:
        pids = subprocess.run(
            ["pgrep", "-x", "llama-server"], capture_output=True, text=True, timeout=5.0
        ).stdout.split()
        if not pids:
            return CheckResult(
                "llm_on_gpu", Status.WARN, "llama-server is not running (start friday-llm)"
            )
        proc = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5.0, check=True,
        )
        on_gpu = {
            parts[0].strip(): parts[1].strip()
            for line in proc.stdout.splitlines()
            if len(parts := line.split(",")) == 2
        }
        for pid in pids:
            if pid in on_gpu and int(on_gpu[pid]) > 500:  # a loaded 7B Q4 is GBs
                return CheckResult(
                    "llm_on_gpu", Status.PASS,
                    f"llama-server pid {pid} holds {on_gpu[pid]} MiB VRAM (GPU offload live)",
                )
        return CheckResult(
            "llm_on_gpu", Status.FAIL,
            "llama-server is running but holds NO VRAM — it fell back to CPU",
            details=(
                "Inference is ~22x slower and every latency budget is void. Usually a "
                "boot race or a kernel/driver upgrade without a reboot. Fix: "
                "`systemctl --user restart friday-llm`, then re-run this check. Confirm "
                "with: journalctl --user -u friday-llm | grep ggml_cuda"
            ),
        )
    except Exception as exc:
        # M-L9: WARN here softened the ONE check that caught the silent
        # CPU-fallback outage. "I could not tell" is not "probably fine".
        return CheckResult(
            "llm_on_gpu",
            Status.FAIL,
            f"could not verify GPU offload: {exc}",
            details="Unverified means unusable: every latency budget assumes the GPU",
        )


def check_power_profile() -> CheckResult:
    """Verify system power profile is balanced/performance, not power-saver (F28 / ADR-107).

    The scaling governor and scaling_max_freq are identical across all profiles ('powersave'
    and 5.4 GHz). Only powerprofilesctl get or /sys/firmware/acpi/platform_profile report
    the real profile. A power-saver profile imposes a +406ms STT latency penalty.
    """
    profile = None
    # 1. Try powerprofilesctl get
    try:
        proc = subprocess.run(
            ["powerprofilesctl", "get"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if proc.returncode == 0:
            profile = proc.stdout.strip()
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired):
        pass

    # 2. Fallback to ACPI platform_profile sysfs
    if not profile:
        sysfs_path = Path("/sys/firmware/acpi/platform_profile")
        if sysfs_path.exists():
            try:
                profile = sysfs_path.read_text(encoding="utf-8").strip()
            except OSError:
                pass

    if not profile:
        return CheckResult(
            "power_profile",
            Status.PASS,
            "Power profile not managed on host (desktop/unsupported)",
        )

    profile_clean = profile.lower().strip()
    if profile_clean in ("power-saver", "powersave", "quiet", "low-power"):
        return CheckResult(
            "power_profile",
            Status.WARN,
            f"Power profile is '{profile_clean}' (+406ms STT latency penalty; recommend 'balanced')",
            details="Run `powerprofilesctl set balanced` to restore full interactive performance",
        )

    return CheckResult(
        "power_profile",
        Status.PASS,
        f"Profile is '{profile_clean}'",
    )


# The four directives this project has actually been bitten by, and the value
# systemd must REPORT for each. `tests/test_service_unit.py` pins them in the
# file; the installed unit is a symlink to that file, so the file check can
# never disagree — which is why it would have stayed green through the weeks
# `systemctl show` said `Type=simple`, `WatchdogUSec=0`, `NeedDaemonReload=yes`
# (M16). Editing a unit is not deploying it: this asks systemd.
_UNIT_EXPECTED: dict[str, str] = {
    "Type": "notify",       # ADR-109 — the watchdog needs it; it read `simple`
    "WatchdogUSec": "10s",  # ADR-109 — it read 0 while WatchdogSec=10s was committed
    "PrivateTmp": "no",     # D30 / ADR-115 — it hid Chromium's singleton socket
    "KillMode": "process",  # D29 / ADR-114 — apps died with the daemon
}


def check_unit_deployed(unit: str = "friday") -> CheckResult:
    """Verify the unit systemd is RUNNING matches the one in the repo (OQ-66).

    Answers the live half of the question `tests/test_service_unit.py` can only
    ask of a file. FAILs on a pending daemon-reload or on any of the four
    load-bearing directives disagreeing; WARNs when there is no user bus or the
    unit is not installed (foreground `just voice` is a supported mode).
    """
    if shutil.which("systemctl") is None:
        return CheckResult("unit_deployed", Status.PASS, "Not a systemd host")

    props_wanted = ["LoadState", "NeedDaemonReload", *_UNIT_EXPECTED]
    argv = ["systemctl", "--user", "show", unit]
    for key in props_wanted:
        argv += ["-p", key]

    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=3.0, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckResult(
            "unit_deployed", Status.WARN, f"systemctl unavailable ({type(exc).__name__})"
        )
    if proc.returncode != 0:
        return CheckResult(
            "unit_deployed", Status.WARN, "No systemd user bus (running unit unknown)"
        )

    props = dict(
        line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line
    )

    if props.get("LoadState") != "loaded":
        return CheckResult(
            "unit_deployed",
            Status.WARN,
            f"{unit}.service is not loaded (LoadState={props.get('LoadState', '?')})",
            details="Install the units: see docs/systemd-setup.md",
        )

    if props.get("NeedDaemonReload") == "yes":
        return CheckResult(
            "unit_deployed",
            Status.FAIL,
            "The unit on disk differs from the one systemd is running",
            details="systemctl --user daemon-reload && systemctl --user restart " + unit,
        )

    drift = [
        f"{k}={props.get(k, '?')} (want {want})"
        for k, want in _UNIT_EXPECTED.items()
        if props.get(k) != want
    ]
    if drift:
        return CheckResult(
            "unit_deployed",
            Status.FAIL,
            "Running unit disagrees with the committed one: " + ", ".join(drift),
            details="systemctl --user daemon-reload && systemctl --user restart " + unit,
        )

    return CheckResult(
        "unit_deployed",
        Status.PASS,
        f"Running {unit}.service matches the repo (reload clean, "
        f"{len(_UNIT_EXPECTED)} directives verified)",
    )


def run_all_checks() -> list[CheckResult]:
    """Execute all self-test checks and return results."""
    return [
        check_llama_server(),
        check_searxng(),
        check_gpu_arch(),
        check_llm_on_gpu(),
        check_database(),
        check_audio_devices(),
        check_panic_switch(),
        check_socket_binds(),
        check_power_profile(),
        check_unit_deployed(),
    ]


def run_selftest() -> int:
    """CLI runner: executes all checks, prints report, returns exit code (0=ok, 1=fail, 2=warn)."""
    print("=" * 65)
    print("  Friday System Self-Test (G9 Service & Health Verification)")
    print("=" * 65)

    results = run_all_checks()
    has_fail = False
    has_warn = False

    for res in results:
        badge = f"[{res.status.value}]"
        if res.status is Status.PASS:
            prefix = f"\033[32m{badge:<6}\033[0m"
        elif res.status is Status.WARN:
            prefix = f"\033[33m{badge:<6}\033[0m"
            has_warn = True
        else:
            prefix = f"\033[31m{badge:<6}\033[0m"
            has_fail = True

        print(f"{prefix} {res.name:<15} {res.message}")
        if res.details:
            print(f"       -> \033[90m{res.details}\033[0m")

    print("-" * 65)
    if has_fail:
        print("\033[31m[FAILED]\033[0m One or more self-test checks failed.")
        return 1
    if has_warn:
        print("\033[33m[DEGRADED]\033[0m One or more self-test checks produced warnings.")
        return 2
    print("\033[32m[PASSED]\033[0m All required system checks passed successfully.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="friday-selftest")
    ap.add_argument("--json", action="store_true", help="output check results as JSON")
    args = ap.parse_args(argv)

    if args.json:
        results = run_all_checks()
        out = [
            {
                "name": r.name,
                "status": r.status.value,
                "message": r.message,
                "details": r.details,
            }
            for r in results
        ]
        print(json.dumps(out, indent=2))
        if any(r.status is Status.FAIL for r in results):
            return 1
        if any(r.status is Status.WARN for r in results):
            return 2
        return 0

    return run_selftest()


if __name__ == "__main__":
    raise SystemExit(main())
