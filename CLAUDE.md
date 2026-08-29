# CLAUDE.md — Working agreement for this repository

Read this before touching anything. It is short on purpose.

## What this is

Friday: a local-first voice and text assistant for one Arch Linux +
Hyprland machine. It can launch a small fixed set of applications,
remember preferences, and search the web through a local proxy.

**Status: G0–G13 done — Phase 1 (G0–G9) + Phase 2 (G10–G13) COMPLETE, then five
review passes. The fifth (the 2026-08-26 full-codebase audit) is FULLY FIXED:
all 12 steps executed 2026-08-29, plus ADR-073 and ADR-074, which came out of
Step 9's real-path run and were not in the audit at all. The TYPED half of
`docs/reality-check.md` is verified; the live-VOICE half is the next session's
whole job.** `friday/` is a real text+voice assistant
that launches apps, remembers preferences, hears you (toggle PTT **and**
`hey_jarvis` wake word, ADR-044/055; TTFA p50 2.16s/p95 2.73s), searches the web
(G7: SearXNG loopback, sanitizer, `final.gbnf` grounding, injection 20/20,
egress proof; ADR-045/046/047), converses naturally (G8: two-stage chat,
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
`uv run pytest` **450 passed**, `just eval` **28/28 reg 0**, `just test-injection`
**20/20 blocked**, `just selftest` **8/8**, `just test-no-fstring-sql` **OK**,
`just test-egress` loopback-only. (Verified 2026-08-29 with the LLM confirmed on
GPU — see `llm_on_gpu`.)

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

**NEXT SESSION: the LIVE-VOICE PASS (`docs/reality-check.md`), not more fixing.**
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
just selftest      # MUST be 8/8. If llm_on_gpu FAILS: systemctl --user restart friday-llm
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
refuse. **Typed rows: verified 2026-08-29** against the real app, real LLM, real
SQLite and real `wl-copy`/`nmcli` — the five confirm paths (C1's blast radius),
`cancel_reminder`'s first ever successful run (ADR-070), `clipboard_read`'s
disclosure gate (ADR-068a), `clipboard_set` really copying, and the audit
contract observed on real rows. Wake, VAD end-of-speech and "voice barge must
not fire" are ticked live from 2026-08-25. **Everything else in the live-voice
half is still the main work**, plus two deliberate hold-outs: `hypr_window`
(acts on the focused window) and `system_wifi{off}`'s affirm (drops the
network). Per defect #4, verify by asking the system, never by what Friday
says.

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
   friday.md          the build plan, gate by gate, with commands (all gates
                      complete — a record of sequencing, not a to-do list)
   spec.md            requirements with IDs and acceptance tests
   architecture.md    modules, interfaces, concurrency, deployment
   adr.md             decisions + why + what they cost.  74 ADRs.
   threat-model.md    threats, controls, and which file enforces each
   open-questions.md  what is undecided and what it blocks (+ ## Closed, which
                      keeps the reasoning behind every answered question)
   tech-stack.md      the pinned versions and what each piece is for
   Alpha-ox-analysis.md
                      the 2026-08-26 audit.  A SNAPSHOT: its line numbers are
                      stale and some point into deleted code.  Read its
                      fix-status table (bottom), not its line numbers.
   diagrams/          ASCII.  02 (injection trust boundary) and 04 (zones +
                      privilege ladder) are the important ones.
   docs/aec-probe.md  the OQ-32 measurement harness (runnable)
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

`gemini-thoughts.md` and `gpt-thoughts.md` ARE archived inputs and contain wrong
technical claims (see ADR-021, ADR-003, ADR-022). **Do not cite them as
current.** (Before 2026-08-29 this paragraph lumped `friday.md` in with them,
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
```

A diagram that disagrees with the code is a bug in the diagram.

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
is no `setup` or `bench`; environment bootstrap is `uv sync` + `just fetch-voice`
+ the llama.cpp build in ADR-021).

```bash
just serve              # start llama-server (or: systemctl --user start friday-llm)
just run                # orchestrator, text mode
just voice              # voice-in daemon (PTT + wake); --dry-run / --no-voice / --no-wake
just eval               # eval fixtures -> pass count (currently 28)
just test               # full unit + adversarial + injection suite (pytest -q)
just test-injection     # G7 hostile-result suite, 20/20 must block
just test-no-fstring-sql# assert store/ SQL is strictly parameterized
just selftest           # health: servers, gpu arch, LLM-actually-on-GPU, db perms, audio, binds (8 checks)
just wake-bench         # G10 live wake-word / VAD benchmark. Reports peak input
                        # level and max score, so "0 hits" can be told apart
                        # from a dead microphone. --duration N, --threshold X
just enroll-voice       # G13 interactive 10-utterance voiceprint enrollment
just ptt press|release  # send a PTT command to the running daemon
just prefs list|forget  # manage stored preferences
```

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
| "A green test suite proves the feature works" | Seven times now, tests passed while the real path was broken (G13 enroll, `clipboard_set`, `file_open`, the CPU-only LLM, 328 green tests over a text UI whose every action confirm crashed, and **both Hyprland tools, whose argv test asserted exactly the string the compositor rejected**). Exercise the actual path; see `docs/reality-check.md`. |
| "The health check is green, so the system is healthy" | `gpu_arch` passed through an entire GPU outage — it asked "does a GPU exist", not "is the LLM using it". A check that cannot fail is worthless; write the FAIL-path test. |
| "I grepped the config, it isn't there" | Grepping a config is not asking the system. The PTT bind was "missing" by `grep` and plainly present in `hyprctl binds` (it routes via Lua). Ask the running system. |
| "The prompt says the values are `up`/`down`, so they are" | A prompt is not a control (ADR-008) — that is the same reasoning that rejects prompt-based injection defence. Closed sets belong in `PARAM_SCHEMA` as enums, enforced by the validator. |
| "Put the search results in the planning turn, one round-trip" | T1. This is the exact attack the design prevents. |
| "A sibling call site uses the same broken thing, but the ticket didn't mention it" | `registry.py` recorded in a comment that Hyprland 0.56 broke `hyprctl dispatch` — and `hypr_workspace`/`hypr_window`, which use the same form, were left broken and announcing success (ADR-074). Knowing a breakage and not grepping for its siblings is how it survives. |
| "The argv test passes, so the tool works" | `test_hypr_tools_argv` asserted `["hyprctl","dispatch","workspace","3"]` for months. That argv is exactly what the code built and exactly what the compositor rejected. A test that asserts the argv the code builds proves only that the code builds it. |
| "Escape the value into the command string carefully" | Don't build the string. `_LUA_DISPATCH` maps a closed param to one of sixteen import-time constants, so there is no interpolation to escape (ADR-074, stricter than ADR-027 because a workspace is one of ten values and a search query is not). |
| "The last session's block says that was already fixed" | It says `just enroll` was corrected in the docstrings; it corrected one file and missed `daemon.py`, in the one warning that fires when speaker verification is failing OPEN. A find-and-replace reported as done. Diff the claim against the tree — `just --list`, `grep`, run it — before believing it. |
| "The launch returned ok, so the app opened" | It did not. The spawn is fire-and-forget (ADR-043) and reports the *spawn*, not the app. Brave died on a missing `DISPLAY` for the entire project while Friday said "Opened Brave." Ask the system: `pgrep -a brave`, `hyprctl clients`. |
| "Only poll the wake detector when we need it" | openWakeWord is a STREAMING model. Starving it leaves stale features and a stale score, and it re-fires the instant you resume — that was OQ-29. Feed it every frame; ignore the result instead. |
| "Speech during playback means the user is interrupting" | On this hardware the AEC gives −5 to −10 dB, so it is usually Friday. Voice barge-in is off (ADR-064); PTT is the interrupt until OQ-32 lands. |
| "The two UIs do the same thing, they just have their own copy of it" | That copy is the bug. The TUI's confirm was never migrated to `PendingAction` and crashed on every G12 action for months (C1). One `turn.resolve_pending`, both callers. |
| "The audit says the cause is X, so fix X" | M-T2's stated mechanism does not reproduce here at all; the leak arrives by a different door. Reproduce the defect before fixing it, or you ship ceremony. |
| "The function has an ordering bug, fix the ordering" | First check anything can reach it. `cancel_reminder`'s branch was unreachable — the validator required an id the planner cannot know — so it had never worked at all (ADR-070). |
| "The confirm is armed, so the user was asked" | Only if the question was actually spoken. Arming before delivery meant a TTS failure left a `system_wifi{off}` pending with no timer, and an unrelated "yeah" dispatched it (ADR-069). |
| "It's just a `notify-send`, it's fast" | It is `subprocess.run(timeout=2)` on the single event loop, in the path that fires while a turn is already running. While the loop blocks, Friday is deaf (H6). |
| "`FRIDAY_DEBUG` only echoes to the console, so nothing hits disk" | Under systemd the console IS journald, and journald persists to `/var/log/journal`. The `no_disk` filter guarded the file handler only, so the workflow built to watch a session wrote every transcript to disk (H8). Name the *sinks that outlive the process*, not the handlers. |
| "The stream object is open, so the mic is being listened to" | sounddevice answers an escaping callback exception by printing it and never calling back again. Open stream, `audio_devices` PASS, wake and VAD dead (M-A1). Both callbacks run through `CallbackGuard` now; if you add a third, use it. |
| "History is in the prompt, so anaphora just works" | It also lets Friday's own suggestion become her own command — a bare "hey jarvis" dispatched `open_app{editor}` 4/4. Plan without history first; confirm anything only history could supply (ADR-065). |
