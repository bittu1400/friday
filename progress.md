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

**Overall status:** G0 PASSED. G1 core risk RETIRED (2026-08-22). G2 PASSED
(2026-08-23). G3 PASSED (2026-08-23) — text mode works: `just run` launches
the 5 apps + youtube, eval 20/20, adversarial 16/16, zero `shell=True`, no
irreversible tools, `thought` removed. Next is G4 (persistence). Four G1
measurements remain deferred (VRAM under desktop load, exact KV size,
whisper CPU bench, CPU-torch check) — none block G4.

```
   G0 REPO        [x]
   G1 TOOLCHAIN   [~]   <-- sm_120a PROVEN. measurements deferred (see G1).
   G2 EVAL        [x]   <-- harness + baseline + adversarial. OQ-08 done.
   G3 TEXT+REG    [x]   <-- registry+executor+TUI. eval 20/20, adv 16/16.
   G4 PERSIST     [x]   <-- SQLite memory, prefs, audit, retention. 98 unit,
                        eval 20/20, adv 16/16.
   G5 VOICE OUT   [ ]
   G6 VOICE IN    [ ]
   G7 SEARCH      [ ]
   G8 SERVICE     [ ]
```

---

## NEXT SESSION — START HERE (written 2026-08-23, after G4)

G4 is done. `just run` is a working text assistant that now remembers
preferences (confirm-first), forgets them, and injects a `<preferences>`
digest into planning. Next is **G5 — Voice out** (Kokoro TTS). Per the
build order `{G4,G5}`, G5 is the remaining half; G6 (voice in) follows.

**G5 optimization research is already DONE (2026-08-23, ADR-039).** The
runtime is settled by benchmark on this laptop: `kokoro-onnx` (ONNX/CPU),
fp32 model, 8 threads, no torch. Only the VOICE (OQ-22, user audition) and
a few integration choices remain — see the G5 build steps below.

### What is true right now
- Branch `main`. G0/G1(core)/G2/G3/G4 all passed. `just run` launches the 5
  apps + youtube, remembers/forgets prefs; `just run --dry-run` = no launch.
- `friday/` code: `llm/` (schema, validate, client, prompt, grammars),
  `tools/` (apps, registry, executor), `store/` (db, prefs, audit,
  migrations), `ui/` (templates, tui), plus `config.py`, `errors.py`,
  `turn.py`, `prefs_cli.py`, `__main__.py`.
- Persistence: SQLite at `~/.local/state/friday/memory.db` (WAL, 0600 in a
  0700 dir), single-writer (`store/db.py`), forward-only migrations. `just
  prefs list|export|forget [--hard]|reset --yes`.
- Deps: `textual` (runtime), `pytest` (dev). Store uses stdlib `sqlite3` —
  no new dep. Venv is CPU-only and stays **torch-free**: G5 uses
  `kokoro-onnx` (onnxruntime), STT will use CTranslate2 — neither needs
  torch (ADR-039). The old "CPU-torch check" G1 item is now moot.
- `just eval` = 20/20, `uv run pytest` = 98 passed. baseline.json committed.
- **No llama-server running** — stopped at end of G4. `just serve` to start.
- `web_search` still returns "not yet wired" — G7. Memory is now wired.

### Memory design as built (G4 — ADR-035/036/037/038)
- **Keys**: model supplies a free key; `store/prefs.py` slugifies it to
  `[a-z0-9_]` and folds common synonyms through the `ALIAS` map onto
  canonical anchors (`my name`→`name`, `web browser`→`browser`, …). A slug
  not in the map is stored as-is (the learned tail). Extend `ALIAS` when a
  near-dupe appears — it is data, not a migration.
- **Values** stored raw, but the digest renders them INERT (newline / fence
  / control-char strip, 200-char cap) — that is the durable-injection
  control, not cosmetics.
- **Confirm-first**: a spoken `remember_preference` does NOT write; the turn
  returns a `pending` preference and the TUI asks yes/no (deterministic, no
  2nd model turn). Only an explicit yes writes, `source='user_confirmed'`.
- **Forget**: the voice tool soft-expires (recoverable). The CLI hard-
  deletes only with `--hard` / `reset --yes`.
- **Retention** (`store/audit.py sweep_retention`): audit + summaries only;
  preferences never age out. `pinned` column is inert (kept for a future
  policy change without a migration).

### Then build G5 — runtime ALREADY decided by benchmark (ADR-039)
The optimization research is DONE (see "G5 PRE-WORK" in the G5 section
below + ADR-039). Do NOT re-benchmark or reconsider the PyTorch path.
Settled: **`kokoro-onnx`, fp32 `model.onnx`, `intra_op_num_threads=8`,
CPU provider, no torch.** Numbers, checksums, and staged files are in the
G5 section.

1. **Read** the G5 PRE-WORK block below + ADR-039 + friday.md §7 (rewritten)
   + ADR-020 (no streaming — the measured RTF ~0.14 means TTFA is already
   ~0.2 s, so streaming is unnecessary at G5).
2. **Ask the G5 question batch FIRST** (working agreement rule #2), in ONE
   round, before any code:
   - **OQ-22 (open): voice preset** — user auditions af_heart/af_bella/
     af_sky through the LAPTOP SPEAKERS. WAVs ready at
     `~/.cache/kokoro-bench/samples/`. Send them / play them, get the pick.
   - **Playback library**: `sounddevice` (PortAudio, same lib G6 uses for
     capture) vs write-wav-and-`aplay`. Recommend sounddevice.
   - **Cancellable playback now, or defer to G6 barge-in?** FR-73 wants
     cancellable; but barge-in only matters once there's a mic (G6). Option
     to ship blocking playback at G5, add cancel at G6.
   - **Speak in the turn loop now, or a standalone `friday-say` at G5?**
     Wiring TTS into `turn.py` couples it to the FSM that lands at G6.
     Cleanest G5: a standalone synth+play path + an audition harness; wire
     into the turn loop at G6. Confirm with the user.
3. **Build:** `uv add kokoro-onnx soundfile`; fetch model+voices to an XDG
   share dir and verify both SHA256 (in ADR-039); `friday/audio/tts.py`
   wrapper with the 8-thread CPU session (`Kokoro._setup(session=...)`);
   playback; an audition script; tests.
4. **Acceptance:** 20 utterances spoken, no clipping (user listens),
   `nvidia-smi` = one compute process during a spoken turn (FR-71), voice
   locked in ADR-005 + OQ-22 closed. `just eval` must still be 20/20.

### Carried-over, still optional (blocks nothing)
- The 4 deferred G1 measurements (VRAM peak under desktop load, exact KV
  size, whisper CPU bench, CPU-torch check). Procedures in the G1 blocks
  below.

---

## PRIOR SESSION NOTE (written 2026-08-22)

Everything below is verified state, not intention. Read this block, then
`git log --oneline -8` to see the commits it refers to.

### What is true right now
- G0 passed. Repo on `main`, pushed to `origin` (github.com/bittu1400/friday, private).
- Python 3.12.13 venv at `.venv`, `uv.lock` committed. No runtime deps yet.
- App registry trimmed to 5 (brave/foot/code/mpv/vlc) — ADR-032. See `tech-stack.md`.
- llama.cpp built at `/opt/llama.cpp` (owned by you), commit `b21e4de`,
  CUDA 13.3, **host compiler g++-15** (system gcc 16 is too new), arch
  **sm_120a**. Binary: `/opt/llama.cpp/build/bin/llama-server`.
- Model: `~/.local/share/friday/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf`
  (SHA256 `65b8fcd9…aa1423`). Verified to run on the GPU.
- NPU present (`/dev/accel/accel0`), reserved for Phase 2.
- **No llama-server is running** — the G1 one was stopped at end of session.

### Start the server (needed for any G1 measurement or G2 work)
```bash
export PATH=/opt/cuda/bin:$PATH
/opt/llama.cpp/build/bin/llama-server \
  --model ~/.local/share/friday/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  --host 127.0.0.1 --port 8080 --ctx-size 8192 --n-gpu-layers 99 \
  --cache-type-k q8_0 --cache-type-v q8_0 --no-webui
```
Health: `curl -s http://127.0.0.1:8080/health` → `{"status":"ok"}`.
(There is NO systemd unit yet — that is G8. Run it by hand for now.)

### Finish the 4 deferred G1 measurements (optional; none blocks G2)
1. **VRAM under load** — you open brave + play a video, then run a
   generation and capture `nvidia-smi --query-compute-apps`. Fills OQ-11.
2. **Exact KV size** — try `-lv 4` or `/props`; expect ~224 MiB (ADR-003).
3. **Whisper CPU bench** — record 20 DMIC clips, `uv add faster-whisper`,
   benchmark int8/8-threads. Full procedure in the G1 whisper block below.
4. **CPU-torch check** — only when torch is first added (G5). Enforcement
   snippet is in the G1 CPU-only block below; apply it BEFORE `uv add torch`.

### Then begin G2 — the eval harness (this is the real next build step)
Read G2 in this file + ADR-017 + ADR-030 (rate gate, not a fixed count) +
the working agreement in CLAUDE.md (batch all G2 questions up front). G2
needs 20 seed fixtures drafted by Claude and edited by you, plus the
adversarial set — that fixture-drafting is the first G2 task.

---

## G0 — Repository and environment

**Acceptance:** `uv run python -V` prints 3.12.x; docs committed; lockfile exists.

- [x] `git init`
- [x] Docs written: `friday.md`, `spec.md`, `adr.md`, `architecture.md`, `threat-model.md`, `open-questions.md`, `diagrams/`
- [x] `friday.md`, `gemini-thoughts.md`, `gpt-thoughts.md` archived to `docs/archive/` with banners
- [x] `just` + `nvtop` present (ADR-025) — both already installed, `just 1.58.0`, no pacman needed
- [x] `.gitignore` written (ADR-023, ADR-024) — `.venv/`, XDG strays, `laptop-specifications.md`
- [x] `origin` = github.com/bittu1400/friday.git (private), `main` tracks `origin/main`
- [x] XDG dirs created: `~/.local/share/friday/models` (755), `~/.local/state/friday` (700)
- [x] `uv venv .venv --python 3.12` — CPython 3.12.13
- [x] `uv.lock` committed — `Resolved 1 package`
- [x] Committed (no deps yet; runtime deps land per gate)

```
EVIDENCE:
$ uv run python -V
Python 3.12.13
```

---

## G1 — Toolchain gate  *** DO THIS FIRST ***

**Acceptance:** sm_120 kernels present; `llama-server` answers curl; peak
VRAM recorded under real desktop load.

This gate exists because the archived blueprint's §5.3 recommended CUDA
12.4 wheels, which contain no sm_120 kernels and would fail at runtime on
this Blackwell GPU (ADR-021). Discovering that at G6 would have cost days.

- [~] Python env is CPU-only (ADR-018) — DEFERRED to when torch is first added (G5)

```bash
uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

```
EVIDENCE (must end in +cpu and print False — False is CORRECT):
  torch is NOT installed yet (no audio deps until G5), so there is nothing
  to check. When torch is added it MUST be the CPU wheel. Enforce in
  pyproject before the first `uv add torch`:
      [tool.uv.sources]  torch = { index = "pytorch-cpu" }
      [[tool.uv.index]]  name = "pytorch-cpu"
                         url = "https://download.pytorch.org/whl/cpu"
                         explicit = true
  Then run the check above and paste `+cpu ... False` here.
  (Empirically already safe: only llama-server holds VRAM, see below.)
```

- [x] `llama.cpp` built with `-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120`

```
BUILD COMMIT:
  b21e4de74567f5eef213765c9476a843c2e43f0d  (ggml 0.21.0, tag shows as b1-b21e4de)
  location: /opt/llama.cpp   (built by user, owned by user, no sudo per build)
  toolchain: CUDA 13.3 (nvcc V13.3.73), Ninja, Release
  HOST COMPILER: g++-15 (gcc 15.3.0) — system gcc is 16.2.1, TOO NEW for
    CUDA 13.3; forced via -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-15.
  ARCH: -DCMAKE_CUDA_ARCHITECTURES=120 was auto-promoted by cmake to 120a
    (Blackwell accelerated variant) — this is correct for the RTX 5070.
  configure line:
    cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON \
      -DCMAKE_CUDA_ARCHITECTURES=120 \
      -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-15 -DLLAMA_CURL=OFF
  build: cmake --build build --target llama-server -j$(nproc)
```

- [x] Model downloaded and checksummed — 4.4 GB, at `~/.local/share/friday/models/`

```
MODEL: bartowski/Qwen2.5-7B-Instruct-GGUF :: Qwen2.5-7B-Instruct-Q4_K_M.gguf  (ADR-029)
SHA256:
  65b8fcd92af6b4fefa935c625d1ac27ea29dcb6ee14589c55a8f115ceaaa1423
```

- [x] Server responds; sm_120a kernels PROVEN to execute on the GPU

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"say ok"}],"max_tokens":5}'
```

```
EVIDENCE (curl response):
  {"choices":[{"finish_reason":"length","message":{"role":"assistant",
   "content":"Ok! How can I"}}], ... "system_fingerprint":"b1-b21e4de",
   "usage":{"prompt_tokens":31,"completion_tokens":5},
   "timings":{"prompt_per_second":480.3, ...}}

DOC DRIFT (noted per progress.md rule 3): the expected startup-log strings
"compute capability 12.0" and "offloaded XX/XX layers to GPU" DO NOT appear
in llama.cpp b21e4de — this build dropped those verbose device lines. The
gate is satisfied by stronger empirical proof instead:

  1. nvidia-smi attributes 4696 MiB of dGPU VRAM to the llama-server pid
     (a CPU-only load would show 0):
       747143  /opt/llama.cpp/build/bin/llama-server   4696 MiB
  2. A real generation returned tokens. If sm_120 kernels were missing the
     call would have died with "no kernel image is available for execution
     on the device" (the exact ADR-021 failure). It did not. Kernels work.

llama-server startup log (b21e4de, verbosity 3, full): loads model, prints
"model loaded" + "listening on http://127.0.0.1:8080"; no CUDA device lines.
```

- [~] VRAM peak — server-loaded snapshot taken; UNDER-LOAD peak DEFERRED to next session (user opens browser+video, decided 2026-08-22)

```
Snapshot with llama-server up (ctx 8192, q8_0 KV), NO browser/video load:
$ nvidia-smi --query-gpu=memory.used,memory.free --format=csv
  4798 MiB, 2949 MiB     (of 8151 MiB total)

$ nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
  747143  llama-server   4696 MiB
  1599    walker           79 MiB    <-- OQ-11: a Wayland launcher IS on the
                                         dGPU. So the desktop is NOT wholly
                                         on the iGPU. Full answer next session
                                         with a browser + video playing.

NEXT SESSION: open brave + play a video, run a llama-server generation,
capture nvidia-smi during it. That is the real peak.
```

- [~] KV cache actual size at ctx 8192 q8_0 — NOT emitted by b21e4de log

```
EVIDENCE (expect ~224 MiB, ADR-003):
  b21e4de does not print per-buffer KV size at verbosity 3. The ~224 MiB
  prediction is unfalsified: total llama-server VRAM 4696 MiB is consistent
  with model (~4.4 GiB) + KV (~224 MiB) + compute buffer. Exact KV number
  DEFERRED: next session try `--verbose`/`-lv 4` or `/props`, or compute
  from n_ctx * 2 * n_layer * n_kv_head * head_dim at q8_0.
```

- [~] Whisper CPU benchmark — OQ-07 — DEFERRED to next session (decided 2026-08-22)

```
   DEFERRED: needs 20 REAL clips from this laptop's DMIC array (synthetic
   was rejected — real mic noise is the point). Blocks nothing on the
   critical path; STT is not wired until G6. Procedure for next session:

   1. Record 20 clips, 2-8 s, normal speaking voice, into a scratch dir:
        for i in $(seq -w 1 20); do
          echo "clip $i: speak now (~5s), Ctrl-C to stop"
          arecord -f S16_LE -r 16000 -c 1 /tmp/wclips/clip_$i.wav
        done
      (confirm the DMIC is the default source first: `arecord -l`)
   2. Install STT deps in the venv:  uv add faster-whisper
   3. Benchmark int8 / cpu_threads=8 over the 20 clips, medium model,
      language="en", VAD on; record p50/p95 wall time per clip.

   clips: 20, lengths 2-8 s, recorded from the laptop DMIC array

   mode              p50 ms   p95 ms   VRAM MiB
   CPU int8 x8        ____     ____       0

   PASS if p95 <= 800 ms.  If it fails, that is stop condition #5 —
   record the GPU numbers here too and reopen ADR-018.

   CUDA int8_float16  ____     ____      ____   (only if CPU failed)

   DECISION:
```

- [x] NPU presence check — OQ-10 — device PRESENT, excluded Phase 1 (ADR-019)

```bash
ls /dev/accel/ 2>/dev/null; lsmod | grep -i vpu
```

```
EVIDENCE:
$ ls /dev/accel/
accel0
$ lsmod | grep -i vpu
intel_vpu             389120  0
```

- [x] No non-loopback bind

```bash
ss -ltnp | grep -E '8080|8888'
```

```
EVIDENCE (must show 127.0.0.1 only):
  LISTEN 0 512 127.0.0.1:8080 0.0.0.0:* users:(("llama-server",pid=747143,fd=37))
  (8888 absent — SearXNG not running until G7, expected)
```

---

## G2 — Eval harness

**Acceptance:** `just eval` prints a pass count. Any count. The number is
the baseline; it does not need to be good yet.

- [x] `tests/fixtures/eval.jsonl` — 20 seed fixtures (ADR-030), drafted by Claude (awaiting user phrasing edits)
- [x] `tests/fixtures/adversarial.jsonl` — 12 (AS-1..AS-12); AS-13..AS-16 deferred to G3 with the youtube URL builder (ADR-033)
- [x] Runner: fixture -> prompt -> llama-server -> validator -> compare — `friday/eval_harness.py`
- [x] Baseline recorded — `tests/fixtures/baseline.json`

New code (G2, minimal-but-real per ADR-033):
```
   friday/llm/schema.py        single source of truth (grammar + validator)
   friday/llm/grammars/*.gbnf   generated: plan.gbnf, plan_no_thought.gbnf
   friday/llm/validate.py      fail-closed plan validator
   friday/llm/client.py        sync stdlib llama client (connect-retry only)
   friday/llm/prompt.py        SYSTEM POLICY (planning prompt)
   friday/eval_harness.py      the runner; prints the 3 ADR-030 numbers
   tests/test_{schema,validate,adversarial}.py
   justfile                    serve / eval / eval-thought / test targets
```

```
BASELINE (G2 historical — SUPERSEDED at G3 by 20/20 after thought removal
+ prompt tuning; the committed baseline.json now reads 20/20):
  fixture-set revision:  d59d519e086c   (sha1 of eval.jsonl)
  eval:        18/20   (90%)   [with thought]  -- E05, E07 the two failures
  known-failing: 0
  adversarial: 12/12  (all AS-1..12 rejected; `uv run pytest` -> 22 passed)
  model artifact: bartowski Qwen2.5-7B-Instruct-Q4_K_M
  date: 2026-08-23

EVIDENCE:
$ uv run python -m friday.eval_harness --both
  === with thought ===     passed 18/20 (90%)  known-failing 0  regressions 0
  === without thought ===  passed 18/20 (90%)  known-failing 0  regressions 0
  OQ-08 delta (thought - no-thought): 0 fixtures

$ uv run pytest -q
  22 passed

FAILURES (baseline reality, tuning targets for G3 — not G2 blockers):
  E05 "open vlc"                     -> none. Model said "vlc is not in the
                                        list of known apps" though vlc IS in
                                        the enum. Prompt-clarity fix at G3.
  E07 "what's the weather in ..."    -> none. Weather query not routed to
                                        web_search. Prompt-tuning at G3.
```

- [x] OQ-08 answered: `thought` on vs off

```
   with thought:    18/20
   without thought: 18/20
   DECISION (updates ADR-011): delta 0 (< 2) -> `thought` earns nothing.
   Remove it from schema/grammar/prompt at the start of G3 (deferred out of
   the G2 commit for a clean re-baseline; flagged for user confirmation).
   OQ-08 closed. See ADR-011, ADR-033.
```

---

## G3 — Text mode and tool registry

**Acceptance:** eval >= 90% (min 20 fixtures), adversarial 16/16, zero `shell=True`.

**Status: PASSED 2026-08-23.** All acceptance conditions met; evidence below.

- [x] `llm/schema.py` — one schema generates BOTH grammars + drives validator; `thought` removed (OQ-08)
- [x] `plan.gbnf` + `final.gbnf` generated and committed (final.gbnf enforced at G7)
- [x] `llm/validate.py` — unknown fields, dup keys, typed params, NFKC, fail-closed
- [x] `tools/registry.py` — frozen dict, `build_argv` in code, `target_binary` preflight
- [x] `tools/executor.py` — argv list, `shell=False`, minimal env, timeout, process-group kill, no retry
- [x] `ui/templates.py` — outcome templates keyed on outcome, no LLM round-trip (ADR-009)
- [x] Panic file honoured before every dispatch (FR-36) — `config.is_disabled()`, tested
- [x] TUI: type, see the action, see the outcome — `friday/ui/tui.py` (textual); `just run`

New code (G3, decisions in ADR-034):
```
   friday/config.py            paths, panic switch (file + FRIDAY_DISABLED env)
   friday/errors.py            Outcome enum + taxonomy codes + PolicyRejected
   friday/turn.py              utterance -> plan -> execute-first -> speak
   friday/tools/apps.py        5 semantic app keys -> (argv, display)
   friday/tools/registry.py    ToolSpec + REGISTRY + youtube_url hardening
   friday/tools/executor.py    async subprocess, shell=False, panic, no retry
   friday/ui/templates.py      outcome -> string (ADR-009)
   friday/ui/tui.py            textual text-mode UI
   friday/__main__.py          `friday` / `just run` [--dry-run]
   tests/test_{registry,executor,youtube,turn}.py
```

```
EVIDENCE (2026-08-23):
$ just eval                         # thought removed, prompt tuned
  fixture-set revision: d59d519e086c
  passed 20/20  (100%)   known-failing 0   regressions 0
  (E05 "open vlc" and E07 "weather" — the two G2 failures — now pass)

$ uv run pytest tests/test_adversarial.py tests/test_youtube.py -q
  17 passed          # AS-1..12 (validator) + AS-13..16 (youtube builder) = 16/16 cases

$ uv run pytest -q
  42 passed

$ grep -rn "shell=True" friday/
  (empty)

$ grep -n "irreversible" friday/tools/registry.py
  (only the Literal type + FR-33 comment; NO irreversible entry)

END-TO-END (dry-run, live server, no windows spawned):
  'open my browser'        -> open_app    dispatched=True  Opened Brave [dry-run: hyprctl dispatch exec brave]
  'put on some lo-fi'      -> youtube_search (fixture E11 passes)
  "what's the weather..."  -> web_search  [planned — arrives at G7]
  'run rm -rf /'           -> none        (no action)
  Real subprocess execution proven by test_executor (true/false/sleep);
  hyprctl argv proven by dry-run. No app windows opened during testing.
```

- [x] OQ-01 answered 2026-08-22 — ADR-032 (5 apps: brave/foot/code/mpv+vlc; supersedes ADR-026)
- [x] OQ-02 answered 2026-08-22 — `run_script` cut from Phase 1
- [x] AS-13..AS-16 (youtube query hardening) written and passing — ADR-027, in `tests/test_youtube.py`

---

## G4 — Persistence  **PASSED 2026-08-23**

**Acceptance:** 100 parallel writes with zero `database is locked`;
permissions correct; export/delete/reset all work.

Decisions this gate: OQ-18..21 answered by user 2026-08-23 →
ADR-035 (free slug + alias anchors), ADR-036 (voice soft / CLI hard),
ADR-037 (confirm-first spoken prefs), ADR-038 (retention = logs only).

- [x] Migrations `store/migrations/001_init.sql`, forward-only, applied at startup (`store/db.py`)
- [x] WAL, `busy_timeout=5000`, single writer (one connection + one lock — FR-51)
- [x] `preferences` with `source`, `updated_at`, `expires_at`, `revision`
- [x] `action_audit` with redacted args (`store/audit.py`)
- [x] `session_summaries`
- [x] `0600` / `0700`, enforced on open, asserted in `test_db.py`
- [x] Retention job (90 days) — audit + summaries only, prefs never age out (ADR-038)
- [x] `just prefs list|export|forget|reset` (`friday/prefs_cli.py`)
- [x] Digest rendering as `key=value` in a fence; values rendered inert (newline/fence-token strip, 200-char cap — the durable-injection control)
- [x] Confirm-first handshake (ADR-037): deterministic yes/no in the TUI, no 2nd model turn
- [x] Preference key slug + curated alias map (ADR-035); free tail learned, common keys deduped

```
EVIDENCE (2026-08-23):

$ uv run pytest -q
  98 passed
  (includes: test_db 100-parallel-writes → 0 locked, 100 rows;
   perms 0600/0700; migrations fresh+existing → v1;
   test_prefs slug/alias/soft-hard/digest; test_audit redaction+retention;
   test_prompt eval-prompt-unchanged; test_no_fstring_sql; test_prefs_cli
   4 subcommands; test_memory_turn confirm-first + soft-forget + digest inject)

$ just eval                       # llama-server up
  passed 20/20  (100%)   regressions vs baseline: 0

$ just test-adversarial
  17 passed  (AS-1..16 = 16/16 + suite)

Live end-to-end (temp DB, real model, dry-run):
  "call me Subham"      → plan remember_preference, pending, NOTHING written
  confirm               → "Okay, I'll remember that your name is Subham." active={'name':'Subham'}
  next turn             → digest injected: '<preferences>\nname=Subham\n</preferences>'
  "forget what you call me" → plan forget_preference, soft-expired, active={}
  perms: db 0o600  dir 0o700 ; audit rows written, args_redacted (no /home/)

$ grep -rn "thought" friday/store/     → 1 hit, a COMMENT in 001_init.sql
  documenting the absence; no `thought` column exists (FR-57 by schema)
```

- [x] OQ-18..21 answered 2026-08-23 — ADR-035/036/037/038
- [x] OQ-04 answered 2026-08-22 — ADR-028, in-memory ring buffer, off by default
- [x] OQ-05 answered provisionally 2026-08-22 — ADR-031, nothing leaves the machine, 0600 sufficient. **OQ-05 stays OPEN** by user request; revisit triggers listed in ADR-031.

---

## G5 — Voice out

**Acceptance:** 20 utterances spoken, no clipping, exactly one CUDA
process during playback, voice locked.

### G5 PRE-WORK — Kokoro optimization benchmark **DONE 2026-08-23** (ADR-039)

Benchmarked every practical Kokoro runtime on THIS laptop before writing
any G5 code. Env: `~/.cache/kokoro-bench` (isolated venv), onnxruntime
1.29.0, `CPUExecutionProvider`. CPU: Core Ultra 9 275HX, 8 P + 16 E, **no
AVX-512**. Median of 3, warm. Paragraph RTF = synth ÷ audio; short =
"Opening Brave." latency.

```
   variant   best para-RTF   short lat @8t   peak RSS   verdict
   fp32       0.138 @8t        0.207 s        845 MB    WINNER, full quality
              0.131 @16t
   q4f16      0.131 @8t        0.207 s        909 MB    ties speed; 4-bit
                                                        risk; MORE RAM
   q8         0.592 @8t        0.916 s        609 MB    ~4x SLOWER
   q8f16      0.602 @8t        0.931 s        601 MB    ~4x SLOWER
   fp16       BROKEN                                    0 samples on the
                                                        paragraph (unusable)

   thread sweep on fp32 (para RTF): 1t 0.63 | 4t 0.25 | 8t 0.138 |
     10t 0.132 | 16t 0.131 | 24t 0.164  -> 8 threads = the P-core count;
     24 (spills onto E-cores) is WORSE. 8t best short latency (0.207 s).

   VRAM during synth: 2 MiB (idle desktop), 0 compute apps. CPU provider
     only -> providers == ['CPUExecutionProvider'].
```

Two counter-intuitive, MEASURED findings (do not "optimize" past them):
1. int8 (q8/q8f16) is ~4x SLOWER than fp32 here — no AVX-512, and ORT int8
   kernels lose to vectorized fp32 AVX2 on this CPU.
2. fp16 is BROKEN on CPU onnxruntime — returns 0 audio samples for
   multi-sentence input.

Runtime choice (ADR-039): **`kokoro-onnx` (ONNX/CPU), fp32 `model.onnx`,
`intra_op_num_threads=8`, inter_op=1, sequential, ENABLE_ALL.** The
PyTorch `kokoro` path is REJECTED — `uv pip install --dry-run kokoro`
pulls 99 pkgs incl. `torch==2.13.0` + full CUDA 13 stack (FR-71 hazard).
`kokoro-onnx` pulls 8 pkgs, no torch → FR-71 holds by construction.

Headroom: RTF ~0.14 (~7x real-time) → ADR-020 holds, no streaming at G5.

Files staged (disk, not repo): `~/.cache/kokoro-bench/models/model.onnx`
(sha256 `8fbea51e…21a34cb`), `voices-v1.0.bin` (sha256 `bca610b8…f1fbf7d`);
audition WAVs in `~/.cache/kokoro-bench/samples/`.

### G5 BUILD — remaining (next session)

- [ ] `uv add kokoro-onnx soundfile` (NO torch); `espeak-ng` present (1.52.0)
- [ ] Fetch model+voices to a runtime dir (XDG share), verify the 2 SHA256s
- [ ] `friday/audio/tts.py`: kokoro-onnx wrapper, 8-thread CPU session
      (inject via `Kokoro._setup(session=...)`), `synth(text)->(samples,sr)`
- [ ] Playback (`sounddevice`), non-blocking + cancellable (FR-73) — or
      defer cancel to G6 barge-in; decide in the G5 question batch
- [ ] **OQ-22: user auditions af_heart/af_bella/af_sky through speakers**,
      picks one → ADR-005 TBD line + config.toml, close OQ-22
- [ ] Wire outcome templates to speak (turn loop or standalone at G5?) —
      G5 question batch
- [ ] `nvidia-smi` during a spoken turn = one compute process (FR-71)
- [ ] 20 utterances spoken, no clipping (user listens)

```
VOICE CHOSEN:        (OQ-22 — pending user audition)
CHECKSUM:            model.onnx 8fbea51e…21a34cb ; voices bca610b8…f1fbf7d
BENCHMARK EVIDENCE:  above (ADR-039)
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
   2026-08-22  registry trimmed 7->5 (drop firefox, kitty)     ADR-032
   2026-08-22  youtube_search allowed as audited exception      ADR-027
   2026-08-22  run_script cut from Phase 1                      OQ-02
   2026-08-22  transcripts: in-memory ring buffer only          ADR-028
   2026-08-22  model artifact pinned to bartowski GGUF          ADR-029
   2026-08-22  eval gate is a RATE on a growing set, not 45/50  ADR-030
   2026-08-22  disk is the boundary, provisionally (OQ-05 open) ADR-031
   2026-08-22  NPU present (/dev/accel/accel0), Phase 2 option  ADR-019/OQ-10
   2026-08-22  llama.cpp sm_120a build runs on GPU; risk gone   G1/ADR-021
   2026-08-22  CUDA 13.3 needs g++-15 host (gcc16 too new)      G1 build note
   2026-08-22  b21e4de log dropped "compute capability" strings G1 doc-drift
   2026-08-23  G2 harness built; baseline 18/20, adversarial 12/12  G2/ADR-033
   2026-08-23  youtube = 2 top-level actions (fixes §5.1 drift)     ADR-033
   2026-08-23  eval scoring: enum exact, free-text lenient          ADR-033
   2026-08-23  G2 adversarial = AS-1..12; AS-13..16 to G3           ADR-033
   2026-08-23  OQ-08 delta 0: drop `thought` (removal at G3)        ADR-011
   2026-08-23  G3 PASSED: eval 20/20, adversarial 16/16            G3/ADR-034
   2026-08-23  `thought` removed from schema/grammar/prompt        ADR-011
   2026-08-23  full textual TUI + --dry-run flag                    ADR-034
   2026-08-23  not_found via which() preflight (hyprctl exits 0)    ADR-034
   2026-08-23  youtube opens in brave, not firefox                  ADR-034
   2026-08-23  panic: DISABLED file or FRIDAY_DISABLED env         ADR-034/FR-36
   2026-08-23  pref keys: free slug + alias anchors (opt d)        OQ-18/ADR-035
   2026-08-23  forget: voice soft-expire, CLI --hard/--yes         OQ-19/ADR-036
   2026-08-23  spoken pref confirmed first (UI handshake)          OQ-20/ADR-037
   2026-08-23  retention = logs only; prefs never age out          OQ-21/ADR-038
   2026-08-23  G4 PASSED: 98 unit, eval 20/20, adv 16/16           G4
   2026-08-23  Kokoro runtime = kokoro-onnx (ONNX/CPU), not torch  ADR-039
   2026-08-23  Kokoro model = fp32; int8 4x slower, fp16 broken    ADR-039
   2026-08-23  ONNX intra_op=8 (P-cores); 24 threads worse         ADR-039
   2026-08-23  venv now torch-free (STT=CT2, TTS=ORT)              ADR-039
   2026-08-23  OQ-22 opened: voice audition (user)                 OQ-22
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
