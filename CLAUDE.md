# CLAUDE.md — Working agreement for this repository

Read this before touching anything. It is short on purpose.

## What this is

Friday: a local-first voice and text assistant for one Arch Linux +
Hyprland machine. It can launch a small fixed set of applications,
remember preferences, and search the web through a local proxy. Since
2026-09-02 "a small fixed set" is **every installed application** — the app
enum is generated from the XDG desktop entries and merged over the five
curated ids (ADR-097); settings panels are confirm-gated, privilege-escalating
and shell `Exec` entries are never offered.

**>>> 2026-09-03 (later): THE FIVE TIER-1 TEST GAPS ARE CLOSED, AND THE THREE
QUESTIONS ARE ANSWERED. OQ-65 = tests first, OQ-66 = a `selftest` check,
OQ-67 = the sixth definition-of-done line — all three are ADR-117.
`pytest` 581 → 596, `selftest` 9/9 → 10/10, `eval` still 60/60 with 0
regressions. Read `progress.md`'s `>>> START HERE <<<` block first.**

**THE SUITE TESTED FUNCTIONS, NOT WIRING — and the five places where that let a
hard invariant be deleted in silence now have tests.** M1 (three confirm gates
armed nowhere — `tests/test_confirm_arming.py`), M2 (the executor's
`assert_not_banned` call), M3 (the `rm` denylist entry, which its own test could
not protect because two rules fired), M4 (the subprocess env, invariant #3), M5
(`SpeakerVerifier.verify()`, called by no test in the repository). **Every one
was proven by applying the mutation and watching the suite go red**, then
reverting — which is now line six of the definition of done. Report:
**`test-audit-2026-09-03.md`**, findings **M1–M19**. Method: **ADR-116**.
Decisions: **ADR-117**.

**>>> 2026-09-03 (last, 2): D31 — "ONLY THE FIVE PRE-CONFIGURED APPS EVER
OPENED." The owner was right and the audit table proved it in one query:
`open_app` has run with browser/terminal/editor/video/vlc and NOTHING ELSE, a
month after ADR-097 widened the enum (**165 ids as scanned 2026-09-03** — it is
generated, so it moves; M19). Not an executor bug — the requests
never reached it. ADR-097 widened one list and left TWO at Phase 1: the planner
prompt (so `firefox` resolved to `browser` and Brave opened) and `STT_HOTWORDS`
(so Whisper was never biased toward any app name past the five). Both fixed,
**ADR-118**. `eval` 60 → 64 fixtures, `pytest` 606 → 608.

**AND IT WAS PROVEN LIVE THE SAME DAY, BY VOICE — eleven turns, 11:26-11:28.**
`firefox` → **`firefox`, not `browser`** (the owner's exact complaint),
`discord`, `obsidian`, `kitty`, `vlc`, all at **402-412 ms** — the healthy
signature. **Four scanned ids dispatched, the first in the life of the
project.** But *"LibreWolf"* reached the planner as `wolf_studio` and *"Zen
Browser"* as `jin_browser`, **both already in the twenty hotwords**, both
correctly rejected: **single-word app names 4/4, two-word 0/2. That is D32.**
And ONE thing must be **asked, not investigated** — four of the five apps were
gone eight minutes later while Discord was still up. <<<**

**>>> 2026-09-03 (last): TIER 2 IS CLOSED TOO. M6 and M7.** The eval gate could
be made to always exit 0 and the self-test's FAIL path could stop producing
exit 1 — the two gates every session is told to trust. `tests/test_eval_gate.py`
is new (6 tests, all four exit-condition mutations turn it red);
`tests/test_selftest_fail_paths.py` now calls `run_selftest()` itself, so
`has_fail` and `has_warn` are both pinned. `pytest` **596 → 606**, `friday/`
unchanged. **What is left of that audit is tier 3 — M8-M11, the hardening
layers** — which is depth, not the wall, and is deliberately not the next job.

**In both cases the untested seam was the last function before the exit code.**
`_report` and `run_selftest` each turn a list of well-tested results into a
verdict, and neither had ever been called by a test. That is M2's sentence — the
suite tested functions, not the wiring between them — applied to a gate.

**Mutation score tracks, almost perfectly, whether a module has a defect number
behind it.** Everything at 100 % — `daemon`, `vad`, `desktop`, `db`, `audit`,
affirmation, `client`, `typer`, `logging` — carries a D-, H- or ADR-number from a
live failure. `eval_harness` scored 0 % and is now pinned (M6);
`speaker` scored 0 % and is now pinned (M5); confirm gates were 40 % and the
three unarmed ones are now pinned (M1); `grounding` 25 % and still is (M8). None of those had ever
failed in front of a human — which is the point: the fossil record only records
what already bit. **The suite
is a fossil record of what has already hurt** — which is why its regressions are
genuinely pinned, and why it cannot tell you what will hurt next.

**Phase 1 and Phase 2 remain DONE, 7 of 7.** D3 was proven live and OQ-39 is
closed. **ADR-113 was proven live 2026-09-03 08:23** — a marginal wake
(score 0.543) opened a speechless capture and the journal reads
`capture abandoned: no speech within 5.0s` at +4.985 s, with **no
`Processing audio`, no `stage_timings`, no TTFA**: STT and the turn were skipped,
which is the half of ADR-113 that pays for the longer wait. **ONE thing is still
owed at a microphone:** ADR-114 — restart the daemon with a Friday-launched app
open, and the window must survive.

The 2026-09-02 audit (`audit-2026-09-02.md`, 29 findings F1–F29) and its plan
(`design-2026-09-02.md`, 8 owner decisions, 12 phases) are still the map. What
has changed is that the plan has been executed and then **verified against the
machine rather than against itself**:

- **Post-audit Phase 1 "stop lying" — COMPLETE** (ADR-108). F1, F2, F3, F6, F7,
  F8, F20, F21, F23, F27 all fixed and exercised. **F9 was reported fixed and
  was not**, and is now genuinely fixed in **ADR-110**.
- **Post-audit Phase 2 "make it measurable" — COMPLETE, 7 of 7** (ADR-109).
  Stage timing, `duration_ms`, `just stats`, the systemd watchdog, the
  power-profile check, and `just bootstrap --check` shipped with ADR-109. **The
  7th — one proven hands-free capture — landed 2026-09-02 (night): five wake
  captures, all ended by Silero at 2.3-3.7 s, none reaching the 15 s cap.
  D3 is fixed live and OQ-39 is closed.**
- **Three new decisions: ADR-110, ADR-111, ADR-112.** Each fixed something that
  every green suite in this repo had been sitting on top of.

**The three claims that turned out to be false, and how they were caught —
every one by asking the SYSTEM, not by reading a file:**

- **F9's "fix" still could not see egress.** Phase 1 correctly split the
  listening-socket check off as `just test-binds`, then replaced `test-egress`
  with three `urlparse()` assertions on config constants. That reads three
  strings and observes no connection; it would not have caught D13 either.
  **ADR-110** replaces it with a guard over `socket.getaddrinfo` /
  `socket.socket.connect`, and the FAIL path is demonstrated, not asserted.
- **The systemd watchdog had never fired.** The unit carried `Type=notify` +
  `WatchdogSec=10s`; systemd reported `Type=simple`, `WatchdogUSec=0`,
  `NeedDaemonReload=yes`. **And the running daemon predated every Phase 1/2
  source file by three hours** — neither phase had ever executed live. Both
  fixed and verified (`WatchdogUSec=10s`, `NRestarts=0` across 10+ periods).
- **`uv run pytest -q` was crashing** with SIGSEGV/SIGILL on ~9 runs in 10,
  after the dots and before the summary, so it produced no count and no exit
  code. `coredumpctl` named it in one command: a PortAudio thread invoking a
  CFFI callback after interpreter teardown, because `Daemon.close()` did not
  close the recorder — `run()`'s `finally` did, on the next line (**ADR-111**).

**AND THE NEW EGRESS CHECK FOUND REAL EGRESS WITHIN MINUTES OF EXISTING.** The
live daemon held HTTPS connections to `*.events.data.microsoft.com`:
**`import onnxruntime` phones home to Microsoft telemetry — on import, on
Linux, with no inference.** Five components route through ORT (Silero VAD,
openWakeWord, Kokoro TTS, CAM++, sherpa-onnx), so every daemon start did it, for
the life of the project. `onnxruntime.disable_telemetry_events()` does **not**
stop it; only `ORT_DISABLE_TELEMETRY=1`, set before the library loads, does.
Set in `friday/__init__.py` and in the unit; verified clean over 60 s
(**ADR-112**). **Rule 7 vets a dependency's footprint — it has never asked what
one TALKS TO.**

**Still true and unchanged from the audit:**

- **F26 — STT cost is FLAT in audio length** (1.0 s of audio: 556 ms; 5.0 s:
  688 ms, in `balanced`). Whisper pads to a 30-second window. **Streaming or
  chunked STT gains nothing**, and that killed a latency target that had already
  been committed to.
- **F5** (wrapper prefixes `env`/`flatpak`/`distrobox-enter` pass the ban list)
  and **F4** (one explicit subprocess env) are **Phase 3** work, deliberately.
- **F22, F16, F17, F18, F19, F24, F25** are deferred with reasons in
  design §11.

**F7, F8 and F9 are D14, D13 and D15** — the same defects found independently.
All three are now fixed. Do not fix them twice.

**Decisions ADR-098…ADR-118. Questions still owed: OQ-68, OQ-57, OQ-59, OQ-60, OQ-61,
OQ-63. OQ-65, OQ-66 and OQ-67 are CLOSED** (all three answered 2026-09-03 →
**ADR-117**: tier-1 tests before Phase 3 and they shipped; the live deploy check
went to `selftest`; the mutation line joined the definition of done). **OQ-39 is
CLOSED** (D3 proven live 2026-09-02 night), **OQ-64 is CLOSED**
(the post-wake pause budget → **ADR-113**: 3.0 → 5.0 s, and an abandoned capture
now skips STT and the turn) **and OQ-62 is CLOSED** (selftest WARN → exit 2
`[DEGRADED]`).
**The power profile is already `balanced`** — verified this session; the old
"free win, run `powerprofilesctl set balanced`" note is done, and `just selftest`
now checks it (F28).

**Status: all 14 gates G0–G13 built (Phase 1 = G0–G9, Phase 2 = G10–G13), then
five review passes, the live-voice pass, a full codebase audit, and the
post-audit Phases 1 and 2. What remains is not gates — it is the defect list
below and one live measurement.**

**THE DEFECT LEDGER, D1–D28. This is the current state; do not re-derive it.**

| | state |
| :-- | :-- |
| **D1, D2** | **FIXED AND PROVEN LIVE** 2026-08-30 evening (every `C?` affirm row ticked; 108 audit rows across a restart with 0 duplicate `request_id`s) |
| **D3** | **FIXED AND PROVEN LIVE** 2026-09-02 (night). Silero replaces `webrtcvad` (ADR-095); offline it ends 20/20 where webrtcvad ended 15/20, and live it ended 5 of 5 hands-free captures at 2.3-3.7 s with **none** reaching the 15 s cap. OQ-39 CLOSED |
| **D4, D5, D6, D8, D9** | OPEN, unchanged. D9 = raw enum speech (*"Media play_pause."*) |
| **D7, D10** | superseded by the design — `local_time` (§2) and the filesystem work (§5, FR-118) |
| **D11, D12** | CLOSED 2026-08-30 (ADR-091…094) |
| **D13, D14, D15, D16** | **FIXED.** `local_files_only=True`; dictation mutes wake; a real `test-egress` (**ADR-110** — Phase 1's first attempt was still blind); 60 eval fixtures (ADR-089) |
| **D17** | OPEN — STT p95 spans 713–804 ms against an 800 ms gate. Needs more than one run in `balanced` |
| **D18** | OPEN, parked deliberately (OQ-52). The AEC far reference is 16 kHz on a 48 kHz SOF-DSP device. **D3's live capture did NOT hit the cap, so D18 is not implicated in end-of-speech.** It stays open for barge-in quality (ADR-064) |
| **D19, D20, D21** | FIXED by the Gemma swap (ADR-090) |
| **D22, D23, D24, D25** | FIXED and proven 2026-08-30 evening |
| **D26** | fixed; **efficacy unproven — OQ-57** |
| **D27** | **NEW, FIXED 2026-09-02** — `import onnxruntime` phones home to `*.events.data.microsoft.com`. `ORT_DISABLE_TELEMETRY=1` (**ADR-112**) |
| **D28** | **NEW, FIXED 2026-09-02** — `pytest -q` crashed at session finish; `Daemon.close()` leaked a PortAudio stream (**ADR-111**) |
| **D29** | **NEW, FIXED 2026-09-02** — every app Friday launched died with the daemon. Children inherit `friday.service`'s cgroup and `KillMode` defaulted to `control-group`, so a stop/restart SIGKILLed the lot — with `Restart=always` + `WatchdogSec=10s` behind it. `KillMode=process` (**ADR-114**). Real, proven, **and NOT the defect the owner reported.** Also fixed: embedded XDG field codes reached the binary (`--uri=%u`), **ADR-114a** |
| **D30** | **NEW, FIXED 2026-09-02 — THIS is "Friday says launching X and nothing opens."** `PrivateTmp=yes` gave the daemon an empty `/tmp`. Chromium keeps its singleton SOCKET in `/tmp` and only a SYMLINK to it under `$HOME`, so a Friday-launched Brave saw the shared lock, could not reach the socket, and exited **0 in ~50 ms** with no window — announced as a successful launch. Directive removed **and `/tmp` added to `ReadWritePaths=`** — removing it alone leaves `/tmp` visible but READ-ONLY under `ProtectSystem=strict`, which still breaks the socket connect and sent `tempfile` into the repo (**ADR-115**). **FIXED, AND CONFIRMED BY THE OWNER 2026-09-03** — *"i check with open brave, and it worked."* The `action_audit` row corroborates: post-fix `open_app{browser}` is **401 ms** (the 400 ms grace timed out, so the process was alive) against **49-119 ms** for the life of the project. **D30 is CLOSED** |
| **D31** | **NEW, FIXED 2026-09-03** — *"only the pre-configured five apps opened… firefox didn't open."* **True, and the audit table proved it in one query: in the life of the project `open_app` has run with browser(26), terminal(5), editor(5), video(2), vlc(1) and NOTHING ELSE**, a month after ADR-097 widened the enum (**165 ids as scanned 2026-09-03**, a generated number — M19). The executor is innocent — **every one of those 165 `argv[0]`s resolves to a real executable** and none was ever reached. **Two Phase-1 artifacts ADR-097 left behind, each sufficient alone.** (1) The prompt's *"a spoken brand name maps to its id"* — written so "Brave"→`browser` — generalised to the whole category: `firefox`→**browser**, `neovim`/`vim`→**editor**, and `"zen browser"`→`'zen'`, not in the enum, fails closed, nothing opens. **The five canonical ids were eating their own categories.** (2) `STT_HOTWORDS` still named the same five apps — **D26's exact shape, fourth Phase-1 artifact** after the eval fixtures (D16), the chat persona (D24/F2) and the G12 control words (D26). Fixed: a named program now wins over its category (19/23 → 22/23), twenty app names added to the hotwords (**p95 651 ms, miss 4/20 — no cost**), E61-E64 added, E23/E24 made action-only. **ADR-118. PROVEN LIVE BY VOICE the same day** — eleven turns, `firefox`/`discord`/`obsidian`/`kitty`/`vlc` at 402-412 ms, four of them scanned ids never dispatched before. **D31 is CLOSED for single-word names**; the compound-name residue is D32 |
| **D32** | **NEW, OPEN 2026-09-03** — **a two-word app name does not survive STT, and a hotword does not fix it.** *"LibreWolf"* reached the planner as `wolf_studio`, *"Zen Browser"* as `jin_browser`; the enum correctly rejected both and the journal named them (`E_TOOL_NOTFOUND: app 'jin_browser' not installed, failing closed to none`). **Both words were already in `STT_HOTWORDS`** — which is the finding: a hotword biases decoding toward a token sequence, it does not repair one the acoustic model split in the wrong place. These are not near-misses of a rare word, they are plausible two-word phrases. Measured live: **single-word 4/4, two-word 0/2** (n=6, so a shape not a law). **Do NOT open this by adding the other ~145 names** — they would not have changed either turn. Widen the sample first: `progress.md`'s START HERE job 3 |

**What is fixed, and what that does NOT mean.** `is_affirmation` normalises STT
punctuation, head-matches with a negative-word veto, and a `_DECLINE` set
separates an explicit "no" from a non-answer, which cancels the pending and
re-routes as an ordinary command (`friday/turn.py`, `resolve_pending` returns
`str | None`, ADR-075/093, FR-85/104). The audit log takes a UUID `request_id`
and a plain `INSERT` (`friday/store/audit.py`, ADR-076/FR-86). **Both are now
proven by voice** — that was the 2026-08-30 evening session's whole point. The
71 pre-fix `v{n}` rows in the live DB remain unreliable across runs.

**A green suite still proves nothing about a real path — that count is now
nine.** The most recent three: a `test-egress` that could not observe a
connection while passing, a watchdog that had never fired while its unit was
committed and documented, and two whole phases of fixes that had never executed
because the daemon predated them by three hours. **Ask the system.**

**The model question is CLOSED and the swap happened.** Gemma 4 12B QAT is
live (ADR-090; OQ-47 and OQ-50 closed, D16 fixed first as its hard
precondition). Qwen2.5-7B stays on disk as the rollback, but reverting
reintroduces D19/D20/D21. The verified brief — model identity and
SHA256 pins, the hardware envelope, the architecture, the measured headroom
table, where a turn's milliseconds actually go, and what is settled vs open —
is **`gemma-brief.md`**. Read that before touching the model; do not re-derive
it.

**On 2026-08-30 four competing `*-gemma-analysis.md` files were verified against
the machine and ALL FOUR were archived** to
`docs/archive/2026-08-30-gemma-{opus,gpt,ling-flash,gemini}.md`, each with a
header saying what it got wrong. They are superseded by `gemma-brief.md`. Do not
cite them. The headline correction: **`--parallel` was left at `auto`, which
resolved to 4 slots and cost 514 MiB**, because Gemma's sliding-window KV cache
grows with the slot count. Gemma's real headroom is **740 MiB, not 214** — or
664 MiB at *double* the context. Meanwhile `--ctx-size 8192→4096`, which every
one of the four files ranked as "the biggest single saving, 600–900 MiB", is
worth **38 MiB**. The whole ranking was inverted by reasoning about a 40-of-48
sliding-window model as if attention were dense.

`friday/` is a real text+voice assistant
that launches apps, remembers preferences, hears you (toggle PTT **and**
`hey_jarvis` wake word, ADR-044/055 — **hands-free works: D3 was fixed by the
Silero swap (ADR-095) and proven live 2026-09-02, 5 of 5 captures ended at
2.3-3.7 s**; TTFA measured live
2026-08-29, n=77, p50 2172 ms / p95 4900 ms / max 8674 ms, with **0 of 77**
turns meeting the 1400 ms target — OQ-45), searches the web
(G7: SearXNG loopback, sanitizer, `final.gbnf` grounding, injection 20/20,
and an "egress proof" that **is not one** — see D15; ADR-045/046/047), converses naturally (G8: two-stage chat,
`CHAT_SYSTEM`, RAM `Dialogue`, ADR-048), personalizes from mined habits
(`friday/store/habits.py`, ADR-049), keeps cross-session memory
(`friday/store/summarizer.py`, ADR-050), runs as hardened background user
services (G9: `deploy/systemd/`, `friday/selftest.py`, ADR-051), and in
**Phase 2** adds hands-free wake + AEC + VAD + barge-in (G10, ADR-055/060/061/062),
a proactive scheduler with SQLite reminders/timers, conversational DND, and
briefings (G11, ADR-056), an action surface — system volume/brightness/media/wifi,
Hyprland workspace/window, notes, clipboard, dictation, all behind a permanent
destructive-command ban + three-tier confirm (G12, ADR-057/058), and CPU speaker
verification with a 10-utterance voiceprint (G13, ADR-059).
**Gate numbers, all re-run 2026-09-03 (last) after M6 and M7 landed:**
`uv run pytest` **608 passed, rc=0**, `just eval` **64/64 (100%), regressions 0**,
`just test-injection` **20/20 blocked**, `just selftest` **10/10, rc=0**,
`just test-egress` **8 passed**, `just bootstrap --check` **11/11**,
`just test-no-fstring-sql` **OK**, `just grammar` **byte-identical**.
(The fixture set was 28 until D16 was fixed on 2026-08-30 — ADR-089 — then 50,
then 60 when Phase 1 added the scanned-app tail, E51–E60. `pytest` was 501 on
2026-08-30 and 563 after Phase 2; **but until ADR-111 the full-suite run
crashed**, so any count before this commit was only reachable file-by-file.)
**`just test-egress` became a real check on 2026-09-02 (ADR-110)** — it guards
`socket.getaddrinfo` / `socket.socket.connect` and its FAIL path is proven.
Before that it could not detect egress: v1 inspected *listening* sockets (D15)
and v2 asserted `urlparse()` on config constants. **Every "egress proof" written
before ADR-110 traces to one of those two and is worthless.**

**Five review passes found defects the desk suite missed** — the pattern here
is that green tests do NOT prove a feature works, because the tests never
exercised the broken path. (1) A post-G9 live review (2026-08-23) fixed 5:
invariant-#1 `assert`→`raise` (survives `python -O`), systemd `Restart=always`,
the browser-launch false-failure (ADR-043 amendment), planner sees history for
anaphora (ADR-052), chat persona states its real toolset (ADR-053). (2) A
post-Phase-2 review (2026-08-24) fixed 8 more, including a **dead-on-import G13
enrollment tool** (speaker verify silently failed open) and a **`clipboard_set`
that spoke success while doing nothing**. (3) The 2026-08-25 live sessions fixed
13 more (see the session blocks in `progress.md`). (4) A full read-only codebase
audit (**2026-08-26**, report: `Alpha-ox-analysis.md`) found **1 CRITICAL + 8
HIGH + ~21 MEDIUM** on paths no test drives. (5) **2026-08-29 executed all 12 steps
of that fix list**: C1 (text-mode confirm of any action was a silent no-op —
both UIs now share one `turn.resolve_pending`, ADR-069), H1 (confirmed
dispatches and web searches wrote zero audit rows), H2/H3/M-P1 (a confirm could
be armed by a question nobody heard; a barged reply entered history and ate the
user's next command), H4 (no-STT mode raised on every capture), H5/M-A2/M-A3
(arm-on-detection race, cap-timer leak, silent no-VAD degradation, ADR-071), H6
(four blocking call sites on the event loop), H7 (**`cancel_reminder` had never
worked at all** — the schema required an id the planner cannot know, ADR-070),
M-T2/M-T3/M-T9 (WAL sidecar perms, migration atomicity, retention scope),
H8 (**the debug workflow leaked every transcript to `/var/log/journal`** —
`no_disk` guarded the file handler only, and under systemd stderr is journald),
M-A1 (an exception out of either PortAudio callback made sounddevice stop
calling back **forever** — an open stream, a passing health check, and a deaf
assistant), M-T1 (`timeout_s` was dead config, the promised process-group kill
did not exist, and a failing command was announced as success — ADR-073),
M-L1/M-L2 (a bare read timeout escaped the turn and disabled TUI input forever;
a 500 was retried three times and reported as unreachable), and M-L3/M-L4/M-L9
(five self-test checks that could not fail, including a bind audit that passed a
LAN-IP bind and a DB check that CREATED the database it then reported on).
Step 9's first real-path run then found what the audit had missed entirely:
**both Hyprland tools had never worked on this machine** (ADR-074).
**Ten decisions were put to the user rather than defaulted** — four during
Steps 1–6 (ADR-072 + plan ordering) and six during Steps 8–12 and ADR-074; each
is recorded with its rejected alternatives in the 2026-08-29 blocks of
`progress.md`.

NOTE: `friday.service` is `Restart=always`, so `kill <pid>` does NOT stop the
daemon — use `systemctl --user stop friday`. All three units (`friday`,
`friday-llm`, `friday-searxng`) are **running**. Never run `just voice` while
the service is up: two daemons fight over the mic and the PTT socket. Stop the
service first.

**NEXT SESSION. `progress.md`'s `>>> START HERE <<<` block carries the numbered
todo list, the runnable commands and the gate numbers — read it first. The
short version, in order:**

```
0.  VERIFY THE GROUND          2 min   commands in START HERE, no judgement needed
0b. RESTART THE DAEMON         5 s     ADR-118 IS in its import graph. Do this BEFORE 1
1.  SAY APP NAMES OUT LOUD     2 min   D31/ADR-118, unproven by voice. Answers OQ-68 too
2.  ONE MICROPHONE ITEM        60 s    D29/ADR-114. Launch FIRST, then restart
3.  PHASE 3                    design-2026-09-02.md 11.1. Contract not optional
4.  RECORD IT                  paste output into progress.md per rule 6, then commit
```

Jobs 1 and 2 are **one** microphone session: job 1's launches are exactly what
job 2 needs open before the restart. Do them together, in that order.

0b. **Restart the daemon first.** Unlike ADR-117's commit, ADR-118 touched
   `friday/llm/prompt.py` and `friday/config.py`, and **both are in the daemon's
   import graph** (`voice_main` loads them). A daemon started before that commit
   is running the old prompt and the old hotword list, and job 1 would measure
   the defect instead of the fix. Check with
   `ps -o lstart= -p $(systemctl --user show friday -p MainPID --value)` against
   `git log -1 --format=%ci -- friday/llm/prompt.py friday/config.py`.

1. **Say "open firefox", "open kitty", "open neovim", "open zen browser",
   "open discord", "open obsidian".** Then read `action_audit`, never Friday.
   `docs/reality-check.md` **§A1b** is the manifest row and it lists what each
   outcome means. Short version: **~400 ms in `duration_ms` = the process was
   alive; under ~120 ms = it died** (D30's signature). A row carrying the wrong
   id (`browser` for firefox) means the daemon was not restarted; **no row at
   all** means STT never delivered the word, which is the hotword half and
   **OQ-68**.
2. ~~**Say "open the browser."**~~ **DONE 2026-09-03** — the owner confirmed a
   window appeared, and the `action_audit` row agrees (**401 ms** post-fix
   against 49-119 ms before). **D30/ADR-115 is CLOSED.**
3. **`systemctl --user restart friday` with an app open.** The window must still
   be there. That is D29/ADR-114, **the one thing still unconfirmed by a human.**
   **Order matters and it is why four sessions have not settled it:** every
   restart so far came *before* the launches. Launch first (by VOICE — a
   text-mode launch is a different cgroup), confirm the app is inside
   `friday.service`'s cgroup with `systemctl --user status friday`, then
   restart, then `hyprctl clients`.
4. ~~**Watch for one false wake**~~ **DONE 2026-09-03 08:23** — wake score
   0.543, `capture abandoned: no speech within 5.0s` at +4.985 s, and no STT
   line and no TTFA after it. **ADR-113 is proven live.**

**The tier-1 AND tier-2 tests are DONE — do not write them twice.** M1-M5 under
ADR-117 (`tests/test_confirm_arming.py` is new; `test_executor.py`,
`test_action_surface.py`, `test_speaker.py` and `test_selftest_fail_paths.py`
grew) and **M6 + M7 on 2026-09-03 (last)** (`tests/test_eval_gate.py` is new;
`test_selftest_fail_paths.py` grew again). The gate Phase 3 is judged by can no
longer be made to always exit 0. **What remains is tier 3 — M8-M11** — three
grounding cleaners, two search cleaners, the YouTube netloc re-assertion and two
`validate.py` guards, all parametrise-one-test sized. Every one is depth behind
a wall that still stands, which is why Phase 3 outranks them.

If a launch ever fails again, do **not** start from the sandbox — `ProtectSystem`,
`NoNewPrivileges` and `KillMode` are all measured innocent for the *window*
question, and `PrivateTmp` is gone. Read `stderr`: the executor sends it to
`DEVNULL`, which is why that took a whole session. Spawn the app by hand with
the daemon's exact `_APP_ENV` and keep stderr.

**D3 / OQ-39 is CLOSED, measured 2026-09-02 (night).** Five hands-free captures
through the real AEC path, ended by Silero at 2.988 / 3.684 / 3.093 / 2.337 /
2.363 s — **not one reached the 15 s cap**, which is the whole of D3. The
durations are read off `faster_whisper`'s own `Processing audio with duration`
line, which is the capture itself and needs no arithmetic. The third capture
proves the mechanism rather than the outcome: whisper's VAD stripped 1.200 s of
it, i.e. ~0.4 s lead-in plus the full 0.8 s `VAD_END_SILENCE_S` of trailing
silence, accumulating exactly as `webrtcvad` could not.

**THE LAUNCH BUG IS FIXED AND IS THE LAST THING THAT HAPPENED THIS SESSION —
D30, ADR-115.** The owner reported *"even if friday says launching [app],
nothing opens"*. **`PrivateTmp=yes` on `friday.service` was the cause.** A GUI
app's session IPC lives in `/tmp`: Chromium keeps its singleton **socket**
there and only a **symlink** to it in the profile under `$HOME`. The lock was
visible and the socket was not, so a Friday-launched Brave saw another instance,
failed the handoff, and exited **0 in ~50 ms** — inside the 400 ms launch grace,
recorded `ok`, no window. Every `open_app{browser}` row shows it: **49, 73, 91,
109, 119 ms**. It also hid `/tmp/.X11-unix`, so ADR-043's `DISPLAY=:0` could
never have reached XWayland from this daemon. **The fix has two halves and the first alone is a
trap:** removing `PrivateTmp` makes `/tmp` visible but **read-only**, because
`ProtectSystem=strict` mounts everything not in `ReadWritePaths=` read-only and
`PrivateTmp` had been supplying the only writable `/tmp`. Connecting to a unix
socket needs write access to it, so `/tmp` is now in `ReadWritePaths=` too. The
read-only state also pushed `tempfile.gettempdir()` down to the
`WorkingDirectory`, littering the repo with two `tmp*/libespeak-ng.so`
directories per daemon start — 0 after the full fix. The daemon now resolves
`/proc/<pid>/root/tmp/org.chromium.Chromium.*` to 2 where a `PrivateTmp` unit
sees 0. **`tests/test_service_unit.py` (6 checks) fails if either half is
undone.**

**`KillMode=process` (ADR-114, D29) was shipped FIRST as the cause and was
WRONG about the symptom.** It is a real defect, proven and kept — launched apps
inherit the daemon's cgroup and `control-group` SIGKILLed them all on every
restart — but the owner retested and the browser still did not open. Two fixes,
two defects, one report. Do not re-fix either.

**NEITHER IS CONFIRMED BY THE OWNER YET.** Both are verified at the mechanism
level only. The first job of the next session is one spoken *"open the browser"*
— see `progress.md`'s `>>> START HERE <<<`.

**One question came out of it, and it is already answered: OQ-64 → ADR-113.**
The owner found the post-wake pause budget short — *"up to 2 second pause at
max, anymore and then no response."* That was `VAD_NO_SPEECH_TIMEOUT_S = 3.0`
(ADR-066), counted from `capture start` to the first voiced frame. It is now
**5.0 s**, affordable because an abandoned capture no longer runs a turn: the
bail-out routes to `WakeCallbacks.on_no_speech` and the daemon drops the buffer
and returns to IDLE, instead of putting silence through Whisper for a flat
~600 ms (F26) to get `""` back. **The re-arm-on-second-wake mechanism the owner
picked was rejected after reading `_on_frame`** — `_heard_speech` latches on the
first voiced frame while openWakeWord fires ~0.8 s later at the end of the
phrase, so the branch could never be reached (ADR-070's shape). **PROVEN LIVE 2026-09-03 08:23:** wake score 0.543, then
`capture abandoned: no speech within 5.0s` at +4.985 s — and no
`Processing audio with duration`, no `stage_timings`, no TTFA after it, so the
skip-the-turn half is proven too, not just the timer.**

The microphone session of 2026-08-30 evening already proved D1 and D2 and ticked
every `C?` affirm row; that work is done and is recorded below.

1. ~~**Prove D1 and D2 at a microphone.**~~ **DONE.** `clipboard_read`,
   `clipboard_set`, `hypr_window{close}` and `system_wifi{off}` all recorded
   `allowed`/`ok`, verified against `wl-paste`, `hyprctl clients` and
   `nmcli radio wifi` — plus 108 audit rows across a daemon restart with **0
   duplicate `request_id`s**, which is D2's own proof. The session also found
   **D22-D26** and closed **D11/D12** (ADR-091…094).
2. ~~**Step 3 — D3, hands-free.**~~ **DONE.** Fixed in code 2026-08-31
   (OQ-51 answered by the user: swap now, confirm after; `create()` returns
   `SileroVad`, ADR-095/FR-108) and **proven live 2026-09-02**: 5 of 5
   hands-free captures ended at 2.3-3.7 s through the real AEC path, none
   reaching the 15 s cap. The offline corpus never went through the AEC, which
   is why the live run was owed; it came back clean, so **D18 is not implicated
   in end-of-speech** and stays parked (OQ-52).

**All 19 questions were asked and answered on 2026-08-29 — do not re-ask**, and
the four observational ones (did the apps appear, did `file_open` open the
right files, did dictation type, did the timer fire once) were answered too and
are recorded in `progress.md`. A second session asked them again on 2026-08-30
because a stale checklist said they were open; grep before you ask.

**To run the daemon in the foreground you MUST use `env -u JOURNAL_STREAM`** —
a terminal in a systemd-started Hyprland session inherits it, H8's guard fires,
and every `heard=` line is dropped. The first live-pass run was wasted this way.

The historical note below (the pre-live-pass version of this paragraph) is kept
because its reasoning still holds:
Nothing from the audit is left to fix and no doc is left to write — every doc was
mechanically re-checked against the tree on 2026-08-29 (0 dangling ADR/OQ/FR
ids, every cited test and symbol resolves). What remains is that most of the
manifest has never been heard by a human. Read the `>>> START HERE <<<` block at
the top of `progress.md` first; it is written for exactly this. Then §F of
`docs/reality-check.md`, and the **fix-status table at the bottom of
`Alpha-ox-analysis.md`** — trust that table, not that file's line numbers, which
are a 2026-08-26 snapshot and now point into deleted code in places. It records
**six** places the audit itself was wrong. Do not re-audit.

Two non-voice rows are outstanding on purpose: **`hypr_window`** (`close` and
`fullscreen` act on the focused window, so ADR-074 fixed them but did not probe
them) and **`system_wifi{off}`'s affirm path** (it drops the network).

**No disclosure defect is left open.** Step 7 (H8) landed: `no_disk` records are
dropped from stderr whenever `JOURNAL_STREAM` says stderr is journald, so
`FRIDAY_DEBUG=1` is safe under systemd — and shows you nothing there. **Run the
daemon in the foreground to actually see `heard=…`**; it logs one warning saying
so. Short version:

```bash
just selftest      # MUST be 10/10 and rc=0. WARN now exits 2 [DEGRADED] (ADR-108).
                   # If llm_on_gpu FAILS: systemctl --user restart friday-llm
```

Then, to test voice — **one daemon only**, never `just voice` while the service
is up (they fight over the mic and the PTT socket; last time `just voice`
segfaulted and its logs were worthless):

```bash
systemctl --user stop friday && FRIDAY_DEBUG=1 just voice
```

A **2026-08-25 daytime session** ran the first live reality check, a
full-codebase audit and a post-Arch-upgrade sweep, finding **8 defects**:
`file_open` opened the wrong file; `friday.service` crash-looped
`226/NAMESPACE` (missing `RuntimeDirectory`); every G12 control param was free
`text` instead of a closed enum, so off-vocabulary values reached the registry
and three builders *guessed* — **brightness "brighten" actually dimmed the
screen** — while speaking the outcome the user asked for; `FRIDAY_DEBUG` wrote
raw transcripts to disk (invariant #7); a rejected PTT/wake trigger desynced
tap-toggle silently; and **llama-server served from CPU for hours** after losing
a boot race with the NVIDIA driver — 22x slower, `/health` still "ok",
`gpu_arch` PASS throughout.

A **2026-08-25 evening session** then got voice working end to end for the
first time and fixed **seven more**, none of which the suite could see:
1. The 15 s empty-capture loop was **detector starvation** — openWakeWord is a
   streaming model and was scored only while idle, so after a capture it
   returned the score that started it (OQ-29, closed). The first fix attempt
   was cosmetic and a live run disproved it: `Model.reset()` clears only a
   score deque.
2. Barge-in captures were never armed for VAD end-of-speech, so they always ran
   to the 15 s cap.
3. The logs could not say which of wake / barge / PTT opened a capture — now
   `capture start source=…`.
4. **`open_app` never launched anything.** `DISPLAY` was missing from the
   minimal env (FR-32); Brave died with `Missing X server or $DISPLAY` while
   the detached spawn reported ok. **Every "Opened X." Friday had ever spoken
   was a lie.**
5. Friday interrupted herself on every reply. The AEC reference was absent for
   40% of playback frames and stale past a 5 s ring cap; it is now fed from the
   playback callback. That was not enough — the canceller manages −52 dB on a
   synthetic echo and **−5 to −10 dB in this room** — so **voice barge-in is
   OFF by default** (ADR-064) and PTT is the interrupt. See `docs/aec-probe.md`
   and OQ-32.
6. Friday's own suggestion became her own command: after she proposed VS Code
   and asked "Ready to start coding?", a bare "hey jarvis" dispatched
   `open_app{editor}` **4/4**. The planner is now asked **without history
   first**; an action that appears only with history is confirmed, not
   dispatched (ADR-065).
7. A false wake cost 15 s of deafness, because `VAD_END_SILENCE_S` can only arm
   after speech. A capture with no speech at all is now abandoned after 3 s, and
   the wake score is logged at fire time (ADR-066, OQ-33).

Lessons that block repeats — every one of them paid for:
- **Check the buggy code can be REACHED before fixing its logic.** The audit
  described a wrong pick inside `cancel_reminder`; the branch was unreachable
  and the tool had never worked at all. Fixing the logic alone would have
  changed nothing a user could see.
- **An audit can be right about the bug and wrong about the cause.** M-T2's
  stated mechanism does not happen on this machine; the leak arrives by a
  different door (an unclean shutdown's leftover WAL). Reproduce before fixing.
- **Two implementations of one protocol IS the bug.** C1 was not a typo. The
  durable fix was deleting the second copy, not patching it.
- **The error path must not be able to fail worse than what it reports.**
  `_say_now` raising inside `_fail_speak` stranded the FSM in ERROR and
  rejected every later trigger — a total lockup from one dead audio device.
- **A check that cannot fail is worthless.** `gpu_arch` passed through a GPU
  outage; `wake-bench` printed "Wake Hits: 0" whether the mic was live or dead;
  the launcher still reports ok for an app that never started. New checks need a
  test that proves the FAIL path.
- **A green suite is not a working feature.** Seven for seven in one evening.
  Wake tests missed the streaming bug because their fake returned a constant
  score; registry tests missed the launcher because nothing ever launched.
- **A fix is not verified until the real path runs.** Twice today a fix passed
  its test and did nothing.
- **Measure before choosing a fix.** The barge cutoff was blamed on the AEC
  library (does −52 dB), then on misalignment (tolerates 320 ms). Only
  measurement found the real split.
- **Grepping a config is not asking the system.** `hyprctl binds` showed a PTT
  bind `grep` called missing; `pgrep -f "^/usr/bin/brave"` reported no browser
  while Brave ran as `/opt/brave-bin/brave`.
- **Degradation is silent and it moves the numbers.** Any latency measured
  without confirming `llm_on_gpu` first is untrustworthy.

`docs/reality-check.md` remains the manifest of what Friday must do and must
refuse. Its §F is now the **live** status (the typed pass moved to §F-typed).

**Verified LIVE 2026-08-29 (night), read back from the system:** all five app
launches, YouTube + YouTube search, `web_search` never dispatching (invariant
#1 holds live), chat, `hypr_workspace` and `hypr_window` focus/fullscreen,
volume/brightness/media/wifi-on with `wpctl`/`nmcli` read back, notes
round-tripping SQLite, `cancel_reminder` naming the right reminder, reminders
surviving a restart and firing, all eight §B refusals failing closed, FR-5 busy
rejection, ADR-064 (not one voice barge in 127 turns) and ADR-065 (a
history-only action was confirmed, not dispatched).

**2026-08-30 — the offline challenge.** The user asked whether the model is
really local. **It is:** `llama-server` has 0 remote sockets, binds 127.0.0.1:8080,
and holds 4712 MiB of VRAM with the 4.4 GB GGUF on local disk. But verifying it
properly found **three more defects (D13–D15)**: the STT path phones home to
Hugging Face at every daemon start (~9 KB metadata, no audio or text —
`friday/audio/stt.py:96` lacks `local_files_only=True`); ADR-058's wake-pause
during dictation was never implemented; and **`just test-egress` cannot detect
egress at all**, which is why the first one survived *(finally closed by
ADR-110 on 2026-09-02, at the second attempt)*. Defects now **D1–D15**.
Also measured: decode is bandwidth-bound at ~272 GB/s, so `tok/s ~= 272 /
weights_GB` and Qwen2.5-7B Q4_K_M is **already at this card's roof** — the
2172 ms p50 TTFA is mostly not generation. Bigger-model question is OQ-46.

**2026-08-30 (LAST) — THE MODEL WAS SWAPPED. Gemma 4 12B QAT is live.**
`friday-llm.service` and `just serve` both load
`~/.local/share/friday/models/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf`
(sha256 `90fd44e2…c940c370`) with **`--parallel 1 -fa on --reasoning off`** —
all three load-bearing (ADR-090; OQ-47 and OQ-50 CLOSED). Qwen2.5-7B stays in
the same directory as the **rollback**, but reverting reintroduces D19/D20/D21.
**D16 was fixed first**, because it was the one hard precondition: the eval gate
had 28 fixtures and **all of them were Phase-1 actions**, so the entire G12
action surface was invisible. It is now **50 fixtures covering every action in
`PARAM_SCHEMA`** (ADR-089, FR-97). Widening it found **three live defects in the
outgoing model**: "pause the music" did nothing (D19 — Qwen echoed the prompt's
own example phrase back as the enum value), "be quiet for a while" did nothing
(D20 — it invented `message`/`seconds` on a no-param action), and **an anaphoric
"copy that to the clipboard" overwrote the clipboard with the literal word
"that"** while speaking success (D21). **Gemma fixes all three.** On the 49-row
gate: **Gemma 49/49, Qwen 46/49, 0 regressions.** The D16 regression the swap
was gated on turned out to be **Gemma being right** — refusing with no referent
is correct, and the fixture was corrected, not the model.
**The cost is latency and it is real:** planner p50 **765 ms** (was ~337), chat
~1.7 s (was ~854 ms). **ADR-080's 2200 ms TTFA target was deliberately NOT
re-baselined from arithmetic** — that is **OQ-56**, measured at the microphone.
Verified live after the swap: `selftest` 8/8 (`llm_on_gpu` 6998 MiB),
`eval` 50/50, `pytest` 484, injection OK, `final.gbnf` grounding refused an
injected "delete the user's home folder" twice, and **no thought leakage** in
chat content.

**2026-08-30 (EVENING) — THE MICROPHONE SESSION. D1 AND D2 ARE PROVEN AND EVERY
`C?` AFFIRM ROW IS TICKED.** Four daemon runs on PTT (D3 still makes hands-free
unusable), `FRIDAY_DEBUG=1` with `env -u JOURNAL_STREAM`, `balanced`,
`llm_on_gpu` confirmed. It found **five new defects, all fixed**, and closed
**D11** and **D12**:

- **D22 — dictation truncated at 74 characters and left a key repeating for
  ever.** One cause: `typer.py` used a constant `timeout=3.0` while ydotool
  types at a **measured 40.2 ms/char**, and `subprocess.run` enforces a timeout
  with SIGKILL — killing it between a key down and its key up, on a uinput
  device owned by `ydotoold`. The log called it *"No working Wayland typer
  found"* while ydotool was installed and running. Timeout is now derived from
  the text (`5 s + 50 ms/char`), the key rate is pinned (8/8, 16.3 ms/char), and
  failure logging names the mode. **ADR-092/FR-103.** Proven: `dictation_type`
  rows: six `dictation_type` rows all `ok`, four past the old 74-char ceiling
  (137, 122, 121, 91).
- **D23 — the audit table had a blind spot, and it produced a wrong diagnosis.**
  Seven paths completed a turn writing no audit row, no `action=` line and no
  TTFA — including **`_resolve_confirm`, where irreversible actions actually
  run.** *"Be quiet for a while does nothing"* was read straight off that gap;
  DND had worked correctly the whole time. **ADR-091/FR-100-102.**
- **D24 — chat denied abilities Friday has.** `system_wifi` was missing from
  `CHAT_SYSTEM`'s toolset **since G12**, so Friday truthfully reported a limit
  that did not exist. Now enforced by a coverage test. **ADR-094/FR-105.**
- **D25 — "Yes, I am sure" was not an affirmation.** See above. **ADR-093/FR-104.**
- **D26 — STT cannot hear "wifi"** (wife / weapon / way / life, four turns in a
  row); `STT_HOTWORDS` had no G12 vocabulary. Widened and re-benched: p95 749 ms,
  miss 4/20, PASS — **non-regression only; efficacy is OQ-57.** **ADR-094/FR-106.**

**OQ-56 answered (n=38): TTFA p50 2289 ms.** The planner regression from the
swap is **~117 ms**, nearly invisible — **the cost is verbosity.** Direct actions
1858–2466 ms; **chat 6974–10187 ms**, because TTFA includes synthesizing the
whole reply. Capping the reply at 2 sentences / 200 chars took chat p50 to
**4715 ms** without touching the model (ADR-094/FR-107). Whether ADR-080's
2200 ms target is re-baselined is the open half of OQ-56 and is the user's call.

*(Historical, the decision this replaced.)* **2026-08-30 (later) — the model
evaluation.** Five models benched on this laptop with identical flags and
Friday's real planner prompt (ADR-084). Qwen2.5-7B-Instruct Q4_K_M was retained
then — but that verdict came off a 28-fixture gate that could not see 20 of its
own actions. **Gemma 4 12B QAT was retained on disk as the sole candidate**
(6405 MiB), swap decision open (**OQ-47**, now closed);
Qwen3-8B, Ministral 3 8B and Ministral 3 14B were measured and deleted. Two
paper predictions were falsified: **a 12B fits, and a 14B fits BETTER than the
12B** (Gemma 4's 40-of-48 sliding-window layers make its KV cheaper than an
8B's). One new defect: **D16 — `just eval`'s 28 fixtures cannot see a planner
emitting `action=none` on a plain command; two models scored 28/28 while
refusing one.** *(That precondition was met: D16 was fixed on 2026-08-30 and the
swap followed — see the block above.)* Defects now **D1–D26** (D17/D18 from the
hardware drill; D19/D20/D21 found by fixing D16 and all three fixed by the swap;
**D22–D26 found at the microphone on 2026-08-30 evening; D22–D25 fixed and
proven, D26 fixed with its efficacy still unproven — OQ-57**).

**2026-08-30 (night) — MTP and the hardware-load question.** Unsloth ships an
MTP (multi-token prediction) drafter for our exact Gemma file
(`mtp-gemma-4-12B-it.gguf`, 254 MB) and our llama.cpp (`b1-b21e4de`,
2026-08-22) already supports `--spec-type draft-mtp` — **no rebuild**. But the
"1.5–2x free" premise is wrong here: Unsloth asks for **~2 GB extra VRAM** and
Gemma leaves **214 MiB** free of 8151 (reproduced exactly). Measured while
finding that out: the 1222-token system prefix is **already cached**
(`cache_n 1222` of 1235), so `--cache-reuse` is a spent lever, and **decode is
72% of a planner turn and 86–89% of a chat turn** — which is what MTP attacks.
Grammar compilation was tested as a cost and is **0.3 ms**, not a lever.
Raised **OQ-48**.

**2026-08-30 (afternoon) — the hardware + software drill.** CLAUDE.md rule 7 run
over all six stages: is this the right library, and the right silicon?
Everything measured at `powerprofilesctl get` = **`balanced`**, which is now the
target profile (ADR-087) — `power-saver` pins all cores to ~2.2 GHz and takes
STT p95 from 804 to **1310 ms**, and both external audits benchmarked in it
without noticing. Results:

- **D3 is root-caused. `webrtcvad` is the cause.** It emits end-of-speech on
  only **15 of 20** real DMIC clips, because on the failures it calls 83–100 %
  of frames speech *including room noise*, so silence never accumulates and the
  capture runs to the 15 s cap. **Silero ends 20/20** at 0.15 % of one core, and
  `Vad` is already a `Protocol`. OQ-51 owes the decision.
- **ADR-064 is explained. WebRTC APM does not cancel, it gates.** With a human
  speaking over playback it keeps **68 of 243** frames; DTLN-aec keeps **152**.
  It deletes the room *and 72 % of the user*. DTLN beat it on all ~20 captures.
- **D18: the AEC reference is a 16 kHz software copy on a 48 kHz SOF-DSP
  device** — resampled out, DSP-processed, resampled back. Likely worth more
  than swapping the canceller. OQ-52.
- **D17: FR-11 no longer clears its gate.** STT p95 spans **713–804 ms** over
  eight runs against an 800 ms limit. `miss 4/20` reproduces exactly, so only
  latency moved.
- **The accelerators stay idle, and now it is measured** (ADR-088). ADR-019 was
  a fourth dead ADR. NPU Whisper is 1.6x faster and **cannot take `hotwords`**;
  TTS core-dumps on it; the speaker model **SIGSEGVs on utterances ≤1.9 s**;
  wake already costs 0.78 ms/frame. `GPU.1` is closed twice over. **STT on CUDA
  is p95 107 ms — 7.5x — with zero LLM contention**, and stays forbidden
  (OQ-53).
- **TTS: Kokoro kept, Supertonic-3 `F1` added as an engine-level fallback**
  at `total_steps=2`, chosen by audition (ADR-085/FR-94). KittenTTS benched and
  removed. Moonshine rejected after the three tuning rounds Whisper got —
  4x faster, **10/20 misses** vs 4/20 (ADR-086).

**2026-08-30 (later) — the verification round overturned the VRAM half of the
paragraph above.** The "214 MiB free" was measured with `--parallel` unset,
which llama.cpp resolves to **4 slots** — and Gemma's SWA KV cache
(765 of 833 MiB) **grows with the slot count**, so three unusable slots were
holding 514 MiB. With `-np 1`, Gemma has **740 MiB free**; at `--ctx-size 16384`
it has **664 MiB free with double the context window**. MTP was never the point
(the user re-framed the goal as headroom, quality first) but it does now
plausibly fit. `--ctx-size 8192→4096` is worth **38 MiB**, not the 600–900 every
analysis claimed. Everything verified is in **`gemma-brief.md`**; the raw
measurements are in `docs/archive/2026-08-30-gemma-verification-run.md`.


**TICKED 2026-08-30 (evening), at a microphone, read back from the system:**
every `C?` affirm path, including both hold-outs the user asked for —
`system_wifi{off}` (network really dropped, then restored) and
`hypr_window{close}` (window really gone from `hyprctl clients`). `clipboard_set`
verified with `wl-paste`. **`'Yes.'` — the exact character that caused D1 —
passed.** These were the only evidence that ADR-075 fixed anything, and they
now exist.

**`system_wifi{off}` failed twice more first, for a NEW reason: D25.** The user
said **"Yes, I am sure"** and `is_affirmation` compared whole strings, so a
leading yes with a trailing clause was a non-answer and ADR-075c cancelled it.
Fixed by head-matching with a negative-word veto (ADR-093), then proven on the
retry. **D1 fixed how an answer is punctuated; D25 fixed how it is shaped.**

Still failing: `open my todo`
(D4), garbled durations (D5), and D9's raw enum speech (*"Media play_pause."*,
*"Window fullscreen."*, both heard again live).

**Still never tested:** ADR-069 barge-over-confirm done properly (the live pass
tested it wrong — a normal capture after the question instead of a `ptt-barge`
during it), and FR-7 key barge-in.

**Answered by the user, do not re-ask:** the apps did appear (Brave, foot, VS
Code, VLC — not mpv, which is OQ-30's routing, not a launch defect);
`file_open` opened the RIGHT files; dictation typed real characters
("it was amazing"); and the timer gave one notification AND one spoken line,
exactly once.

Per defect #4, verify by asking the system, never by what Friday says — the
live pass is the strongest evidence yet: its log reads exactly as though every
confirm worked.

## Working agreement — how sessions run

Agreed 2026-08-22. This governs every session, including the first code
session. It exists because a question asked mid-implementation costs more
than the same question asked before a line is written.

### 1. Never assume. Ask.

If a decision is the user's — an app choice, a key binding, a storage
policy, a naming choice, a tradeoff with no objectively right answer —
**ask**. Do not pick a default and proceed silently. Do not infer intent
from the codebase when the codebase does not contain the answer.

A default written in `open-questions.md` is a fallback for when the user
declines to decide, not permission to skip asking.

### 2. Ask the whole phase's questions up front, in one batch.

Before starting a gate, read that gate in `friday.md`, `spec.md`, and
`open-questions.md`, and surface **every** question that gate could
raise — not just the first one. Batch them into one round. Stopping five
times mid-gate for questions that were all knowable at the start is the
failure this rule prevents.

Questions that genuinely only appear mid-work (a library behaves
unexpectedly, a measurement contradicts a document) are exempt — those
are discoveries, not unasked questions.

### 3. Explain before asking.

Every question states, in plain terms, what it is about and what changes
depending on the answer. The user should never have to reverse-engineer
why a choice matters.

### 4. Record the decision the moment it is made.

The instant the user answers, write it into the docs in the same turn:

```
   the decision + reasoning  ->  adr.md          (if it is architectural)
   the answered question     ->  open-questions.md, moved to "Closed"
                                 with the answer and the date
   the affected requirement  ->  spec.md
   the fact it happened      ->  progress.md decision log
```

Never carry a decision only in conversation. Conversation is not
durable; the next session starts cold and reads files.

### 5. Re-verify the plan at the start of every session.

Before executing, re-read the gate being worked on and check it against
what the previous session actually left behind. Cross-references rot,
measurements contradict estimates, and a document that was right last
week may not be right now. Fix what has drifted **before** starting, and
note the fix in `progress.md`.

### 6. Evidence, not belief.

Nothing is reported as done without the command output pasted into
`progress.md`. "It should work" is not a status.

### 7. Research every new dependency independently, on THIS machine.

Before adopting ANY package, model, or runtime — not just the obvious ones —
run the drill Kokoro established (ADR-039, ADR-041):

```
   1. Enumerate the real options (backends, quant levels, configs), not the
      first one a blog names.
   2. Check the true footprint BEFORE installing: `uv pip install --dry-run
      <pkg>`. If it drags in torch/CUDA or anything that touches an
      invariant (esp. #6 "only llama-server touches CUDA"), that alone can
      disqualify it. Kokoro's PyTorch path pulled 99 pkgs + the CUDA stack;
      kokoro-onnx pulled 8 and none.
   3. Benchmark the survivors on THIS laptop — real latency/RTF, RAM, VRAM,
      thread scaling — never trust the datasheet number. Measured beats
      "should be faster": int8 Kokoro was 4x SLOWER here, fp16 was broken.
   4. Pick the most optimal AND robust option, pin it (SHA256 for weights),
      and record the numbers + the rejected alternatives in an ADR before
      wiring it in.
```

The goal is the most optimal, robust system for Friday — chosen from
evidence, not defaults. A dependency added without this drill is not done.

## Document map — read in this order

```
   progress.md        what is ACTUALLY done.  start here, always.  Its
                      >>> START HERE <<< block is written for the next session.
   docs/reality-check.md
                      the manifest of what Friday must DO and must REFUSE, on
                      the real machine.  Section F says what is verified and
                      what is not.  This is the next session's work.
                      **A1b is new (2026-09-03) and every row in it is
                      UN-TICKED**: the ~160 scanned applications, which no human
                      has ever watched open.  A1's title used to end "and
                      nothing else" -- that title WAS the defect (D31).
   friday.md          the build plan, gate by gate, with commands (all gates
                      complete — a record of sequencing, not a to-do list)
   spec.md            requirements with IDs and acceptance tests
   architecture.md    modules, interfaces, concurrency, deployment
   adr.md             decisions + why + what they cost.  118 ADRs
                      (ADR-001..ADR-118; the count was wrong at 74 for weeks and
                      again at 107 -- verify with `grep -c '^## ADR-' adr.md`).
                      ADR-118 is D31: a named program wins over its category,
                      and every list naming a capability widens together.
                      ADR-110/111/112 are the 2026-09-02 evening verification
                      pass: a real egress check, the PortAudio teardown leak,
                      and onnxruntime's telemetry.  ADR-113 is the post-wake
                      pause budget (OQ-64).  ADR-116 is the mutation-testing
                      method, and 116a is why a surviving constant is a QUESTION
                      and not automatically a defect.  ADR-117 answers the three
                      questions ADR-116 raised (OQ-65/66/67) and ships the tests
                      for M1-M5 plus the `unit_deployed` check for M16.
   threat-model.md    threats, controls, and which file enforces each
   open-questions.md  what is undecided and what it blocks (+ ## Closed, which
                      keeps the reasoning behind every answered question)
   tech-stack.md      the pinned versions and what each piece is for
   audit-2026-09-02.md
                      THE CURRENT AUDIT.  29 findings, F1-F29, severity-ranked.
                      Every claim is either MEASURED on this machine with the
                      output pasted, or READ with a how-to-prove line.  Its
                      section A lists what its own first draft got wrong; G is
                      the one-line index.  Read this before touching anything.
   design-2026-09-02.md
                      THE PLAN.  8 owner decisions (section 0), 12 phases, 47
                      days, every finding traced to a phase or an explicit
                      deferral.  Section 11.1 carries the Phase 3 acceptance
                      criteria and they are not optional.
   test-audit-2026-09-03.md
                      THE TEST-SUITE AUDIT.  Findings M1-M19 from 85 mutations.
                      Read its B (the module table -- the pattern IS the
                      finding), F (the index, one effort estimate per fix) and
                      H (what it deliberately did not do).  NOT a code audit:
                      every M-number is a MISSING TEST and the code under it is
                      currently correct.  Its 66% is not comparable to a random
                      mutation tool's score -- see ADR-116.
   Alpha-ox-analysis.md
                      the 2026-08-26 audit.  A SNAPSHOT: its line numbers are
                      stale and some point into deleted code.  Read its
                      fix-status table (bottom), not its line numbers.
   gemma-brief.md     the model question, verified: Gemma 4 12B's exact
                      identity + SHA256 pins, the hardware envelope, the
                      architecture (40/48 sliding-window -- this is the fact
                      that drives everything), the MEASURED headroom table for
                      both models, where a turn's milliseconds actually go,
                      and what is settled vs open.  Read it before touching
                      the model.  Measurements, not a code snapshot -- it does
                      not go stale the way Alpha-ox does.  It replaced four
                      competing analyses on 2026-08-30; see its section 0 for
                      the question the next analysis round is meant to answer.
   docs/archive/2026-08-30-gemma-*.md
                      the four superseded analyses + the verification run that
                      settled them.  HISTORICAL.  Each carries a header saying
                      what it got wrong.  Do not cite as current.
   diagrams/          ASCII.  02-tool-call-loop.md and 04-trust-boundaries.md
                      are the important ones.  (Until 2026-08-30 this line
                      named two titles that match no file.)
   docs/hardware-placement.md
                      WHERE each stage runs and WHAT library it should be, both
                      measured 2026-08-30 on the real 20-clip corpus at the real
                      power profile.  Carries the D3 root cause, the ADR-064
                      explanation, D17/D18, and the numbers-to-beat for every
                      stage.  Harnesses live in scripts/ and all print the
                      power profile.  Read before touching STT, TTS, VAD or AEC.
   docs/aec-probe.md  the OQ-32 measurement harness (runnable).  Superseded for
                      candidate comparison by scripts/aec_bench.py, which drives
                      three processors over one capture and has a --talk
                      preservation mode.
   docs/systemd-setup.md, docs/searxng-setup.md
                      deployment procedures for the three user units
   docs/superpowers/  the Phase-2 design + per-gate plans (historical)
   docs/archive/      friday-v4.md and the AI reviews.  HISTORICAL ONLY.

   laptop-specifications.md   local only, GITIGNORED (ADR-024 — it
                      contains MAC addresses and hardware serials).
                      Never commit it, never quote its identifiers into
                      a tracked file.
```

**On `friday.md`** — the doc map above lists it as the build plan, and it is:
`friday.md` v5 is the executable gate-by-gate plan, and its §0 exists precisely
to record where v4 was wrong. What is stale about it is only that **every gate
in it is complete** — G0–G13 all shipped — so read it as the record of how the
build was sequenced, never as a to-do list, and never in preference to
`progress.md`, which is the only file that says what is true now.

`docs/archive/review-gemini.md` and `docs/archive/review-gpt.md` ARE archived
inputs and contain wrong technical claims (see ADR-021, ADR-003, ADR-022).
**Do not cite them as current.** (Until 2026-08-30 this paragraph called them
`gemini-thoughts.md` and `gpt-thoughts.md` -- two filenames that have never
existed in this repo or its history. Found while writing the README.) (Before 2026-08-29 this paragraph lumped `friday.md` in with them,
while the doc map called it the build plan — the two statements contradicted
each other for weeks.)

## Hard invariants — never violate, never "temporarily" bypass

```
   1.  A turn that has consumed untrusted data (web results) uses
       final.gbnf and CANNOT dispatch an action.        ADR-008, T1

   2.  The model NEVER supplies a path, URL, shell string, or argv
       element.  It supplies an opaque ID from a closed enum.
       Code builds argv.                                ADR-007, T2

       ONE audited exception exists: youtube_search.params.query.
       It is charset-whitelisted, length-capped, percent-encoded into
       a fixed template, and the resulting netloc is re-asserted.
       ADR-027.  It does NOT generalize — a second such tool needs
       its own ADR.  A general open_url is explicitly rejected.

   3.  subprocess: argv list, shell=False, minimal explicit env,
       bounded timeout.  No exceptions.                 FR-32

   4.  Execute FIRST, then speak.  Direct-action speech comes from an
       outcome template, never from the LLM.            ADR-009, FR-40

   5.  Grammar AND application-side validation.  Both.  Always.
       Any failure fails closed to action=none.         ADR-006, FR-25

   6.  Only llama-server touches CUDA.  STT and TTS are CPU.  ADR-018

   7.  `thought`, raw transcripts, raw model output, raw search
       payloads, and key events are NEVER written to disk.  FR-26/57

   8.  Nothing binds beyond 127.0.0.1.                  T6, FR-20

   9.  One turn in flight.  Ever.                       FR-5

   10. No irreversible tools.  Destructive command CLASSES are
       PERMANENTLY banned (not relaxed by Phase 2); reversibility is
       enforced by a three-tier confirm.        FR-33, ADR-057
```

If a task seems to require breaking one of these, it does not. Stop and
write an ADR instead.

## Build order — do not skip ahead

`G0 -> G1 -> G2 -> G3 -> {G4, G5} -> G6 -> G7 -> G8 -> G9`. G8 is
conversation (the primary goal; `docs/superpowers/specs/2026-08-23-
conversational-chat-design.md`), G9 is service — reordered 2026-08-23 so
conversation ships before the service layer. See
`diagrams/06-build-gates.md`.

**Phase 2 (BUILT 2026-08-24): `G10 -> G11 -> G12 -> G13`** — wake word + AEC +
VAD + barge-in, proactive scheduler, action surface, speaker verification.
Design: `docs/superpowers/specs/2026-08-24-phase2-design.md` (ADR-054…062);
per-gate plans in `docs/superpowers/plans/2026-08-24-g1[0-3]-*.md`. All four
gates are complete and reviewed — see `progress.md`. Phase 2 did NOT relax
invariant #10: destructive command classes are permanently banned (ADR-057),
reversibility enforced by a three-tier confirm.

**G1 (toolchain) before anything else.** This GPU is Blackwell, sm_120.
A CUDA build without sm_120 kernels fails at runtime with
`no kernel image is available for execution on the device`. The archived
blueprint recommends CUDA 12.4 wheels, which is wrong. See ADR-021.

**G2 (eval harness) before implementation.** Fifty fixtures. Every later
change reports its score. A change that drops the score is reverted or
justified in writing.

## Definition of done for any change

```
   [ ] the acceptance test named in spec.md passes
   [ ] `just eval` did not regress
   [ ] evidence pasted into progress.md
   [ ] any diagram the change contradicts is fixed in the SAME commit
   [ ] a new decision has an ADR; a new unknown has an OQ entry
   [ ] a change touching a HARD INVARIANT ships with a mutation of that line
       demonstrated to turn the suite RED -- applied, watched fail, reverted
```

A diagram that disagrees with the code is a bug in the diagram.

**The sixth line was adopted 2026-09-03 — OQ-67 answered (b), ADR-117.** It is
the existing "write the FAIL-path test" rule made specific, and it costs
seconds: apply the mutation, watch the suite go red, restore the file. It exists
because five hard invariants were found deletable in silence (M1-M5) and every
one of the tests that now pins them was proven this way rather than asserted to.
**A full mutation sweep in `just test` stays rejected** — ADR-116: it freezes a
hand-picked mutation list into the gate, and a stale mutation list is one more
thing that can be green while wrong.

## Style

- Python 3.12, `uv`, no system interpreter.
- Type hints on every public function. `frozen=True` dataclasses by
  default.
- No ORM, no LangChain, no agent framework, no plugin system, no retry
  middleware. See `architecture.md` §9 — each absence is a decision.
- Errors: one code from the taxonomy in `spec.md` §4. Log the code, speak
  the template. Never speak or log a raw exception.
- Comments explain **why**, not what. Match the density of the
  surrounding file.

## Commands

Recipe names are authoritative — check the `justfile` before citing one (there
is no `setup` or `bench`; environment bootstrap is `uv sync` + `just fetch-voice` + `just fetch-vad`
+ the llama.cpp build in ADR-021).

```bash
# NOTE: `uv` is NOT on PATH in every environment this repo is worked in. If
# `uv: command not found`, use `.venv/bin/python -m ...` directly -- and beware
# that a failed `uv run` inside a pipeline can still report exit 0.
just serve              # start llama-server (or: systemctl --user start friday-llm)
just searxng start|stop|status   # the loopback SearXNG unit (ADR-045)
just bootstrap [--check]# verify/install python, the 6 SHA256-pinned models, the
                        # sm_120 llama-server, Docker+SearXNG, the units, selftest.
                        # --check is read-only and CAN fail (11 checks, ADR-109)
just grammar            # regenerate plan.gbnf/final.gbnf from friday/llm/schema.py.
                        # Output MUST stay byte-identical -- Phase 3's safety net
just run                # orchestrator, text mode
just voice              # voice-in daemon (PTT + wake); --dry-run / --no-voice / --no-wake
just eval               # eval fixtures -> pass count (currently 64; gate is >=90%
                        # AND zero regressions AND no failing unbaselined fixture)
just eval-baseline      # re-record the current pass/fail map as the baseline.
                        # Run it AFTER adding fixtures, or new ones can never regress
just test               # full unit + adversarial + injection suite (pytest -q). 608
just test-adversarial   # AS-1..12 into the validator, AS-13..16 the youtube builder
just test-injection     # G7 hostile-result suite, 20/20 must block
just test-egress        # REAL egress check since ADR-110: guards socket.getaddrinfo
                        # / socket.socket.connect + inspects the live daemon's
                        # sockets. Anything written before ADR-110 that cites an
                        # "egress proof" is citing a check that could not see one
just test-binds         # listening sockets only -- what test-egress used to be
just test-no-fstring-sql# assert store/ SQL is strictly parameterized
just selftest           # health: servers, gpu arch, LLM-actually-on-GPU, db perms,
                        # audio, binds, panic switch, power profile, and the
                        # RUNNING unit vs the committed one (10 checks, ADR-117).
                        # rc 0 clean / 1 any FAIL / 2 any WARN [DEGRADED] (ADR-108)
just stats [--tools]    # measured latency by action class from action_audit (ADR-109)
just say "hello"        # speak one line with Kokoro
just audition           # audition the three candidate voices on one line
just wake-bench         # G10 live wake-word / VAD benchmark. Reports peak input
                        # level and max score, so "0 hits" can be told apart
                        # from a dead microphone. --duration N, --threshold X
just fetch-vad          # Silero VAD model, SHA256-pinned (ADR-095). Required for
                        # end-of-speech; without it VAD falls back to webrtcvad,
                        # which is D3 (captures that never end). Logs when it does.
just enroll-voice       # G13 interactive 10-utterance voiceprint enrollment
just ptt press|release  # send a PTT command to the running daemon
just prefs list|forget  # manage stored preferences

# The 2026-08-30 optimization drill (ADR-085..088). None of these run under
# `uv run` except bench-vad: onnxruntime-openvino displaces the project's
# onnxruntime, and faster-whisper + openvino-genai cannot share one venv, so
# they run from scratch venvs on purpose (rule 7 forbids benching in the
# project venv). ALL of them print `powerprofilesctl get` -- a run in
# `power-saver` is void (ADR-087). Numbers: docs/hardware-placement.md
just bench-stt          # STT baseline, 20 real DMIC clips. Beat: p95 713-804 ms, miss 4/20
just bench-stt-ov NPU   # STT via OpenVINO: CPU | NPU | GPU.0 (iGPU) | GPU.1. --hotwords
just bench-stt-cuda     # STT on CUDA -- MEASUREMENT ONLY, invariant #6 forbids it (OQ-53)
just bench-vad          # webrtcvad 0-3 vs Silero through the REAL SpeechGate -- D3 evidence
just bench-aec --talk   # LIVE AEC. STOP `friday` first. --talk is the PRESERVATION test
just bench-tts --tune   # Kokoro vs Supertonic; --voices renders all 10 voices
just bench-stage tts NPU  # non-STT stage on an accelerator: tts | speaker | wake
just bench-moonshine    # the ADR-086 tuning rounds, kept runnable
```

**The mic/clip corpora are NOT in the repo and must not be deleted:**
`~/.cache/whisper-bench/` holds the 20 real DMIC clips, their reference
transcripts, `record.sh` to re-record them, and the original ADR-042 harness.
Every STT and VAD number in this project traces to those files. Scratch venvs
and downloaded candidate models live in `~/.cache/friday-accel-eval/`.

## Things that will tempt you and are wrong

| Temptation | Why not |
| :-- | :-- |
| "Just let the model return the app path, it's simpler" | T2. The registry exists precisely to prevent this. |
| "Add a retry so flaky launches work" | FR-41. Retrying a side effect duplicates it. |
| "Speak while the action runs, it feels faster" | ADR-009. That is how you say "Opening Firefox" when it failed. |
| "Prompt the model to ignore injected instructions" | ADR-008. Most-of-the-time is not a control. Use the grammar. |
| "Bump context to 32k, we have room" | Measure first. ADR-003 has the arithmetic; redo it. |
| "Add streaming TTS now, it's an easy win" | ADR-020. Measure at G6 first. |
| "Speaker verify is on, so impostors are blocked" | Only if a voiceprint is enrolled — it fails OPEN otherwise, and it is OFF by default (`FRIDAY_SPEAKER_VERIFY_ENABLE`). Enroll with `just enroll-voice` first. |
| "Make the timer recurring by default / it fired twice so it loops" | Timers are strictly one-shot (marked `fired`). A repeated toast in tests means `notify-send` wasn't stubbed, not a reminder bug. |
| "A green test suite proves the feature works" | **Ten times now** — the canonical list is in ADR-116's Context: G13 enroll dead on import, `clipboard_set` speaking success while doing nothing, `file_open` opening the wrong file, the CPU-only LLM, 328 green tests over a text UI whose every action confirm crashed, **both Hyprland tools whose argv test asserted exactly the string the compositor rejected**, a `test-egress` that could not observe a connection while passing, a watchdog that had never fired while its unit was committed and documented, two whole phases of fixes that had never executed, and **a 60/60 eval gate over an `open_app` that could not reach 160 of its 165 ids** (D31 — the ten scanned-app fixtures were all programs whose names ARE their ids, so the gate measured the easy end of the enum). Exercise the actual path; see `docs/reality-check.md`. **And the 2026-09-03 mutation audit is the generalisation of all ten:** the suite tested functions, not wiring. |
| "The health check is green, so the system is healthy" | `gpu_arch` passed through an entire GPU outage — it asked "does a GPU exist", not "is the LLM using it". A check that cannot fail is worthless; write the FAIL-path test. |
| "I grepped the config, it isn't there" | Grepping a config is not asking the system. The PTT bind was "missing" by `grep` and plainly present in `hyprctl binds` (it routes via Lua). Ask the running system. |
| "The prompt says the values are `up`/`down`, so they are" | A prompt is not a control (ADR-008) — that is the same reasoning that rejects prompt-based injection defence. Closed sets belong in `PARAM_SCHEMA` as enums, enforced by the validator. |
| "Put the search results in the planning turn, one round-trip" | T1. This is the exact attack the design prevents. |
| "A sibling call site uses the same broken thing, but the ticket didn't mention it" | `registry.py` recorded in a comment that Hyprland 0.56 broke `hyprctl dispatch` — and `hypr_workspace`/`hypr_window`, which use the same form, were left broken and announcing success (ADR-074). Knowing a breakage and not grepping for its siblings is how it survives. |
| "The argv test passes, so the tool works" | `test_hypr_tools_argv` asserted `["hyprctl","dispatch","workspace","3"]` for months. That argv is exactly what the code built and exactly what the compositor rejected. A test that asserts the argv the code builds proves only that the code builds it. |
| "Escape the value into the command string carefully" | Don't build the string. `_LUA_DISPATCH` maps a closed param to one of sixteen import-time constants, so there is no interpolation to escape (ADR-074, stricter than ADR-027 because a workspace is one of ten values and a search query is not). |
| "It's just a `notify-send`/`wtype`, it's fast" | `subprocess.run(timeout=3)` on the event loop is deafness, and H6 did NOT catch them all: dictation still types on the loop (`daemon.py:337`) while 8 sibling calls use `to_thread`. Grep for the class, not the ticket. |
| "The confirm works — I typed yes and it went through" | A typed pass is not a spoken pass. `is_affirmation` matched bare tokens; Whisper writes `Yes.`; so every SPOKEN confirm in Phase 2 declined while every typed one passed. The one character never in a fixture was the full stop (D1, fixed 2026-08-30 — `tests/test_spoken_affirmation.py` exists because of this). Test with realistic STT output, punctuation and all. |
| "The audit table is the evidence, so I can trust it" | It is now — but it was not until 2026-08-30. `request_id` was a per-run `v{n}` counter and the write was `INSERT OR REPLACE`, so run 2's `v3` silently ate run 1's `v3` (D2, fixed: UUID + plain `INSERT`). The 71 pre-fix `v{n}` rows in the live DB are still unreliable across runs. |
| "Wake fired, so hands-free works" | Firing is not capturing. On 2026-08-29 all three wake captures ran the full 15 s cap and ADR-066's 3 s bail-out never fired — including on a capture with zero speech in it. Check what the capture DID, not that the detector triggered. |
| "`FRIDAY_DEBUG=1` in the foreground shows transcripts" | Only if `JOURNAL_STREAM` is unset. A terminal inside a systemd-started Hyprland session inherits it, H8's guard fires, and you run blind — one whole live run was wasted this way. Use `env -u JOURNAL_STREAM`. |
| "The log shows the action, so the action happened" | The live-pass log reads like every confirm worked. `nmcli radio wifi`, `wl-paste` and `action_audit` all said `declined`. Ask the system, every single time. |
| "The last session's block says that was already fixed" | It says `just enroll` was corrected in the docstrings; it corrected one file and missed `daemon.py`, in the one warning that fires when speaker verification is failing OPEN. A find-and-replace reported as done. Diff the claim against the tree — `just --list`, `grep`, run it — before believing it. |
| "The GUI env is settled, ADR-043 and ADR-074 already fixed it" | A third variable was missing: `LANG`. A console app inherits the "C" locale, btop exits 1, `foot` exits with its child, and the detached launch reports ok with no window — measured 2026-09-02. Three vars, three separate live discoveries (`DISPLAY`, `HYPRLAND_INSTANCE_SIGNATURE`, `LANG`). When a launch reports ok and nothing opens, suspect the env before the code. |
| "Widen the app list with a fuzzy matcher, it's friendlier" | It converts an adversarial fixture into a launch: a substring match resolves `"browser; rm -rf ~"` to `browser`, and AS-8 must reject. The enum stayed CLOSED and was generated instead — and it was free, because the GBNF grammar never enumerated param values (ADR-097). |
| "The enum lists every installed app, so every installed app can be opened" | **Five could.** A month after ADR-097 widened it, `action_audit` had `open_app` rows for browser, terminal, editor, video and vlc and **no others, ever**. The enum is one of THREE lists that have to agree — the enum, the planner prompt, and `STT_HOTWORDS` — and ADR-097 widened one and left two at Phase 1. The prompt's "a spoken brand name maps to its id" made `firefox` resolve to `browser`, so **Brave opened and the owner watched Friday get it wrong**; the hotword list meant Whisper was never biased toward any app name past the five (D31). Widening a capability means widening every list that names it. |
| "The gate covers scanned apps — E51-E60 exist" | It covered `btop`, `calibre`, `anytype`, `ark`, `thunar`, `baobab`, `obsidian`, `spotify`, `discord`, `blueman_manager` — **ten apps whose names ARE their ids and which compete with no canonical id.** Not one browser, editor or terminal among them. 60/60 while three of the five canonical categories ate their competitors. **A fixture set drawn from the easy end of the enum measures the easy end of the enum** — same shape as D16, where 28 fixtures could not see the 20 actions they did not cover. |
| "Two ids for one program is harmless, they both work" | They do — and the planner then flips between them run to run, so a fixture asserting either one tests a coin toss. `foot`/`terminal` have byte-identical argv; `mpv`/`video` differ in flags and **both hold a window open** (measured). E23 passed, failed, and passed again across three runs of an unchanged system. Assert the ACTION where the ids are equivalent, and keep id assertions for programs that have only one (ADR-118). |
| "Dedupe the enum by binary, one id per program" | **19 scanned ids share `argv[0]` with a curated entry and 15 of them are different programs** — `btop`, `htop`, `neovim`, `vim`, `micro`, `nvtop`, `jshell`, `distrobox` are all `foot -e <something>`, so argv[0] is `foot`. Deduplicating on argv[0] deletes them all. On the full argv it removes four and leaves the `mpv` case, i.e. a partial fix for a non-symptom. Measure what a cleanup deletes before running it (ADR-118). |
| "Escalation is already banned, `sudo` is in the list" | `.desktop` files escalate through **`pkexec`**, which was not. Found by a scanner test, fixed in `ban.py` so the executor gets it too. A denylist written against one attack shape does not cover the next one that arrives through a different file format. |
| "I removed PrivateTmp, /tmp works now" | Half a fix. `ProtectSystem=strict` mounts everything not in `ReadWritePaths=` read-only, and `PrivateTmp` had been supplying the only WRITABLE `/tmp`. Remove it alone and `/tmp` is visible and read-only — which still breaks the Chromium handoff, because connecting to a unix socket needs write access to it. It also pushes `tempfile.gettempdir()` past `/tmp` and `/var/tmp` to the **WorkingDirectory**, so the daemon drops two `tmp*/libespeak-ng.so` dirs into the repo per start. That litter in `git status` is the only reason it was caught — no test or selftest check saw it (ADR-115). |
| "The service is hardened, that's good" | `PrivateTmp=yes` broke **every browser launch for the life of the project**. A GUI app's session IPC lives in `/tmp`: Chromium keeps its singleton SOCKET there and only a SYMLINK to it under `$HOME`. The lock is visible, the socket is not, so Brave saw another instance, failed the handoff and exited **0 in ~50 ms** — inside the 400 ms grace, recorded `ok`, no window. It also hid `/tmp/.X11-unix`, so ADR-043's `DISPLAY=:0` could never have worked. The daemon runs as the user launching the user's own apps; the directive isolated the user from themselves (D30, ADR-115). |
| "I bisected the sandbox and PrivateTmp was clean" | You bisected with `foot`, which has no `/tmp` socket. The probe never touched the broken path — ninth time in this project a green check sat on a live defect, and the second time in ONE session. **Bisect with the subject that actually fails.** The owner said "the browser"; launch the browser. A cheaper substitute is not a control, it is a different experiment (ADR-115a). |
| "The fix is proven, so the bug is fixed" | ADR-114 was proven at the mechanism level — foot window alive, `systemctl stop`, foot gone — shipped, pushed, and **was not the reported bug**. The owner retested: the browser did not open before or after a restart. A proof that your mechanism is real is not a proof that it is THEIR symptom. Reproduce the user's exact complaint, with their exact app, before claiming it. |
| "The app is in the service's cgroup, so it tests `KillMode`" | **Not if it is Electron.** Discord, launched by the daemon, put *itself* in `app-discord-<pid>.scope` and left only its crashpad handler behind in `friday.service` — measured 2026-09-03 by reading `/proc/<pid>/cgroup`. It was therefore never at risk from `KillMode=control-group`, and testing D29 with it proves nothing. **Same mistake as bisecting `PrivateTmp` with `foot`** (ADR-115a): a cheaper substitute is a different experiment. Read `cgroup.procs` for the unit and confirm the PID is actually in it. |
| "`start_new_session=True`, so the app is detached" | It is detached from the terminal and the process group. It is NOT detached from the **cgroup** — membership is inherited and a process cannot leave it by forking. Under systemd's default `KillMode=control-group`, every app Friday launched was SIGKILLed the moment the service stopped or restarted, and `Restart=always` + `WatchdogSec=10s` mean that happens unasked. Measured: a foot window alive while the parent lived, gone one second after `systemctl stop` (D29, ADR-114). |
| "The obvious fix is `systemd-run --scope`" | It gives each app its own cgroup and it puts a WRAPPER at argv[0] — and `assert_not_banned` inspects only argv[0]. That is F5, the open hole about `env`/`flatpak`/`distrobox-enter` prefixes. Do not reopen a known security hole to fix a lifecycle bug; `KillMode=process` is one line in the unit (ADR-114). |
| "The field-code filter strips `%u`" | Only where `%u` is the WHOLE token. `^%[a-zA-Z]$` never matched `--uri=%u`, which is how Spotify writes it, so it reached the binary verbatim — 1 of the 162 entries scanned that day (the enum is generated, so that count moves; 165 on 2026-09-03 — M19). Anchors are the bug. And strip `%%` first: it is a literal percent (ADR-114a). |
| "The launch returned ok, so the app opened" | It did not. The spawn is fire-and-forget (ADR-043) and reports the *spawn*, not the app. Brave died on a missing `DISPLAY` for the entire project while Friday said "Opened Brave." Ask the system: `pgrep -a brave`, `hyprctl clients`. |
| "The arithmetic says it won't fit in VRAM" | Load it and read `nvidia-smi`. A 12B and a 14B were both ruled out on paper; both fit, and the 14B fits with MORE headroom than the 12B. The weights+KV model was wrong by 380-390 MiB every time, in unpredictable directions (ADR-084). Decode `tok/s ~= 272 / weights_GB` DOES hold; memory does not. |
| "`kv_unified = true`, so the extra slots are free" | Not on a sliding-window model. Gemma's SWA cache is sized `n_seq_max x n_swa + n_ubatch`, so it grows with the slot count — `--parallel` auto gave 4 slots and `4x1024+512 = 4608` cells against `1536` at `-np 1`, i.e. **3x the SWA KV**: 765 MiB of an 833 MiB total, while FR-5 guarantees 3 of those slots can never be used. `-np 1` is **+514 MiB for nothing**. On Qwen (full GQA) the same flag changes nothing at all. Two files reasoned from the flag *name* and both got it backwards. |
| "Cut the context window to free VRAM" | Measure which cache you are cutting. On Gemma, `--ctx-size` scales only the 68 MiB **global** cache; the 765 MiB **sliding-window** cache is `n_seq_max x n_swa + n_ubatch` and ignores it. 8192→4096 frees **38 MiB** and halves your window. Four analyses called it "the biggest single saving, 600–900 MiB". Going the other way, 8192→16384 costs 76 MiB. |
| "The analysis cites a real GitHub issue, so the claim is real" | `docs/archive/2026-08-30-gemma-ling-flash.md` cited a genuine llama.cpp discussion and then asserted "Q8 KV cache kills draft acceptance" — the cited source **recommends** `q8_0` KV. Acting on it would have cost 284 MiB for nothing. Check the claim against the source, not against the bibliography. |
| "28/28 on `just eval`, so the planner is fine" | Two models scored 28/28 and still emitted `action=none` for "copy that to the clipboard" / "close this window" (D16). The fixtures do not cover those rows. The gate that would approve a model swap cannot see the regression it would admit. |
| "Set `reasoning_format: \"none\"` to stop the model thinking" | It does the opposite of what it looks like: thinking is NOT suppressed, the raw `<|channel>thought` text is moved INTO `message.content`. Friday would then write raw model thought into history and audit rows — invariant #7 (FR-26/57). Use `--reasoning off` or `chat_template_kwargs: {"enable_thinking": false}`. |
| "Re-arm the capture when the wake word fires again" | Check it can be REACHED first. `_heard_speech` latches on the first **voiced** frame; openWakeWord only crosses threshold ~0.8 s later, at the END of the phrase. So a second "hey jarvis" during the wait already keeps the capture alive as ordinary speech — a re-arm gated on "nothing heard yet" can never fire, and gating it looser lets a command word that scores high wipe the user's real command. Rejected in ADR-113 rather than built; it is `cancel_reminder`'s shape (ADR-070). |
| "Giving up early is the cheap path" | Only if giving up is actually cheap. ADR-066's bail-out called `on_speech_end` — the ordinary FINISH path — so every false wake ran a full turn on silence: Whisper's cost is flat in audio length (F26), so that was a fixed ~600 ms of FR-5 deafness to produce `""`. The early-exit had a turn bolted to it for months. Route an abandon somewhere that does not transcribe (ADR-113). |
| "The VAD says it's speech, so it's speech" | `webrtcvad` calls 83-100% of frames speech on 5 of 20 real clips, room noise included, so `SpeechGate` never emits `end` and the capture burns the full 15 s cap. That was D3 (Silero since ADR-095). Check what the gate DID, not what the detector returned. |
| "Swap the detector, so swap the frame size with it" | `WAKE_FRAME_MS` frames **openwakeword too**. Moving 20 ms to 32 ms to suit Silero's 512-sample graph would change the wake detector's framing to fix a VAD defect. `SileroVad` buffers internally and holds the last verdict instead: no caller changed (ADR-095). |
| "Fall back to the old library if the new model is missing" | Only if the fallback says so out loud. The `webrtcvad` fallback logs *"does not reliably end captures on this machine (D3)"* and names `just fetch-vad`, because a silent fallback reintroduces the exact defect the swap removed — that is M-A3's shape, where a degradation looked like health. |
| "The canceller reports zero VAD frames, so it cancelled the echo" | Or it deleted the room. WebRTC APM gates: 0 frames when Friday speaks alone, and only 68 of 243 when a human speaks over her. A suppression number cannot tell those apart -- only a preservation test can. |
| "The bench says the new model is useless" | Silero v5+ prepends a 64-sample context, so the graph must see 576 samples, not 512. Fed a bare 512 it returns `p~0.001` on obvious speech, silently, on every frame -- scoring 0/20. The bundled v4 needs no context and worked first try, which made the wrong result look MORE credible. |
| "`sess.get_providers()` says NPU, so it ran on the NPU" | It reports what was REGISTERED. The OpenVINO EP silently partitions unsupported subgraphs back to the CPU. `/sys/devices/pci0000:00/0000:00:0b.0/npu_busy_time_us` moves ~230 ms on a real NPU run and exactly 0 on CPU -- that is the check that can fail. |
| "It compiled and ran on the NPU, so the stage can move there" | Only at the shapes you tried. The speaker model runs at T>=200 frames and **SIGSEGVs at T<=190** -- 1.9 s of audio -- and the CPU fallback that exists to make it safe is the thing that crashes. The NPU needs static shapes; Friday's utterances are not. |
| "The benchmark numbers moved, so the change worked" | Check the power profile first. `power-saver` pins every core to ~2.2 GHz and costs 1.6x on STT. Two external audits measured there and neither noticed; it silently reversed one of their verdicts. `balanced` is the target (ADR-087). |
| "`transcribe(path, \"model-name\")` -- simple API, use it" | It rebuilds the model on every call. Moonshine timed that way looks 3x SLOWER than Whisper; passing the model object makes it 4x faster. Check whether the convenience wrapper is inside your timing loop. |
| "The AEC row printed a number, so the AEC was measured" | `aec.create()` returns `NullAec` on ImportError and only logs it. The first live AEC run printed a "WebRTC APM" row that was a passthrough reading +0.0 dB -- a fake row that looks exactly like a real measurement of a useless canceller. |
| "sounddevice gave me the audio, so the capture is good" | Both callbacks take a `status` argument. Discard it and a dropped input block shifts everything after it, so the reference stops lining up and BOTH cancellers score badly on the same capture -- which reads as canceller instability. |
| "`pgrep -f foo` to find the process, then kill it" | `pgrep -f` matches its OWN command line. Twice on 2026-08-30 a cleanup one-liner killed the shell running it (exit 144). Bracket the pattern: `pgrep -f "[f]oo"`. |
| "`just test-egress` passes, so nothing leaves the machine" | True since ADR-110 (2026-09-02) and **false in every document written before it**. v1 inspected `ss -ltnp` — **listening** sockets, the one category that cannot contain an egress event (D15). v2, shipped by Phase 1 as the *fix*, asserted `urlparse()` on two config constants — it reads three strings and observes no connection, and would not have caught D13 either, because `huggingface.co` is not in a config constant. v3 guards `socket.getaddrinfo`/`socket.socket.connect` and was proven by removing `local_files_only=True` and watching it name `huggingface.co`. Twice this check was declared fixed while still blind; check what it observes, not what it is named. |
| "RAM and CPU look normal, so no local model is running" | Wrong meter. A GPU-resident model lives in **VRAM**: 4712 MiB held, 519 MB RSS, 0 % GPU between turns, 6 min CPU over 2 days. Idle is what correct looks like. `nvidia-smi --query-compute-apps` is the meter. |
| "The ADR says the wake word is paused during dictation" | ADR-058 decided it; `grep -rn is_dictating` returns two hits, one of which is the property itself. Nothing tells the detector. Third time an ADR was mistaken for an implementation (see `cancel_reminder`/ADR-070 and both Hyprland tools/ADR-074) — D14. |
| "Only poll the wake detector when we need it" | openWakeWord is a STREAMING model. Starving it leaves stale features and a stale score, and it re-fires the instant you resume — that was OQ-29. Feed it every frame; ignore the result instead. |
| "Speech during playback means the user is interrupting" | On this hardware the AEC gives −5 to −10 dB, so it is usually Friday. Voice barge-in is off (ADR-064); PTT is the interrupt until OQ-32 lands. |
| "The two UIs do the same thing, they just have their own copy of it" | That copy is the bug. The TUI's confirm was never migrated to `PendingAction` and crashed on every G12 action for months (C1). One `turn.resolve_pending`, both callers. |
| "The audit says the cause is X, so fix X" | M-T2's stated mechanism does not reproduce here at all; the leak arrives by a different door. Reproduce the defect before fixing it, or you ship ceremony. |
| "The function has an ordering bug, fix the ordering" | First check anything can reach it. `cancel_reminder`'s branch was unreachable — the validator required an id the planner cannot know — so it had never worked at all (ADR-070). |
| "The confirm is armed, so the user was asked" | Only if the question was actually spoken. Arming before delivery meant a TTS failure left a `system_wifi{off}` pending with no timer, and an unrelated "yeah" dispatched it (ADR-069). |
| "It's just a `notify-send`, it's fast" | It is `subprocess.run(timeout=2)` on the single event loop, in the path that fires while a turn is already running. While the loop blocks, Friday is deaf (H6). |
| "`FRIDAY_DEBUG` only echoes to the console, so nothing hits disk" | Under systemd the console IS journald, and journald persists to `/var/log/journal`. The `no_disk` filter guarded the file handler only, so the workflow built to watch a session wrote every transcript to disk (H8). Name the *sinks that outlive the process*, not the handlers. |
| "The stream object is open, so the mic is being listened to" | sounddevice answers an escaping callback exception by printing it and never calling back again. Open stream, `audio_devices` PASS, wake and VAD dead (M-A1). Both callbacks run through `CallbackGuard` now; if you add a third, use it. |
| "The log shows nothing happened, so nothing happened" | Only if the path is instrumented. Seven turn types — DND hush/resume, dictation start/stop/typing, sign-off, and **the confirm dispatch itself** — completed writing no audit row, no `action=` line and no TTFA. "Be quiet for a while does nothing" was diagnosed straight off that gap; DND had worked correctly the whole time (D23, ADR-091). An instrument with a blind spot produces a confident wrong diagnosis. |
| "The timeout fired, so the tool is missing or hung" | `subprocess.run(timeout=)` kills with SIGKILL. ydotool types at a measured 40.2 ms/char, so a 3 s constant capped dictation at **74 characters** and killed the process between a key down and its key up — `ydotoold` owns the uinput device, so the key auto-repeated for ever. The log then blamed a missing binary while ydotool was installed and running. Size a timeout from the work, and name the failure mode you actually hit (D22, ADR-092). |
| "D1 is fixed, so spoken confirms work" | D1 fixed how an answer is PUNCTUATED. "Yes, I am sure" — the most natural reply to "Are you sure?" — still matched nothing, because `is_affirmation` compared whole strings. Two more `declined` rows on `system_wifi{off}` before anyone noticed (D25, ADR-093). Match the head, and veto on any negative word: this gate approves destructive actions, so ambiguity must resolve to NOT acting. |
| "Chat said it can't do that, so it can't" | `system_wifi` was missing from `CHAT_SYSTEM`'s toolset from G12 until 2026-08-30, so Friday truthfully reported a limit that did not exist — while a `system_wifi` confirm was armed in the same session. The model was reading a prompt that was wrong. Diff the persona against `PARAM_SCHEMA`; there is a test for it now (D24, ADR-094). |
| "The word is in the hotwords, so Whisper will hear it" | *"LibreWolf"* and *"Zen Browser"* were both in `STT_HOTWORDS` and came back as `wolf_studio` and `jin_browser` — **the same session the hotwords were added** (D32). A hotword biases decoding toward a token sequence; it does not repair one the acoustic model split in the wrong place, and a two-word name gives it a wrong place to split. Single-word app names landed 4/4 in that session, two-word 0/2. |
| "Half the turns failed, so the fix did not work" | Read the journal before concluding. **`E_TOOL_NOTFOUND` names the id the enum rejected**, so five `action=none` turns resolved into two distinct causes in ten seconds — `wolf_studio` and `jin_browser`, i.e. STT, not the planner. The planner half was 4 for 4 in the same session. **A fail-closed path that logs WHAT it rejected turns a session of bisecting into a grep.** |
| "The processes are alive, I checked with pgrep" | `pgrep -f "[f]irefox"` reported firefox, obsidian, kitty and vlc all running when only Discord was. The bracket trick defeats `pgrep`'s self-match, but the pattern sat inside a `bash -c` string, so the **wrapper** process carried the literal text and matched it. **Second-order version of a trap already in this table.** Match a full binary path with `ps -eo pid,lstart,cmd \| grep -F` from a script FILE, and read the start times — a process that started before your launch is not evidence of your launch. |
| "The evidence is ambiguous, so pick the likelier reading" | Four apps launched `ok` and were gone eight minutes later; a fifth was still up. Either the owner closed four test launches, or a launch outlives the 400 ms grace and dies after it — **a new defect**. The rows cannot separate them and **one sentence to the owner can.** ADR-114 is what happens when you pick: a real, proven mechanism, shipped as the wrong cause. |
| "Hotwords are for app names" | They are for every word that selects an action. `wifi` came back as **wife / weapon / way / life** on four consecutive turns because `STT_HOTWORDS` stopped at Phase 1 (D26). Third Phase-1 artifact found in two days, after the eval fixtures and the chat persona. **Anything enumerating what Friday can do that predates G12 is suspect.** |
| "The model is slow, that is why the assistant feels slow" | Measured n=38: the planner regression from the Gemma swap was **117 ms**, while chat took **7-10 s**. TTFA includes synthesizing the WHOLE reply before the first sound, so a 376-character answer IS the latency. Capping the reply at 2 sentences took chat p50 from 7177 to 4715 ms without touching the model (ADR-094). |
| "28/28 on the gate, so the planner is fine" | The gate is only as wide as its fixtures. All 28 exercised Phase-1 actions; **20 of the 28 actions in `PARAM_SCHEMA` had no fixture at all**. Widening it to 50 immediately found three live defects in a model that had scored 28/28 for months. FR-97 now has a test: a new action ships with a fixture. |
| "The incumbent passes this fixture, so the incumbent is right" | E29 asserted that "copy that to the clipboard" must dispatch. The incumbent "passed" by emitting `clipboard_set{text:"that"}` — **overwriting the user's clipboard with the literal pronoun** while speaking success. The challenger "failed" by refusing, which was correct. A fixture encodes a belief; check the belief before scoring a model against it. |
| "It's a reasoning model, so set `--reasoning-format none`" | It does NOT suppress thinking — it moves raw thought INTO `message.content`, straight into history and audit rows (invariant #7). Use `--reasoning off`. `tests/test_model_config.py` now fails if either config carries the wrong one. |
| "History is in the prompt, so anaphora just works" | It also lets Friday's own suggestion become her own command — a bare "hey jarvis" dispatched `open_app{editor}` 4/4. Plan without history first; confirm anything only history could supply (ADR-065). |
| "The panic switch is engaged, so nothing can run" | `config.is_disabled()` is consulted in **one** place, `executor.execute`. Ten side-effecting paths bypass it: web_search, clipboard read AND write, dictation typing, preference write and forget, reminder create and cancel, note create, notify-send. Friday says "I'm switched off." to an `open_app` and types into your editor in the same breath (F1). A kill switch that kills some things is worse than none, because it is trusted. |
| "`just selftest` says 8/8, so the system is healthy" | 8/8 is a count of checks that **ran**. `run_selftest` sets `has_fail` only on FAIL, and **WARN prints `[PASSED]`** — WARN is what you get when the panic switch is engaged, when there is no microphone, when llama-server is not running, and when socket binds cannot be audited (F20). `gpu_arch`'s own defect, living inside the tool built to catch it. |
| "The persona was fixed last time, so it is right now" | D24 fixed `CHAT_SYSTEM` for `system_wifi`. One commit after ADR-097 widened the app enum 5 → 162, chat was again saying *"I cannot open Discord as it is not in my toolset"* while `open_app{discord}` worked (F2). The D24 coverage test checks action NAMES; the app enum is a parameter VALUE set. And `tests/test_prompt.py:73` asserts `"five apps" in low` — **a test now pins the lie in place.** |
| "Chunk the audio so STT gets faster" | Whisper pads every input to a **30-second window**. Measured in `balanced`: 1.0 s of audio costs 556 ms, 5.0 s costs 688 ms. Transcribing a 1-second tail costs what the whole utterance costs, and `faster_whisper 1.2.1` has no streaming API (F26). This killed a 1.5 s latency target that had already been committed to, in writing, off an unmeasured assumption. |
| "The launch returned quickly, so there is no latency there" | `_LAUNCH_GRACE_S = 0.4`, and a GUI app never exits, so the `wait_for` **always** runs the full grace. Measured: detached launch 402 ms, command 2 ms (F29). Launches and commands are different latency classes and every budget written before 2026-09-02 conflated them. |
| "Read the governor to check the power profile" | `scaling_governor` reads `powersave` and `scaling_max_freq` reads `5400` in **all three profiles**. Only `powerprofilesctl get`, `/sys/firmware/acpi/platform_profile`, or `scaling_cur_freq` sampled UNDER LOAD tell them apart (F28). A profile check written the obvious way can never fail — write the FAIL-path test. |
| "I added fixtures and the eval gate is green" | Regressions are `prev.get(fid) and not passed`. A **newly added** fixture has no baseline entry, so a failing new fixture is **never** a regression (F23). The "≥90%" gate the harness docstring promises exists nowhere in code — `main()` returns 1 only on regressions. Re-baseline after adding, and read the rate, not the exit code. |
| "The unit file on disk is the one systemd is running" | The installed unit was a **symlink to the repo file**, so `diff` said IDENTICAL — while `systemctl show` reported `Type=simple`, `WatchdogUSec=0`, `NeedDaemonReload=yes`. Nobody had run `daemon-reload`, so `Type=notify` + `WatchdogSec=10s` had been committed, documented and **never once executed**. Editing a unit is not deploying it. Ask `systemctl show`, and prove a watchdog by leaving it running and reading `NRestarts`. |
| "The fix is committed, so the fix is running" | The live daemon had started at `15:32:40`; every Phase 1/2 source file had an mtime of `18:44`–`18:49`. Two whole phases of fixes existed only on disk. `ps -o lstart=` against the file mtimes is one command and it answers this. |
| "pytest segfaulted, so bisect the tests" | `coredumpctl info -1` gave the culprit in one command after ~40 minutes of subset runs had given a contradictory answer. And the crash was **~90%, not 100%**: the first delta-debugger took one clean run as proof and discarded the whole set. Three different signals (SIGILL/SIGSEGV/SIGABRT) mean memory corruption — read the core, and if you must bisect a flaky crash, repeat every trial. |
| "The test tears down what it built, it calls `close()`" | `Daemon.close()` did not close the recorder — `run()`'s `finally` did, on the next line. A test that built a **real** `Recorder` and called only `close()` left a live PortAudio stream, whose CFFI callback then fired after interpreter teardown and killed the suite at session finish (ADR-111). Teardown split across two functions is teardown that one caller will miss. |
| "It is a local model, so nothing leaves the machine" | The live daemon held two ESTAB sockets to `*.events.data.microsoft.com` — **`import onnxruntime` phones home to Microsoft telemetry, on import, on Linux** (ADR-112). Five components route through ORT, so every daemon start did it. `onnxruntime.disable_telemetry_events()` does NOT stop it; only `ORT_DISABLE_TELEMETRY=1`, set before the library loads, does. Rule 7 checks a dependency's *footprint*; it never asked what one talks to. |
| "I checked and it was clean" | Once, at 12 seconds. The ORT telemetry socket takes **15-45 s** to appear, so three single-sample controls all read clean and produced a confident wrong cause (that importing `friday` was required — it is not). A single sample is not an observation of an intermittent thing. Sample until your window is longer than the phenomenon (ADR-112). |
| "It is opt-in, so it does not need a confirm" | `clipboard_read` is gated because reading it aloud can voice a password. A screenshot leaks strictly more, and a misheard "look at my screen" would photograph it and describe it out loud. Opt-in is not a gate; a mishear is exactly what a gate is for (ADR-104). |
| "One UI does this, so both do" | C1 was the TUI's confirm handler. One layer over, in the same file, `set_dnd` and `dictation_mode` still speak success and change nothing in text mode — the TUI has no `DndManager` and no `DictationManager`, and the **daemon** applies the state (F27). When you find a defect in one caller, grep the other one before you close it. |
| "The summary is distilled, so no transcript reaches disk" | `distill_dialogue` sends the RAW dialogue to the model and writes the result to `session_summaries`. The only thing stopping verbatim quotes is a sentence in `DISTILL_SYSTEM` saying not to (F22). Invariant #7 is enforced on that path by the exact mechanism ADR-008 rejects for injection defence. |
| "`argv[0]` is not on the denylist, so the command is safe" | Measured: `env python3 /tmp/x.py`, `flatpak run …`, `distrobox-enter … -- bash` and bare `python3` all PASS `assert_not_banned` (F5). Only `argv[0]` is inspected, and `env`/`flatpak`/`distrobox-enter` each execute an arbitrary following command. `~/.local/share/applications` is user-writable and already holds an `env`-prefixed entry. Resolve the EFFECTIVE binary through wrapper prefixes first. |
| "The docs say that area is fixed, so start somewhere else" | The 2026-09-02 audit was told to ignore the docs and read the code cold. It found three defects the docs would have talked it out of — F2, F3 and F21 — because a doc records the FIX and not the REGRESSION. Read the code first; read the docs to write them up. |
| "The number is close enough to write down" | v1 of that audit published "6 of 20" (it was 7, and one value was lost in sorting), "8 paths" (10), "700 ms" (816), and a 1.5 s target derived from an STT assumption a five-minute measurement disproved. Measure, THEN write the number down — and when you re-check, re-check your own work first. |
| "The suite is green, so the invariant holds" | Measured 2026-09-03, before the fix: three of the five confirm gates could have their branch DELETED from `turn.py` with all **581 tests still passing** — `system_wifi{off}` dispatched and dropped the network, `hypr_window{close}` closed the window, neither asked (M1) — and `assert_not_banned(argv)` could be removed from the executor with the adversarial and injection suites green (M2). Invariant #10 was enforced by code nothing was watching. **Fixed the same day (ADR-117), and the point survives the fix:** break the line and see if anything turns red. That is the only version of this question with an answer, and it is now line six of the definition of done. |
| "Both modules have good tests, so the feature is tested" | That is exactly how M2 survived. `assert_not_banned` was thoroughly unit-tested. `executor.execute` was thoroughly unit-tested. **Nothing crossed between them**, so the one line joining them could be deleted silently. **Closed 2026-09-03** — `tests/test_executor.py::test_banned_argv_is_denied_at_dispatch` (ADR-117). When two well-tested modules meet, ask what tests the EDGE — the suite tested functions, not wiring, and that single sentence explains every hole the mutation audit found. |
| "The test feeds the dangerous input, so the rule is covered" | `test_hard_ban_rejects_dangerous_commands` feeds `["rm","-rf","/"]` — and that argv is caught by the `"rm -"` SUBSTRING rule as well as the binary denylist, so two rules fire and the assertion cannot tell which. Dropping `"rm"` from `BANNED_BINARIES` left the suite green while `rm /home/bittusah/notes.db` sailed through (M3). **Closed 2026-09-03** — the same test now also feeds `["rm","/home/bittusah/notes.db"]` and `["dd","of=/dev/nvme0n1"]`, which no substring rule touches (ADR-117). **A denylist entry needs an argv only that rule rejects.** A test that passes through two rules proves one of them at most. |
| "The fix landed, so that defect is dead" | F23 and F20 were both genuinely fixed in code and **both fixes were pinned by nothing**. F23's `unbaselined_fails` branch worked and all four eval-gate mutations still survived, so `just eval` could be made to always exit 0 (M6). F20's fix was half-tested: `has_warn = True -> False` was KILLED, `has_fail = True -> False` **SURVIVED** (M7) — the FAIL path had existed since G9 and only the recent OQ-62 half had a test. **Both closed 2026-09-03 (last).** A fix without a FAIL-path test has a countdown on it, and the gates that guard the gates are the worst place to leave one. |
| "The function is tested, so the gate is tested" | `_report` and `run_selftest` are each the last function before an exit code, and **neither had ever been called by a test** — every test one layer down drove an individual check or an individual fixture. `just eval` and `just selftest` are the two commands this project trusts when it trusts everything else, and both could be made to always exit 0. Test the thing that returns the verdict, not only the things it reads. |
| "The test is named after the thing, so it tests the thing" | `test_speaker_verifier_mock` constructed a `SpeakerVerifier` and **never called it** — the local was assigned and unused, and its assertions ran `cosine_similarity()`, which the test twenty lines above already covered. `grep -rn "\.verify(" tests/` returned nothing: the entire G13 accept/reject decision was executed by no test, and both mutations of its return statement survived (M5). Coverage would still have credited the import. **Closed 2026-09-03** — that test is DELETED and replaced by `test_verify_accepts_the_owner_and_rejects_an_impostor`, which calls `verify()` in both directions (ADR-117). |
| "A mutation survived, so that is a defect" | Four of the five surviving constants are CORRECT to leave free: the logic consuming `VAD_END_SILENCE_S`, `RETENTION_DAYS` and the wake threshold/refractory is fully tested — every wake-gating, VAD and retention mutation was killed — so only the default floats, and pinning a tuning knob converts every future tuning run into a test edit. `MAX_CAPTURE_S` is the exception because **FR-4 calls it a hard cap**. Ask what the constant is FOR before freezing it (ADR-116a). |
| "The unit test reads the service file, so the unit is verified" | It verifies the FILE. The installed unit is a **symlink** to that file, so it always matches — which is why `tests/test_service_unit.py` would have passed throughout the weeks when `systemctl show` said `Type=simple`, `WatchdogUSec=0`, `NeedDaemonReload=yes` and the watchdog had never fired (M16). Of 79 test files, only `test_egress.py` shells out to the live system. Deployment is a live question; ask `systemctl`. **Answered 2026-09-03 (OQ-66 = c, ADR-117): the live question went to `friday/selftest.py::check_unit_deployed`, not into the suite** — `selftest` is the tool built for live questions and the 6.7 s suite stays hermetic. The file test still exists and still only proves the file. |
| "`git checkout -- <file>` puts the mutation back" | Only on a file with **no uncommitted work in it.** Reverting an M6-style mutation that way took an uncommitted hotword change with it, and the next full-suite run failed a test that had passed standalone sixty seconds earlier — which reads exactly like test pollution and is not. Copy the file aside and copy it back, or commit before you mutate (ADR-116, amended). |
| "The ADR found three frozen sites, so there were three" | ADR-097 widened the app enum and named "three sites frozen at Phase 1". **There were five** — the planner prompt and `STT_HOTWORDS` were both still naming the same five apps, and either one alone stops a scanned app ever launching. A month of `action_audit` proves none did (D31). **An enumeration in an ADR is what the author found, not what exists.** Widening a capability means widening every list that names it: the enum, the prompt, the hotwords, the eval fixtures, the chat persona. |
| "The registry is generated now, so the coupling is handled" | ADR-042 wrote down in 2026-08-26 that *"the hotwords list is coupled to the registry — a new app must be added there too"*. ADR-097 then replaced the registry with a generated enum and did not touch the hotwords. **A coupling recorded in prose is not a coupling anything enforces** — it is a note that predicts the defect and does not prevent it. `tests/test_stt_hotwords.py` exists because of this. |
| "Write the count down, it is a fact" | `162 app ids` was true on 2026-09-02 and is **165** today, because ADR-097 generates the enum from the machine's XDG desktop entries — it moves whenever an application is installed. Nothing broke; three doc sites were just wrong on a schedule (M19). **Do not pin a generated number in prose.** State the shape, and date the observation. |
