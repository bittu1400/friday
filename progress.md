# Friday — Progress

The only file that says what is actually true. A gate is passed when its
acceptance test runs green **and the evidence is pasted into this file**.

Rules:

1. No box is ticked on belief. Paste the command output.
2. No gate is worked on before the one above it passes.
3. If a measurement contradicts a document, fix the document in the same
   commit and note it here.
4. "Works on my machine" is the only kind of evidence that exists here —
   this is a single-machine project. Paste it.

**Overall status:** G0 in progress. Nothing else started. No code exists.

```
   G0 REPO        [ ]
   G1 TOOLCHAIN   [ ]   <-- highest risk. blocks everything.
   G2 EVAL        [ ]
   G3 TEXT+REG    [ ]
   G4 PERSIST     [ ]
   G5 VOICE OUT   [ ]
   G6 VOICE IN    [ ]
   G7 SEARCH      [ ]
   G8 SERVICE     [ ]
```

---

## G0 — Repository and environment

**Acceptance:** `uv run python -V` prints 3.12.x; docs committed; lockfile exists.

- [x] `git init`
- [x] Docs written: `friday.md`, `spec.md`, `adr.md`, `architecture.md`, `threat-model.md`, `open-questions.md`, `diagrams/`
- [x] `friday.md`, `gemini-thoughts.md`, `gpt-thoughts.md` archived to `docs/archive/` with banners
- [ ] `sudo pacman -S just nvtop`   (ADR-025; nvtop for G1 evidence)
- [ ] `.gitignore` written (ADR-023, ADR-024)
- [ ] `git remote add origin`, `git branch -M main`
- [ ] XDG dirs created: `~/.local/share/friday/models`, `~/.local/state/friday`
- [ ] `uv venv .venv --python 3.12`
- [ ] `uv.lock` committed
- [ ] Initial commit

```
EVIDENCE:
$ uv run python -V
  (paste)
```

---

## G1 — Toolchain gate  *** DO THIS FIRST ***

**Acceptance:** sm_120 kernels present; `llama-server` answers curl; peak
VRAM recorded under real desktop load.

This gate exists because the archived blueprint's §5.3 recommended CUDA
12.4 wheels, which contain no sm_120 kernels and would fail at runtime on
this Blackwell GPU (ADR-021). Discovering that at G6 would have cost days.

- [ ] Python env is CPU-only (ADR-018 enforcement)

```bash
uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

```
EVIDENCE (must end in +cpu and print False — False is CORRECT):
  (paste)
```

- [ ] `llama.cpp` built with `-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120`

```
BUILD COMMIT:
  (paste git rev-parse HEAD from the llama.cpp checkout)
```

- [ ] Model downloaded and checksummed

```
MODEL: bartowski/Qwen2.5-7B-Instruct-GGUF :: Qwen2.5-7B-Instruct-Q4_K_M.gguf  (ADR-029)
SHA256:
  (paste)
```

- [ ] Server responds, reports compute capability 12.0, offloads all layers

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"say ok"}],"max_tokens":5}'
```

```
EVIDENCE (curl response):
  (paste)

EVIDENCE (llama-server startup log — require "compute capability 12.0"
and "offloaded XX/XX layers to GPU" with XX==XX):
  (paste)
```

- [ ] VRAM peak under real desktop load (browser open, video playing)

```
$ nvidia-smi --query-gpu=memory.used,memory.total --format=csv
  (paste)

$ nvidia-smi --query-compute-apps=pid,used_memory --format=csv
  (paste)      <-- OQ-11: is the desktop on the dGPU or the iGPU?
```

- [ ] KV cache actual size at ctx 8192 q8_0 (from server startup log)

```
EVIDENCE (expect ~224 MiB, ADR-003):
  (paste)
```

- [ ] Whisper CPU benchmark — OQ-07

```
   clips: 20, lengths 2-8 s, recorded from the laptop DMIC array

   mode              p50 ms   p95 ms   VRAM MiB
   CPU int8 x8        ____     ____       0

   PASS if p95 <= 800 ms.  If it fails, that is stop condition #5 —
   record the GPU numbers here too and reopen ADR-018.

   CUDA int8_float16  ____     ____      ____   (only if CPU failed)

   DECISION:
```

- [ ] NPU presence check — OQ-10

```bash
ls /dev/accel/ 2>/dev/null; lsmod | grep -i vpu
```

```
EVIDENCE:
  (paste)
```

- [ ] No non-loopback bind

```bash
ss -ltnp | grep -E '8080|8888'
```

```
EVIDENCE (must show 127.0.0.1 only):
  (paste)
```

---

## G2 — Eval harness

**Acceptance:** `just eval` prints a pass count. Any count. The number is
the baseline; it does not need to be good yet.

- [ ] `tests/fixtures/eval.jsonl` — 20 seed fixtures (ADR-030), drafted by Claude, edited by user
- [ ] `tests/fixtures/adversarial.jsonl` — 16 malformed/hostile model outputs (incl. AS-13..AS-16)
- [ ] Runner: fixture -> prompt -> llama-server -> validator -> compare
- [ ] Baseline recorded

```
BASELINE:
  fixture-set revision:  ____   (git short sha of eval.jsonl)
  eval:        __/__   (___%)
  known-failing: __
  adversarial: __/16
  model artifact: bartowski Qwen2.5-7B-Instruct-Q4_K_M
  date:
```

- [ ] OQ-08 answered: `thought` on vs off

```
   with thought:    __/__
   without thought: __/__
   DECISION (updates ADR-011):
```

---

## G3 — Text mode and tool registry

**Acceptance:** eval >= 90% (min 20 fixtures), adversarial 16/16, zero `shell=True`.

- [ ] `llm/schema.py` — one schema generates both grammar and validator
- [ ] `plan.gbnf` generated and committed
- [ ] `llm/validate.py` — unknown fields, duplicate keys, typed params, fail-closed
- [ ] `tools/registry.py` — frozen dict, `build_argv` in code
- [ ] `tools/executor.py` — argv list, `shell=False`, minimal env, timeout, process-group kill
- [ ] `ui/templates.py` — outcome templates, no LLM round-trip (ADR-009)
- [ ] Panic file honoured before every dispatch (FR-36)
- [ ] TUI: type, see the action, see the outcome

```
EVIDENCE:
$ just eval
  passed __/__  known-failing __  regressions __

$ just test-adversarial
  __/16

$ grep -rn "shell=True" friday/
  (must be empty)

$ grep -rn "irreversible" friday/tools/registry.py
  (must be empty in Phase 1)
```

- [x] OQ-01 answered 2026-08-22 — ADR-026 (7 apps, firefox/foot/mpv defaults)
- [x] OQ-02 answered 2026-08-22 — `run_script` cut from Phase 1
- [ ] AS-13..AS-16 (youtube query hardening) written and passing — ADR-027

---

## G4 — Persistence

**Acceptance:** 100 parallel writes with zero `database is locked`;
permissions correct; export/delete/reset all work.

- [ ] Migrations 001_init.sql, forward-only, applied at startup
- [ ] WAL, `busy_timeout=5000`, single writer queue
- [ ] `preferences` with `source`, `updated_at`, `expires_at`, `revision`
- [ ] `action_audit` with redacted args
- [ ] `session_summaries`
- [ ] `0600` / `0700`, verified by self-test
- [ ] Retention job (90 days, 50 MB)
- [ ] `friday prefs list|export|forget|reset`
- [ ] Digest rendering as `key=value` in a fence, capped at 300 tokens

```
EVIDENCE:
$ just test-concurrency
  (paste: 100 writes, 0 locked errors)

$ stat -c '%a %n' ~/.local/state/friday/memory.db ~/.local/state/friday
  (must be 600 and 700)

$ grep -rn "thought" friday/store/
  (must be empty)

$ just test-redaction
  (log contains no /home/ paths)
```

- [x] OQ-04 answered 2026-08-22 — ADR-028, in-memory ring buffer, off by default
- [x] OQ-05 answered provisionally 2026-08-22 — ADR-031, nothing leaves the machine, 0600 sufficient. **OQ-05 stays OPEN** by user request; revisit triggers listed in ADR-031.

---

## G5 — Voice out

**Acceptance:** 20 utterances spoken, no clipping, exactly one CUDA
process during playback.

- [ ] `uv pip install "kokoro>=0.9.2" soundfile sounddevice`, `espeak-ng` present
- [ ] Weights from `huggingface.co/hexgrad/Kokoro-82M` only, checksummed
- [ ] Voice audition: `af_heart` / `af_bella` / `af_sky`, same 5 sentences, laptop speakers
- [ ] Voice locked and written into ADR-005
- [ ] Playback non-blocking and cancellable
- [ ] `nvidia-smi` shows exactly one compute process during a spoken turn (FR-71)

```
VOICE CHOSEN:
CHECKSUM:
EVIDENCE (nvidia-smi during playback):
  (paste)
```

---

## G6 — Voice in

**Acceptance:** 20 spoken utterances produce the correct action; TTFA p95
recorded.

- [ ] `capture.py` — ring buffer, 15 s cap, callback allocates nothing
- [ ] `gate.py` — mic open only in CAPTURING
- [ ] `stt.py` — CPU, `language="en"`, `cpu_threads=8`, VAD
- [ ] PTT via Hyprland bind (try this first — ADR-013, OQ-03)
- [ ] If the bind failed: evidence here, then narrow udev ACL, one device, no `grab()`
- [ ] Barge-in: PTT during SPEAKING cancels
- [ ] FR-5: five rapid submits produce one turn and four rejections

```
PTT PATH SHIPPED:  hyprland-bind | evdev
IF EVDEV, WHY THE BIND FAILED:
  (paste evidence — this is a privilege escalation, justify it)

SPOKEN EVAL: __/20

TTFA (end of speech -> first audio):
  p50 ____ ms     p95 ____ ms
  target 1400 / hard fail 4400

OQ-09 DECISION (streaming needed?):
```

---

## G7 — Search  *** the only egress ***

**Acceptance:** IS-1..IS-20 all blocked, asserted on the executor.

- [ ] SearXNG running on `127.0.0.1:8888`
- [ ] `tools/search.py` client + sanitizer (markup, control chars, zero-width, 5 results, 1500 tokens, URLs out of band)
- [ ] `final.gbnf` — action enum length asserted == 1 by a unit test
- [ ] `llm/client.py` asserts: untrusted region non-empty implies `final.gbnf`
- [ ] `tests/fixtures/injection.jsonl` — 20 hostile results
- [ ] Connected mode opt-in, visibly indicated in the TUI
- [ ] Local mode refuses search audibly

```
EVIDENCE:
$ just test-injection
  blocked __/20     (must be 20/20)
  dispatches from grounding turns: __ (must be 0)

$ just test-grammar-lock
  final.gbnf action enum size: __ (must be 1)

EGRESS TEST (block all non-loopback, confirm everything else still works):
  (paste)
```

---

## G8 — Service

**Acceptance:** survives `kill -9` of llama-server; survives suspend/resume.

- [ ] `friday-llm.service`, `friday.service`, ordering, restart backoff
- [ ] `friday --selftest`: server reachable, GPU arch, DB schema + perms, audio devices, panic file, no wildcard bind
- [ ] Log rotation (10 MB x 5)
- [ ] Graceful shutdown, model unload
- [ ] Panic switch documented and tested

```
EVIDENCE:
$ systemctl --user status friday
  (paste)

$ kill -9 $(pgrep llama-server); sleep 10; just selftest
  (paste — must recover)

suspend/resume audio recovery:
  (paste)
```

---

## Decision log

Append a line whenever a measurement changes a document.

```
   DATE        WHAT CHANGED                                    WHERE
   2026-08-22  ctx 2048 -> 8192 q8_0 after pricing KV cache    ADR-003
   2026-08-22  CUDA 12.4 guidance retracted (needs sm_120)     ADR-021
   2026-08-22  wake word cut from Phase 1                      ADR-012
   2026-08-22  STT moved to CPU, one CUDA context              ADR-004/018
   2026-08-22  friday.md v4 archived, no longer authoritative  ADR-022
   2026-08-22  runtime files moved to XDG dirs                  ADR-023
   2026-08-22  laptop-specifications.md gitignored (MACs)       ADR-024
   2026-08-22  task runner = just (installed, not make)         ADR-025
   2026-08-22  app registry fixed: 7 entries, no files/spotify  ADR-026
   2026-08-22  youtube_search allowed as audited exception      ADR-027
   2026-08-22  run_script cut from Phase 1                      OQ-02
   2026-08-22  transcripts: in-memory ring buffer only          ADR-028
   2026-08-22  model artifact pinned to bartowski GGUF          ADR-029
   2026-08-22  eval gate is a RATE on a growing set, not 45/50  ADR-030
   2026-08-22  disk is the boundary, provisionally (OQ-05 open) ADR-031
```

## Time log

Optional, but the honest version of "how long will this take".

```
   GATE   ESTIMATE   ACTUAL   NOTES
   G0     1 h        ____
   G1     3 h        ____     highest variance — CUDA build
   G2     4 h        ____     writing 50 fixtures is the slow part
   G3     8 h        ____
   G4     4 h        ____
   G5     3 h        ____
   G6     6 h        ____     PTT path unknown
   G7     5 h        ____
   G8     3 h        ____
```
