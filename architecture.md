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
     __init__.py            sets ORT_DISABLE_TELEMETRY=1 BEFORE onnxruntime can be
                            imported. Not decoration: `import onnxruntime` opens
                            sockets to *.events.data.microsoft.com, five components
                            route through ORT, and the Python API for this does
                            not work (D27, ADR-112, FR-133)
     __main__.py            text-mode entrypoint (TUI), --selftest CLI flag
     voice_main.py          voice-in entrypoint: builds daemon, wake listener + startup wait
     daemon.py              the voice loop: PTT/Wake -> capture -> STT -> turn ->
                            speak, barge-in, confirm-first voice handshake, DND/signoff
     config.py              typed config, fixed paths, panic switch, wake/AEC/VAD/speaker constants
     capabilities.py        ONE RECORD PER CAPABILITY (Phase 3 §1; ADR-123,
                            ADR-124, ADR-125). `Risk` (5 tiers) + frozen
                            `Capability` + the 25 actions in one ORDERED tuple --
                            the order is load-bearing, because `ACTIONS` is
                            `tuple(PARAM_SCHEMA)` and the committed grammars
                            enumerate names in that sequence. `risk` is
                            `Risk | Callable[[Params], Risk]`: three of the five
                            live confirm gates key on a PARAM value, not the
                            action (`system_wifi` off, `hypr_window` close,
                            `open_app` Settings), which design §1's flat field
                            could not express.
                            FIELDS AND THEIR CONSUMERS -- every one has a test:
                              id, params  -> PARAM_SCHEMA -> both grammars (3.2)
                              risk        -> the confirm decision AND the panic
                                             gate, in `gate.py` (3.5, 3.8)
                              summary     -> SYSTEM_POLICY's action block, VERBATIM
                                             and byte-identical (3.3)
                              persona     -> CHAT_SYSTEM's toolset sentence (3.3)
                              ask         -> the spoken confirm question, verbatim
                              describe    -> what the held PendingAction records
                              subject     -> (kind, subject, argv) a FIRST_USE
                                             approval is keyed to (3.9)
                              examples    -> >=2 utterances that MUST exist in
                                             tests/fixtures/eval.jsonl (3.6)
                              hotwords    -> config.STT_HOTWORDS, derived (3.7)
                            `risk`, `summary` and `persona` have NO DEFAULT: a
                            capability that omits one does not construct.
                            `examples` DOES default to `()`, on purpose, so that
                            forgetting it is possible and
                            `tests/test_fixture_obligation.py` is the thing that
                            catches it.
                            NOT derived, deliberately (ADR-125): the phrasing in
                            `habits.describe_action` (the OBLIGATION is derived,
                            the hundred lines of tuned prose are not), and
                            `summary`'s length
     errors.py              Outcome enum + error taxonomy codes (spec §4)
     turn.py                one turn: utterance -> plan -> GATE -> handler ->
                            outcome (TurnResult); execute-first (ADR-009). 246
                            lines since criterion 3.4 (was 941). It owns the
                            two-pass plan (ADR-065), the gate call, and the ONE
                            shared body every subprocess capability dispatches
                            through. It holds NO per-capability branch --
                            `tests/test_handler_table.py` fails if one appears.
                            The single exemption is `plan.name == "none"`, which
                            is ADR-065's re-plan trigger: a property of the plan,
                            not a capability. Re-exports every name that moved,
                            because ~30 test files and both UIs import from here
     gate.py                the derived gate + the confirm handshake (3.5, 3.9).
                            `_panic_blocked` -- one panic check for every tier
                            above NONE, replacing eight hand-written
                            `config.is_disabled()` blocks (F1's fix, finished).
                            `_confirm_question` -- the confirm decision, read off
                            `risk_for(params)`, replacing five hand-coded
                            branches, THREE of which could be deleted with the
                            whole suite green (M1). `_record_approval` -- writes a
                            FIRST_USE grant, and ONLY from a completed handshake,
                            and only AFTER the panic check (design §3.2; that
                            ordering survived its first mutation, so it has a
                            test named after it). Also owns `PendingAction`,
                            `TurnResult`, `is_affirmation`/`is_decline`, and
                            `resolve_pending`, the ONE confirm resolver both UIs
                            call (ADR-069) -- it was two copies until the TUI's
                            crashed on every G12 action (audit C1). Returns
                            `str | None` since ADR-075: `None` means the answer
                            was neither a yes nor a no, so the pending has been
                            cancelled + audited and the CALLER must run the same
                            text as a fresh command.
                            PATCH HERE, NOT VIA `friday.turn`: `friday.turn`
                            re-exports these names, and rebinding a re-export
                            does not reach the caller -- two tests proved it
     handlers.py            one handler per capability + `HANDLERS`, the table the
                            turn looks into (3.4). `TurnContext` carries what a
                            handler may reach and nothing more. A handler runs
                            only AFTER both gates pass, so NO handler checks
                            `config.is_disabled()` and NO handler asks a
                            question -- if you are writing either, it belongs in
                            `risk`. Capabilities with a `Subprocess` spec are
                            deliberately absent: they share one body in `turn.py`
                            and the lookup MISSING is what selects it.
                            A handler that does real work AUDITS it -- including
                            `_h_chat` since D37, whose row carries `params={}`
                            because the utterance and the reply are both what
                            invariant #7 forbids on disk (FR-150). A handler's
                            own error path needs its own test: `daemon.py`
                            catches `Exception` and speaks one line for every
                            failure, so 653 tests were green over a handler that
                            raised `NameError` instead of failing closed (D35)
     dialogue.py            in-RAM session dialogue ring buffer (ADR-048)
     logging_config.py      structured JSON logging, 10MB x 5 rotation, redaction (FR-43)
     selftest.py            unified 10-subsystem sanity & health check CLI (G9, F28,
                            ADR-109; the 10th asks systemd whether the RUNNING unit
                            matches the committed one -- M16, ADR-117)
     stats_cli.py           `just stats` — latency & TTFA breakdown by action class
                            (ADR-107, FR-128). `ACTION_CLASSES` is the one
                            remaining hand-written list that names capabilities;
                            a test asserts every capability but `none` has an
                            entry, and the buckets are DERIVED from it rather
                            than re-listed (FR-152) -- re-listing them made the
                            latency tool raise KeyError on the first row of any
                            class added to it
     watchdog.py            systemd sd_notify READY/STOPPING + periodic WATCHDOG task (F11, ADR-109)
     prefs_cli.py           `just prefs` — list/export/forget/reset
     ptt_cli.py             `friday-ptt toggle|press|release|cancel` client
     speaker_enroll.py      `just enroll-voice` — interactive 10-utterance profiler (G13)
     eval_harness.py        the G2 runner (the 3 ADR-030 numbers)

     llm/
       client.py            llama-server HTTP client (retries ONLY on connect)
       chat.py              stage 2 free-text conversational reply generator
       grounding.py         search grounding turn under final.gbnf
       grammars/
         plan.gbnf          full action enum (30 actions); 9 closed enums constrained (ADR-128, ADR-129)
         final.gbnf         action enum = ["none"] ONLY (enforced at G7)
       schema.py            grammar + validator generator. NO LONGER the source of
                            truth: since ADR-123 `PARAM_SCHEMA` is a VIEW over
                            `friday/capabilities.py` (and since ADR-128/ADR-129 derives
                            GBNF rules for the nine closed enum actions directly
                            from `Capability.params`, with open_app and window_focus_app
                            explicitly excluded as machine-dependent). The param vocabularies are
                            re-exported here so `from friday.llm.schema import WORKSPACE_ENUM`
                            keeps working, but they are DECLARED with the record
       prompt.py            SYSTEM POLICY + <preferences> digest assembly. BOTH
                            prompt regions are DERIVED from `capabilities.py`
                            (3.3): the action block is one `summary` per
                            capability and comes out BYTE-IDENTICAL to the
                            hand-written string it replaced (5381 chars, 1401
                            tokens, pinned against
                            `tests/fixtures/system_policy.txt`); the chat
                            persona's toolset sentence is one `persona` clause
                            per capability and is the one region deliberately
                            REWORDED, because the old prose grouped clauses in an
                            order the record does not have. That closes F2 by
                            CONSTRUCTION -- the persona had denied an ability the
                            schema had twice, months apart
       validate.py          strict parse, fail-closed. A miss on `open_app.app`
                            retries ONCE through `desktop.app_key` -- the same
                            function that generated every id -- and accepts only an
                            exact member (D34, ADR-121). Not fuzzy matching:
                            `app_key` is a whitelist, so AS-7/8/9 and a bare prefix
                            all still reject. The rejection names the RAW value the
                            planner emitted, which is what makes E_TOOL_NOTFOUND
                            diagnosable

     proactive/
       __init__.py          proactive module package
       dnd.py               conversational DND state manager & hush phrase matchers (G11)
       notifier.py          notify-send desktop notification adapter (G11)
       briefing.py          startup & sign-off close summaries (G11)
       scheduler.py         background reminder poller & single turn arbiter (G11).
                            Takes NO DndManager: timers and reminders fire during
                            DND by decision (2026-08-24), and the unused `dnd=`
                            parameter that implied otherwise was removed 2026-08-29

     tools/
       registry.py          frozen dict: tool_id -> ToolSpec (system, hyprland, files, apps)
       executor.py          subprocess argv, no shell, bounded timeout, ban preflight
       apps.py              app_id -> argv map. THREE id sources, because no single
                            one is a name a human says: the `.desktop` Name (carries
                            releases and codenames), the binary basename (`idea`,
                            `studio` -- abbreviations), and since ADR-122 the vendor
                            path `.../<app-name>/bin/<exe>`. Filesystem furniture is
                            excluded and an alias claimed by TWO entries is dropped,
                            never resolved (D33)
       desktop.py           XDG desktop-entry scan -> the installed applications
                            (ADR-097). Owns `app_key` (casefold, then `[^a-z0-9]+`
                            to "_"), the field-code stripper (ADR-114a) and the
                            Settings-category test. Runs every scanned argv through
                            `ban.assert_not_banned`, so a stricter ban list DELETES
                            enum ids -- measure the whole table before tightening it
       env.py               `SUBPROCESS_ENV`: the ONE explicit environment every
                            subprocess runs under (F4, FR-140, ADR-119). Was
                            `registry._build_app_env`; `registry._APP_ENV` is now an
                            alias. Invariant #3's fourth clause had FIVE unlabelled
                            exceptions until 2026-09-04 -- clipboard x2, typer x2 and
                            proactive/notifier inherited all ~50 of the daemon's
                            variables, `NOTIFY_SOCKET` included
       search.py            searxng client + sanitizer (G7)
       ban.py               permanent hard ban validator (G12). The RiskTier
                            enum was deleted 2026-08-29: never referenced — the
                            three tiers lived in the confirm logic, and since
                            ADR-123 they live in `capabilities.Risk`.
                            Since ADR-119 (F5) a WRAPPER at argv[0] means every
                            remaining token is checked, `--opt=value` split on the
                            first `=`. `WRAPPER_BINARIES` covers `env`, `flatpak`,
                            `distrobox-enter`, `timeout`, `systemd-run`, `unshare`
                            and the terminal emulators (`-e` is the same escape;
                            15 of the live app ids are `foot -e <something>`)
       typer.py             Wayland typer using ydotool or wtype fail-soft (G12)
       status.py            system status reader: battery, disk, ram, network, window, media (ADR-129)
       windows.py           Hyprland window list & focus dispatch by application key (ADR-129)

     audio/
       capture.py           sounddevice input, 15 s ring, gate, ensure_open (G6/G9)
       state.py             the FSM (diagram 01) + mic_open gate
       stt.py               faster-whisper backend + FR-12/13 policy
       ptt.py               unix-socket PTT server + client (FR-3)
       tts.py               kokoro-onnx wrapper (ONNX/CPU, fp32, 8t, far-end reference tap)
                            + `_Supertonic`, an OPTIONAL engine-level fallback
                            (ADR-085). It duck-types the one method `say()` uses
                            -- `create(text, voice=, speed=, lang=) ->
                            (samples, sr)` -- so barge-in, `stop()` and the AEC
                            reference path are untouched. Reached only when
                            Kokoro cannot speak AT ALL; a missing voice vector
                            still goes to `af_heart` first.
       say.py               `just say` / audition CLI (G5)
       aec.py               WebRTC APM EchoCanceller adapter (G10)
       vad.py               Silero / WebRTC VAD & SpeechGate debounce state machine (G10, ADR-087)
       wake.py              openWakeWord hey_jarvis detector, FarEndRef, WakeListener (G10)
       dictation.py         DictationManager & spoken punctuation formatter (G12)
       speaker.py           SpeakerVerifier using sherpa-onnx 3D-Speaker CAM++ (G13)
       guard.py             CallbackGuard: nothing escapes a PortAudio callback,
                            consecutive failures degrade loudly (M-A1, 2026-08-29)

     store/
       __init__.py          `prompt_digests` — the habits + session digests both
                            UIs hand to a worker thread (H6)
       db.py                connection, WAL, single-writer (FR-50..53);
                            0600 on the DB AND its -wal/-shm sidecars;
                            migrations are transactional + idempotent
       migrations/          001_init.sql, 002_reminders.sql, 003_notes.sql,
                            004_approvals.sql (forward only; schema v4)
       prefs.py             slug+alias keys, CRUD, inert digest rendering
       audit.py             redacted dispatch records + retention sweep
                            (audit, summaries, TERMINAL reminders; never notes,
                            preferences, or active reminders — ADR-068b)
       habits.py            deterministic habit pattern mining (ADR-049)
       summarizer.py        session dialogue distillation into summary (ADR-050)
       reminders.py         SQLite reminder & timer store (G11)
       notes.py             SQLite quick notes store (G12)
       approvals.py         the FIRST_USE allowlist (criterion 3.9, design §3.3).
                            A grant is written ONLY by a completed confirm
                            handshake -- no planner output reaches this table --
                            and the subject is a closed-enum id, never free text.
                            Keyed to `argv_sha256`, NOT to the id alone:
                            `desktop.app_key` resolves a collision with
                            `setdefault`, first wins, so an uninstall-then-install
                            can hand a stored approval to a DIFFERENT binary. An
                            approval whose fingerprint no longer matches does not
                            apply and Friday asks again. NEVER swept by retention
                            (user intent, like a preference). With no store the
                            tier degrades to asking EVERY time, which is the safe
                            direction: a grant that cannot be recorded must not
                            be assumed. Revocation is keyboard-only and the CLI
                            is not built yet (`just approvals`, Phase 7,
                            FR-122/ADR-103); `forget`/`reset` exist on the store

     ui/
       tui.py               textual app, mode indicator, confirm prompt
                            (delegates resolution to turn.resolve_pending;
                            `_turn_body` is the turn itself, extracted from the
                            `_do_turn` worker so a re-routed non-answer can
                            reuse it without a worker cancelling its caller)
       templates.py         outcome -> speech strings

   deploy/
     searxng/
       friday-searxng.service   SearXNG loopback container service
       settings.yml             SearXNG loopback configuration
     systemd/
       friday-llm.service       llama-server systemd user unit
       friday.service           orchestrator daemon systemd user unit (Type=notify, WatchdogSec=10s)

   scripts/
     bootstrap.py           deterministic bootstrap & verification harness (§10, F24, ADR-109)
     wake_bench.py          live wake-word, AEC, and VAD benchmark harness
     stt_accel_bench.py     STT across CPU / OpenVINO(CPU,NPU,iGPU) / CUDA, and
                            moonshine, on the 20 real DMIC clips (ADR-086/088)
     accel_stage_bench.py   TTS / speaker / wake on CPU, NPU, iGPU, GPU.1;
                            prints `npu_busy_time_us` so "it ran on the NPU"
                            is a claim that can fail (ADR-088)
     vad_bench.py           webrtcvad 0-3 vs three Silero generations, driven
                            through the REAL `SpeechGate` (OQ-39/OQ-51)
     aec_bench.py           WebRTC APM vs DTLN-aec over one live capture;
                            `--talk` is the preservation test, `--sweep` the
                            reference-alignment sweep (OQ-32/OQ-52)
     tts_bench.py           Kokoro vs Supertonic; `--voices`, `--tune` (ADR-085)
     moonshine_tune.py      the ADR-042-equivalent tuning rounds (ADR-086)

   tests/
     fixtures/
       eval.jsonl           60 fixtures (ADR-030, ADR-089)
       adversarial.jsonl    AS-1..12 (+ youtube AS-13..16 in test_youtube)
       injection.jsonl      20 hostile search results (FR-63)
     test_*.py              81 files + conftest.py; 608 collected tests.
                            Counts move every session -- read the summary
                            line from `pytest -q`, never this number.
                            Counts move -- read them with
                            `.venv/bin/python -m pytest -q`, never from prose

   diagrams/                ASCII, authoritative, updated with code
```

---

## 3. Key interfaces

### 3.1 Turn

```python
@dataclass(frozen=True)
class Turn:
    request_id: str          # uuid4, threaded through logs + audit.
                             # TRUE EVERYWHERE ONLY SINCE 2026-08-30: the voice
                             # daemon generated `v{n}` per process until then,
                             # and `INSERT OR REPLACE` made every restart eat
                             # the previous run's rows (D2, ADR-076). The 71
                             # pre-fix `v{n}` rows in the live DB predate this.
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
    timeout_s: float                          # COMMANDS only (ADR-073)
    detach: bool                              # True = GUI launch, not waited on
    param_schema: dict                        # typed, closed
```

`build_argv` is a function in code. The model's params are inputs to it,
never members of the returned list verbatim unless they came from a
closed enum. This is the whole of ADR-007 in one type.

### 3.3 Executor contract

```python
async def execute(spec: ToolSpec, params: dict, request_id: str) -> ToolResult
```

Guarantees (as actually implemented 2026-08-26; see ADR-067d):

- `shell=False`, argv list, explicit minimal env
- a tool is a LAUNCH or a COMMAND, and they are bounded differently
  (`ToolSpec.detach`, ADR-073, landed 2026-08-29):
  - **command** — awaited under `spec.timeout_s`; on expiry its whole process
    **group** is SIGKILLed (`start_new_session=True` makes the child a group
    leader, so a forking tool cannot orphan a grandchild) and the outcome is
    `TIMEOUT`. A non-zero exit is `ERROR`: for a command the exit code IS the
    verdict
  - **launch** — `_LAUNCH_GRACE_S = 0.4`, then the await is abandoned and
    nothing is killed; the exit code is ignored, because a single-instance
    handoff exits non-zero ON SUCCESS (ADR-043). What the launch cannot know —
    whether a window appeared — the template no longer claims: it speaks
    "Launching X.", not "Opened X."
  `spec.timeout_s` was dead config until this landed
- never retried for `reversible` or `irreversible` risk classes
- returns a typed `Outcome`, never raises to the caller
- audit rows are written by the CALLERS (`turn.py`'s dispatch tail, the
  handlers in `handlers.py`, and `gate.resolve_pending`), not by the executor
  itself. Since criterion 3.5 the DISABLED row is written in ONE place --
  `gate._panic_blocked` -- for every capability, rather than in eight
  hand-written blocks. Until the hardening
  phase (ADR-067b, landed 2026-08-29) the confirm paths and web_search wrote
  none; `tests/test_audit_contract.py` now walks the schema and asserts
  exactly one row per executed dispatch. **`chat` joined them 2026-09-04
  (D37/FR-150)** and is the only row that is deliberately EMPTY -- it records
  that a chat turn happened and how long it took, never a word of it. Four
  capabilities still write nothing (`none`, `read_notes`, `list_reminders`,
  `resume_dnd`): **OQ-70**, recorded rather than defaulted

---

## 4. Prompt assembly

Built fresh per turn from typed regions. There is no long-lived prompt
string being appended to.

```
   +--------------------------------------------------+
   | SYSTEM POLICY            static, 1401 tok         |
   |   identity, action contract, refusal rules        |
   |   DERIVED: the action block is one `summary` per  |
   |   capability, assembled byte-identical and pinned |
   |   against tests/fixtures/system_policy.txt        |
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

**The `<=600 tok` figure in that box was wrong for months and is now
measured.** `SYSTEM_POLICY` is **1401 tokens** (llama-server's `/tokenize`,
2026-09-04). It was re-baselined from 1298 in ADR-123 because ADR-118's
`open_app` paragraph — the D31 fix — grew it the day before Phase 3 opened, and
"meet the number" would have meant compressing the exact text that fixed a live
defect. Compressing it is deliberately a **separate, measurable commit**
(ADR-125): inside a behaviour-freeze refactor, a regression and an intended
change are indistinguishable.

---

## 4a. Adding a capability

Phase 3 exists so that this list is short and so that forgetting a piece fails
the suite rather than shipping. All of it (ADR-123, ADR-124, ADR-125):

```
   1.  friday/capabilities.py   one Capability(...) in _ALL.
                                id, params, risk, summary, persona are
                                REQUIRED -- no defaults, it will not construct.
                                ask/describe only if the tier confirms;
                                subject only for FIRST_USE; hotwords if there
                                is a word the user must SAY to reach it.
   2.  friday/handlers.py       one HANDLERS row -- unless it is a plain
                                subprocess, in which case a tools/registry.py
                                spec instead, and the turn's shared body runs
                                it. Never both.
   3.  tests/fixtures/eval.jsonl   >=2 fixtures, then `just eval` and
                                `just eval-baseline`. A NEW fixture that fails
                                is never a regression (F23), so read the rate
                                and the `unbaselined failures` line, not the
                                exit code.
   4.  just grammar             regenerate. The .gbnf diff is the review:
                                nothing else should have moved.
```

Four tests fail if a piece is missing: `test_capabilities.py` (the required
fields), `test_handler_table.py` (reachable exactly one way),
`test_fixture_obligation.py` (>=2 examples, each an actual fixture) and
`test_prompt.py` (the assembled prompt matches the record).

**What you do NOT touch:** `PARAM_SCHEMA`, either `.gbnf`, `SYSTEM_POLICY`'s
action block, `CHAT_SYSTEM`'s toolset sentence, the confirm branches, the panic
gate, or `STT_HOTWORDS`. All seven are derived. If you find yourself editing one
by hand, the capability record is missing a field.

**Two things are still hand-written on purpose** (ADR-125):
`habits.describe_action`'s phrasing chain — the obligation to have phrasing is
derived, the tuned prose is not — and `summary`'s length.

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

CPU-bound and otherwise blocking work runs in a thread pool via
`asyncio.to_thread`: `whisper`, `kokoro`, speaker-verification ONNX inference,
`generate_signoff_summary`'s LLM round-trip, `store.prompt_digests`' SQLite
reads, and `notify-send`. The last four were inline on the loop until
2026-08-29 (audit H6) — while the loop is blocked nothing is read from the PTT
socket, no timer fires and no wake callback drains, so Friday is simply deaf
for the duration. `tests/test_event_loop_blocking.py` asserts each runs on a
thread other than the loop's, which is the only observable that separates
`await to_thread(f)` from `f()`.

The audio callback allocates nothing and never touches the database. It also
does not mutate capture state: since ADR-071 it scores, it may fire `on_wake`,
and arming VAD end-of-speech is the loop's job, after the FSM has accepted.

It also cannot die quietly (M-A1, 2026-08-29). Both callbacks run through one
`CallbackGuard` (`friday/audio/guard.py`), because sounddevice answers an
escaping exception by printing it and **never calling back again** — leaving an
open stream, a passing `audio_devices` self-test, and a deaf assistant. The
guard swallows, counts *consecutive* failures, and past the limit logs
`E_AUDIO_DEAD` once at ERROR: the wake detector is then disabled outright
(nothing pretends to listen for the wake word), while the capture callback,
which only gate-checks and copies, keeps running degraded.

Backpressure:

```
   audio ring buffer     fixed 15 s, preallocated, overwrites oldest
   turn queue            depth 0.  a second request is REJECTED, not queued
   db write queue        depth 1000, then drop-oldest for audit rows,
                         block for preference writes (they are user intent)
   tool concurrency      1
```

### 5.1 Teardown — who owns the audio devices

`Daemon.close()` owns the audio lifecycle: it stops the wake listener and closes
the recorder **first**, before the session distillation (which calls the LLM and
can take seconds). `run()`'s `finally` calls `close()` and does **not** close the
recorder separately any more.

This was split across two functions until 2026-09-02, and the split was the bug:
`run()`'s `finally` closed the recorder on the line after `await self.close()`,
so **every caller of `close()` that was not `run()` leaked a live PortAudio
stream.** A unit test that built a real `Recorder` did exactly that, and the
stream then outlived the interpreter — PortAudio's thread invoked a CFFI
callback after Python state was torn down, and `pytest` died at session finish
with SIGSEGV/SIGILL and no summary line (D28, **ADR-111**, FR-132).

Both calls are idempotent. **A future teardown step for a new device belongs in
`close()`, not in `run()`.**

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
| User walks away mid-confirm | 30 s timeout | drop the pending; the FSM is NOT touched, so a capture already in flight finishes and is read as a fresh command (ADR-069) |
| Confirm question never reaches the speaker (TTS raises, or barge-in) | `_speak` returns not-delivered | no pending is armed and no window opens — an undelivered question is not a question (ADR-069) |
| Crash mid-migration | version and schema move in one transaction | next start re-applies idempotently; no `Restart=always` crash loop (FR-53) |
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

Per-stage timings are kept in-process. TTFA (end-of-speech → first audio
sample) is logged as `[debug] vN TTFA … ms` when `FRIDAY_DEBUG` is set
(`daemon._ttfa_logger`); wake/VAD latency has its own harness, `just
wake-bench`. No metrics server, no Prometheus. One user, one machine.

Health: `friday --selftest` runs **10 checks** — llama-server reachability,
SearXNG reachability, GPU arch, that the LLM is actually resident on the GPU,
DB schema version and permissions (incl. the `-wal`/`-shm` sidecars, read
BEFORE the DB is opened), audio devices, the panic file, the loopback bind
audit, the power profile, and **that the unit systemd is running matches the
one committed** (`check_unit_deployed`, ADR-117 — asked of `systemctl show`,
since the installed unit is a symlink to the repo file and the file test can
never disagree with itself). Exit 0 all PASS / 1 any FAIL / 2 any WARN, printed
as `[DEGRADED]` (ADR-108). Run it at every gate.

Every check must be able to FAIL — `tests/test_selftest_fail_paths.py` drives
one FAIL path per check, 19 test functions / 22 collected. `gpu_arch` once
PASSed through an entire GPU outage; that file exists because of it.

---

## 8. Deployment

`systemd --user` units, not a login shell script.

```
   ~/.config/systemd/user/friday-llm.service
     ExecStart=/opt/llama.cpp/build/bin/llama-server \
       --model  %h/.local/share/friday/models/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf \
       --host   127.0.0.1 --port 8080 \
       --ctx-size 8192 --n-gpu-layers 99 \
       --cache-type-k q8_0 --cache-type-v q8_0 -fa on \
       --reasoning off --no-webui
     Restart=always
     RestartSec=3s

   ~/.config/systemd/user/friday.service
     After=friday-llm.service
     Requires=friday-llm.service
     Type=notify
     WatchdogSec=10s
     ExecStart=%h/Projects/Personal/Intern/friday/.venv/bin/python -m friday.voice_main
     Restart=always
     RestartSec=3s
```

Hardening on the orchestrator unit: `NoNewPrivileges=yes`,
`ProtectSystem=strict`,
`ReadWritePaths=%h/.local/state/friday %t/friday %h/.local/share/friday /tmp`,
and `KillMode=process` (ADR-114). **`PrivateTmp` is deliberately NOT set**
(ADR-115): a GUI app's session IPC lives in `/tmp` — Chromium keeps its
singleton socket there and only a symlink to it under `$HOME` — so a private
`/tmp` made every browser launch exit 0 in ~50 ms with no window, and hid
`/tmp/.X11-unix` besides. **`/tmp` is in `ReadWritePaths` for the same reason
and the two are one fix:** `ProtectSystem=strict` mounts everything else
read-only, connecting to a unix socket needs write access to it, and a
read-only `/tmp` also sends `tempfile.gettempdir()` down to the
`WorkingDirectory` (two stray `tmp*/libespeak-ng.so` dirs in the repo per
daemon start). `tests/test_service_unit.py` fails if either directive is
changed back — and since ADR-117, `selftest`'s `check_unit_deployed` fails if
the unit systemd is *running* drifts from the file, which the file test cannot
see (the installed unit is a symlink to it).
Note that `open_app` must still reach the Hyprland socket — verify the
sandbox does not break `hyprctl` before enabling `ProtectSystem`.

Startup ordering matters: the orchestrator must tolerate `llama-server`
not being ready yet (retry the health ping, do not crash-loop).

**Editing a unit file is not deploying it.** The installed units are symlinks
into `deploy/systemd/`, so `diff` reports IDENTICAL while systemd continues to
run the configuration it loaded at boot. `Type=notify` + `WatchdogSec=10s` sat
committed and documented for a whole session while `systemctl show` reported
`Type=simple`, `WatchdogUSec=0`, `NeedDaemonReload=yes` — the watchdog had never
once fired. After ANY change under `deploy/systemd/`:

```bash
systemctl --user daemon-reload && systemctl --user restart friday
systemctl --user show friday -p Type -p WatchdogUSec -p NRestarts   # must not be 0/simple
```

`notify_ready()` is sent at the end of `Daemon.run()`, after the model loads and
the startup briefing — measured at ~5 s against a 90 s `TimeoutStartSec`. The
heartbeat is an asyncio task, so a wedged event loop stops it and systemd
restarts the service; `NRestarts=0` over many watchdog periods is what proves it
is actually beating.

---

## 9. What is deliberately absent

```
   no vector database         50 preferences fit in a prompt
   no TEXT embedding model    nothing to embed at this scale.  (G13 DOES run a
                              512-dim VOICE embedding for speaker verification,
                              ADR-059 — what is absent is semantic text
                              retrieval, not embeddings as such)
   no ORM                     six tables, parameterized SQL is clearer
   no message queue           one user, one turn at a time
   no ORM migration tool      forward-only numbered SQL, applied in ONE
                              transaction (M-T3): a half-applied migration
                              crash-looped the daemon
   no docker for the app      systemd user units are the native answer
   no web UI                  textual TUI, per the mandate
   no plugin system           every capability is a reviewed code change
   no retry middleware        retries on side effects are a bug, not a feature
   no LangChain / agent fwk   the whole control flow is ~200 lines of FSM
```

Each line is a decision, not an omission. Adding any of them requires an
ADR that names the problem it solves.
