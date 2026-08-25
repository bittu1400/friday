# CLAUDE.md — Working agreement for this repository

Read this before touching anything. It is short on purpose.

## What this is

Friday: a local-first voice and text assistant for one Arch Linux +
Hyprland machine. It can launch a small fixed set of applications,
remember preferences, and search the web through a local proxy.

**Status: G0–G13 done — Phase 1 (G0–G9) + Phase 2 (G10–G13) COMPLETE, then two
review passes (2026-08-24 desk review, 2026-08-25 first LIVE reality check +
full-codebase audit)** that fixed real defects the build suite missed. `friday/` is a real text+voice assistant that launches apps,
remembers preferences, hears you (toggle PTT **and** `hey_jarvis` wake word,
ADR-044/055; TTFA p50 2.16s/p95 2.73s), searches the web (G7: SearXNG loopback,
sanitizer, `final.gbnf` grounding, injection 20/20, egress proof; ADR-045/046/047),
converses naturally (G8: two-stage chat, `CHAT_SYSTEM`, RAM `Dialogue`, ADR-048),
personalizes from mined habits (`friday/store/habits.py`, ADR-049), keeps
cross-session memory (`friday/store/summarizer.py`, ADR-050), runs as hardened
background user services (G9: `deploy/systemd/`, `friday/selftest.py`, ADR-051),
and in **Phase 2** adds hands-free wake + AEC + VAD + barge-in (G10, ADR-055/060/061/062),
a proactive scheduler with SQLite reminders/timers, conversational DND, and
briefings (G11, ADR-056), an action surface — system volume/brightness/media/wifi,
Hyprland workspace/window, notes, clipboard, dictation, all behind a permanent
destructive-command ban + three-tier confirm (G12, ADR-057/058), and CPU speaker
verification with a 10-utterance voiceprint (G13, ADR-059).
`uv run pytest` **321 passed**, `just eval` **28/28 reg 0** (9.9 s on GPU), `just test-injection`
**20/20 blocked**, `just selftest` **8/8**, `just test-no-fstring-sql` **OK**, `just test-egress` loopback-only.
(Verified 2026-08-25 with the LLM confirmed on GPU — see `llm_on_gpu`.)

**Three review sessions found defects the desk suite missed** — the pattern here
is that green tests do NOT prove a feature works, because the tests never
exercised the broken path. (1) A post-G9 live review (2026-08-23) fixed 5:
invariant-#1 `assert`→`raise` (survives `python -O`), systemd `Restart=always`,
the browser-launch false-failure (ADR-043 amendment), planner sees history for
anaphora (ADR-052), chat persona states its real toolset (ADR-053). (2) A
post-Phase-2 review (2026-08-24) fixed 8 more, including a **dead-on-import G13
enrollment tool** (speaker verify silently failed open) and a **`clipboard_set`
that spoke success while doing nothing**. The full, current truth is the two
**"SESSION 2026-08-24 (part 2)"** and **"SESSION 2026-08-23"** blocks at the top
of `progress.md`, plus the `>>> START HERE <<<` block written 2026-08-25.
NOTE: `friday.service` is `Restart=always`, so `kill <pid>` does NOT stop the
daemon — use `systemctl --user stop friday`. As of 2026-08-25 all three units
(`friday`, `friday-llm`, `friday-searxng`) are **running**, 0 restarts. Never
run `just voice` while the service is up: two daemons fight over the mic and the
PTT socket. Stop the service first.

**NEXT SESSION: read the `>>> START HERE <<<` block at the top of
`progress.md` first.** It has the exact first four commands, the one open bug,
and the ordered task list. Short version:

```bash
just selftest      # MUST be 8/8. If llm_on_gpu FAILS: systemctl --user restart friday-llm
```

A **2026-08-25 session** ran the first live reality check, then a full-codebase
audit, then a post-Arch-upgrade sweep. It found **8 defects**, 7 fixed:
`file_open` opened the wrong file; `friday.service` had been crash-looping
`226/NAMESPACE` (missing `RuntimeDirectory`); every G12 control param was
declared free `text` instead of a closed enum, so off-vocabulary values reached
the registry; three builders then *guessed* — **brightness "brighten" actually
dimmed the screen** — while speaking the outcome the user asked for; `FRIDAY_DEBUG`
wrote raw transcripts to disk (invariant #7); a rejected PTT/wake trigger
desynced tap-toggle silently; and **llama-server had been serving from CPU for
hours** after losing a boot race with the NVIDIA driver — 22x slower, `/health`
still "ok", and `gpu_arch` reported PASS the whole time. The one open bug is the
**15-second empty-capture loop (OQ-29)**, which needs the user at a mic.

Three lessons that block repeats, all earned this session:
- **A check that cannot fail is worthless.** `gpu_arch` asked "does a GPU
  exist", never "is the LLM using it". New checks need a test for the FAIL path.
- **Grepping a config is not asking the system.** "The PTT key is not bound" was
  a false positive from `grep`; `hyprctl binds` showed it bound all along.
- **Degradation is silent and it moves the numbers.** Any latency measured
  without confirming `llm_on_gpu` first is untrustworthy.

`docs/reality-check.md` remains the manifest of what Friday must do and must
refuse. Its text-mode rows are verified; **every live-voice row is still
unticked** — that is the next session's main work.

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
   progress.md        what is ACTUALLY done.  start here, always.
   friday.md          the build plan, gate by gate, with commands
   spec.md            requirements with IDs and acceptance tests
   architecture.md    modules, interfaces, concurrency, deployment
   adr.md             decisions + why + what they cost
   threat-model.md    threats, controls, and which file enforces each
   open-questions.md  what is undecided and what it blocks
   diagrams/          ASCII.  02 (trust boundary) is the important one.
   docs/archive/      friday-v4.md and the AI reviews.  HISTORICAL ONLY.

   laptop-specifications.md   local only, GITIGNORED (ADR-024 — it
                      contains MAC addresses and hardware serials).
                      Never commit it, never quote its identifiers into
                      a tracked file.
```

`friday.md`, `gemini-thoughts.md`, and `gpt-thoughts.md` are archived
inputs. They contain at least one wrong technical claim each (see
ADR-021, ADR-003, ADR-022). **Do not cite them as current.**

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
just wake-bench         # G10 live wake-word / VAD benchmark
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
| "A green test suite proves the feature works" | Four times now, tests passed while the real path was broken (G13 enroll, `clipboard_set`, `file_open`, the CPU-only LLM). Exercise the actual path; see `docs/reality-check.md`. |
| "The health check is green, so the system is healthy" | `gpu_arch` passed through an entire GPU outage — it asked "does a GPU exist", not "is the LLM using it". A check that cannot fail is worthless; write the FAIL-path test. |
| "I grepped the config, it isn't there" | Grepping a config is not asking the system. The PTT bind was "missing" by `grep` and plainly present in `hyprctl binds` (it routes via Lua). Ask the running system. |
| "The prompt says the values are `up`/`down`, so they are" | A prompt is not a control (ADR-008) — that is the same reasoning that rejects prompt-based injection defence. Closed sets belong in `PARAM_SCHEMA` as enums, enforced by the validator. |
| "Put the search results in the planning turn, one round-trip" | T1. This is the exact attack the design prevents. |
