# Friday v1 reopened: Friday 2's features ported in — design

**Date:** 2026-10-07 · **Status:** written, owner review pending · **Base:** v1 at `48514b1`
**Source of the ports:** `~/Projects/Personal/friday2`, branch `claude/phase2` at `9721355`
(copy, never import; v2 is frozen once this spec is approved).

## 0. Why

Friday 2 (started 2026-09-22) was an always-listening assistant built around Laya, a calibrated
classifier, with no daytime LLM. On 2026-10-07 the owner recorded, in v2's own log (D108):
*"I haven't found anything impressive. It's just so-so"*, and asked to move back to Gemma like
Friday 1. The LoRA retrain meant to rescue Laya was refused by its own gate the same day (C171).

The owner then asked for this: **v1 is the base, v2 is the updates.** Take everything from v2
that makes v1 better, and bring v1 to a more mature level.

What v1 keeps, unchanged: Gemma 4 12B QAT on `llama-server` as the planner, the grammar lock,
application-side validation, the capability record, the eval gate, and the ten hard invariants
(two amended below, in writing, by ADR).

## 1. Success criteria

1. Everything v2 does that the owner chose (§2) works in v1, behind v1's gates: each new
   capability is one `Capability(...)`, one handler row and ≥2 eval fixtures.
2. After the wake word, Friday keeps listening for 90 s, and only the owner's voice can act.
3. `pytest` green, `just eval` with **0 regressions** on the 91 existing fixtures, and every new
   fixture passing, at the end of every phase.
4. Planner latency is measured after each phase, not assumed (§6).
5. A new session can start from a CLAUDE.md of ~250 lines instead of 1,532.

## 2. Owner decisions, 2026-10-07

Each is written into `adr.md` in Phase A (ADR numbers planned below), into `progress.md`'s decision
log, and into `spec.md` where a requirement changes.

| # | Decision | Planned ADR |
|---|---|---|
| 1 | v1 is the base; v2's features are ported in; v2's Laya, nightly training, Qwen3-ASR and LFM2.5 stay behind (§3) | ADR-131 |
| 2 | Wake word stays (`hey_jarvis` + PTT). **After it, Friday keeps listening for 90 s**, restarting after every command, so "oh, and also…" needs no wake word | ADR-132 |
| 3 | Inside the window: commands act; **chat and questions always get a reply** (owner chose this over "only if named") | ADR-132 |
| 4 | **Speaker check always on**: ERes2Net-en (v2 D68) replaces CAM++, the owner's existing v2 voiceprint, threshold **0.35** (v2 D104) | ADR-133 |
| 5 | **7-day heard log** (v2 D65): what Friday heard from the owner's voice and what it did. Amends invariant #7 | ADR-134 |
| 6 | **Results by notification, speech for chat and answers.** Confirms are spoken and also carry Confirm/Cancel buttons | ADR-135 |
| 7 | Capability groups: **work tools, clipboard & screen, personal data, routines & memory** — all four | one per phase (B–E) |
| 8 | Upgrades: **speak per sentence, Smart Turn, status pill + buttons, local web app** — all four | with Phase B (the web app with E) |
| 9 | **Carry over v2's answered choices unchanged** (§2.1) | per capability ADR |
| 10 | **Slim the docs** | ADR-141 |

### 2.1 Carried over from v2 unchanged (decision 9)

- Notes in **Anytype** (v2 D12, pairing C142: `/v2` routes, space-scoped key). v1's 2 SQLite notes
  are copied in once.
- Default editor **VS Code** (`code`), `nvim` when named (D26); default terminal **kitty**, `foot`
  when named (D27).
- Bookmarks are a config file of named links (D29), with a browser per bookmark (D41) and a Google
  account per bookmark through `authuser=` (D42).
- Contacts from Thunderbird's address book plus memory (D30); **Friday never presses Send**
  (C17, D28): Thunderbird's Send button is the confirmation.
- News: approved RSS/Atom feeds fetched at **06:00 and 19:00** (D55); the schedule counts as asking
  (D57); the egress test allows exactly the feed hosts and fails on any other; feed text is
  untrusted and only ever displayed, escaped.
- Routines are **suggested** from 7 days of app / project / media habits (D87), **never window
  titles or content**, and run only after the owner approves each one.
- Always confirm: starting a job, adding a calendar event, Bluetooth connect (v2's R2 tier; v1's
  `Risk.ALWAYS`).
- While the laptop's own speakers play sound, bare speech needs the wake word (v2 D49/C39: the
  speaker check cannot tell a podcast from the owner). Headphones and HDMI don't count.
- During a call (another program holds a real microphone, v2 C23), nothing is spoken and the
  window closes.
- "What did I ask about X" searches the heard log (7 days) **and the text of commands Friday acted
  on, kept 90 days** (v2 D15/D89). **This second store also amends invariant #7** — called out
  here so the owner sees it in review rather than inheriting it silently.

## 3. The re-check: every v2 piece, and where it goes

Read module by module on 2026-10-07 (`friday2/*.py` docstrings, spec §6, held-out data,
decisions D1–D108). "Phase" is §5's.

### 3.1 Brought over

| v2 piece | What v1 gains | Phase |
|---|---|---|
| `speaker.py` (ERes2Net-en, D68/D104) | speaker check that rejects podcasts (0/13 vs CAM++'s 12/13) | B |
| voiceprint `voiceprint-eres2net.npy` | no re-enrolment; copied and SHA-pinned | B |
| `turn.py` (Smart Turn v3.2, D99) | a turn ends ~0.58 s sooner; "hey jarvis," alone still waits | B |
| `talk.py` (sentence by sentence, C156) | first sound 4.43 s → 1.08 s on long answers (v2 measurement) | B |
| `heard.py` + `friday2 heard` (D65) | 7-day heard log, `just heard` to watch it live | B |
| `calls.py` (C23) | window closes in a call; Friday stays silent in a call | B |
| `playback.py` (D49) | bare speech in the window ignored while the speakers play | B |
| `phrases.py` C0 exact phrases | "pause", "next", "stop talking", "speak to me", "that's all", "undo", yes/no skip the planner (~700 ms saved) | B |
| `config.py` `[aliases]` (D70) | the owner's word list: post-STT fixes for words Whisper keeps mishearing | B |
| `notify.ask` + caelestia "Open expanded" (D96) | Confirm/Cancel buttons on confirm notifications | B |
| `ui/pill/shell.qml` + `state.json` (D37, C163) | status pill: off / idle / window open / thinking / speaking | B |
| speak mode (§5.4) | "speak to me" / "stop talking" toggles spoken results | B |
| `data/heldout/heldout.jsonl` (348 labelled phrasings, 61 not addressed) | eval fixtures for every new capability, and `none` fixtures for window ambient speech | B–E |
| `caps.py` open project (zoxide) / open URL / bookmarks | `open_project`, `open_bookmark`, `open_copied_link` | C |
| `findcaps.py` (fd, rg, recent files) | `find_file`, `find_code`, `find_recent`; results shown, a file opens only on click | C |
| `jobs.py` (`[[run.job]]` allowlist) | `run_job` (always confirms), `list_jobs`, `stop_job` | C |
| `askcap.py` (explain / summarise / translate / transform) | "explain this": the clipboard as untrusted content, answered by Gemma on the grounded path | C |
| `caps.py` clipboard history, OCR region, colour pick | `clipboard_history`, `ocr_region`, `color_pick` | C |
| `syscaps.py` lock, Bluetooth, system info extras | `lock_screen`, `bluetooth_connect` (always confirms); battery / temperature / CPU / GPU / network merged into `system_status` | C |
| `captypes.Outcome.undo` (C113) | "undo" for volume, brightness, window move, workspace, DND, calendar add | C |
| `slots.py` time rules (dateparser) | **fixes v1's open D5** (garbled durations): the model passes the time phrase, code parses it | C |
| `anytype.py` | notes in Anytype | D |
| `calcaps.py` + `eds_helper.py` | `calendar_agenda`, `calendar_add` (always confirms), undo of an add | D |
| capability 17 (Thunderbird compose) | `email_compose`, never sends | D |
| `news.py` | news digest, "what's the news" | D |
| `briefing.py` | one morning notification: reminders, agenda, news, waiting suggestions | D |
| `habits.py` + `routines.py` | habit capture, suggested routines, `run_routine` | E |
| `search.py` (FTS5 in memory) | "what did I ask about X" | E |
| `memory.py` "what do you remember about X" | `recall_memory` over preferences and session summaries | E |
| `web.py` | local web page on 127.0.0.1: heard log, news, search, stats | E |
| `llm.py` random API key (C150) | **security fix**: v1's `llama-server` on :8080 has no key, so any web page in the owner's browser can call it | A |
| `models.py` pins verified at every start | v1 checks pins in `bootstrap --check` only; the daemon will refuse a mismatched model at start | A |

### 3.2 Already in v1 (nothing to port)

Open app from `.desktop` (v1's is the more hardened copy, ADR-097/119/121/122), reminders and
timers, media, volume and brightness, window move to workspace, DND, system info basics, the audio
callback guard, systemd hardening, Silero VAD, Kokoro `af_bella`, the follow-up for "yes"/"no"
confirms, process-group kills, the panic switch, `just stats`.

### 3.3 Not brought over, and why

| v2 piece | Why not |
|---|---|
| Laya (`decide.py`, `train.py`, `calibration.py`, `tlog.py`, `nightly.py`, `stats.py`, seed data) | Gemma decides again (decision 1). The thing the owner found "so-so" |
| Qwen3-ASR-1.7B (`stt.py`) | 3.9 GB of VRAM; Gemma holds ~7 GB of 8,151 MiB. Invariant #6 keeps STT on the CPU |
| LFM2.5-2.6B and Gemma 4 E4B for "ask" (`llm.py` server) | Gemma 12B is already resident and answers better; a second server would not fit |
| Always listening with no wake word, the Laya addressee gate (`gate.py`) | owner chose the wake word plus a window (decision 2) |
| Quick questions (`ask.py`) | they exist to resolve Laya's conformal sets; the planner returns one action |
| Context digest (`context.py`) | packs signals into Laya's token budget; v1 resolves "this" in code (focused window) |
| Corrections as gold labels, the nightly teacher, suggested facts | training data for Laya. Revisit only if a learner returns |
| The keyword spotter (`models/kws`) | v2 dropped it itself: 9/36 of the owner's bare words (D71) |
| Golden *command* recordings | never recorded (v2's 1e was left to the owner). The **speaker** golden set exists and is used in Phase B |

## 4. Design

### 4.1 The listening window (decisions 2, 3)

A new state in `audio/state.py`: **`LISTENING`**, entered where today's FSM returns to `IDLE` after
a turn that began with the wake word or PTT, and after every turn inside the window.

```
IDLE --wake/PTT--> CAPTURING -> TRANSCRIBING -> PLANNING -> SPEAKING/notify
                                                                  |
          +-------------------------------------------------------+
          v
      LISTENING (90 s, restarts after each turn)
          | Silero onset (with pre-roll) --> CAPTURING   (no wake word)
          | wake word / PTT ---------------> CAPTURING   (as today)
          | 90 s / "that's all" / "thanks Friday" / call starts / panic --> IDLE
```

- **One turn in flight** (invariant #9) still holds: `LISTENING` is between turns, never during one.
- **Who:** every utterance passes the speaker check before STT (§4.2); a non-owner utterance is
  dropped untranscribed and the window keeps its timer.
- **What:** an utterance in the window goes through the same turn as a woken one. The difference:
  planner `none` is **silent** (no "didn't catch that"), because most speech in the window isn't
  for Friday. Outside the window, v1's behaviour is unchanged.
- **Chat in the window always replies** (decision 3). Known cost: Friday may answer a question
  said to someone else; the owner chose that knowingly.
- **ADR-065 holds:** an action that appears only with history is confirmed, not dispatched.
- **Speakers playing (D49):** while the laptop speakers play non-Friday audio, the window ignores
  bare speech; the wake word still works.
- **Call (C23):** another program opening a real microphone closes the window, and nothing is
  spoken until the call ends.
- **Half duplex stays:** the mic is muted while Friday speaks (FR-6), and the speaker check
  rejects Friday's own voice besides.

### 4.2 Hearing path

```
mic -> Silero VAD -> [Smart Turn after 0.2 s of silence, else the 0.8 s rule]
    -> speaker check (ERes2Net-en, 0.35) -> faster-whisper (CPU, as today)
    -> owner's word list -> exact phrases (C0) -> planner
```

- **Smart Turn** needs Whisper log-mel features. v2 imported `transformers` for them (~1 GB).
  v1 uses `faster_whisper.feature_extractor.FeatureExtractor` (numpy, already installed) instead:
  **no new dependency**. Phase B proves the two give the same features on the owner's clips.
- **Speaker check always on** (decision 4): ERes2Net-en model and voiceprint copied into
  `~/.local/share/friday/models/speaker/`, SHA-pinned. CAM++ code and pins are removed.
- **Exact phrases** skip the planner: "pause", "play", "next", "previous", "stop", "stop talking",
  "speak to me", "that's all", "thanks Friday", "undo", "yes", "no", "cancel". Matched after
  normalisation, never by substring (v2 C145: the STT prompt echoed back as "pause" five times).

### 4.3 Output (decision 6)

- **Action results** go out as a notification, from the same outcome template that is spoken today
  (invariant #4: execute first, then report; the text never comes from the LLM).
- **Chat and answers are spoken**, sentence by sentence: synthesis of sentence n+1 overlaps
  playback of sentence n.
- **Confirms are spoken** and the notification carries Confirm/Cancel buttons; the click and a
  spoken "yes" end in the same `gate.resolve_pending` (v1's lesson: one protocol, one
  implementation).
- **Speak mode:** "speak to me" also speaks action results; "stop talking" returns to quiet.
- **Errors** of an action: a critical notification.
- **In a call:** notifications only.

### 4.4 New capabilities

Each is one `Capability(...)` in `friday/capabilities.py`, one row in `friday/handlers.py`, and ≥2
fixtures in `tests/fixtures/eval.jsonl`, seeded from v2's held-out phrasings. Risk uses v1's tiers.

| Capability | Params | Risk | Note |
|---|---|---|---|
| `open_project` | `project`: generated enum (zoxide + known projects) | LOW | free in the grammar like `open_app`, validated against the generated set (ADR-128's reason) |
| `open_bookmark` | `name`: enum from config | LOW | browser and `authuser` per bookmark |
| `open_copied_link` | — | LOW | code reads the clipboard, accepts only `http(s)://`; the model never supplies a URL |
| `find_file` / `find_code` / `find_recent` | `query`: text | NONE | **invariant #2 exception, own ADR** (like ADR-027): charset- and length-capped, one argv element after `--` |
| `run_job` / `list_jobs` / `stop_job` | `job`: enum from config | ALWAYS / NONE / LOW | argv exactly the config's; jobs run in the background, turns stay one at a time |
| `ask_about_clipboard` | `op`: explain / summarise / translate / transform | NONE | clipboard is untrusted: runs on the grounded path (`final.gbnf`), text only (invariant #1) |
| `clipboard_history` / `ocr_region` / `color_pick` | — | LOW | cliphist; grim + slurp + tesseract `eng+nep`; hyprpicker |
| `lock_screen` | — | LOW | no undo, ever |
| `bluetooth_connect` | `device`: enum of paired devices | ALWAYS | |
| `undo` | — | LOW | reverses the last reversible outcome, if it is under 90 s old |
| `create_note` / `read_notes` | as today | as today | backend moves to Anytype |
| `calendar_agenda` / `calendar_add` | `when`: time phrase, `title`: text | NONE / ALWAYS | EDS through the system Python helper |
| `email_compose` | `to`: contact enum, `subject`, `body` | LOW | Thunderbird `-compose`; quoting is built by code and covered by an adversarial test; never sends |
| `news` | `topic`: enum from config | NONE | display only |
| `run_routine` / `list_routines` | `name`: enum of approved routines | LOW | steps are only app / project / media |
| `search_log` | `query`: text | NONE | FTS5 in memory, nothing indexed on disk |
| `recall_memory` | `topic`: text | NONE | preferences and summaries |

`set_reminder` changes: `seconds` becomes `when` (the spoken time phrase), parsed by code with
`dateparser` (fixes D5). `dateparser` is the only new runtime dependency and gets the rule-7 drill
before it is added.

### 4.5 Invariant amendments (each its own ADR, each with a mutation shown RED)

- **#2:** one more audited free-text argv element: the find query (an exception like ADR-027).
- **#7:** the 7-day heard log and the 90-day acted-command text (§2.1). `thought`, raw model
  output, raw search payloads, key events and **audio** stay never-on-disk. The daemon log and
  journald stay text-free.
- **Egress:** news feed hosts at the scheduled times; the egress test allows exactly those hosts.
- **Unchanged:** #1, #3, #4, #5, #6, #8, #9, #10.

### 4.6 Owner config

`~/.config/friday/config.toml`, 0600: `[bookmarks]`, `[aliases]`, `[[run.job]]`, `[notes]`,
`[news]`, copied from v2's file. It holds the owner's email addresses: never committed, never
quoted in a tracked file. A `docs/config.example.toml` with fake values is committed.

## 5. Phases

Every phase ends with: `pytest` green, `just eval` 0 regressions (new fixtures re-baselined),
`just grammar` regenerated and committed in the same commit as the capability that changed it,
`just test-egress` passing, evidence pasted into `progress.md`, ADRs written, a mutation shown RED
for any invariant-touching line, and the diagrams it contradicts fixed in the same commit.

**A — Ground and docs**
1. Re-verify v1's gates on today's tree. This needs `friday-llm` running, so the v2 daemon and
   pill are stopped first, **with the owner's OK at that moment**.
2. ADR-131..141 and the decision log (§2).
3. `llama-server` gets a random API key per start, read by the client from a 0600 file (C150).
4. Model pins verified at daemon start.
5. Slim the docs. CLAUDE.md goes to ~250 lines: what Friday is, the invariants, the working
   agreement, the doc map, the commands, and the current state. The full temptation table moves to
   `docs/lessons.md`, still linked. `progress.md` gets a short current-state top, and sessions
   before 2026-10-07 move to `docs/archive/progress-2026-08-22..2026-09-08.md`. `adr.md` is not
   auto-loaded and stays whole.
6. Add a "frozen" note to v2's CLAUDE.md, only with the owner's OK.

**B — Hearing and the window**
1. ERes2Net speaker check, always on. Acceptance: on v2's speaker golden set (93 clips), v1's code
   path reproduces v2's scores to 3 decimals.
2. Smart Turn on numpy features. Acceptance: features match `transformers`' within tolerance on
   the golden clips (measured in a scratch venv, rule 7), and model probabilities agree.
3. The `LISTENING` state and window rules (§4.1), with FAIL-path tests for each closing condition.
4. Exact phrases, word list, speak per sentence, speak mode, notification output, Confirm/Cancel
   buttons, pill, heard log + `just heard`.
5. Eval: window `none` fixtures from v2's 61 not-addressed rows.
6. Live at the microphone: wake → command → bare follow-up within 90 s acts → another voice is
   dropped → music playing → bare speech ignored → "that's all" closes. Read back from the system
   (`action_audit`, the heard log, `wpctl`, `hyprctl`), never from what Friday says.

**C — Work tools, clipboard and screen.** The capabilities of §4.4 marked C in §3.1, `undo`, and the
reminder time-phrase change (D5). Live check per capability.

**D — Personal data.** Anytype (pair, copy the 2 notes), calendar, email compose, news + egress
allow-list, morning briefing.

**E — Routines, memory, web app.** Habit capture, routine suggestions and approval, `run_routine`,
`search_log`, `recall_memory`, the 127.0.0.1 page.

Each phase gets its own implementation plan (`docs/superpowers/plans/`), written when the phase
before it closes, so a plan never describes code that has since moved.

## 6. Risks and measurements

- **Planner size.** 30 actions become about 50. Measured after each phase: eval pass rate and
  planner p50 (699 ms today, 22 tokens, 40.2 tok/s). If p50 grows past **840 ms (+20%)** or any
  existing fixture regresses, stop and open an OQ before adding more. Options then: shorter
  `summary` texts (ADR-125 deferred that), or a two-stage route (group first, then action).
- **`SYSTEM_POLICY` pin.** `tests/test_prompt.py` pins it byte-identical at 1401 tokens. Each
  capability commit re-pins it on purpose and records the new token count.
- **VRAM.** Nothing new goes on the GPU: ERes2Net, Smart Turn, OCR and Kokoro are CPU. Gemma's
  726 MiB headroom is re-read with `nvidia-smi` after Phase B.
- **CPU in the window.** Each window utterance costs one speaker check (~27 ms) and, for the owner's
  voice, one Whisper pass (~600 ms flat, F26). Measured live in Phase B.
- **False acts in the window.** The speaker check let 3 of 88 phone-video voices through at 0.35;
  ALWAYS-tier actions still confirm. Counted from the heard log during Phase B's live week.

## 7. Not doing (YAGNI)

- No new decision model, no nightly training, no second LLM server.
- No always-listening without a wake word.
- No messaging other than email compose (v2 non-goal, kept).
- No generic `open_url`, no arbitrary shell, no package management (v1 invariants, v2 non-goals).
