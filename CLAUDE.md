# CLAUDE.md — Working agreement for this repository

Read this before touching anything. It is short on purpose.

## What this is

Friday: a local-first voice and text assistant for one Arch Linux +
Hyprland machine. It can launch a small fixed set of applications,
remember preferences, and search the web through a local proxy.

**Status: G0–G7 done** (2026-08-23, G7 merged to main). `friday/` is a real
text+voice assistant that launches apps, remembers preferences, hears you
(toggle PTT, ADR-044; spoken eval 20/20, TTFA p50 2.16s/p95 2.73s), and
searches the web (G7: SearXNG loopback, sanitizer, `final.gbnf` grounding,
injection 20/20, egress proof; ADR-045/046/047). `just eval` 24/24, `uv run
pytest` 176 passed.
**PRIMARY GOAL: conversation** (chit-chat + suggestions) — gate **G8**, build
order **G7 (search) ✓ → G8 (conversation) → G9 (service)**. Design:
`docs/superpowers/specs/2026-08-23-conversational-chat-design.md`; **G8 Build 1
plan WRITTEN** (`docs/superpowers/plans/2026-08-23-g8-conversation-build1.md`,
10 TDD tasks) — next step is to EXECUTE it. `progress.md` is the only file that
says what is actually true — start there.

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
   friday.md  the build plan, gate by gate, with commands
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

   10. No irreversible tools in Phase 1.                FR-33
```

If a task seems to require breaking one of these, it does not. Stop and
write an ADR instead.

## Build order — do not skip ahead

`G0 -> G1 -> G2 -> G3 -> {G4, G5} -> G6 -> G7 -> G8 -> G9`. G8 is
conversation (the primary goal; `docs/superpowers/specs/2026-08-23-
conversational-chat-design.md`), G9 is service — reordered 2026-08-23 so
conversation ships before the service layer. See
`diagrams/06-build-gates.md`.

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

```bash
just setup       # uv venv 3.12, install, build llama.cpp with sm_120
just serve       # start llama-server
just run         # start the orchestrator (text mode)
just eval        # 50 fixtures -> pass count
just test        # unit + adversarial + injection
just selftest    # health: gpu arch, server, db perms, audio, binds
just bench       # TTFA p50/p95, VRAM peak
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
| "Ship the wake word, it's just a training run" | ADR-012. FA/FR tuning is the real cost, and PTT already works. |
| "Put the search results in the planning turn, one round-trip" | T1. This is the exact attack the design prevents. |
