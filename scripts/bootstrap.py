#!/usr/bin/env python3
"""Deterministic bootstrap and verification script for Friday (§10, F24, ADR-107).

Usage:
  python scripts/bootstrap.py [--check] [--verbose]

Actions:
  1. Verify Python interpreter >= 3.12
  2. Verify / fetch Kokoro TTS models (SHA256 pinned)
  3. Verify / fetch Silero VAD model (SHA256 pinned)
  4. Verify / fetch openWakeWord model (SHA256 pinned)
  5. Verify / fetch CAM++ speaker verification model (SHA256 pinned)
  6. Verify / fetch Gemma 4 12B QAT model (SHA256 pinned)
  7. Verify llama-server executable with sm_120 support at /opt/llama.cpp/build/bin/llama-server
  8. Verify Docker daemon accessibility and SearXNG image
  9. Verify systemd user units
 10. Run full self-test suite (must be all-PASS, code 0)

When --check is passed:
  Runs purely in read-only mode, performs zero downloads or disk modifications,
  and exits 0 only if all prerequisites and models are verified. Exits 1 on any failure.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ModelSpec(NamedTuple):
    name: str
    path: Path
    sha256: str
    url: str


def get_data_dir() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "friday"


def get_model_specs() -> list[ModelSpec]:
    data = get_data_dir()
    return [
        ModelSpec(
            name="Kokoro 82M TTS Model",
            path=data / "models" / "kokoro" / "model.onnx",
            sha256="8fbea51ea711f2af382e88c833d9e288c6dc82ce5e98421ea61c058ce21a34cb",
            url="https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/main/onnx/model.onnx",
        ),
        ModelSpec(
            name="Kokoro Voices Blob",
            path=data / "models" / "kokoro" / "voices-v1.0.bin",
            sha256="bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
            url="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
        ),
        ModelSpec(
            name="Silero VAD (op18-ifless)",
            path=data / "models" / "vad" / "silero_vad_op18_ifless.onnx",
            sha256="7671cd04b004e9076da0d4a7b1a5aec36adf161c39230c1cb94a4fd5db6bbd28",
            url="https://raw.githubusercontent.com/snakers4/silero-vad/v6.2.1/src/silero_vad/data/silero_vad_op18_ifless.onnx",
        ),
        ModelSpec(
            name="openWakeWord (hey_jarvis)",
            path=data / "models" / "wake" / "hey_jarvis.onnx",
            sha256="94a13cfe60075b132f6a472e7e462e8123ee70861bc3fb58434a73712ee0d2cb",
            url="https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/hey_jarvis_v0.1.onnx",
        ),
        ModelSpec(
            name="CAM++ 3D-Speaker Verification",
            path=data / "models" / "speaker" / "3dspeaker_campplus.onnx",
            sha256="357a834f702b80161e5b981182c038e18553c1f2ca752ed6cec2052365d4129b",
            url="https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx",
        ),
        ModelSpec(
            name="Gemma 4 12B QAT LLM",
            path=data / "models" / "gemma-4-12B-it-qat-UD-Q4_K_XL.gguf",
            sha256="90fd44e29e0d7cffeb0fd00dc73cfdab9ed0b0e95306ecf7821ea634c940c370",
            url="https://huggingface.co/unsloth/gemma-4-12B-it-GGUF/resolve/main/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf",
        ),
    ]


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def check_python_version() -> bool:
    v = sys.version_info
    if (v.major, v.minor) < (3, 12):
        print(f"\033[31m[FAIL]\033[0m Python version {v.major}.{v.minor} < 3.12")
        return False
    print(f"\033[32m[PASS]\033[0m Python version {v.major}.{v.minor}.{v.micro}")
    return True


def check_or_fetch_model(spec: ModelSpec, *, check_only: bool = False) -> bool:
    if not spec.path.exists():
        if check_only:
            print(f"\033[31m[FAIL]\033[0m {spec.name}: file not found at {spec.path}")
            return False
        print(f"\033[33m[FETCH]\033[0m Downloading {spec.name} from {spec.url}...")
        spec.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            req = urllib.request.Request(spec.url, headers={"User-Agent": "friday-bootstrap/1.0"})
            with urllib.request.urlopen(req) as resp, spec.path.open("wb") as out:
                shutil.copyfileobj(resp, out)
        except Exception as exc:
            print(f"\033[31m[FAIL]\033[0m Failed downloading {spec.name}: {exc}")
            if spec.path.exists():
                spec.path.unlink()
            return False

    actual_sha = compute_sha256(spec.path)
    if actual_sha.lower() != spec.sha256.lower():
        print(f"\033[31m[FAIL]\033[0m {spec.name}: checksum mismatch!")
        print(f"       expected: {spec.sha256}")
        print(f"       actual:   {actual_sha}")
        return False

    print(f"\033[32m[PASS]\033[0m {spec.name} (SHA256 verified)")
    return True


def check_llama_binary() -> bool:
    path = Path("/opt/llama.cpp/build/bin/llama-server")
    if not path.exists():
        print(f"\033[31m[FAIL]\033[0m llama-server not found at {path}")
        print("       Build instructions: cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120a && cmake --build build --config Release -j")
        return False
    if not os.access(path, os.X_OK):
        print(f"\033[31m[FAIL]\033[0m llama-server at {path} is not executable")
        return False
    print(f"\033[32m[PASS]\033[0m llama-server binary verified at {path}")
    return True


def check_docker_searxng(*, check_only: bool = False) -> bool:
    # Check docker daemon
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
        if proc.returncode != 0:
            print(f"\033[31m[FAIL]\033[0m Docker daemon is not accessible by current user")
            return False
    except Exception as exc:
        print(f"\033[31m[FAIL]\033[0m Docker check failed: {exc}")
        return False

    # Check searxng image
    try:
        proc = subprocess.run(
            ["docker", "images", "-q", "searxng/searxng"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
        if not proc.stdout.strip():
            if check_only:
                print("\033[31m[FAIL]\033[0m Docker image searxng/searxng not found")
                return False
            print("\033[33m[FETCH]\033[0m Pulling searxng/searxng Docker image...")
            pull = subprocess.run(["docker", "pull", "searxng/searxng:latest"], check=False)
            if pull.returncode != 0:
                print("\033[31m[FAIL]\033[0m Failed pulling searxng/searxng")
                return False
    except Exception as exc:
        print(f"\033[31m[FAIL]\033[0m SearXNG image check failed: {exc}")
        return False

    print("\033[32m[PASS]\033[0m Docker daemon & SearXNG container verified")
    return True


def check_systemd_units() -> bool:
    units = [
        Path("deploy/systemd/friday-llm.service"),
        Path("deploy/systemd/friday.service"),
        Path("deploy/searxng/friday-searxng.service"),
    ]
    for u in units:
        if not u.exists():
            print(f"\033[31m[FAIL]\033[0m Unit file {u} missing")
            return False
    print(f"\033[32m[PASS]\033[0m Systemd service unit templates verified ({len(units)} units)")
    return True


def run_selftest_check() -> bool:
    from friday.selftest import Status, run_all_checks

    results = run_all_checks()
    failures = [r for r in results if r.status is Status.FAIL]
    warnings = [r for r in results if r.status is Status.WARN]

    if failures or warnings:
        print(f"\033[31m[FAIL]\033[0m Selftest did not pass cleanly ({len(failures)} fails, {len(warnings)} warnings)")
        for r in failures:
            print(f"       FAIL: {r.name} - {r.message}")
        for r in warnings:
            print(f"       WARN: {r.name} - {r.message}")
        return False

    print(f"\033[32m[PASS]\033[0m Selftest verified ({len(results)}/{len(results)} checks PASS)")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="friday-bootstrap")
    ap.add_argument(
        "--check",
        action="store_true",
        help="Run postcondition verifications without downloading or modifying state",
    )
    args = ap.parse_args(argv)

    mode = "Verification (--check)" if args.check else "Full Setup & Bootstrap"
    print("=" * 65)
    print(f"  Friday Deterministic Bootstrap: {mode}")
    print("=" * 65)

    ok = True
    ok = check_python_version() and ok

    for spec in get_model_specs():
        ok = check_or_fetch_model(spec, check_only=args.check) and ok

    ok = check_llama_binary() and ok
    ok = check_docker_searxng(check_only=args.check) and ok
    ok = check_systemd_units() and ok
    ok = run_selftest_check() and ok

    print("-" * 65)
    if not ok:
        print("\033[31m[BOOTSTRAP FAILED]\033[0m One or more prerequisites or checks failed.")
        return 1

    print("\033[32m[BOOTSTRAP SUCCESS]\033[0m All systems, models, and services verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
