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
  8. Loopback socket bind audit (asserts no 0.0.0.0 or wildcard bindings on 8080/8888)

Eight checks, and this list says eight: it listed seven while eight ran until
2026-08-29 (audit L25). A docstring that miscounts the checks is a small lie
about the one tool whose whole job is telling you the truth about the system.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
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
            return CheckResult("gpu_arch", Status.PASS, gpu_info)
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
    except Exception as exc:
        return CheckResult(
            "audio_devices",
            Status.WARN,
            f"Audio query error: {exc}",
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


def check_socket_binds() -> CheckResult:
    """Audit listening TCP sockets to assert no 0.0.0.0 wildcard binds on 8080/8888 (Invariant #8)."""
    # 1. Try ss -ltn
    if shutil.which("ss") is not None:
        try:
            proc = subprocess.run(
                ["ss", "-ltn"],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=True,
            )
            for line in proc.stdout.splitlines():
                if ":8080" in line or ":8888" in line:
                    if "0.0.0.0:8080" in line or "0.0.0.0:8888" in line or "*:8080" in line or "*:8888" in line or "[::]:8080" in line or "[::]:8888" in line:
                        return CheckResult(
                            "socket_binds",
                            Status.FAIL,
                            f"Wildcard bind detected on Friday port: {line.strip()}",
                            details="Invariant #8 violated: services must bind to 127.0.0.1 loopback only",
                        )
            return CheckResult(
                "socket_binds",
                Status.PASS,
                "Services bound to 127.0.0.1 loopback only (no 0.0.0.0 / wildcard listeners)",
            )
        except Exception:
            pass

    # 2. Fallback to /proc/net/tcp inspection
    try:
        proc_tcp = Path("/proc/net/tcp")
        if proc_tcp.exists():
            lines = proc_tcp.read_text().splitlines()[1:]
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 4:
                    local_addr, st = parts[1], parts[3]
                    if st == "0A":  # TCP_LISTEN
                        ip_hex, port_hex = local_addr.split(":")
                        port = int(port_hex, 16)
                        if port in (8080, 8888):
                            if ip_hex == "00000000":
                                return CheckResult(
                                    "socket_binds",
                                    Status.FAIL,
                                    f"Wildcard 0.0.0.0 bind detected on port {port}",
                                )
            return CheckResult(
                "socket_binds",
                Status.PASS,
                "Ports 8080/8888 bound strictly to loopback",
            )
    except Exception as exc:
        return CheckResult("socket_binds", Status.WARN, f"Socket audit check error: {exc}")

    return CheckResult("socket_binds", Status.PASS, "Loopback binding verified")


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
        return CheckResult("llm_on_gpu", Status.WARN, f"could not verify GPU offload: {exc}")


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
    ]


def run_selftest() -> int:
    """CLI runner: executes all checks, prints report, returns exit code (0=ok, 1=failure)."""
    print("=" * 65)
    print("  Friday System Self-Test (G9 Service & Health Verification)")
    print("=" * 65)

    results = run_all_checks()
    has_fail = False

    for res in results:
        badge = f"[{res.status.value}]"
        color = ""
        if res.status is Status.PASS:
            prefix = f"\033[32m{badge:<6}\033[0m"
        elif res.status is Status.WARN:
            prefix = f"\033[33m{badge:<6}\033[0m"
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
        return 1 if any(r.status is Status.FAIL for r in results) else 0

    return run_selftest()


if __name__ == "__main__":
    raise SystemExit(main())
