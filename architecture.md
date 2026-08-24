# Friday — Architecture

Companion to `spec.md` (what) and `adr.md` (why). This file is **how**.
Diagrams live in `diagrams/`; this is the prose that binds them.

---

## 1. Shape of the system

One orchestrator process, one inference server, everything else in
library form inside the orchestrator.

```
   friday-llm.service     llama-server, CUDA, loopback (127.0.0.1:8080)
   friday.service         orchestrator: TUI/voice, FSM, whisper, kokoro, sqlite
   friday-searxng.service loopback search proxy (127.0.0.1:8888)
```

Deliberately **not** microservices. Three services is already two more
than the problem needs; the split exists because `llama-server` is a C++
binary with a different lifecycle and a different failure mode
(GPU/driver) from the Python process.

See `diagrams/00-system-overview.md`.

---

## 2. Module layout

As-built through Phase 2 (G13). The FSM lives in `audio/state.py`, the half-duplex gate
is a property on it (`TurnState.mic_open`), dialogue context lives in RAM
(`dialogue.py`), habits, session summaries, reminders, and notes distill into SQLite (`store/`),
proactive scheduling & DND live in `proactive/`, hands-free wake/AEC/VAD/speaker verification live in `audio/`,
and logging & health audits live in `logging_config.py` and `selftest.py`.

```
   friday/
     __main__.py            text-mode entrypoint (TUI), --selftest CLI flag
     voice_main.py          voice-in entrypoint: builds daemon, wake listener + startup wait
     daemon.py              the voice loop: PTT/Wake -> capture -> STT -> turn ->
                            speak, barge-in, confirm-first voice handshake, DND/signoff
     config.py              typed config, fixed paths, panic switch, wake/AEC/VAD/speaker constants
     errors.py              Outcome enum + error taxonomy codes (spec §4)
     turn.py                one turn: utterance -> plan -> execute -> outcome
                            (TurnResult); execute-first (ADR-009)
     dialogue.py            in-RAM session dialogue ring buffer (ADR-048)
     logging_config.py      structured JSON logging, 10MB x 5 rotation, redaction (FR-43)
     selftest.py            unified 7-subsystem sanity & health check CLI (G9)
     prefs_cli.py           `just prefs` — list/export/forget/reset
     ptt_cli.py             `friday-ptt toggle|press|release|cancel` client
     speaker_enroll.py      `just enroll-voice` — interactive 10-utterance profiler (G13)
     eval_harness.py        the G2 runner (the 3 ADR-030 numbers)

     llm/
       client.py            llama-server HTTP client (retries ONLY on connect)
       chat.py              stage 2 free-text conversational reply generator
       grounding.py         search grounding turn under final.gbnf
       grammars/
         plan.gbnf          full action enum
         final.gbnf         action enum = ["none"] ONLY (enforced at G7)
       schema.py            single source of truth; generates grammar+validator
       prompt.py            SYSTEM POLICY + <preferences> digest assembly
       validate.py          strict parse, fail-closed

     proactive/
       __init__.py          proactive module package
       dnd.py               conversational DND state manager & hush phrase matchers (G11)
       notifier.py          notify-send desktop notification adapter (G11)
       briefing.py          startup & sign-off close summaries (G11)
       scheduler.py         background reminder poller & single turn arbiter (G11)

     tools/
       registry.py          frozen dict: tool_id -> ToolSpec (system, hyprland, files, apps)
       executor.py          subprocess argv, no shell, bounded timeout, ban preflight
       apps.py              app_id -> argv map
       search.py            searxng client + sanitizer (G7)
       ban.py               permanent hard ban validator & RiskTier enum (G12)
       typer.py             Wayland typer using ydotool or wtype fail-soft (G12)

     audio/
       capture.py           sounddevice input, 15 s ring, gate, ensure_open (G6/G9)
       state.py             the FSM (diagram 01) + mic_open gate
       stt.py               faster-whisper backend + FR-12/13 policy
       ptt.py               unix-socket PTT server + client (FR-3)
       tts.py               kokoro-onnx wrapper (ONNX/CPU, fp32, 8t, far-end reference tap)
       say.py               `just say` / audition CLI (G5)
       aec.py               WebRTC APM EchoCanceller adapter (G10)
       vad.py               WebRTC VAD & SpeechGate debounce state machine (G10)
       wake.py              openWakeWord hey_jarvis detector, FarEndRef, WakeListener (G10)
       dictation.py         DictationManager & spoken punctuation formatter (G12)
       speaker.py           SpeakerVerifier using sherpa-onnx 3D-Speaker CAM++ (G13)

     store/
       db.py                connection, WAL, single-writer (FR-50..53)
       migrations/          001_init.sql, 002_reminders.sql, 003_notes.sql (forward only)
       prefs.py             slug+alias keys, CRUD, inert digest rendering
       audit.py             redacted dispatch records + retention sweep
       habits.py            deterministic habit pattern mining (ADR-049)
       summarizer.py        session dialogue distillation into summary (ADR-050)
       reminders.py         SQLite reminder & timer store (G11)
       notes.py             SQLite quick notes store (G12)

     ui/
       tui.py               textual app, mode indicator, confirm prompt
       templates.py         outcome -> speech strings

   deploy/
     searxng/
       friday-searxng.service   SearXNG loopback container service
       settings.yml             SearXNG loopback configuration
     systemd/
       friday-llm.service       llama-server systemd user unit
       friday.service           orchestrator daemon systemd user unit

   scripts/
     wake_bench.py          live wake-word, AEC, and VAD benchmark harness

   tests/
     fixtures/
       eval.jsonl           28 fixtures (ADR-030)
       adversarial.jsonl    AS-1..12 (+ youtube AS-13..16 in test_youtube)
       injection.jsonl      20 hostile search results (FR-63)
     test_*.py              290 unit tests across all subsystems

   diagrams/                ASCII, authoritative, updated with code
```

---

## 3. Key interfaces

### 3.1 Turn

```python
@dataclass(frozen=True)
class Turn:
    request_id: str          # uuid4, threaded through logs + audit
    source: Literal["text", "ptt"]
    transcript: str
    plan: Plan | None        # validated model output
    tool_result: ToolResult | None
    outcome: Outcome         # ok | not_found | timeout | denied | error
    spoken: str
    timings: dict[str, float]
```

### 3.2 ToolSpec (the registry entry)

```python
@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    risk: Literal["read_only", "reversible", "irreversible"]
    build_argv: Callable[[dict], list[str]]   # CODE builds argv, not the model
    cwd: str
    env: Mapping[str, str]                    # minimal, explicit, no inherit
    timeout_s: float
    param_schema: dict                        # typed, closed
```

`build_argv` is a function in code. The model's params are inputs to it,
never members of the returned list verbatim unless they came from a
closed enum. This is the whole of ADR-007 in one type.

### 3.3 Executor contract

```python
async def execute(spec: ToolSpec, params: dict, request_id: str) -> ToolResult
```

Guarantees:

- `shell=False`, argv list, explicit minimal env
- bounded by `spec.timeout_s`, process group killed on timeout
- never retried for `reversible` or `irreversible` risk classes
- returns a typed `Outcome`, never raises to the caller
- writes exactly one audit row before returning

---

## 4. Prompt assembly

Built fresh per turn from typed regions. There is no long-lived prompt
string being appended to.

```
   +--------------------------------------------------+
   | SYSTEM POLICY            static, <=600 tok        |
   |   identity, action contract, refusal rules        |
   |   asserted by a unit test; build fails if over    |
   +--------------------------------------------------+
   | <preferences>            <=300 tok                |
   |   editor=code                                     |
   |   browser=brave                                   |
   | </preferences>           DATA, not instructions   |
   +--------------------------------------------------+
   | conversation ring        <=4500 tok               |
   |   evict oldest PAIR, never split a pair           |
   +--------------------------------------------------+
   | <untrusted_data>         <=1500 tok, GROUNDING    |
   |   ...sanitized search results...                  |   TURNS ONLY
   | </untrusted_data>                                 |
   +--------------------------------------------------+
   | current user utterance                            |
   +--------------------------------------------------+
```

**Invariant:** if the `<untrusted_data>` region is non-empty, the request
MUST use `final.gbnf`. Asserted in `llm/client.py` before the request is
sent, not merely by convention at the call site.

Preference rendering is `key=value` inside a fence — never prose. A
preference must never be able to read as a system instruction; that is
the durable-injection vector (a preference written once steers every
future turn).

---

## 5. Concurrency model

Single asyncio event loop. One turn in flight, enforced by the FSM, not
by a lock.

```
   event loop
     |
     +-- TUI task                 (textual, always live) [text mode]
     +-- PTT socket server        (unix socket; Hyprland bind -> friday-ptt
                                   -> one line; NO evdev, ADR-013) [G6]
     +-- audio callback           (PortAudio thread -> ring, NEVER allocates)
     +-- turn task                (at most ONE, cancellable) — FSM in
                                   audio/state.py, one turn enforced there
     +-- speak task               (at most ONE, cancellable = barge-in) [G6]
     +-- db writer task           (serialized queue consumer)
     +-- retention task           (periodic, low priority)
```

CPU-bound work (`whisper`, `kokoro`) runs in a thread pool via
`asyncio.to_thread`, sized explicitly. The audio callback allocates
nothing and never touches the database.

Backpressure:

```
   audio ring buffer     fixed 15 s, preallocated, overwrites oldest
   turn queue            depth 0.  a second request is REJECTED, not queued
   db write queue        depth 1000, then drop-oldest for audit rows,
                         block for preference writes (they are user intent)
   tool concurrency      1
```

---

## 6. Failure and recovery

| Failure | Detection | Recovery |
| :-- | :-- | :-- |
| `llama-server` dies | connect error / health ping | speak `E_LLM_DOWN`; systemd restarts with backoff; orchestrator reconnects, no restart of itself |
| GPU falls off the bus | CUDA error in server logs | server exits, systemd restarts; if 3 restarts in 60 s, stay down and tell the user |
| Audio device lost (suspend) | PortAudio error | close streams, re-enumerate on next PTT, speak nothing |
| SearXNG down | connect error within 8 s | `E_NET_DOWN`, degrade to a non-search answer |
| DB locked | `sqlite3.OperationalError` | one retry after `busy_timeout`, then `E_DB_LOCKED` |
| Model emits garbage | validator | `action=none`, `E_SCHEMA`, log the raw output ONLY to the debug ring buffer |
| Turn hangs | per-stage timeout | cancel the task, release the FSM to IDLE |
| User walks away mid-confirm | 30 s timeout | cancel silently |
| Everything | panic file `~/.local/state/friday/DISABLED` | all dispatch refused; checked before every execute |

**Restart is always safe.** No in-memory state is authoritative. Anything
that matters is in SQLite before the turn completes.

---

## 7. Observability

Structured JSON lines to `~/.local/state/friday/friday.log`, rotated at 10 MB,
5 files. Every line carries `request_id`.

```json
{"ts":"...","lvl":"info","rid":"a1b2","stage":"plan","ms":842,"tool":"open_app","decision":"allow"}
{"ts":"...","lvl":"info","rid":"a1b2","stage":"exec","ms":31,"outcome":"ok"}
```

**Never logged:** `thought`, raw transcripts (unless debug mode is
explicitly on), raw model output, raw search payloads, key events,
absolute home paths, preference values. A redaction filter runs on every
record; a test greps the log for `/home/` and fails on a hit.

Per-stage timings are kept in-process and printed by `just bench` as
p50/p95. No metrics server, no Prometheus. One user, one machine.

Health: `friday --selftest` checks llama-server reachability, GPU arch,
DB schema version, DB permissions, audio devices, and the panic file, and
exits non-zero on any failure. Run it at every gate.

---

## 8. Deployment

`systemd --user` units, not a login shell script.

```
   ~/.config/systemd/user/friday-llm.service
     ExecStart=/opt/llama.cpp/build/bin/llama-server \
       --model  %h/.local/share/friday/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
       --host   127.0.0.1 --port 8080 \
       --ctx-size 8192 --n-gpu-layers 99 \
       --cache-type-k q8_0 --cache-type-v q8_0 \
       --no-webui
     Restart=on-failure
     RestartSec=5s

   ~/.config/systemd/user/friday.service
     After=friday-llm.service
     Requires=friday-llm.service
     ExecStart=%h/Projects/Personal/Intern/friday/.venv/bin/python -m friday
     Restart=on-failure
```

Hardening on the orchestrator unit: `NoNewPrivileges=yes`,
`PrivateTmp=yes`, `ProtectSystem=strict`, `ReadWritePaths=%h/.local/state/friday`.
Note that `open_app` must still reach the Hyprland socket — verify the
sandbox does not break `hyprctl` before enabling `ProtectSystem`.

Startup ordering matters: the orchestrator must tolerate `llama-server`
not being ready yet (retry the health ping, do not crash-loop).

---

## 9. What is deliberately absent

```
   no vector database         50 preferences fit in a prompt
   no embedding model         nothing to embed at this scale
   no ORM                     six tables, parameterized SQL is clearer
   no message queue           one user, one turn at a time
   no docker for the app      systemd user units are the native answer
   no web UI                  textual TUI, per the mandate
   no plugin system           every capability is a reviewed code change
   no retry middleware        retries on side effects are a bug, not a feature
   no LangChain / agent fwk   the whole control flow is ~200 lines of FSM
```

Each line is a decision, not an omission. Adding any of them requires an
ADR that names the problem it solves.
