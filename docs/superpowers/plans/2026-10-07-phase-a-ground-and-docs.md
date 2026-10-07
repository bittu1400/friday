# Phase A — Ground and docs: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove v1 still stands on today's machine, write the 2026-10-07 owner decisions into the
decision record, close the two security/integrity gaps the Friday 2 re-check found (an
unauthenticated `llama-server`, and model pins checked only by `bootstrap`), and cut CLAUDE.md
from 1,532 lines to about 250 without losing anything.

**Architecture:** No new subsystem. Two small code changes:
- `friday/llm/client.py` sends a bearer key that `llama-server` now requires; both launch paths
  generate a fresh key per start.
- A new `friday/models.py` becomes the one home of the SHA256 pins. `scripts/bootstrap.py` and
  the daemon's start both read it.

The rest is the decision record and a doc split: history moves to `docs/archive/`, and the still-valid
lessons move to `docs/lessons.md`.

**Tech Stack:** Python 3.12 stdlib (`hashlib`, `urllib`), systemd user units, `just`,
`llama-server` (`/opt/llama.cpp/build/bin/llama-server`, which has `--api-key-file`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-07-friday2-merge-design.md` (§2, §3.1 last two rows,
§5 "A").

## Global Constraints

- Python 3.12 via `uv`; stdlib only for anything in this phase. **No new dependency.**
- `pytest` green at the end of every task; `just eval` **0 regressions** on the 91 fixtures
  (**91/91** on 2026-09-04).
- `just grammar` stays **byte-identical**: this phase changes no capability.
- Nothing binds beyond 127.0.0.1 (invariant #8). Subprocess rules unchanged (invariant #3).
- A change touching a hard-invariant or security line ships with a mutation of that line, run so
  the suite goes RED, then reverted **by copying the file aside and back, never
  `git checkout -- <file>`** (ADR-116 amendment).
- Evidence (command output) is pasted into `progress.md` for every claim of done (rule 6).
- Commit locally after each task. **Never push without asking** (owner preference).
- `config.MEMORY_DB` is `~/.local/state/friday/memory.db`. **Never** `~/.local/share/friday/…`:
  `sqlite3` creates an empty database at a wrong path (D36).
- Friday 2's daemon and pill hold the mic and ~5.6 GB of VRAM. They are stopped **only after the
  owner says yes in chat at that moment**.

## Review Focus

1. **`llama-server` restarts while the daemon keeps running.** The key changes on every start, so
   the client must read the key file per request, not once. Pinned in Task 3,
   `test_a_rotated_key_is_picked_up_without_restarting_the_client`.
2. **The key file is missing** (the service is down, or someone runs `just eval` against a server
   started by hand without a key). The request goes out without a header. A 401 becomes
   `LlamaServerError(401)`, which surfaces as `E_LLM_DOWN` with "returned HTTP 401" in the log and
   never crashes the turn. Pinned in Task 3, `test_no_key_file_sends_no_header_and_a_401_is_a_server_error`.
3. **The key file ends in a newline** (`base64` writes one). It must be stripped, or every request
   sends `Bearer abc…\n` and gets 401. Pinned in Task 3, `test_the_key_is_stripped_of_its_newline`.
4. **A pinned model file is missing, not mismatched.** The daemon must still start, because Silero,
   Kokoro and the speaker model each have a logged fallback. Only a file that exists with the
   wrong hash stops the start. Pinned in Task 4, `test_a_missing_file_is_not_a_mismatch`.
5. **The doc split deletes a command a test pins.** `tests/test_doc_paths.py::RUNBOOKS` requires
   `progress.md` to still carry the `sqlite3 … approvals` command with the real `memory.db` path.
   A rewritten `progress.md` that drops it turns that test red. Covered by Task 5 Step 6, which
   runs that file.

---

### Task 1: Re-verify the ground

Rule 5: the plan is checked against what the last session actually left. No code changes. Expected
numbers come from CLAUDE.md's 2026-09-08 line. Any difference is written down as found, not
"fixed" here.

**Files:**
- Modify: `progress.md` (evidence block under the 2026-10-07 entry)

- [ ] **Step 1: Ask the owner before stopping Friday 2**

Say in chat: "Friday 2's daemon and pill are running and hold the mic and 5.6 GB of VRAM; Gemma
needs ~7 GB. OK to stop both now? They restart with the commands in friday2's CLAUDE.md."
Wait for a yes. On a no, skip Steps 2–3 and the LLM-dependent gates in Step 5, and record that.

- [ ] **Step 2: Stop Friday 2 (only after a yes)**

These are the commands friday2's CLAUDE.md documents. The `$` anchors keep `pgrep` from matching
the shell that runs it.

```bash
kill $(pgrep -f '\.venv/bin/friday2 daemon$') ; kill $(pgrep -f '^qs -p ui/pill/shell.qml$')
```

Then confirm:

```bash
ps -eo pid,cmd | grep -F -e 'friday2 daemon' -e 'ui/pill/shell.qml' | grep -v grep ; nvidia-smi --query-gpu=memory.used --format=csv,noheader
```

Expected: no process lines; memory.used well under 1 GB.

- [ ] **Step 3: Start the LLM**

```bash
systemctl --user start friday-llm && sleep 20 && systemctl --user is-active friday-llm && curl -s 127.0.0.1:8080/health
```

Expected: `active` and `{"status":"ok"}`.

- [ ] **Step 4: Offline gates**

```bash
powerprofilesctl get
uv run pytest -q 2>&1 | tail -3
just grammar && git status --short friday/llm/grammars
just test-no-fstring-sql
just bootstrap --check 2>&1 | tail -15
```

Expected: `balanced`; `712 passed`; empty `git status` (grammars byte-identical);
`OK`; `11/11` checks pass.

- [ ] **Step 5: LLM-dependent gates**

```bash
just eval 2>&1 | tail -6
just test-injection 2>&1 | tail -3
just test-egress 2>&1 | tail -3
just selftest; echo "rc=$?"
```

Expected: `91/91 (100%)`, `regressions 0`, `unbaselined failures: 0`; injection `20/20`; egress
`8 passed`. `selftest`: `friday.service` is not running in this step, so a WARN is likely on the
daemon checks. Record the exact line and rc. **Do not start `friday.service`** without asking: it
opens the mic.

- [ ] **Step 6: Paste the evidence**

Under the `>>> 2026-10-07` block of `progress.md`, add `### Phase A, Task 1: ground re-verified`
with every command above and its output tail. List each number that differs from 712 / 91/91 /
20/20 / 8 / 11/11 / byte-identical as a finding, with its first error line.

- [ ] **Step 7: Commit**

```bash
git add progress.md
git commit -m "docs(progress): Phase A task 1 -- ground re-verified on 2026-10-07

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Record the owner's decisions (ADR-131..136)

Working agreement rule 4. The decisions were taken in chat on 2026-10-07 and so far exist only in
the spec and a short `progress.md` block. This task writes the ADRs.

**Files:**
- Modify: `adr.md` (append), `docs/superpowers/specs/2026-10-07-friday2-merge-design.md` (§2 ADR column), `progress.md`

**Interfaces:**
- Produces: ADR numbers that Tasks 3–5 and Phases B–E cite. The final map: 131 base/port,
  132 window, 133 speaker check, 134 heard log + 90-day command text, 135 output channel,
  136 carried-over choices, 137 `llama-server` key (Task 3), 138 model pins at start (Task 4),
  139 slim docs (Task 5).

- [ ] **Step 1: Check the next free number**

```bash
grep -c '^## ADR-' adr.md ; grep '^## ADR-' adr.md | tail -2
```

Expected: the last one is `## ADR-130`. If not, renumber everything in this plan from the real
next number.

- [ ] **Step 2: Append ADR-131..136 to `adr.md`**

Use the file's existing shape: `## ADR-NNN — title`, then `**Date:**`, `**Status:**`, and
`### Context` / `### Decision` / `### Consequences` / `### Rejected`. The content of each comes
from the spec section named below, without paraphrase drift:

| ADR | Title | Source in the spec | Status line |
|---|---|---|---|
| 131 | v1 is reopened as the base; Friday 2's features are ported in by copy | §0, §3.1–3.3 (Rejected = §3.3's table, plus spec §"Approaches": swap Gemma into v2; a third repo) | Accepted 2026-10-07 |
| 132 | A 90 s listening window after the wake word; chat in the window always replies | §2 rows 2–3, §4.1 | Accepted; built in Phase B |
| 133 | ERes2Net-en replaces CAM++, always on, threshold 0.35, the owner's v2 voiceprint | §2 row 4, §4.2 (cite v2 D68, D104 numbers) | Accepted; built in Phase B |
| 134 | Invariant #7 amended: a 7-day heard log and 90-day text of acted commands | §2 row 5, §2.1 last bullet, §4.5 | Accepted; **effective only when Phase B / E ship**. Until then #7 stands as written |
| 135 | Results by notification; speech for chat and answers; confirm buttons; speak mode | §2 row 6, §4.3 | Accepted; built in Phase B |
| 136 | Friday 2's answered choices are carried over unchanged | §2.1 (all bullets except the last, which is ADR-134) | Accepted |

ADR-134's `### Consequences` must say in so many words that `thought`, raw model output, raw
search payloads, key events and audio remain never-on-disk, and that the daemon log and journald
stay text-free.

- [ ] **Step 3: Align the spec's ADR column**

In the spec's §2 table, set the "Planned ADR" column to the numbers above: rows 1–6 → 131–136;
row 7 stays "one per phase (B–E)"; row 8 stays "with Phase B (the web app with E)"; row 9 → 136;
row 10 → 139. Change §2's intro sentence "ADR numbers planned below" to "ADR-131..139".

- [ ] **Step 4: Verify the record**

```bash
grep -c '^## ADR-' adr.md ; grep -o 'ADR-13[0-9]' docs/superpowers/specs/2026-10-07-friday2-merge-design.md | sort -u
uv run pytest -q tests/test_doc_paths.py
```

Expected: `136`; only numbers ≤ 139 appear; doc paths pass.

- [ ] **Step 5: Commit**

```bash
git add adr.md docs/superpowers/specs/2026-10-07-friday2-merge-design.md progress.md
git commit -m "docs(adr): ADR-131..136 -- the 2026-10-07 owner decisions (v1 reopened, Friday 2 ported in)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `llama-server` requires a fresh random key per start (ADR-137, FR-158)

Why: `llama-server` started with Friday's flags allows every web origin and has no key. Friday 2
measured it (its C150): the server logs "CORS is set to allow all origins ('*') and no API key is
set … security risk". Binding 127.0.0.1 does not stop a web page in the owner's browser from
posting to `127.0.0.1:8080`. v1 runs the server permanently, so the window is always open.

**Files:**
- Modify: `friday/config.py` (add `LLAMA_KEY_FILE`), `friday/llm/client.py` (send the key),
  `deploy/systemd/friday-llm.service`, `justfile` (`serve`), `tests/test_model_config.py`,
  `spec.md` (FR-158), `adr.md` (ADR-137), `progress.md`
- Test: `tests/test_llm_auth.py` (new)

**Interfaces:**
- Produces: `config.LLAMA_KEY_FILE: Path`, i.e. `$XDG_RUNTIME_DIR/friday-llm/api.key`.
  `friday.llm.client.auth_headers(key_file: Path | None = None) -> dict[str, str]` returns
  `{"Authorization": "Bearer <key>"}`, or `{}` when the file is absent or empty.
  `LlamaClient.key_file: Path | None` defaults to `config.LLAMA_KEY_FILE`.

- [ ] **Step 1: Probe the live server first (the before picture)**

```bash
journalctl --user -u friday-llm -b --no-pager | grep -i -m2 'cors\|api key'
curl -s -o /dev/null -w '%{http_code}\n' -X POST 127.0.0.1:8080/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"hi"}],"max_tokens":1}'
```

Expected: the CORS warning line, and `200`, which proves the hole. Paste both into `progress.md`.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_llm_auth.py`:

```python
"""llama-server requires a per-start random key (ADR-137, FR-158).

Without one, any web page open in the owner's browser can POST to
127.0.0.1:8080 -- llama-server allows every CORS origin by default (Friday 2
measured the warning, its C150). The key rotates on every server start, so the
client must read it per request, not once.
"""

import json

import urllib.error

import pytest

from friday import config
from friday.llm.client import LlamaClient, LlamaServerError, auth_headers


class _Resp:
    def __init__(self, body: dict):
        self._b = json.dumps(body).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_OK = {"choices": [{"message": {"content": "{}"}}]}


def _capture(monkeypatch, resp=None, exc=None):
    seen = []

    def fake_urlopen(req, timeout=None):
        seen.append(req)
        if exc is not None:
            raise exc
        return resp or _Resp(_OK)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return seen


def test_the_default_key_file_lives_in_the_runtime_dir():
    assert config.LLAMA_KEY_FILE.parts[-2:] == ("friday-llm", "api.key")


def test_a_present_key_is_sent_as_a_bearer_header(tmp_path, monkeypatch):
    key = tmp_path / "api.key"
    key.write_text("s3cret")
    seen = _capture(monkeypatch)
    LlamaClient(key_file=key).complete(system="s", user="u")
    assert seen[0].get_header("Authorization") == "Bearer s3cret"


def test_the_key_is_stripped_of_its_newline(tmp_path):
    key = tmp_path / "api.key"
    key.write_text("abc\n")
    assert auth_headers(key) == {"Authorization": "Bearer abc"}


def test_a_rotated_key_is_picked_up_without_restarting_the_client(tmp_path, monkeypatch):
    key = tmp_path / "api.key"
    key.write_text("first")
    seen = _capture(monkeypatch)
    c = LlamaClient(key_file=key)
    c.complete(system="s", user="u")
    key.write_text("second")          # llama-server restarted: new key
    c.complete(system="s", user="u")
    assert [r.get_header("Authorization") for r in seen] == ["Bearer first", "Bearer second"]


def test_no_key_file_sends_no_header_and_a_401_is_a_server_error(tmp_path, monkeypatch):
    err = urllib.error.HTTPError("http://127.0.0.1:8080/v1/chat/completions", 401,
                                 "Unauthorized", {}, None)
    seen = _capture(monkeypatch, exc=err)
    with pytest.raises(LlamaServerError) as ei:
        LlamaClient(key_file=tmp_path / "missing").complete(system="s", user="u")
    assert ei.value.status == 401
    assert seen[0].get_header("Authorization") is None
    assert len(seen) == 1             # an HTTP status is never retried (FR-42a)


def test_an_empty_key_file_sends_no_header(tmp_path):
    key = tmp_path / "api.key"
    key.write_text("\n")
    assert auth_headers(key) == {}
```

Append to `tests/test_model_config.py`:

```python
def test_both_launch_paths_require_a_fresh_api_key() -> None:
    """ADR-137. The key file is generated on every start and passed with
    --api-key-file; the service gets a private runtime dir that systemd
    removes on stop, so a stopped server leaves no key behind."""
    unit, just = UNIT.read_text(), JUSTFILE.read_text()
    for f, text in (("friday-llm.service", unit), ("justfile", just)):
        assert "--api-key-file" in text, f"{f}: llama-server started without a key"
        assert "/dev/urandom" in text, f"{f}: key not generated per start"
    assert "RuntimeDirectory=friday-llm" in unit
    assert "RuntimeDirectoryMode=0700" in unit
```

- [ ] **Step 3: Run them and watch them fail**

Run: `uv run pytest -q tests/test_llm_auth.py tests/test_model_config.py`
Expected: FAIL. `ImportError: cannot import name 'auth_headers'` for the first file;
`--api-key-file` missing for the second.

- [ ] **Step 4: Implement**

`friday/config.py`: add next to `LLAMA_BASE_URL` (line 24):

```python
# ADR-137: llama-server requires a key, regenerated on every start into a
# private runtime dir (the unit's RuntimeDirectory=friday-llm, or `just serve`).
LLAMA_KEY_FILE: Path = (
    Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "friday-llm" / "api.key"
)
```

`friday/llm/client.py`: add `from pathlib import Path` and `from .. import config` to the imports,
then above `@dataclass(frozen=True) class LlamaClient`:

```python
def auth_headers(key_file: Path | None = None) -> dict[str, str]:
    """The bearer header llama-server requires (ADR-137), or {} with no key.

    Read on EVERY call: the key rotates whenever llama-server restarts, and the
    daemon outlives it. No key is not an error here -- the server answers 401,
    which `complete` already maps to LlamaServerError / E_LLM_DOWN.
    """
    path = key_file if key_file is not None else config.LLAMA_KEY_FILE
    try:
        key = path.read_text().strip()
    except OSError:
        return {}
    return {"Authorization": f"Bearer {key}"} if key else {}
```

In `LlamaClient`, add the field after `connect_backoff_s`:

```python
    key_file: Path | None = None   # None -> config.LLAMA_KEY_FILE (tests pass a tmp file)
```

and change the request headers in `complete` from
`headers={"Content-Type": "application/json"},` to:

```python
                headers={"Content-Type": "application/json", **auth_headers(self.key_file)},
```

`deploy/systemd/friday-llm.service`: after the GPU-wait `ExecStartPre=` line add:

```ini
# ADR-137: llama-server allows every CORS origin, so without a key any web page
# in the owner's browser can POST to 127.0.0.1:8080. A fresh key per start, in a
# 0700 runtime dir that systemd removes on stop; the client reads it per request.
RuntimeDirectory=friday-llm
RuntimeDirectoryMode=0700
ExecStartPre=/bin/sh -c 'umask 077 && head -c 32 /dev/urandom | base64 > %t/friday-llm/api.key'
```

and add `--api-key-file %t/friday-llm/api.key \` to `ExecStart`, just before `--no-webui`.

`justfile` `serve` recipe (keep it equivalent to the unit, FR-98):

```make
serve:
    mkdir -p -m 700 "$XDG_RUNTIME_DIR/friday-llm"
    umask 077 && head -c 32 /dev/urandom | base64 > "$XDG_RUNTIME_DIR/friday-llm/api.key"
    PATH=/opt/cuda/bin:$PATH /opt/llama.cpp/build/bin/llama-server \
      --model {{model}} \
      --host 127.0.0.1 --port 8080 --ctx-size 8192 --n-gpu-layers 99 \
      --parallel 1 --cache-type-k q8_0 --cache-type-v q8_0 -fa on \
      --reasoning off --api-key-file "$XDG_RUNTIME_DIR/friday-llm/api.key" --no-webui
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest -q tests/test_llm_auth.py tests/test_model_config.py tests/test_llm_client_edges.py`
Expected: all pass.

- [ ] **Step 6: Deploy the unit and check the live server**

```bash
systemctl --user daemon-reload && systemctl --user restart friday-llm && sleep 20
systemctl --user show friday-llm -p NeedDaemonReload -p ActiveState
stat -c '%a %n' "$XDG_RUNTIME_DIR/friday-llm" "$XDG_RUNTIME_DIR/friday-llm/api.key"
curl -s -o /dev/null -w 'no key: %{http_code}\n' -X POST 127.0.0.1:8080/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"hi"}],"max_tokens":1}'
curl -s -o /dev/null -w 'key: %{http_code}\n' -X POST 127.0.0.1:8080/v1/chat/completions -H 'Content-Type: application/json' -H "Authorization: Bearer $(cat "$XDG_RUNTIME_DIR/friday-llm/api.key")" -d '{"messages":[{"role":"user","content":"hi"}],"max_tokens":1}'
curl -s -o /dev/null -w 'health: %{http_code}\n' 127.0.0.1:8080/health
```

Expected: `NeedDaemonReload=no`, `ActiveState=active`; `700` and `600`; `no key: 401`;
`key: 200`; `health: 200`.

**If `health:` is 401**, `/health` is not public in this build. Then `selftest.check_llama_server`
(line 74) and `voice_main.wait_for_llm` (line 48) both need the header. In each, change
`headers={"User-Agent": …}` to `headers={"User-Agent": …, **auth_headers()}`, with
`from friday.llm.client import auth_headers`. Add one test per call site in
`tests/test_llm_auth.py` asserting the header is on the captured request. Re-run Step 5.

- [ ] **Step 7: The eval gate still passes through the key**

Run: `just eval 2>&1 | tail -4`
Expected: `91/91`, `regressions 0`. The harness builds `LlamaClient(base_url=…)`, which now
reads the default key file.

- [ ] **Step 8: Mutation**

```bash
cp friday/llm/client.py .git/client.py.bak
sed -i 's/, \*\*auth_headers(self.key_file)}/}/' friday/llm/client.py
uv run pytest -q tests/test_llm_auth.py 2>&1 | tail -2
cp .git/client.py.bak friday/llm/client.py && uv run pytest -q tests/test_llm_auth.py 2>&1 | tail -1
```

Expected: the mutated run fails (≥2 tests); the restored run passes. Remove the backup: `rm .git/client.py.bak`.

- [ ] **Step 9: Record**

- `adr.md`: ADR-137, "llama-server requires a fresh random key per start". Context: the Step 1
  output. Decision: the unit/`serve` mechanism above. Consequences: the key is readable only by
  the owner's own processes (0700 dir, 0600 file); a hand-started server without
  `--api-key-file` still works with the client (no header is sent when no file exists).
  Rejected: a fixed key in config (would be on disk forever); `--api-key` on argv (visible in
  `ps` to the same user only, but the file is no worse and survives `just serve` parity);
  disabling CORS alone (a simple POST needs no preflight, so CORS does not stop the request
  being executed).
- `spec.md`: FR-158 in the requirements table, test names from Step 2.
- `progress.md`: Steps 1, 6, 7 and 8 output.

- [ ] **Step 10: Full suite and commit**

```bash
uv run pytest -q 2>&1 | tail -2
git add friday/config.py friday/llm/client.py deploy/systemd/friday-llm.service justfile tests/test_llm_auth.py tests/test_model_config.py spec.md adr.md progress.md
git commit -m "fix(llm): llama-server requires a fresh random key per start (ADR-137, FR-158)

llama-server allows every CORS origin and had no key, so any web page in the
owner's browser could POST to 127.0.0.1:8080. Found by Friday 2 (its C150).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: `719 passed` (712 + 7 new; +2 more if Step 6's conditional health tests were needed).

---

### Task 4: Model pins live in one module, and the daemon checks them at start (ADR-138, FR-159)

Why: the SHA256 pins exist only inside `scripts/bootstrap.py`, so they are checked when someone
runs `just bootstrap --check` and never when the daemon loads a model. Friday 2 checked its pins
at every start. A file that exists with the wrong hash now stops the start, loudly. A missing
file does not, because each loader already has a logged fallback (Silero → `webrtcvad`, Kokoro →
Supertonic/silent, speaker verify off).

**Files:**
- Create: `friday/models.py`
- Modify: `scripts/bootstrap.py:41-100` (import instead of defining),
  `friday/voice_main.py:149-170` (check at start), `friday/errors.py` (`E_MODEL_PIN`),
  `spec.md` (§4 taxonomy + FR-159), `adr.md` (ADR-138), `progress.md`
- Test: `tests/test_models_pins.py` (new)

**Interfaces:**
- Produces: `friday.models.ModelPin(name: str, path: Path, sha256: str, url: str)` (a
  `NamedTuple` with the same fields as bootstrap's old `ModelSpec`); `PINS: tuple[ModelPin, ...]`
  (all six); `DAEMON_PINS: tuple[ModelPin, ...]` (the five the daemon process loads: no GGUF,
  which `llama-server` loads); `sha256(path: Path) -> str`;
  `mismatched(pins: Iterable[ModelPin]) -> list[str]` returns the `name`s of files that exist and
  whose hash differs. `errors.E_MODEL_PIN = "E_MODEL_PIN"`. Phase B appends ERes2Net, the
  voiceprint and Smart Turn to `DAEMON_PINS`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_models_pins.py`:

```python
"""One home for the SHA256 pins, checked at daemon start (ADR-138, FR-159).

Before this, the pins lived in scripts/bootstrap.py and were checked only when
someone ran `just bootstrap --check`; the daemon loaded whatever was on disk.
"""

import hashlib
import logging
from pathlib import Path

from friday import models, voice_main
from friday.errors import E_MODEL_PIN
from friday.models import ModelPin


def _pin(path: Path, data: bytes | None, good: bool = True) -> ModelPin:
    digest = hashlib.sha256(data or b"").hexdigest()
    if data is not None:
        path.write_bytes(data)
    return ModelPin("m", path, digest if good else "0" * 64, "https://example.invalid/m")


def test_a_matching_file_passes(tmp_path):
    assert models.mismatched([_pin(tmp_path / "a", b"weights")]) == []


def test_a_changed_file_is_reported_by_name(tmp_path):
    assert models.mismatched([_pin(tmp_path / "a", b"weights", good=False)]) == ["m"]


def test_a_missing_file_is_not_a_mismatch(tmp_path):
    # Each loader has its own logged fallback for a MISSING model; only a file
    # that is present and different is a reason to refuse the start.
    assert models.mismatched([_pin(tmp_path / "absent", None, good=False)]) == []


def test_the_daemon_set_never_hashes_the_gguf():
    # 6.4 GB, loaded by llama-server, not by this process.
    assert not any(p.path.suffix == ".gguf" for p in models.DAEMON_PINS)
    assert {p.name for p in models.DAEMON_PINS} < {p.name for p in models.PINS}


def test_bootstrap_reads_the_same_pins():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "bootstrap", Path(__file__).parent.parent / "scripts" / "bootstrap.py")
    boot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(boot)
    assert list(boot.get_model_specs()) == list(models.PINS)


def test_the_daemon_refuses_to_start_on_a_mismatched_model(monkeypatch, caplog):
    monkeypatch.setattr(models, "mismatched", lambda pins: ["Kokoro 82M TTS Model"])
    # setup_logging installs the daemon's own handlers; keep caplog's.
    monkeypatch.setattr(voice_main, "setup_logging", lambda **k: None)
    monkeypatch.setattr(voice_main, "wait_for_llm",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("started")))
    with caplog.at_level(logging.ERROR):
        assert voice_main.main(["--dry-run"]) == 1
    assert E_MODEL_PIN in caplog.text and "Kokoro 82M TTS Model" in caplog.text
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest -q tests/test_models_pins.py`
Expected: FAIL with `ImportError: cannot import name 'models' from 'friday'`.

- [ ] **Step 3: Create `friday/models.py`**

Move the six specs out of `scripts/bootstrap.py:52-92`, values unchanged:

```python
"""The SHA256 pins for every model file Friday loads (rule 7, ADR-138).

One home: `scripts/bootstrap.py` fetches and checks against these, and the
daemon refuses to start if a file it loads is present with a different hash.
A MISSING file is not refused here -- each loader has its own logged fallback
(Silero -> webrtcvad, Kokoro -> Supertonic, speaker verify off).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, NamedTuple

from . import config


class ModelPin(NamedTuple):
    name: str
    path: Path
    sha256: str
    url: str


_M = config._DATA_DIR / "models"

KOKORO = ModelPin(
    "Kokoro 82M TTS Model", _M / "kokoro" / "model.onnx",
    "8fbea51ea711f2af382e88c833d9e288c6dc82ce5e98421ea61c058ce21a34cb",
    "https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/main/onnx/model.onnx")
KOKORO_VOICES = ModelPin(
    "Kokoro Voices Blob", _M / "kokoro" / "voices-v1.0.bin",
    "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin")
SILERO = ModelPin(
    "Silero VAD (op18-ifless)", _M / "vad" / "silero_vad_op18_ifless.onnx",
    "7671cd04b004e9076da0d4a7b1a5aec36adf161c39230c1cb94a4fd5db6bbd28",
    "https://raw.githubusercontent.com/snakers4/silero-vad/v6.2.1/src/silero_vad/data/silero_vad_op18_ifless.onnx")
WAKE = ModelPin(
    "openWakeWord (hey_jarvis)", _M / "wake" / "hey_jarvis.onnx",
    "94a13cfe60075b132f6a472e7e462e8123ee70861bc3fb58434a73712ee0d2cb",
    "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/hey_jarvis_v0.1.onnx")
SPEAKER = ModelPin(
    "CAM++ 3D-Speaker Verification", _M / "speaker" / "3dspeaker_campplus.onnx",
    "357a834f702b80161e5b981182c038e18553c1f2ca752ed6cec2052365d4129b",
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx")
GEMMA = ModelPin(
    "Gemma 4 12B QAT LLM", _M / "gemma-4-12B-it-qat-UD-Q4_K_XL.gguf",
    "90fd44e29e0d7cffeb0fd00dc73cfdab9ed0b0e95306ecf7821ea634c940c370",
    "https://huggingface.co/unsloth/gemma-4-12B-it-GGUF/resolve/main/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf")

PINS: tuple[ModelPin, ...] = (KOKORO, KOKORO_VOICES, SILERO, WAKE, SPEAKER, GEMMA)
#: What the daemon process itself loads. The GGUF is llama-server's.
DAEMON_PINS: tuple[ModelPin, ...] = (KOKORO, KOKORO_VOICES, SILERO, WAKE, SPEAKER)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def mismatched(pins: Iterable[ModelPin]) -> list[str]:
    """Names of pinned files that are PRESENT with a different hash."""
    return [p.name for p in pins if p.path.is_file() and sha256(p.path) != p.sha256]
```

Before writing `_M`, check that `config._DATA_DIR` is the name in `friday/config.py` (it is used
at lines 55–56). If the config has a public name for it, use that instead.

- [ ] **Step 4: Point bootstrap at it**

In `scripts/bootstrap.py`, delete `class ModelSpec`, `get_data_dir`'s use in `get_model_specs`,
the body of `get_model_specs`, and `compute_sha256`. Replace them with:

```python
from friday.models import ModelPin as ModelSpec, PINS, sha256 as compute_sha256  # noqa: E402


def get_model_specs() -> list[ModelSpec]:
    return list(PINS)
```

Keep `get_data_dir` only if something else in the file still calls it:
`grep -n get_data_dir scripts/bootstrap.py`.

- [ ] **Step 5: Check at daemon start**

Add `from friday import models` and `from friday.errors import E_MODEL_PIN` to
`friday/voice_main.py`. In `main()`, right after `setup_logging(level=args.log)`, add:

```python
    # ADR-138: a model file that is present but not the pinned one is refused,
    # loudly, before anything loads it. A missing one is left to each loader's
    # own logged fallback.
    bad = models.mismatched(models.DAEMON_PINS)
    if bad:
        logging.getLogger("friday.startup").error(
            "%s: refusing to start, model file differs from its pin: %s", E_MODEL_PIN, ", ".join(bad))
        return 1
```

In `friday/errors.py`, beside `E_AUDIO_DEAD`, add:

```python
E_MODEL_PIN = "E_MODEL_PIN"  # a model file differs from its SHA256 pin -> no start, logged only
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest -q tests/test_models_pins.py tests/test_bootstrap.py`
Expected: all pass.

- [ ] **Step 7: Measure the cost and check the real files**

```bash
uv run python -c "import time; from friday import models; t=time.perf_counter(); print(models.mismatched(models.DAEMON_PINS)); print(f'{time.perf_counter()-t:.2f}s')"
just bootstrap --check 2>&1 | tail -8
```

Expected: `[]` and well under 1 s (~370 MB hashed); bootstrap still `11/11`. If the time is above
1 s, record it in ADR-138's Consequences. The daemon is restarted rarely, so that alone does not
block.

- [ ] **Step 8: Mutation**

```bash
cp friday/voice_main.py .git/voice_main.py.bak
sed -i '/refusing to start, model file differs/{n;s/return 1/pass/}' friday/voice_main.py
uv run pytest -q tests/test_models_pins.py 2>&1 | tail -2
cp .git/voice_main.py.bak friday/voice_main.py && uv run pytest -q tests/test_models_pins.py 2>&1 | tail -1
```

Expected: the mutated run fails `test_the_daemon_refuses_to_start_on_a_mismatched_model`; the
restored run passes. If the `sed` does not change the file (check `diff`), edit the `return 1` to
`pass` by hand. The mutation is the point, not the `sed`. Remove the backup: `rm .git/voice_main.py.bak`.

- [ ] **Step 9: Record and commit**

- `adr.md` ADR-138: Context, the paragraph at the top of this task. Decision: `friday/models.py`
  as above. Rejected: hashing the GGUF in the daemon (6.4 GB, not loaded by this process);
  refusing on a missing file (would remove the deliberate fallbacks, and D3's
  webrtcvad-fallback warning already says what is missing).
- `spec.md` §4: add `E_MODEL_PIN  model differs from its pin -> logged only, no start` under
  `E_AUDIO_DEAD`, and FR-159 with the test names.
- `progress.md`: Step 7 and Step 8 output.

```bash
uv run pytest -q 2>&1 | tail -2
git add friday/models.py friday/voice_main.py friday/errors.py scripts/bootstrap.py tests/test_models_pins.py spec.md adr.md progress.md
git commit -m "feat(models): one home for the SHA256 pins, checked at daemon start (ADR-138, FR-159)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Slim the docs (ADR-139)

Owner decision 10. CLAUDE.md is 1,532 lines and loads into every session. `progress.md` is 11,555
lines. Nothing is deleted: history goes to `docs/archive/` verbatim, still-valid rules go to
`docs/lessons.md`, and CLAUDE.md links both. `adr.md` is not auto-loaded and stays whole.

**Files:**
- Create: `docs/archive/CLAUDE-2026-09-08.md`, `docs/archive/progress-2026-08-22..2026-09-08.md`,
  `docs/lessons.md`
- Modify: `CLAUDE.md` (rewrite), `progress.md` (rewrite), `README.md` (two references),
  `.claude/skills/landing-a-friday-change/SKILL.md` (only if it cites moved sections), `adr.md`
  (ADR-139)

- [ ] **Step 1: Archive both files verbatim**

```bash
cp CLAUDE.md docs/archive/CLAUDE-2026-09-08.md
git mv progress.md "docs/archive/progress-2026-08-22..2026-09-08.md"
```

`git mv` keeps `progress.md`'s blame history on the archive. CLAUDE.md is copied, because the file
is rewritten in place and keeps its own history.

- [ ] **Step 2: Write `docs/lessons.md`**

Header: one paragraph saying these are rules paid for by live defects, moved out of CLAUDE.md on
2026-10-07 (ADR-139), still in force, read before touching the area they name. Then, copied
**verbatim** from the old CLAUDE.md (line numbers as of `48514b1`):

1. `## The defect ledger, D1–D37`: the table under "THE DEFECT LEDGER" (from line 330 to the end
   of that table).
2. `## Lessons that block repeats`: the bulleted list starting at line 729.
3. `## Things that will tempt you and are wrong`: the whole table from line 1378 to the end of the
   file.

Then `## Hardware facts worth keeping`: the measured numbers still true and cited from
`gemma-brief.md` / `docs/hardware-placement.md`. Copy the sentences, don't paraphrase:
- `tok/s ≈ 272 / weights_GB`;
- `--parallel 1` is worth 514 MiB;
- `--ctx-size 8192→4096` frees 38 MiB;
- STT cost is flat in audio length (F26);
- `power-saver` voids measurements, and `balanced` is the target (ADR-087);
- `pgrep -f` matches its own command line.

- [ ] **Step 3: Rewrite `CLAUDE.md` (target ≤ 300 lines)**

Sections in this order. Text marked *verbatim* is copied from the old file unchanged; the rest is
new and short.

1. `# CLAUDE.md — Working agreement for this repository`, then one line: "Read this before
   touching anything. Lessons: `docs/lessons.md`. History: `docs/archive/`."
2. `## What this is` (≤ 15 lines, new):
   - Friday is a local voice + text assistant for one Arch + Hyprland laptop.
   - Gemma 4 12B QAT on `llama-server` 127.0.0.1:8080 plans every turn, locked by
     `plan.gbnf`/`final.gbnf`.
   - Reopened 2026-10-07 as the base for Friday 2's features (ADR-131; spec
     `docs/superpowers/specs/2026-10-07-friday2-merge-design.md`).
   - Friday 2 lives in `~/Projects/Personal/friday2`: copy from it, never import, and stop its
     daemon before a live v1 run.
   - Friday never uses ollama; the models in `ollama list` are the owner's.
3. `## Where things stand` (≤ 25 lines, new): a dated table of the gate numbers from Task 1's
   evidence, plus Tasks 3–4's new pytest count. The current phase and its plan path. Open defects
   (D4, D5, D6, D8, D9, D17, D18, each with one line from the old ledger). Open questions (the
   OQ ids from the old file's "Questions still owed" line). "Start with `progress.md` →
   `>>> START HERE <<<`."
4. `## Working agreement`: *verbatim*, old lines 952–1037 (rules 1–7).
5. `## Hard invariants`: *verbatim* block, old lines 1205–1246. Append to #7 one line:
   "Amended by ADR-134 (heard log 7 d, acted-command text 90 d), **effective only when Phase B / E
   ship**." Append to #2: "A second exception, the find query, is planned for Phase C under its own
   ADR."
6. `## Definition of done`: *verbatim*, old lines 1272–1294 (the checklist plus the
   sixth-line paragraph).
7. `## Commands`: *verbatim*, old lines 1307–1377, with one edit: the `just test` comment's count
   becomes the current pytest number.
8. `## Document map`: rewrite the old 1038–1204 block as one line per document, ≤ 30 lines. Same
   files, plus `docs/lessons.md`, `docs/archive/`, and the 2026-10-07 spec and plans. Keep the
   `laptop-specifications.md` GITIGNORED warning *verbatim*.
9. `## The ten rules most often paid for` (≤ 25 lines, new): one line each, linking
   `docs/lessons.md`. Pick from the temptation table:
   - a green suite is not a working feature;
   - ask the system, not the config;
   - a check that cannot fail is worthless;
   - grep for the class, not the ticket;
   - mutate-and-watch-red, and copy aside rather than `git checkout`;
   - re-baseline after adding eval fixtures (F23);
   - `memory.db` lives under `state` (D36);
   - `env -u JOURNAL_STREAM` for foreground debug;
   - never `just voice` while the service is up;
   - read the CONSUMER of anything you start writing.
10. `## Style`: *verbatim*, old lines 1295–1306.

Drop entirely from CLAUDE.md (it is in the archive and the lessons file): every dated `>>> … <<<`
block, the per-session narratives, the defect ledger, the build-order section (all gates are
done; one line in the doc map points to `friday.md`), and the archived-reviews paragraph.

- [ ] **Step 4: Write the new `progress.md` (target ≤ 200 lines)**

1. The old header *verbatim* (title, the "only file that says what is actually true" paragraph,
   rules 1–4).
2. `## >>> START HERE <<<`:
   - the current phase and plan path;
   - the gate numbers from Task 1;
   - the stop-v2-first rule;
   - the FIRST_USE check command, which `tests/test_doc_paths.py::RUNBOOKS` pins:
     `sqlite3 -readonly ~/.local/state/friday/memory.db 'SELECT kind, subject, argv_sha256, approved_at FROM approvals;'`
     (columns as of 2026-10-07, the same command as `docs/reality-check.md` §G1 step 5).
   - "History before 2026-10-07: `docs/archive/progress-2026-08-22..2026-09-08.md`."
3. `## Decision log`: the 2026-10-07 block (moved from the archive copy's top, *verbatim*) and one
   line per ADR-131..139.
4. `## Evidence`: the Phase A evidence from Tasks 1, 3 and 4. Those sections were written into the
   old `progress.md` before Step 1 moved it, so move them here *verbatim* and delete them from the
   archive copy, so evidence is not in two places.

- [ ] **Step 5: Fix references to moved text**

```bash
grep -rn 'CLAUDE.md' --include=*.md . | grep -v '^./docs/archive/' | grep -i -e 'tempt' -e 'ledger' -e 'lesson' -e 'START HERE'
grep -rn 'progress.md' .claude/skills README.md docs/*.md | grep -v archive
```

Any hit that points at the temptation table or ledger "in CLAUDE.md" is repointed to
`docs/lessons.md`. A `progress.md` reference to a dated session block is repointed to the archive
file. `README.md:50` (invariants in CLAUDE.md) stays correct, and so does `README.md:277`.

- [ ] **Step 6: Verify**

```bash
wc -l CLAUDE.md progress.md docs/lessons.md
uv run pytest -q tests/test_doc_paths.py 2>&1 | tail -2
uv run pytest -q 2>&1 | tail -2
diff <(sed -n '1205,1246p' docs/archive/CLAUDE-2026-09-08.md) <(awk '/^## Hard invariants/,/^## Definition of done/' CLAUDE.md) | head -20
```

Expected: CLAUDE.md ≤ 300, progress.md ≤ 200; doc paths pass, including both `RUNBOOKS` cases;
the full suite passes. The invariants diff shows only the two appended amendment lines (and
section-heading context lines).

- [ ] **Step 7: Record and commit**

ADR-139 in `adr.md`. Context: the line counts. Decision: the split above. Consequences: every
session loads ~250 lines instead of 1,532; a session that needs history greps `docs/archive/`.
Rejected: trimming in place (history is evidence, rule 6); deleting the temptation table (each row
was paid for).

```bash
git add CLAUDE.md progress.md docs/lessons.md docs/archive/ README.md .claude/skills adr.md
git commit -m "docs: slim CLAUDE.md 1532 -> ~250 lines and progress.md; history to docs/archive, lessons to docs/lessons.md (ADR-139)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Mark Friday 2 frozen (only with the owner's OK)

**Files:**
- Modify: `~/Projects/Personal/friday2/CLAUDE.md` (a different repo)

- [ ] **Step 1: Ask**

"May I add a three-line 'frozen' note at the top of friday2's CLAUDE.md and commit it locally
there (branch `claude/phase2`, not pushed)?" On a no, skip this task and record that in
`progress.md`.

- [ ] **Step 2: Add the note**

Insert after the file's first line:

```markdown
> **FROZEN 2026-10-07.** The owner found Friday 2 "so-so" (D108) and reopened Friday v1 as the
> base (`~/Projects/Personal/Intern/friday`, ADR-131). Features are ported there by copy; do not
> develop here. The daemon and pill must be stopped before any v1 live run.
```

- [ ] **Step 3: Commit there**

```bash
git -C ~/Projects/Personal/friday2 add CLAUDE.md
git -C ~/Projects/Personal/friday2 commit -m "docs: frozen -- Friday v1 reopened as the base (2026-10-07)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Close Phase A

**Files:**
- Modify: `progress.md`

- [ ] **Step 1: The whole gate, once more**

```bash
uv run pytest -q 2>&1 | tail -2
just grammar && git status --short friday/llm/grammars
just eval 2>&1 | tail -4
just test-injection 2>&1 | tail -2
just test-egress 2>&1 | tail -2
just bootstrap --check 2>&1 | tail -3
just selftest; echo "rc=$?"
```

Expected:
- pytest: 712 plus this phase's new tests, all passing;
- grammars byte-identical;
- eval `91/91`, regressions 0;
- injection `20/20`;
- egress `8 passed`;
- bootstrap `11/11`;
- selftest as in Task 1, no new FAIL.

- [ ] **Step 2: Hand-off**

In `progress.md`'s START HERE, write:
- Phase A closed, with the numbers above;
- the next job: "write the Phase B plan (hearing and the window) from spec §4.1–4.3 and §5 B";
- `friday-llm` is left running and `friday.service` is not started;
- Friday 2's state (stopped or not).

- [ ] **Step 3: Commit**

```bash
git add progress.md
git commit -m "docs(progress): Phase A closed -- gates, START HERE for Phase B

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Then ask the owner whether to push. Never push unasked.
