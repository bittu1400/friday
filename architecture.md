# Friday — Architecture

Companion to `spec.md` (what) and `adr.md` (why). This file is **how**.
Diagrams live in `diagrams/`; this is the prose that binds them.

---

## 1. Shape of the system

One orchestrator process, one inference server, everything else in
library form inside the orchestrator.

```
   friday-llm.service     llama-server, CUDA, loopback/unix socket
   friday.service         orchestrator: TUI, FSM, whisper, kokoro, sqlite
   searxng.service        optional, only in connected mode
```

Deliberately **not** microservices. Three services is already two more
than the problem needs; the split exists because `llama-server` is a C++
binary with a different lifecycle and a different failure mode
(GPU/driver) from the Python process.

See `diagrams/00-system-overview.md`.

---

## 2. Module layout

```
   friday/
     __main__.py            entrypoint, arg parsing, service wiring
     config.py              typed config load + defaults + validation
     errors.py              Outcome enum + error taxonomy codes (spec §4)
     fsm.py                 turn state machine (diagram 01)
     turn.py                Turn dataclass: request_id, transcript,
                            plan, tool_result, outcome, timings

     llm/
       client.py            llama-server HTTP client, timeouts, retries
                            (retries ONLY on connect, never on generate)
       grammars/
         plan.gbnf          full action enum
         final.gbnf         action enum = ["none"] ONLY
       schema.py            single source of truth; generates BOTH the
                            grammar and the validator
       validate.py          strict parse: unknown fields, dup keys,
                            typed params, fail-closed

     tools/
       registry.py          frozen dict: tool_id -> ToolSpec
       executor.py          subprocess argv, no shell, bounded timeout
       apps.py              app_id -> argv map
       search.py            searxng client + sanitizer
       memory_tools.py      remember / forget

     audio/
       capture.py           sounddevice input, ring buffer, mic gate
       stt.py               faster-whisper wrapper, CPU pinned
       tts.py               kokoro wrapper, chunked playback, cancel
       gate.py              the half-duplex boolean (diagram 05)

     store/
       db.py                connection, WAL, single-writer queue
       migrations/          001_init.sql, 002_....sql (forward only)
       prefs.py             CRUD + digest rendering
       audit.py             redacted dispatch records

     ui/
       tui.py               textual app, mode indicator, confirm prompt
       templates.py         outcome -> speech strings

     obs/
       log.py               structured JSON logs, redaction filter
       metrics.py           per-stage timings, in-process counters

   tests/
     fixtures/
       eval.jsonl           50
       adversarial.jsonl    12
       injection.jsonl      20
     test_*.py

   diagrams/                ASCII, authoritative, updated with code
   scripts/                 registered scripts, absolute paths, no args
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
     +-- TUI task                 (textual, always live)
     +-- PTT listener task        (hyprctl signal or evdev)
     +-- audio callback           (PortAudio thread -> queue, NEVER blocks)
     +-- turn task                (at most ONE, cancellable)
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
