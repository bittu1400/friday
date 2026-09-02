# Friday — Open Questions

Every entry: what is unknown, who decides, what it blocks, and what
happens if nobody decides. An open question with no blocking gate is not
open — it is a note, and it belongs elsewhere.

**Status values:** `OPEN` / `ANSWERED` / `DEFERRED`
**Decider:** `USER` (needs your judgement) or `MEASURE` (a benchmark
answers it, no opinion required).

---

## Blocking Phase 1

_None — all Phase 1 questions are resolved and all gates G0 through G9 have passed._

---

## Blocking the post-live-pass fix list (raised 2026-08-29 by the LIVE-VOICE PASS)

_All seven are knowable now. Working agreement §2: ask them in ONE batch before
a line of the fix list is written. Evidence for every one of them is in
`progress.md`, "SESSION 2026-08-29 (night, later)"._

### OQ-40 — What counts as a spoken "yes", and what should a non-answer do?
**Decider:** USER · **Blocks:** D1 (CRITICAL) · **Status:** **ANSWERED 2026-08-29 → ADR-075 · IMPLEMENTED 2026-08-30 (`9e9a447`), NOT YET PROVEN BY VOICE**

**Answer:** normalise punctuation **and widen** the phrase set ("go ahead", "do
it", "please do", "confirm"); a non-answer cancels the pending **and is then run
as a fresh command**. The user was shown that both halves loosen the same gate
and chose them anyway — that risk is recorded in ADR-075, not overlooked.

Two questions. The first is narrow: `is_affirmation` (then at
`friday/turn.py:47-53`, now `turn.py:53-92`) matched bare tokens, so Whisper's
`"Yes."` was not an affirmation and every
spoken confirm has declined. Stripping trailing punctuation is the obvious
minimum — but is the accepted set also too narrow for speech ("go ahead",
"yeah do it", "please do", "confirm")? Widening it trades a missed yes for a
wrongly-accepted one on a destructive action.

The second is the interesting half: **today ANY non-affirmation cancels**
(ADR-069's fail-safe). During the live pass the user issued `Open a terminal`
while a preference confirm was live; it was swallowed as a decline and the
terminal never opened. Should a clearly-new command RUN instead of cancelling
— and if so, how is "clearly a new command" decided without a second model turn
(which ADR-037 rules out)?

**If nobody decides:** default to the narrow fix — normalise punctuation only,
keep the fail-safe cancel — and leave the second half open. That is the smaller
change and it does not weaken invariant #10.

### OQ-41 — What should `request_id` be, and should the audit write be `INSERT OR REPLACE`?
**Decider:** USER (architectural) · **Blocks:** D2 · **Status:** **ANSWERED 2026-08-29 → ADR-076 · IMPLEMENTED 2026-08-30 (`e7ed078`), real-path proof across a live daemon restart still owed**

**Answer:** UUID plus a plain `INSERT`. The readable `v{n}` stays in the debug
log for correlation; it stops being the database key.

`friday/store/audit.py:56` wrote `INSERT OR REPLACE INTO action_audit` keyed
on `request_id`, and `friday/daemon.py:136,288` generated that id as `v{seq}`
with `seq` resetting to 0 on every daemon start. So every restart silently
overwrites the previous run's low-numbered rows. Proven live: run 2's `v3`
replaced run 1's `v3` web_search row.

Options: a per-run prefix (`{boot_id}-v{n}`), a UUID, a monotonic rowid, or
keeping the id and making the write a plain `INSERT` that fails loudly on
collision. The choice decides whether the audit log is trustworthy across
restarts, which is why it is an ADR and not a patch.

**If nobody decides:** the audit table keeps eating itself, and it is the
primary evidence channel for verifying every other fix.

### OQ-42 — Should Friday have a local-time action?
**Decider:** USER · **Blocks:** D7 · **Status:** **ANSWERED 2026-08-29 → ADR-078**

**Answer:** yes, add `get_time`. Code reads the clock, a template speaks it, the
model never supplies the string.

"What time is it?" routes to `web_search` and answers from a scraped page —
live evidence: *"05:00:05 P.M. UTC-7 as of 08/28/2026"* when the real local
time was 20:29. No invariant broke (a search turn cannot act), but Friday
states a wrong fact confidently with the machine's own clock available.

A `get_time` action would be a new entry in the closed enum plus an outcome
template; per invariant #2 and ADR-009 the model must never supply the time
string — code reads the clock, the template speaks it.

**If nobody decides:** it keeps answering wrongly from the web.

### OQ-43 — What happens when no duration is stated?
**Decider:** USER · **Blocks:** D5 · **Status:** **ANSWERED 2026-08-29 → ADR-077**

**Answer:** ask again and set nothing. This needs a new **clarify turn**
mechanism — the only question Friday can pose today is a yes/no confirm.

`set_reminder`'s `seconds` is `{"kind": "text"}` (`friday/llm/schema.py:72`) —
free text the model fills in. Live: `'suited timer for uhh... umm...'` became a
60-second timer and `'remind me to call my mom later'` became a 3600-second
one, both dispatched, both spoken as if the user had said so. The manifest
promises it asks; **no ask path exists anywhere in the codebase.**

This is the 2026-08-25 brightness defect's shape (a free-text param a builder
guesses at) in the one place a closed enum cannot help, because a duration is a
number and not a vocabulary. What is the rule — a bounded numeric with a
"was a duration actually spoken?" test, a clarify turn, or something else?

**If nobody decides:** garbled speech keeps becoming real timers.

### OQ-44 — Should spoken model output have a sanity floor?
**Decider:** USER · **Blocks:** D6 · **Status:** **ANSWERED 2026-08-29 → ADR-079**

**Answer:** floor plus the existing fixed fallback. LLM summaries are kept —
they are good; the failure was a degenerate output, not the feature.

Friday spoke the literal string `String.Empty` (her own stored session summary
records it). It came from the model via
`friday/proactive/briefing.py:57-62`, which speaks `distill_dialogue`'s raw
output. Startup briefings and sign-off summaries are the two places raw model
text reaches the speaker by design (they are not direct-action templates, so
ADR-009 does not cover them). Should there be a floor — reject output that is
empty, a bare identifier, or non-prose — and fall back to the fixed line?

**If nobody decides:** Friday occasionally says something that is obviously a
programming artefact.

### OQ-45 — Is the 1400 ms TTFA target still the target?
**Decider:** USER · **Blocks:** nothing today · **Status:** **ANSWERED
2026-08-29 → ADR-080**

**Answer:** re-baseline to the measurement — p50 2200 ms, p95 hard fail
3600 ms — and exclude `web_search` turns from the hard fail.

Measured live with `llm_on_gpu` PASS, n=77:

```
min=1689  p50=2172  p90=3613  p95=4900  max=8674  mean=2483  (ms)
over the 4400 ms hard fail: 4    at or under the 1400 ms target: 0
```

**Zero of 77 turns met the p50 target and the observed floor is 1689 ms.**
Three of the four hard-fail breaches are `web_search` (network + grounding,
arguably exempt); the fourth is not. Either the target moves to something the
system can actually hit, or optimisation gets scheduled. Note the clock
includes STT, since `_capture_end` starts it.

**If nobody decides:** the manifest keeps carrying a target nothing has ever
met, which is worse than no target.

---

### OQ-46 — Offline hardening, and is a bigger model worth its latency?

**Decider:** USER · **Blocks:** nothing today · **Status:** OPEN (raised
2026-08-30 by the offline challenge)

Two decisions, kept in one entry because they trade against each other on the
same 8151 MiB of VRAM.

**(a) Close the STT phone-home (D13).** `friday/audio/stt.py:96` passes a model
*name* to `WhisperModel`, so `huggingface_hub` contacts `huggingface.co` at every
daemon start to check the cached revision — measured at 1899 B out / 7637 B in.
No audio or text leaves; what leaks is that this machine loaded
`Systran/faster-whisper-small.en`. Options:

  1. `local_files_only=True` at the call site — narrowest, fails loudly if the
     cache is ever missing, and does not affect other libraries.
  2. `Environment=HF_HUB_OFFLINE=1` in `friday.service` — one line, covers any
     future `huggingface_hub` caller, but is invisible from the code and is not
     inherited by a foreground `just voice`.
  3. Both.

A separate sub-decision: `just test-egress` (D15) needs replacing with a check
that can fail, or deleting so it stops being cited as proof.
**RESOLVED 2026-09-02 (ADR-110):** replaced, and the replacement's FAIL path is
demonstrated rather than asserted. It found D27 within minutes — see OQ-63.

**(b) Bigger model?** The user asked whether an 8B or 12B would be stronger.
Measured constraint, not estimated: decode here is memory-bandwidth-bound at
~272 GB/s, so `tok/s ~= 272 / weights_GB`, and 3026 MiB of VRAM is free.

| Candidate | Q4_K_M weights | Predicted decode | Fits 8 GB? |
| :-- | :-- | :-- | :-- |
| Qwen2.5-7B (current) | 4.4 GB | 61.9 tok/s (measured) | yes, 3.0 GB spare |
| 8B class | ~4.9 GB | ~55 tok/s | yes, comfortably |
| 12B class | ~7.1 GB | ~38 tok/s | only by cutting ctx or KV quant |
| 14B class | ~9 GB | — | **no** |

The tension: TTFA already fails 0-of-77 (OQ-45/ADR-080), and a bigger model can
only make it worse. It also buys least where Friday spends most of its turns —
the planner is GBNF-constrained to a closed tool enum, so capacity is largely
wasted there; the gain would land in G8 chat only. A hybrid-thinking model must
have thinking disabled or TTFA explodes.

**If nobody decides:** (a) stays open and the "local-first" claim keeps a small
hole in it with a test that cannot find it; (b) defaults to keeping
Qwen2.5-7B, which is the safe answer — it already sits at this card's
bandwidth roof.

**Note:** ADR-041's dependency drill applies. No swap without `just eval`
(28 fixtures) plus a TTFA sample on this laptop, and an ADR recording the
rejected alternatives.

**UPDATE 2026-08-30 — part (b) is MEASURED and closed; part (a) is still open.**
Five models were benched on this laptop (ADR-084). The table above was wrong in
both directions: a 12B *and* a 14B both fit, and the 14B fits with more headroom
than the 12B. Nothing beat Qwen2.5-7B on correctness. Gemma 4 12B QAT is
retained as the sole candidate and the swap decision moved to **OQ-47**.
Part (a) — the D13 phone-home and the D15 dead egress check — was deferred by
the user on 2026-08-30 to keep that session single-purpose, and remains OPEN.

---

### OQ-50 — Do we set `--parallel 1` on `friday-llm.service`?

**Decider:** USER · **Blocks:** the Gemma swap (OQ-47) · **Status:** **CLOSED
2026-08-30 — TAKEN.** `--parallel 1` shipped with the swap (ADR-090). Measured
after the swap on the live service: 7008 MiB held, **739 MiB free**, exactly
reproducing the 740 MiB prediction. `just selftest` 8/8.

One line in one service file. Measured, not estimated:

| model | stock free | with `-np 1` | delta |
| :-- | --: | --: | --: |
| Qwen2.5-7B (live today) | 3042 MiB | 3042 MiB | **0** |
| Gemma 4 12B QAT | 226 MiB | **740 MiB** | **+514** |

**Why it does nothing for Qwen and everything for Gemma.** Qwen is full GQA: one
unified 238 MiB KV cache at `4/1 seqs` and `1/1 seqs` alike. Gemma is hybrid
sliding-window — 40 of 48 layers @1024 — and llama.cpp allocates the SWA cache
with the sequence count: `4608 cells = n_seq_max x n_swa + n_ubatch =
4 x 1024 + 512`, against `1 x 1024 + 512 = 1536` at `-np 1`. `kv_unified = true`
covers the global cache only. `--parallel` unset resolves to **4 slots**.

**What it costs: nothing that exists.** FR-5 is "one turn in flight. Ever." Slots
1-3 can never be reached under any code path.

**The argument for taking it now, before any swap:** a flag left at `auto` is a
decision nobody made, and this project has been bitten by exactly that before —
the CPU-serving incident of 2026-08-25 was an auto-resolution nobody observed.
`--n-gpu-layers 99` is explicit for the same reason. Taking it while Qwen is live
is a no-op that can be verified safely (`just selftest` 8/8), which is a better
time to take it than during a model swap.

**The argument for waiting:** it changes nothing today, and a check phase is not
a commit.

**If nobody decides:** the flag stays `auto`, and 514 MiB silently disappears the
day Gemma lands. Full measurement: `gemma-brief.md` §3-§4.

---

### OQ-56 — What is TTFA on Gemma 4, and where does ADR-080 re-baseline to?
**Status:** **CLOSED 2026-08-31 → ADR-096.** The user chose to restate the target **per action class** rather than re-baseline to the 2289 ms aggregate or leave chat out of scope: direct actions p50 2.2 s / p95 3.6 s, chat p50 5.0 s / p95 7.0 s, `web_search` tracked with no hard fail. The aggregate was rejected because it hides a 4715 ms chat p50 inside one number and lets a regression in one class be absorbed by the other. NFR-1 is now NFR-1/1b/1c.

*(Original text below.)*


**Decider:** MEASUREMENT, then USER · **Status:** **MEASURED 2026-08-30 at the
microphone. The re-baseline number is the USER's call and is still open.**

**n=38 live turns, Gemma 4 12B, `balanced`, `llm_on_gpu` confirmed:**

```
all turns   p50 2289 ms   p95 10187 ms   max 13277 ms   0/38 under 1400 ms
```

**The planner regression is almost invisible and that was a surprise.** TTFA
p50 moved **2172 → 2289 ms**, about 117 ms, against the ~430 ms the planner
arithmetic predicted. Arithmetic about this model has now been wrong three
times, in both directions.

**The cost is verbosity, not the planner** — and it splits cleanly by action:

| | TTFA |
| :-- | --: |
| direct actions (`hypr_*`, `system_*`, notes) | 1858-2466 ms |
| **chat** | **6974-10187 ms** |
| web_search | 5553-13277 ms |

TTFA includes synthesizing the **whole** reply before the first sound, and
Gemma wrote 157-376 characters where the prompt asked for four short sentences.
ADR-094 capped the reply at 2 sentences / 200 characters and re-measured live:
**chat p50 7177 → 4715 ms**, max 10187 → 6289 ms; live replies mean 279 → 146
chars (n=5 vs n=9).

**What is still open:** whether ADR-080's 2200 ms target is re-baselined to the
measured 2289 ms all-turn p50, or restated per action class (direct actions
already clear it at 1858-2466 ms; chat does not at 4715 ms), or left as-is with
chat treated as out of scope for TTFA. **That is a judgement about what the
target is FOR, so it is the user's.** The measurement no longer blocks it.

**The real lever if chat must get faster is streaming TTS** (ADR-020, deferred
at G6 "measure first"). This is the measurement: 86-89 % of a chat turn is
decode plus synthesis of text the user is waiting on serially.

*(Original text below.)*

ADR-080 re-baselined the TTFA target to **2200 ms** from a live sample on the
incumbent (n=77, p50 2172 ms, p95 4900 ms, **0 of 77** turns under the old
1400 ms goal). The swap makes the planner ~2x slower — measured, 765 ms p50
against ~337 — so TTFA moves further from that target.

**What is NOT being done here: arithmetic.** Adding 430 ms to 2172 gives
~2600 ms, and this project has been wrong about this model by 380-390 MiB on
five loads and by 20x on the context lever. The projection is written down in
ADR-090 as a projection and nothing depends on it.

**What settles it:** the microphone session that is already the next task —
the `C?` affirm rows for D1/D2 — logs TTFA per turn for free. Take n>=30 in
`balanced` (FR-96) with `llm_on_gpu` confirmed, then either re-baseline ADR-080
to the measured p50 or, if the number is genuinely unpleasant, reopen the
model choice with a real figure instead of an estimate.

**If nobody decides:** NFR-1 carries a target the system knowingly misses, which
is the state ADR-080 existed to end.

---

### OQ-58 — Should desktop `Keywords` become app ids, for the long tail the model cannot guess?

**Decider:** USER · **Blocks:** nothing; ADR-097 already ships and works ·
**Status:** OPEN (raised 2026-09-02 by ADR-097)

`open_app` now reaches 101 installed applications, and the planner was probed
against the real Gemma to find where that stops working. It resolves a command
name or a display name reliably:

```
open discord               -> open_app {'app': 'discord'}
open spotify               -> open_app {'app': 'spotify'}
open obsidian              -> open_app {'app': 'obsidian'}
open thunderbird           -> open_app {'app': 'thunderbird'}
launch bluetooth settings  -> open_app {'app': 'bluetooth_manager'}  pending
open the firewall settings -> open_app {'app': 'gufw'}               pending
open blender               -> none        (not installed: fails closed)
```

**Where it stops:** an app whose spoken description matches neither its command
name nor its display name. Measured miss: **"open the printer settings" ->
none**, because the entry is `Name=Manage Printing` running
`system-config-printer`, and no id resembles "printer settings". It fails
CLOSED, which is correct — it is a discoverability gap, not a safety one.

**The candidate fix and why it was not taken.** 62 of the entries carry a
`Keywords=` line, and gufw's contains `firewall`. Registering keywords as ids
would cover this class. But the keywords are generic — gufw's are
`gufw;security;firewall;network` — so "open network" would map to whichever
entry claimed it first, and the user would get a launch they did not describe.
Cheap to add, easy to regret, and it is exactly the "guess rather than fail
closed" shape ADR-009 and the G12 enum work exist to prevent. **Left for the
user to decide.**

**Note before dismissing it as small:** the fix that DID land was a prompt
sentence. Telling the planner to prefer the COMMAND name took "open the
firewall settings" from `none` to `gufw` and "open firewall configuration"
from `none` to `firewall_configuration`, at zero code cost — measured, not
assumed. A second prompt sentence may be worth more than a keyword index.

### OQ-57 — Do the widened hotwords actually fix the G12 vocabulary?
**Status:** OPEN — **scheduled 2026-08-31 by the USER for the next microphone session.** The G12 clips are to be recorded into `~/.cache/whisper-bench/clips` with `record.sh` ("turn off my wifi", "make this fullscreen", "go to workspace three", "copy that to the clipboard", "start dictation"), reference transcripts added, and `just bench-stt` re-run. That permanently widens the STT gate the way FR-97 widened the planner gate.


**Decider:** MEASUREMENT · **Blocks:** nothing; D26 is already better than it
was · **Status:** OPEN (raised 2026-08-30 by ADR-094)

`STT_HOTWORDS` carried only Phase-1 vocabulary, and the cost was four
consecutive live turns lost to *"wifi"* coming back as **wife**, **weapon**,
**way** and **life**. The G11/G12 control vocabulary has been added and
re-benched per ADR-042: **p95 749 ms, miss 4/20, PASS** — identical misses, no
latency cost.

**That measures non-regression, not efficacy.** The 20-clip corpus in
`~/.cache/whisper-bench/` is itself Phase-1 only — every clip is an app launch,
a search, or a preference — so it contains no utterance that exercises a G12
word and **cannot show that "wifi" is now heard correctly.** The bench that
would catch this is as narrow as the fixture set D16 was.

**What settles it:** record a handful of G12 clips into the corpus with
`~/.cache/whisper-bench/record.sh` — "turn off my wifi", "make this fullscreen",
"go to workspace three", "copy that to the clipboard", "start dictation" — add
their reference transcripts, and re-run `just bench-stt`. That also permanently
widens the STT gate the same way FR-97 widened the planner gate, which is the
more valuable half.

**Note the pattern before dismissing it as small:** this is the third artifact
found frozen at Phase 1 in two days — the eval fixtures (D16, 20 of 28 actions
uncovered), `CHAT_SYSTEM`'s toolset (D24, `system_wifi` missing since G12), and
now the hotwords and the STT corpus. **Assume there are more.** Anything
enumerating "what Friday can do" that predates G12 is suspect.

**If nobody decides:** the hotwords help or they do not, and nobody finds out
until a user loses four turns to it again.

---

### OQ-49 — Does `q4_0` KV cache hold quality?

**Decider:** USER, on evidence · **Blocks:** an extra 152 MiB of headroom ·
**Status:** OPEN (raised 2026-08-30 by the verification round)

Measured on Gemma 4 12B with `-np 1` at ctx 8192: `q8_0` KV leaves 740 MiB free,
`q4_0` KV leaves **892 MiB**. KV drops 323 -> 171 MiB. The **size** is measured.
The **quality is not tested at all.**

**Why this is a real gate and not a formality.** The user's standing instruction,
2026-08-30: *"quality is our top priority and so is VRAM. Though quality wins in
all."* A lever that buys memory by costing quality loses by definition.

**What would settle it:**
1. `just eval` must stay **28/28, 0 regressions** — necessary, not sufficient.
2. **Chat judged by ear.** `just eval` structurally cannot see chat quality, and
   chat is the entire reason Gemma is a candidate (G8, the primary goal). This is
   the same blind spot as D16 and it cannot be closed by the fixtures.

KV quantization error accumulates with context depth; Friday's working set is
~1235 tokens, so the effect *should* be near-nil — and "should" is precisely what
this project punishes.

**If nobody decides:** keep `q8_0`. 740 MiB is already ample and costs nothing.

---

### OQ-48 — Do we adopt MTP speculative decoding, and what do we spend to fit it?

**Decider:** USER · **Blocks:** nothing today; entangled with OQ-47 ·
**Status:** OPEN (raised 2026-08-30, measured the same day)

Unsloth ships an MTP drafter for **this exact** model
(`unsloth/gemma-4-12B-it-qat-GGUF`, root `mtp-gemma-4-12B-it.gguf`, 254 MB),
and our llama.cpp (`b1-b21e4de`, 2026-08-22) already supports
`--spec-type draft-mtp`. Claimed 1.4-2.2x generation speed.

**Why it is worth wanting.** Measured on this laptop: decode is **72% of a
planner turn** and **86-89% of a chat turn**. That is exactly what MTP
attacks. At 1.4-2.0x on the decode leg, a chat turn goes 1959 ms ->
1466-1097 ms.

**Why it is not free.** Two obstacles, both measured or sourced:

1. **VRAM — SUPERSEDED 2026-08-30 by the verification round. It now fits.**
   The "214 MiB free" was measured with `--parallel` unset, which llama.cpp
   resolves to **4 slots** — and Gemma's sliding-window KV cache (765 of
   833 MiB) **grows with the slot count**, so three slots FR-5 guarantees can
   never be used were holding 514 MiB. With `-np 1` Gemma has **740 MiB free**;
   at `--ctx-size 16384` it has **664 MiB with double the context**. The
   drafter's Q4_0 weights are 242 MiB and its own KV cache is one filtered
   layer (`/opt/llama.cpp/src/llama-model.cpp:2154,2207,2326`), so ~500 MiB
   remains. **No context, KV precision, or batch size needs to be spent at
   all.** Unsloth's "~2 GB headroom" is generic guidance, not a measurement of
   this configuration. See `gemma-brief.md` §4.
2. **Acceptance under a grammar is unknown.** Unsloth reports 0.70 acceptance
   for this model on a B200; the repo's own MTP README reports **0.51**. The
   planner emits ~22 grammar-constrained tokens, which is the worst case for
   speculative decoding. The chat path is where it would pay.

**What would settle it:** free ~2 GB by whatever trade the user authorises,
load the drafter, and measure acceptance and wall time on both the
grammar-constrained planner path and the free-text chat path. Numbers, not the
datasheet — ADR-084's whole lesson.

**If nobody decides:** do nothing. MTP is a speed optimisation for a model we
have not adopted (OQ-47), on a machine where it does not currently fit.
Full measurement: `~/.cache/friday-model-eval/RESULTS-mtp-feasibility.md`.

### OQ-47 — Do we swap to Gemma 4 12B, and what has to be true first?

**Decider:** USER · **Status:** **CLOSED 2026-08-30 — SWAPPED.** The user
decided: *"Swap model first, then we begin anything else."* Executed the same
day as **ADR-090**, after **D16 was fixed first (ADR-089)** because it was the
one hard precondition.

**How it actually came out, on the widened 49-fixture gate:** Gemma **49/49**
vs the incumbent's **46/49**, 0 regressions. The three the incumbent misses are
live defects the old 28 fixtures could not see (D19, D20, D21) and Gemma fixes
all three. **The D16 regression this OQ was gated on — `action=none` on "copy
that to the clipboard" — was Gemma being RIGHT**: the incumbent dispatches
`clipboard_set{text:"that"}` and overwrites the user's clipboard with the
literal pronoun. The fixture was corrected, not the model (ADR-089).

**The cost, unchanged and real:** planner p50 **765 ms** (measured post-swap,
better than the 891 ms this OQ predicted, because `-np 1` and `--reasoning off`
were not in that measurement) against ~337 ms; chat ~1.7 s against ~854 ms.
Precondition 4 — re-baselining ADR-080 — is deliberately NOT done from
arithmetic; it is **OQ-56**, from a real TTFA sample at the microphone.

*(Original text below, kept for the reasoning.)*

Gemma 4 12B QAT survived the evaluation as the only candidate that ties the
incumbent on `just eval` (28/28, 0 regressions) **and** clearly beats it on
chat, which is the primary goal and the one thing the fixtures cannot measure.
The user's standing decision is *candidate retained, decision still open*.

What a swap would cost, measured not estimated:

| | Qwen2.5-7B (current) | Gemma 4 12B QAT |
| :-- | --: | --: |
| planner p50 | 373 ms | 891 ms (+518) |
| chat p50 | 854 ms | 2340 ms |
| VRAM free (stock) | 3441 MiB | ~~214 MiB~~ **740 MiB with `-np 1`** |
| projected TTFA p50 | 2172 ms | **~2690 ms** |

**Preconditions, if the answer is yes.** These are not optional:

1. **D16 first.** Fixtures must exist for the rows the current 28 cannot see —
   Gemma 4 emits `action=none` for "copy that to the clipboard" while scoring
   28/28. Swapping before the gate can see that is swapping blind.
2. **`--reasoning off` must be in `friday-llm.service`.** Gemma 4 thinks by
   default; without the flag, chat answers come back EMPTY once thinking eats
   the token budget. Verified.
3. **Never `reasoning_format: "none"`.** It leaks raw `<|channel>thought` into
   `message.content` → invariant #7 (FR-26/57). It looks like the fix.
4. **ADR-080 must be re-baselined again**, one day after it was set from
   measurement, or the swap knowingly breaks the NFR.
5. ~~**Decide the 214 MiB headroom.**~~ **LARGELY RETIRED 2026-08-30.** The
   figure was an artefact of an unset `--parallel`; with `-np 1` Gemma has
   **740 MiB free**, or **664 MiB at `--ctx-size 16384`** — double the window it
   has today, which also retires the "a web-search turn overflows the context"
   worry. Cutting `--ctx-size` to buy margin turns out to be worth **38 MiB**
   (it scales only the 68 MiB global cache), so that option was never the one to
   take. **`-np 1` must ship with the swap** — see OQ-50. The remaining live
   objection to Gemma is **latency**, not memory.

**If nobody decides:** Qwen2.5-7B stays, which is the safe answer — it is the
fastest, ties on correctness, and leaves 3441 MiB spare. The 6.3 GB candidate
sits on disk unused.

**Updated 2026-08-30 (verification round).** The memory objection is much weaker
than the table above suggested — Gemma's real headroom is 740 MiB, not 214, and
it can run a 16384-token window for 76 MiB. Nothing about latency changed, and
**D16 is still the hard precondition.** The full verified record is
`gemma-brief.md`; the four analyses this OQ was written against are archived in
`docs/archive/2026-08-30-gemma-*.md` and should not be cited.

**Sub-question the evaluation did not answer:** chat quality was judged by
reading three transcripts. The user chose to be the judge (2026-08-30). Nobody
has heard Gemma 4 through Kokoro, and voice changes the calculus — verbosity
that reads fine takes real seconds to speak.

---

## Blocking nothing, owed a decision (raised 2026-08-30 by the hardware/software drill)

_Every one of these has its measurement already done — see
`docs/hardware-placement.md` and ADR-085…ADR-088. What is missing is a choice,
not a number. None of them blocks the D3–D16 fix list; D17 and D18 are new
defects raised by the same drill and are recorded in `progress.md`._

### OQ-51 — Do we replace `webrtcvad` with Silero VAD?
**Status:** **ANSWERED 2026-08-31 by the USER → ADR-095 · IMPLEMENTED, green offline over the real corpus, and **CONFIRMED LIVE 2026-09-02** — five hands-free captures ended by Silero at 2.3-3.7 s, none reaching the 15 s cap (OQ-39, now closed).**

**Answer: yes, swap now and confirm at the microphone afterwards.** The user was shown the alternative — run the live AEC-path probe first and decide from that — and chose the swap, on the grounds that the offline evidence already identifies the mechanism, so the live run becomes a confirmation of a fix rather than another probe of a known-broken detector. `create()` now returns `SileroVad` with `webrtcvad` as a loudly-logged fallback. One thing turned out differently from the text below: the frame size did **not** change to 32 ms, because `WAKE_FRAME_MS` also frames openwakeword. `SileroVad` buffers to 512 internally and holds the last verdict instead. See ADR-095.

*(Original text below.)*


**Evidence is decisive and it root-causes D3.** Driven through the real
`friday.audio.vad.SpeechGate` on the 20 real DMIC clips, each with 2 s of that
clip's own quietest room noise appended:

```
  webrtcvad mode 0/1/2/3   start 20/20   end 14 / 14 / 15 / 16 of 20
  silero v4                start 20/20   end 20/20      0.0643 ms/frame
  silero current           start 20/20   end 20/20      0.0538 ms/frame
  silero current, If-free  start 20/20   end 20/20      0.0484 ms/frame
```

Every detector starts. **Only Silero ever ends.** On the clips webrtcvad fails
(`clip_01` .891, `clip_02` 1.000, `clip_06` .971, `clip_07` .996,
`clip_08` .829) it calls 83–100 % of frames speech **including the appended
room noise**, so trailing silence never accumulates, `SpeechGate` never emits
`end`, and the capture runs to the 15 s cap. That is D3's reported symptom
exactly. Silero's voiced fraction never exceeds 0.482 on any clip.

**Cost:** 0.048 ms per 32 ms frame — 0.15 % of one core. `Vad` is already a
`Protocol`, so a Silero backend drops in behind it; the only integration change
is 32 ms frames instead of 20 ms, and `SpeechGate` already takes `frame_ms`.

**Pick `silero_vad_op18_ifless.onnx`**: fastest of the three and built without
the ONNX `If` op — the operator that made openwakeword's classifier
unconvertible on both Intel devices. Accelerator-portable for free.

**What this does NOT close.** It is offline, on clips recorded through the real
microphone but **not through the AEC path**. OQ-39 asks for live frames through
`wake.py:_on_frame`. This identifies the mechanism and makes the live run a
confirmation rather than an exploration.

**Default if undecided:** swap it. The incumbent is the cause of the top open
defect.

### OQ-52 — Do we replace WebRTC APM with DTLN-aec, or fix the reference path first?
**Status:** OPEN — **explicitly deferred 2026-08-31 by the USER.** Asked whether D18 (the 16 kHz software reference on a 48 kHz SOF-DSP device) was in scope alongside the VAD swap, the answer was to park it and do VAD only: D3 is a VAD defect and the AEC merely feeds it frames, so keeping the diff to one detector keeps the causality readable. OQ-39's live confirmation **passed** on 2026-09-02, so D18 is not preventing end-of-speech detection and this stays parked; it remains open for barge-in quality (ADR-064), which is a different failure.


**What is robust across ~20 live captures:** DTLN-aec 512 suppresses **8–20 dB
more than WebRTC APM on every single capture**, without exception. The ordering
never inverted.

**The preservation test (n=1), which is the one that matters for barge-in.**
With the owner speaking over the playback:

```
  none (raw mic)            243 frames
  WebRTC APM (incumbent)     68 frames   -> preserves 28 % of the user
  DTLN-aec 512              152 frames   -> preserves 63 % of the user
```

WebRTC's `0 frames` on quiet captures was **a gate, not cancellation** — it
deletes the room, and it deletes 72 % of the user with it. That is a complete
explanation for why voice barge-in never worked (ADR-064).

**Cost, measured:** dtln_aec_128 0.197 ms/hop and dtln_aec_512 0.448 ms/hop on
CPU — 2.5 % and 5.6 % of an 8 ms hop. On the NPU they run (this is the **first
Friday-relevant workload that does**, `npu_busy_time_us` +242/+351 ms) but 8x
slower; they belong on the CPU.

**What is NOT established:** absolute suppression. Live values swung −11 to
−32 dB for DTLN and −1.2 to −14.9 dB for WebRTC, and **both processors degrade
on the same captures**, which no quality difference can cause. Ruled out:
estimator resolution (GCC-PHAT at sample resolution did not fix it), clock
drift (per-window lag is stable at 0.5–2.5 ms), and dropped callback frames
(zero XRUNs reported once the callbacks stopped discarding `status`).

**The remaining hypothesis, and it may matter more than the swap — see D18.**
The far reference is a 16 kHz software copy on a 48 kHz SOF-DSP device:
resampled going out, DSP-processed after that, resampled again coming back.
Both cancellers are fed a reference that never matches the acoustic path, which
explains −52 dB synthetic vs −5 dB real far better than canceller quality does.
Fixing the reference may be worth more than changing the canceller, and it is
cheaper.

**Default if undecided:** do not swap yet. Test D18 first.

### OQ-53 — Do we amend invariant #6 to let STT use CUDA?

STT on the dGPU is **p95 107 ms against the incumbent's 713–804 ms** — 7.5x, at
unchanged accuracy — for 556 MiB and no measurable LLM contention (359 / 357 /
359 ms). TTFA p50 is 2172 ms with ~750 ms of it STT, and **0 of 77 turns have
ever met the 1400 ms target** (OQ-45). This is the only measured change that
brings it into reach.

Against it: it breaks invariant #6 and FR-71 as written, it costs 1234 ms
construct + 5566 ms first-transcription at daemon start, and **it couples to
OQ-47** — Qwen leaves 2486 MiB after it, Gemma 4 12B at `-np 1` leaves 184 MiB,
Gemma at stock slots does not fit at all. CUDA STT and the Gemma swap spend the
same budget.

**Default if undecided:** invariant #6 stands. It has never been amended and an
invariant that bends under a latency argument is not an invariant.

### OQ-54 — How should Friday behave in `power-saver`?

ADR-087 accepted profile-aware degradation in principle and implemented none of
it. In `power-saver` all cores pin to ~2.2 GHz and STT p95 goes 804 → 1310 ms;
every latency target is missed silently. The owner's framing (2026-08-30):
*power-saver should cap what Friday attempts, not just make everything slower.*

Open: which intents are "cheap", whether Friday says so out loud, whether it
reads `powerprofilesctl get` or the D-Bus property, and how often.

**NARROWED 2026-09-02 by measurement (ADR-106).** All three profiles were
benchmarked at the owner's request. `balanced` is the target and `performance`
is rejected (it improves STT p50 by 10 ms and makes p95 **worse**). The
"how does Friday detect it" half is **answered**: `powerprofilesctl get` or
`/sys/firmware/acpi/platform_profile`, because `scaling_governor` and
`scaling_max_freq` read **identically in all three profiles** (audit F28) — a
check written against them can never fail.

What remains open is only the **degradation policy**: should Friday cap what it
attempts in `power-saver`, or merely be slower and say so? Nothing blocks on it;
the Phase 2 self-test check simply FAILs outside `balanced`.

**Default if undecided:** do nothing. Silent slowness is bad; guessing which
features to amputate without the owner naming them is worse.

### OQ-55 — Do we arm the Supertonic fallback?

ADR-085 wired, tested and vendored it, and the owner chose to keep the
dependency out of `pyproject.toml`. So today `_Supertonic.load()` returns
`None` in the project venv and Friday degrades to `af_heart` exactly as before:
**the fallback is inert.** One command arms it — `uv add supertonic` — at the
cost of a second TTS engine in the dependency tree.

This is deliberately the project's own worst pattern (a decision that never
runs) held in the open where it can be seen, rather than in an ADR that reads
as though it shipped.

**Default if undecided:** leave it disarmed and re-read this entry before the
next release.

## Blocking the 2026-09-02 audit plan (raised by `audit-2026-09-02.md`)

### OQ-59 — Shorten the GUI launch grace from 400 ms to 150 ms?

**Decider:** USER · **Blocks:** the launch-class TTFA budget only (ADR-107) ·
**Status:** OPEN (raised 2026-09-02, audit F29)

`executor._LAUNCH_GRACE_S = 0.4`. A GUI app never exits, so the `wait_for`
**always** runs the full grace. Measured:

```
  detach=True  (GUI launch): 402 ms   outcome=ok   duration_ms=402
  detach=False (command)   :   2 ms   outcome=ok   duration_ms=1
```

Every `open_app`, `open_youtube`, `youtube_search` and `file_open` therefore
carries **402 ms of dead time** between the spawn and the spoken line — a fifth
of the whole budget, on the most common thing a user asks for.

The grace exists to catch a binary that dies at startup. Against it: the outcome
template already declines to claim a window appeared (`"Launching Brave."` —
ADR-043), `shutil.which` has already preflighted, a real exec failure raises
`FileNotFoundError` → NOT_FOUND regardless, and **a binary that dies at 500 ms is
reported OK today anyway**.

| option | saves | costs |
| :-- | --: | :-- |
| keep 400 ms | 0 | status quo; launch TTFA ~2.05 s |
| **150 ms (recommended)** | **252 ms** | catches a death inside 150 ms instead of 400. Launch TTFA ~1.80 s. |
| drop the wait | 402 ms | the last cheap signal that the spawn survived is gone |

**Default if nobody decides:** keep 400 ms. It is the safe direction and it only
costs latency.

---

### OQ-60 — Amend invariant #6 to let STT use CUDA?

**Decider:** USER · **Blocks:** the 1.5 s direct-action target, nothing else ·
**Status:** OPEN (raised 2026-09-02, audit F26 / ADR-107)

STT cost is **flat in audio length** — Whisper pads to a 30-second window, so a
1-second tail costs what the whole utterance costs (556 ms vs 688 ms for 5 s, in
`balanced`). `faster_whisper 1.2.1` has no streaming API. **There is no software
path to a faster STT on CPU**, which is what makes this a real question rather
than an optimisation.

With `balanced` + streaming TTS + the launch-grace fix, the achievable figures
are **~1.62 s commands / ~1.80 s launches / ~2.52 s chat**. Against the owner's
1.5 s / 2.5 s target: chat lands, commands are ~120 ms over, launches are over.

| option | command | launch | chat | cost |
| :-- | --: | --: | --: | :-- |
| stay CPU | 1.62 s | 1.80 s | 2.52 s | none |
| **STT on CUDA** | **1.07 s** | **1.25 s** | **1.97 s** | amends invariant #6; contends for 1131 MiB of free VRAM. ADR-088 measured p95 **107 ms**, 7.5×. |
| variable-length STT model | ~1.4 s | ~1.6 s | ~2.3 s | ADR-086 measured **10/20 misses vs 4/20**. Rejected: that is a different product, not a latency trade. |

Invariant #6 exists because STT stealing VRAM from the LLM under load is a real
failure mode, and that has not stopped being true. **Recommendation:** evaluate
in Phase 5 with its own ADR and a measured contention test; do not amend now.

**Default if nobody decides:** stay CPU, accept ~1.6 s.

---

### OQ-61 — Invariant #7 on the session-summary path is enforced by a prompt. Accept, or add a control?

**Decider:** USER · **Blocks:** nothing; it is a standing exposure ·
**Status:** OPEN (raised 2026-09-02, audit F22)

`store/summarizer.py:distill_dialogue` sends the **raw dialogue** — verbatim
user speech and Friday's replies — to the model, and writes the result to
`session_summaries` on disk.

The only thing stopping a verbatim transcript reaching disk is a sentence in
`DISTILL_SYSTEM`: *"Never use verbatim quotes."* `_sanitize_summary` strips
markdown, URLs and control characters and caps at 250 chars. **None of that
prevents the model from quoting the user.**

Invariant #7 says raw transcripts are NEVER written to disk. On this one path it
is enforced by the same mechanism this project rejects for injection defence
(ADR-008: a prompt is not a control).

| option | cost |
| :-- | :-- |
| accept as a bounded exception, and **write it into invariant #7** | honest; the invariant stops being absolute |
| add a real control — reject a summary whose longest common substring with the dialogue exceeds N words | cheap, ~15 lines, and it can fail loudly |
| drop session summaries entirely | loses ADR-050's cross-session memory |

**Default if nobody decides:** add the substring control. It is the smallest
change that makes the invariant true again.

---

### OQ-62 — What should `just selftest` do with a WARN?

**Decider:** USER · **Blocks:** Phase 1 item, weakly ·
**Status:** **CLOSED 2026-09-02 — three states shipped (ADR-108).** `run_selftest`
returns 0 clean / 1 on any FAIL / 2 with a `[DEGRADED]` headline on any WARN.
Verified live: 9/9 PASS, rc=0. The default was taken; nothing scripted the old
exit code.

`run_selftest` sets `has_fail` **only** on `Status.FAIL`. WARN prints yellow and
the run still ends `[PASSED] All required system checks passed`. WARN is
returned when the panic switch is **engaged**, when there is **no default audio
input device**, when `sounddevice` is missing, when **llama-server is not
running**, when `nvidia-smi` cannot be parsed, and when socket binds are
**unverifiable**.

So "`just selftest` 8/8" — the sentence this project uses to mean healthy — is
compatible with an assistant that cannot hear, has no brain, and is
deliberately disabled. It all genuinely passes today; this is latent, not
active. It is `gpu_arch`'s defect living inside the tool built to catch
`gpu_arch`.

The question is only about **exit-code semantics**, because something may be
scripted on the current behaviour:

| option | |
| :-- | :-- |
| **three states (recommended)** | FAIL → 1, WARN → 2 with a `[DEGRADED]` headline, clean → 0. `panic_switch` engaged moves out of the tally entirely — it is a fact about *intent*, not health. |
| WARN → exit 1 | simplest; makes an engaged panic switch look like a broken system |
| keep as is, change only the headline | no script breaks; the exit code still lies |

**Default if nobody decides:** three states. Nothing in this repo scripts the
exit code.

---

### OQ-63 — Should rule 7 gain an egress probe, and does the ORT telemetry payload need auditing?

**Decider:** USER · **Blocks:** nothing · **Status:** OPEN (raised 2026-09-02, D27/ADR-112)

Two dependencies have now transmitted off this machine without anyone noticing,
in two different libraries, for months each:

- **D13** — `faster-whisper` resolved `huggingface.co` at every daemon start.
- **D27** — `import onnxruntime` opens sockets to `*.events.data.microsoft.com`,
  on import, on Linux. Five components route through ORT.

Neither was visible to any test until ADR-110, and **CLAUDE.md rule 7 did not
ask the question**: it vets a candidate's *footprint* (`uv pip install
--dry-run`, does it drag in torch/CUDA, does it touch an invariant) and its
*benchmarks*. It has never asked what a dependency **talks to**.

Two things are owed, and they are independent:

| | |
| :-- | :-- |
| **a. Amend rule 7?** | Add a step: run `python -c "import <pkg>; time.sleep(60)"` and watch `ss -tnp` — **sampling, not glancing**, because the ORT socket takes 15–45 s to appear. Cost: about ninety seconds per new dependency. Recommended. |
| **b. Audit the payload?** | ORT documents its telemetry as build/EP/model metadata, and nothing observed contradicts that — but it was **not inspected**, and an assistant whose first invariant is that nothing leaves the machine does not get to assume. Inspecting it means MITM-ing a TLS session on the owner's own machine, which is a decision, not a chore. |

**Default if nobody decides:** do (a), skip (b). The variable is set, the
transmission has stopped, and the remaining question is about a payload that no
longer leaves. Re-open (b) only if a dependency is added that cannot be opted
out of.

---

## Kept Open (Long-Term / Optional)

### OQ-28 — Should a meta-question about capability route to chat, not web_search?
**Decider:** USER · **Blocks:** nothing · **Status:** OPEN (live-review 2026-08-23)

"can you search the web?" routes to a literal `web_search` (it searches for that
phrase) rather than a `chat` answer about its abilities. Harmless — it *can*
search — but slightly awkward. A planner-prompt nuance (distinguish "can you X"
meta-questions from "do X" commands). Low priority; note it if it recurs.

### OQ-05 — Does the disk count as the security boundary?
**Decider:** USER · **Blocks:** nothing today · **Status:** OPEN (answered
provisionally 2026-08-22 — deliberately kept open at the user's request)

**Current answer:** nothing leaves this machine, so `0600` on
`~/.local/state/friday/memory.db` is sufficient and no at-rest encryption
is built. See ADR-031.

**Kept open because this may change later, possibly much later.** Any one
of these reopens it:

```
   - cloud sync, offsite backup, or snapshot replication is enabled
   - the machine is shared, lent, or sold
   - transcripts are ever persisted (currently forbidden — ADR-028)
   - a second user account is added
```

If that happens the work is: exclude `~/.local/state/friday/` from the
sync, or encrypt `memory.db` at rest plus a key-management decision that
does not exist yet.

---

### OQ-11 — Does the desktop actually consume dGPU VRAM?
**Status:** ANSWERED 2026-08-30 — **NO, zero.** *(Duplicate entry. The answer,
the commands and the evidence live in the single copy under "Answered by
measurement" below. This stub is kept only so the id resolves from here; it said
`OPEN` until 2026-08-30 while a second copy of the same question existed further
down the file.)*

---

### OQ-09 — Is ~1.4 s TTFA actually a problem?
**Decider:** MEASURE then USER · **Blocks:** any streaming work · **Status:**
ANSWERED 2026-08-23 — TTFA measured at G6 spoken eval: p50 2156 ms, p95 2731 ms
(well within the 4.4 s hard fail cap). Streaming is not needed for Phase 1.

---

## Answered by measurement (no opinion needed)

### OQ-07 — Does whisper meet latency on CPU?
**Decider:** MEASURE · **Blocks:** G1 (deferred), now G6 · **Status:**
ANSWERED 2026-08-23 — YES, with the right model. `large-v3-turbo` (FR-10's
old pin) FAILED at p95 2.7 s, but `small.en` int8 beam=1 hotwords hits p95
**741 ms** (< 800 ms) on this CPU. CPU STT is viable; no GPU; ADR-018 stays
closed. Full 3-round table in ADR-042 + progress.md G6. int8 beat fp32 here
(no AVX-512 penalty for CTranslate2, unlike Kokoro).

CPU is the default (ADR-004): it removes an entire CUDA context and keeps
the Python environment CUDA-free, which is what makes FR-71 checkable.

Measure CPU only. 20 clips, 2-8 s, from the actual laptop mic. Pass if
p95 <= 800 ms. Only on failure does the CUDA arm get installed and
measured — that is stop condition #5, and it reopens ADR-018.

**Scope widened 2026-08-23 (ADR-041 standing rule).** Instead of accepting
the FR-10 pin (`faster-whisper large-v3-turbo`) unexamined, G6 benchmarks
it against at least one rival CPU backend (`whisper.cpp`, which keeps STT
out of the Python venv entirely and off onnxruntime). Winner chosen on
measured p50/p95 + footprint + robustness, recorded in an ADR; FR-10's pin
is provisional until then. Kokoro (ADR-039) is the worked precedent.

Record the table in `progress.md` G1/G6.

---

### OQ-08 — Does `thought` actually improve tool selection?
**Decider:** MEASURE · **Blocks:** nothing, informs ADR-011 · **Status:**
ANSWERED 2026-08-23 — delta 0

Ran the seed set twice, with and without `thought`, temperature 0:
**18/20 both ways, delta 0 fixtures.** Under the pre-committed threshold of
2, so the field earns nothing. Recommendation recorded in ADR-011: remove
`thought` from schema/grammar/prompt at the start of G3 (removal deferred
out of the G2 commit for a clean re-baseline; flagged for confirmation).
Re-measurable if the grown suite ever disagrees.

---

### OQ-09 — Is ~1.4 s TTFA actually a problem?
**Status:** ANSWERED 2026-08-23, then **superseded**. *(Duplicate entry — the
answer lives in the copy under "Kept Open" above, which recorded p50 2156 ms /
p95 2731 ms at G6 and "streaming is not needed for Phase 1". This stub still said
`OPEN` on 2026-08-30, years of drift after the question was settled.)*

**Read `OQ-45` and `ADR-080` instead of either copy.** Live TTFA was re-measured
on 2026-08-29 at p50 2172 ms / p95 4900 ms / max 8674 ms (n=77), with **0 of 77**
turns meeting the 1400 ms target, and the target was re-baselined to 2200 ms. The
2026-08-23 answer is true as of its date and is no longer the current picture.

---

### OQ-10 — Is the Intel NPU actually usable?
**Decider:** MEASURE · **Blocks:** nothing in Phase 1 · **Status:** ANSWERED 2026-08-22 — device PRESENT

```bash
ls /dev/accel/ 2>/dev/null; lsmod | grep -i vpu
```

Result: `/dev/accel/accel0` exists and `intel_vpu` (389120) is loaded. The
blueprint's "NPU dead on Linux" claim is **false** on this kernel. Not
built on in Phase 1 (ADR-019 stands); filed as a Phase 2 option for
offloading whisper to free P-cores. Whether it is *usable* for STT (an
OpenVINO NPU path) is unmeasured — presence is confirmed, throughput is
not. See ADR-019.

---

### OQ-11 — Does the desktop actually consume dGPU VRAM?
**Decider:** MEASURE · **Blocks:** ~~G1 sizing~~ (G1 shipped long ago) ·
**Status:** ANSWERED 2026-08-30 — **NO. The desktop consumes zero dGPU VRAM.**

```bash
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
```

with Hyprland running and a browser open. On hybrid graphics, both should be on
the Intel iGPU. If the output is empty, roughly 1.9 GB of the projected VRAM peak
does not exist and the working ceiling can rise.

**Result — measured during the 2026-08-30 verification round, Brave running:**

```
$ nvidia-smi --query-compute-apps=pid,used_memory --format=csv
pid, used_gpu_memory [MiB]
536902, 4696 MiB                      <- llama-server, and nothing else

$ nvidia-smi   (Processes section)
|  GPU  PID      Type  Process name                     GPU Memory |
|    0  536902   C     ...llama.cpp/build/bin/llama-server  4696MiB |
```

**Not one graphics (`G`) client.** Only Friday's compute process. Corroborated
three ways:

1. With `friday-llm` **stopped**, `nvidia-smi` reports **2 MiB used, 7745 free** —
   the card is empty when Friday is not on it.
2. Hyprland's open fds: **6 on `dri/renderD128` (Intel iGPU) against 2 on
   `dri/renderD129` (NVIDIA)** — it renders on the iGPU.
3. `lspci`: the Intel Arrow Lake-S iGPU (`00:02.0`, driver `i915`) is present with
   its own render node.

**Consequence — the working ceiling did rise, and by more than this OQ expected.**
The whole 8151 MiB card is Friday's; usable is **7745 MiB**, with 406 MiB
reserved and **not attributable to any process** (what reserves it was not
determined — "driver/context overhead" is the usual explanation and is inference,
not a measurement here).

**This also corrects the archived record.** `docs/archive/2026-08-30-gemma-opus.md`
§3 states "~406 MiB held by the desktop with no model loaded". The number is right
(8151 − 7745); the attribution is wrong. Nothing is held by the desktop. Carried
into `gemma-brief.md` §1.

Caveat, stated rather than glossed: the browser was open but **not confirmed
playing video**. Video decode would go through VA-API on the iGPU in any case, and
with zero graphics clients on the dGPU there is no path for it to consume VRAM
there.

---

## Phase 2 — active and deferred

Phase 2 = G10 wake word, G11 proactive, G12 action surface, G13 speaker
verification (ADR-054; design `docs/superpowers/specs/2026-08-24-phase2-design.md`).

### OQ-12 — Wake word: which one, and at what FA/FR?
**Status:** PARTIALLY ANSWERED 2026-08-24 (ADR-055).

`hey_jarvis` (openWakeWord pretrained, non-commercial licence, CPU)
adopted for G10, additive to PTT, with mandatory AEC (ADR-014) and a
RAM-only buffer. **Still open:** the custom "Friday" word — deferred
*within* Phase 2; the user will cue when it is worth the sample
synthesis + augmentation + per-room FA/FR training. FA/FR targets for
both `hey_jarvis` (G10) and the eventual custom word are measured, not
felt.

### OQ-22 — Wayland typing backend for dictation (gates G12 dictation)
**Status:** OPEN — spike. `wtype` vs `ydotool` (+uinput daemon) on this
Hyprland machine: focus reliability, latency, setup/permission cost.
Record in ADR-058's follow-up.

### OQ-23 — Speaker-embedding model (gates G13)
**Status:** OPEN — spike. SpeechBrain ECAPA-TDNN vs Resemblyzer vs
alternatives, CPU only: embedding latency, RAM, owner/non-owner
separation on real samples, footprint. Pin weights (SHA256). Record in
the G13 ADR (extends ADR-059).

### OQ-36 — Should a wake trigger be refused outright when there is no VAD?
**Status:** OPEN — needs data, raised 2026-08-29 while fixing M-A3.

Without a VAD there is no end-of-speech and no ADR-066 no-speech bail-out, so
every hands-free capture runs the full 15 s cap with Friday deaf throughout.
ADR-071 takes the conservative half-step: `arm_end_of_speech` refuses and warns
once, naming the consequence and the workaround (use PTT). It does **not**
refuse the wake trigger itself, because that would silently remove hands-free
operation on a degraded install, and nothing measures how often `webrtcvad`
actually fails to load on this machine — the answer so far is "never observed".

**What decides it:** the warning firing in a real session. If it does, refusing
the trigger (wake logs "no VAD, PTT only" and does not open a capture) is
strictly better than 15 s of deafness. If it never fires, this stays as is.
**Blocks:** nothing. **Default if undecided:** keep ADR-071's behaviour.

**ASKED AND DEFERRED 2026-08-29.** Put to the user the same day it was raised,
with the option of refusing the wake trigger outright or failing at startup.
Answer: **wait for the warning to actually fire.** `webrtcvad` failing to load
has never been observed on this machine, so refusing wake would be designing
for a state with no evidence behind it — and it has its own failure mode
(silently removing hands-free operation on a degraded install). This is a
deliberate hold, not an unanswered question: it stays open **until the log line
appears**, and the next session should not re-litigate it without that
evidence.

---

### OQ-32 — Which echo canceller actually works on this laptop? (BLOCKS hands-free barge-in)
**Status:** OPEN — a full ADR-039/041 dependency drill. Raised 2026-08-25.

`pywebrtc_audio`'s EchoCanceller delivers **−52 dB** on a clean synthetic echo
and only **−5 to −10 dB** on this machine's real speaker→mic path, with the
reference correct and callback-synced (measured lag 58 ms, envelope correlation
0.53; `stream_delay_ms` at 0/30/60/90/120 ms changes nothing). The barge VAD
therefore called 238 of 349 playback frames speech, and Friday cut herself off
on every reply. Voice barge-in is off by default as a result (ADR-064).

Run the drill from CLAUDE.md rule 7: enumerate the real options (speexdsp,
WebRTC APM builds with the full AGC/NS chain rather than the bare
EchoCanceller, adaptive-filter implementations), check the footprint with
`uv pip install --dry-run` BEFORE installing (anything dragging in torch/CUDA
is disqualified by invariant #6), benchmark the survivors **on this laptop**
with the probe already written for it, and record the numbers plus the rejected
alternatives in an ADR before wiring anything in.

**THE DRILL WAS RUN 2026-08-30. The result reframes the question.**
Candidates enumerated, footprint checked with `--dry-run` before installing
(nothing dragged torch/CUDA), survivors benched on this laptop with
`scripts/aec_bench.py`, which drives three processors over ONE capture.

1. **DTLN-aec wins, on every capture.** 8-20 dB more suppression than the
   incumbent across ~20 live captures; the ordering never inverted. Cost
   0.448 ms per 8 ms hop for the 10.4M model (5.6 % of one core). It ships
   TF-lite, which OpenVINO reads directly.
2. **The incumbent does not cancel — it gates.** This is the finding that
   explains ADR-064. With a human speaking over playback:
   `none 243 frames · WebRTC APM 68 · DTLN-aec 152`. WebRTC's apparent
   `0 frames` on quiet captures is **the room being deleted, and 72 % of the
   user with it.** A suppression number cannot distinguish "cancelled the echo"
   from "muted everything"; only a preservation test can, and none of the
   earlier work ran one.
3. **Absolute suppression could NOT be stabilised** — DTLN -11 to -32 dB,
   WebRTC -1.2 to -14.9 dB, and **both degrade on the same captures**, which no
   quality difference between them can cause. Eliminated by measurement:
   estimator resolution (replaced with sample-resolution GCC-PHAT), clock drift
   (per-window lag stable at 0.5-2.5 ms), dropped callback frames (zero XRUNs
   once the harness stopped discarding sounddevice's `status`).

**What is left is D18, and it is upstream of the canceller choice.** The far
reference is a 16 kHz software copy on a device that runs
`s32le 2ch 48000Hz` out and `s32le 4ch 48000Hz` in: resampled by PipeWire on
the way out, processed by the SOF HDA DSP after that, resampled again on
capture. Neither canceller has ever been given the signal that actually reached
the room. That explains -52 dB synthetic versus -5 dB real far better than
canceller quality does. The 4 microphone channels were checked for a hardware
echo reference — they are a mic array
(`front-left,front-right,rear-left,rear-right`), not a reference.

**Recommended order: fix D18, then re-run this bench, then choose.** Swapping
the canceller first would be measuring the same broken reference with a
different algorithm. The swap decision is **OQ-52**.

**What blocks it:** D18. **What it unblocks:** hands-free interruption. Until
then PTT is the interrupt and ADR-064 stands.

### OQ-33 — What should `WAKE_THRESHOLD` actually be? (needs logged score data)
**Status:** OPEN — needs one live session's logs. Raised 2026-08-25.

`WAKE_THRESHOLD` is 0.5 and has never been chosen from data. A 90 s bench in a
quiet room scored **0 false fires** (peak input 0.1250, max score 0.002), but a
live 3-minute session with the user present produced **three captures with no
speech in them at all** — false wakes. Ambient silence is clearly not the
trigger; something in the room (movement, keyboard, speech that is not the wake
word) crosses 0.5.

ADR-066 caps the *cost* of a false wake at ~3 s but does not reduce the rate.

**What blocks the answer:** score data at fire time, which did not exist until
ADR-066 added `wake fired score=… threshold=…`. Run one normal live session,
then:
```bash
journalctl --user -u friday | grep 'wake fired'
```
Compare the scores of genuine wakes against the false ones. If false fires
cluster just above 0.5 and real ones sit near 0.9, raise the threshold. If they
overlap, the threshold is the wrong lever and the answer is a second-stage
check (speaker verification, G13, already built but off by default).

### OQ-30 — Should "play a video" open mpv or search YouTube?
**Decider:** USER · **Status:** **ANSWERED 2026-08-29 (live pass)**

**Answer:** YouTube stays the default. When it cannot work — e.g. the network
is down — fall back to VLC or mpv, and Friday **may ask** which at that point.

**This is why mpv never opened during the live pass:** `'Play a video'` →
`youtube_search{"query": "play a video"}` (audit v28), never `open_app{video}`.
`open VLC` did reach `open_app`, so a bare app name still works.

**Two constraints on implementing it, both from ADR-043 and the live pass:**
the launch is fire-and-forget, so Friday **cannot** detect that YouTube failed
to load — the only honest pre-dispatch signal is network state (`nmcli`). And
the "may ask" half needs the clarify turn of **ADR-077**, so it lands with that
work or not at all.

### OQ-31 — Wake-word feedback: is a busy toast the right channel?
**Status:** PROVISIONALLY ANSWERED 2026-08-25 — revisit after live use.

A trigger rejected under FR-5 (one turn in flight) now raises a low-urgency
desktop toast, because a silent rejection desyncs tap-toggle PTT and made the
user record an empty room. Toast was chosen over an earcon: no new asset, no
collision with TTS or the mic, and `notify-send` was already a G11 dependency.
**Open:** whether a toast per rejection becomes noise in real use, or whether a
short earcon reads better hands-free. Decide after the live-voice pass.

---

### OQ-13 — Multilingual re-enablement plan
**Status:** DEFERRED

Re-enabling Hindi/Spanish is not a config flag. It changes STT
(auto-detect reintroduces hallucination risk on noisy input), TTS
(voice routing), the prompt, and — critically — the **eval and injection
suites**, which are English-only today. Budget a full fixture set per
language. Phase 2 must not bypass Phase 1's policy layer.

---

### OQ-14 — Screen vision placement
**Status:** DEFERRED (Phase 3)

Moondream2 at int8 is ~1.2 GB of system RAM and roughly 600-900 ms on 24
cores, so CPU placement likely avoids the VRAM problem entirely — no
model swapping needed. Unbenchmarked.

Security note that must not be lost: **a screenshot is attacker-
controllable content.** Text rendered in any window becomes a new
injection sink, and it would arrive with far more authority than a search
snippet. If this is ever built, `look_at_screen` output is Zone 3 and its
grounding turn is grammar-locked exactly like search (ADR-008).

---

## Closed

_(Move entries here with the answer and the date. Do not delete them —
the reasoning behind a closed question is the thing you will want in six
months.)_

- **OQ-64 — How long may the user pause after "hey jarvis" before speaking?**
  **ANSWERED 2026-09-02 (night) by the USER → ADR-113, implemented and deployed
  the same session.** The user was shown four options and chose the largest:
  *raise it AND cut the cost of being wrong*. Both halves shipped, but **not the
  mechanism the option named** — see below, and this is the part worth keeping.

  **Shipped:** `VAD_NO_SPEECH_TIMEOUT_S` 3.0 → 5.0 s, and the ADR-066 bail-out
  now routes to a new `WakeCallbacks.on_no_speech` whose daemon handler ends the
  capture, drops the buffer via the `Recorder.reset()` that already existed, and
  returns to IDLE — **no STT, no turn.** It had been calling `on_speech_end`,
  the ordinary finish path, which transcribes: Whisper's cost is flat in audio
  length (F26), so every false wake spent a fixed ~600 ms of FR-5 deafness
  turning silence into `""`. Removing that surcharge is what pays for the longer
  wait.

  **REJECTED after reading the code: re-arming the capture on a second wake.**
  The chosen option named it and it does not survive contact with `_on_frame`.
  `_heard_speech` latches on the first **voiced frame**; openWakeWord only
  crosses threshold ~0.8 s later, at the END of the phrase. So a repeated "hey
  jarvis" during the wait **already** keeps the capture alive as ordinary speech
  and FR-5 never swallows it — a re-arm gated on "nothing heard yet" could never
  fire, and gating it looser lets a command word scoring above threshold wipe a
  real command mid-capture. That is an unreachable branch, the `cancel_reminder`
  defect shape (ADR-070). Reported back rather than built.

  **Cost of the trade, stated plainly:** a false wake now costs 5.0 s instead of
  3.0 s + ~600 ms, about 1.4 s worse in the bad case, for 2.0 s more thinking
  time in the good one.

  **Not yet proven live.** The OQ-39 session produced five real wakes and zero
  false ones, so the abandon path has not been exercised at a microphone since
  the change. `capture abandoned: no speech within 5.0s` in the journal is what
  confirms it. The original write-up follows.


  **Decider:** USER · **Blocks:** nothing — hands-free works; this is comfort ·
  **Status:** OPEN, raised 2026-09-02 (night) by the owner during the OQ-39
  capture session.

  **The observation, in the owner's words:** *"it could hold up to 2 second pause
  at max, anymore and then no response."*

  **It is real and it is one constant.** `VAD_NO_SPEECH_TIMEOUT_S = 3.0`
  (`friday/config.py:158`, ADR-066). `friday/audio/wake.py:299-316` increments
  `_silent_frames` on **every** frame of a capture and latches `_heard_speech` on
  the first voiced frame, so the budget is *3.0 s from `capture start` to your
  first voiced frame* — after which the capture is abandoned and **nothing is
  spoken back**, which is exactly the reported symptom. `VAD_MIN_SPEECH_S` does
  not eat into it. The felt budget is shorter than 3.0 s because openWakeWord
  fires some way after the wake phrase ends and the capture starts there, not
  where the user stops talking.

  **Do not confuse it with the other pause.** A pause *mid-sentence* is
  `VAD_END_SILENCE_S = 0.8` and truncates the capture instead of abandoning it —
  a wrong answer, not a silent one. Both were exercised in the OQ-39 session; the
  third capture stripped 1.200 s of silence, which is 0.8 s of that timer plus
  lead-in.

  **The tradeoff, which is why this is the user's call and not a default.**
  ADR-066 chose 3.0 s to bound the cost of a *false* wake: FR-5 allows one turn
  in flight, so an abandoned capture is time Friday is deaf. Raising the timeout
  buys thinking time on real commands and pays for it in deafness after every
  false wake. The wake scores in the OQ-39 session were 0.548-0.984 against a
  0.50 threshold, so false wakes are not hypothetical here.

  **Options:**

  - **(a) Leave it at 3.0 s.** Costs nothing; the owner adapts to the rhythm.
  - **(b) Raise it to 5.0 s.** ~2 s more thinking time; a false wake now costs
    5 s of deafness instead of 3.
  - **(c) Make it an env override** (`FRIDAY_VAD_NO_SPEECH_TIMEOUT_S`) like
    `FRIDAY_VAD_THRESHOLD` already is, and tune it live without a redeploy.
  - **(d) Raise it AND cut the cost of being wrong** — abandon on the timeout as
    today, but let a wake fire again during the wait instead of holding the turn.
    The largest change and the only one that needs an ADR.

  **Default if nobody decides:** (a). Hands-free is working as of 2026-09-02 and
  a constant that has never been measured against a false-wake rate should not be
  moved on a single session's feel.


- **OQ-39 — What is `webrtcvad` actually reporting on this microphone?**
  **ANSWERED 2026-09-02 (night) at the microphone. D3 IS FIXED LIVE.** Five
  consecutive hands-free captures through the real AEC path, service running,
  no PTT touched. Every one was ended by Silero; **not one reached the 15 s
  cap**, which is the entire content of D3. `faster_whisper` prints each
  capture's true length, so the durations are read off the capture itself and
  not inferred from log gaps: **2.988 / 3.684 / 3.093 / 2.337 / 2.363 s**.
  Wake scores 0.548-0.984 against a 0.50 threshold; `capture abandoned` never
  fired; TTFA 1555 / 1670 / 1671 / 1764 / 2255 ms.

  The third capture is the one that proves the mechanism rather than the
  outcome: 3.684 s captured of which whisper's own VAD filter stripped
  **1.200 s** — roughly 0.4 s of lead-in plus the full `VAD_END_SILENCE_S`
  0.8 s of trailing silence. That is `SpeechGate` closing on trailing silence,
  which is exactly what `webrtcvad` could not do here on 5 of 20 clips.

  **D18 is NOT implicated and stays parked (OQ-52).** It was the named suspect
  if this measurement had come back at ~15 s; it did not, so the 16 kHz
  software reference is not preventing end-of-speech detection. It remains an
  open question for barge-in quality (ADR-064), which is a different failure.

  Evidence pasted in `progress.md`, "SESSION 2026-09-02 (night, at the
  microphone)". **The original write-up follows.**

  **Decider:** MEASURE · **Blocks:** D3 (hands-free is unusable) · **Status:** **OPEN, but narrowed to a live confirmation.**

  **2026-08-31:** the swap landed first by the user's decision (OQ-51, ADR-095), so what is owed here is no longer a probe that decides anything — it is one live hands-free capture with the voiced fraction logged at `wake.py:_on_frame`, confirming that Silero ends captures through the **AEC path** as it does offline. If it does not, the suspect is D18 (the reference path), not the detector.

  **2026-09-02 (evening): attempted, NOT answered.** This is the item Phase 2
  shipped without and did not count (design §11). The daemon was restarted onto
  current code, `vad.create()` was confirmed to return `SileroVad`, the wake
  listener was confirmed active in the journal, and a 180-second journal window
  was opened to catch `capture start source=wake` and time what followed. **The
  window closed with zero lines** — nothing was said, so nothing was captured.
  That is not evidence in either direction. The rig is correct and takes three
  minutes; it needs a human at the microphone. Re-run it exactly as staged:
  watch for `capture start source=wake` and measure the gap to the next line —
  **~2-4 s means Silero ended the capture and D3 is fixed live; ~15 s means the
  cap fired and the next suspect is D18, not the detector.**


  All three wake captures ran the full 15 s cap. One contained zero speech by
  Silero's reckoning yet ADR-066's 3 s bail-out never fired, which can only
  happen if `_heard_speech` went true — i.e. `webrtcvad` called the room voiced.
  The same code ended captures at 2.0/3.4/1.7/1.9 s on 2026-08-25.

  **What answers it:** a probe that prints the voiced-fraction of live mic frames
  at `VAD_AGGRESSIVENESS` 0-3, through the same AEC path as
  `friday/audio/wake.py:_on_frame`, in this room. Nothing is decided until that
  number exists — the 2026-08-25 barge-in cutoff was blamed on two wrong causes
  before measurement found the real one.

  **MEASURED OFFLINE 2026-08-30 — the mechanism is now known, the live half is
  not.** `scripts/vad_bench.py` ran all four aggressiveness levels through the
  **real** `SpeechGate` on the 20 real DMIC clips, each with 2 s of that clip's
  own quietest room noise appended:

  ```
    webrtcvad mode=0   voiced p50 0.500   start 20/20   end 14/20
    webrtcvad mode=1   voiced p50 0.489   start 20/20   end 14/20
    webrtcvad mode=2   voiced p50 0.444   start 20/20   end 15/20   <- INCUMBENT
    webrtcvad mode=3   voiced p50 0.407   start 20/20   end 16/20
    silero (all three) voiced p50 0.35-0.37  start 20/20  end 20/20

    webrtcvad mode=2 never ends on 5 of 20:
      clip_01 voiced=0.891   clip_02 voiced=1.000   clip_06 voiced=0.971
      clip_07 voiced=0.996   clip_08 voiced=0.829
  ```

  **The hypothesis in the paragraph above is confirmed: `webrtcvad` calls the
  room voiced.** On the failing clips it classifies 83-100 % of frames as speech
  **including the appended room noise**, so trailing silence never accumulates,
  `SpeechGate` never emits `end`, and the capture runs to the 15 s cap. Raising
  aggressiveness to 3 helps by exactly one clip and is not a fix. Silero's voiced
  fraction never exceeds 0.482 on any clip and it ends 20/20.

  **STILL OPEN, and it is the half that matters for D3:** these are clips
  recorded through the real microphone but **NOT through the AEC path**. The
  question as written asks for live frames through `wake.py:_on_frame`, and the
  AEC is now known to be doing something violent to its input (OQ-32 / D18), so
  the live voiced fraction may be worse than these numbers, not better.

  **What is left:** one live capture with the voiced fraction logged at
  `_on_frame`, comparing `webrtcvad` against Silero on the same frames. The
  replacement decision itself is **OQ-51**.

  **If nobody decides:** hands-free stays unusable and PTT is the only trigger.

- **OQ-38 — How should the Hyprland tools talk to Hyprland 0.56's Lua
  dispatcher?** ANSWERED 2026-08-29, the same day it was raised (**ADR-074**),
  and implemented the same day. Both `hypr_workspace` and `hypr_window` had
  **never worked on this machine** while Friday announced success every time —
  two causes: `HYPRLAND_INSTANCE_SIGNATURE` was missing from the executor's
  minimal env (`hyprctl` cannot find the compositor, rc=1), and Hyprland 0.56
  routes `dispatch` through Lua so the old positional form no longer parses
  (rc=7). Found only because ADR-073 made a command's exit code a verdict.
  Two questions were put to the user: **fix now, before Step 10** (rather than
  after Step 12), and **treat the Lua as its own audited exception with its own
  ADR** (rather than an ordinary `build_argv` change). The answer went stricter
  than ADR-027: no parameter is formatted into the Lua at all — a closed-set
  param SELECTS one of sixteen import-time constants — and `workspace` became a
  closed enum in `PARAM_SCHEMA` instead of free text. Verified against the live
  compositor (workspace 3 -> 1 -> 2, read back with `hyprctl activeworkspace`).
  `hypr_window` is implemented but deliberately NOT live-probed: `close` and
  `fullscreen` act on the focused window, so it stays a hand-tick row in
  `docs/reality-check.md` §A10. The original write-up follows.

  **The evidence, as first written:**

  `hypr_workspace` and `hypr_window` have **never worked on this machine**, and
  Friday announced success every time. Found the moment ADR-073 made a command's
  exit code a verdict. Two independent causes, both measured through the real
  executor (evidence in `docs/reality-check.md` §A10 and the Step 9 session block
  in `progress.md`):

  1. `HYPRLAND_INSTANCE_SIGNATURE` is missing from `registry._APP_ENV`, so
     `hyprctl` cannot find the compositor at all (rc=1). One line to fix; the
     systemd unit already passes the variable through.
  2. `hyprctl dispatch workspace 2` no longer parses — Hyprland 0.56 routes
     `dispatch` through Lua (rc=7). `registry.py`'s own comment records this for
     `dispatch exec` (it is why apps are spawned directly); nobody checked the
     sibling call sites. The working form here, verified by switching workspaces
     and reading `hyprctl activeworkspace` back, is
     `hyprctl dispatch 'hl.dsp.focus{workspace=N}'`, with window dispatchers
     under `hl.dsp.window.*` (`close`, `fullscreen`, `float`, …).

  **What decides it:** the user, on two points. (a) Fix now or after Steps 10–12
  — ADR-067 explicitly rejected opportunistic fixes during other work, which is
  why this was recorded instead of folded into Step 9. (b) Whether building a
  **Lua expression** in `build_argv` needs its own ADR. It is not an invariant-#2
  breach as long as the parameter stays a closed set (workspace is a validated
  1–10, the window action a closed enum) — code owns the template, the model owns
  only an enum member — but it is the same *shape* as ADR-027's audited youtube
  exception, and that precedent says a second string-building tool gets its own
  ADR rather than inheriting one.
  **Blocks:** two of the twelve G12 rows of `docs/reality-check.md`.
  **Default if undecided:** fix both causes with the measured syntax, under a new
  ADR, immediately after Step 12.

  ---

- **OQ-37 — Should a DECLINED confirm write an audit row?** ANSWERED
  2026-08-29: **yes** (ADR-072), and it is implemented the same day. The four
  confirm-gated tools are exactly the dangerous ones, and "Friday *proposed*
  turning off Wi-Fi and I said no" is the more interesting half of that
  exchange — it is also the half that says something about the planner, since a
  proposal the user keeps refusing is a mis-planning signal that was previously
  invisible. FR-58 changes from "one row per dispatch" to "one row per resolved
  action, dispatched or declined". Two constraints came with the answer: a
  declined row must never feed `mine_habits` (it filters `outcome='ok'`, and a
  test now proves five consecutive declines mine to zero habits — Friday
  learning "you often turn off Wi-Fi" from five refusals is the worst possible
  reading of this data), and the redaction rule lives in exactly one function,
  `turn.audit_params`, called by both the executed and declined paths. Rejected:
  the narrower "only for confirm-gated tools" option, which describes the same
  set today and would need re-deciding the moment a fifth confirm-gated tool
  appears; and reusing `outcome='denied'`, which already means "policy refused
  it" and would conflate a user changing their mind with the ban list firing.

- **OQ-34 — Should `clipboard_read` ever speak clipboard contents aloud?**
  ANSWERED 2026-08-27: **no, not without an explicit confirm each time**
  (option d, ADR-068a). `clipboard_read` now returns a `PendingAction` and
  speaks the contents only after an affirmative answer — the same handshake
  that already guards `clipboard_set`. The user rejected the silent-safe
  fallback (c) because it removes the feature from voice mode, which is the
  mode Friday is used in, and rejected the secret-detection heuristic (b)
  because it fails both ways: a space-separated passphrase reads as prose and
  gets spoken, an ordinary long URL gets refused. A confirm asks honestly
  instead of guessing. This makes `clipboard_read` the first read-only tool
  behind a confirm — the gate is for disclosure, not reversibility.
  **IMPLEMENTED 2026-08-29** (fix-phase Step 2), and slightly stronger than the
  decision: the clipboard is not *read at all* until the user says yes, so a
  declined confirm never fetches the selection, let alone speaks it.
  `tests/test_clipboard_confirm.py`.

- **OQ-35 — Retention policy for `notes` (and terminal-state reminders)?**
  ANSWERED 2026-08-27: **notes kept indefinitely, fired/cancelled reminders
  pruned at 90 days** (ADR-068b), matching FR-59's existing audit window rather
  than adding a second constant. Active reminders are never pruned regardless
  of age. Notes are user-authored content the user expects to still be there;
  terminal-state reminders are machine exhaust. Closes M-T9.
  **IMPLEMENTED 2026-08-29** (fix-phase Step 6), `audit.sweep_retention`;
  `tests/test_db_integrity.py` proves notes and active reminders survive at
  100 days while fired/cancelled ones do not.

- **OQ-29 — What re-triggers the 15-second empty-capture loop?** ANSWERED
  2026-08-25. Not ambient noise and not a wake false fire: a 90 s
  `just wake-bench` scored **0 wake hits** (peak input 0.1250, max score 0.002 —
  the bench now prints both, because "0 hits" could not previously be told
  apart from a dead microphone). The cause is **detector starvation**.
  `WakeListener._on_frame` scored the detector only inside `if self.is_idle()`,
  so openWakeWord — a streaming model with rolling melspectrogram and embedding
  buffers — received nothing for the whole 15 s capture. One frame is 320
  samples and a prediction chunk is 1280, so the first frame after the capture
  could not run a new prediction and returned *the score that started the
  capture*: above threshold, refractory long expired, wake re-fires. One real
  "hey jarvis" seeds an endless loop; a daemon restart clears it, which is why
  it read as intermittent.

  **The first fix attempt was wrong and a live run disproved it.** Flushing the
  detector on resume looked right but was cosmetic: openWakeWord's
  `Model.reset()` only reassigns `prediction_buffer` (a deque of past scores)
  and leaves `preprocessor.melspectrogram_buffer` / `feature_buffer` intact, so
  the stale *features* survived and re-fired anyway. The correct fix is to stop
  starving it: score **every** frame and ignore the result unless idle
  (`friday/audio/wake.py`). Regression test
  `test_stale_score_cannot_refire_wake_after_capture`, proven to fail without
  it. The original wake tests could never have caught this — their
  `FakeDetector` returns a constant score, so the streaming contract it violates
  is invisible; the test now uses a `StreamingFakeDetector`.
  `WAKE_THRESHOLD` stays 0.5; no early-bail was added.

- **OQ-00 — Should context stay at 2048?** ANSWERED 2026-08-22. No.
  8192 with q8_0 KV costs 224 MiB. See ADR-003.
- **OQ-01 — Which apps in the registry?** ANSWERED 2026-08-22. Trimmed
  same day to five entries — browser=brave, terminal=foot, editor=code,
  media=mpv+vlc; no file manager, no Spotify; YouTube covers music and
  video. See ADR-032 (supersedes ADR-026), ADR-027.
- **OQ-02 — Does `run_script` ship in Phase 1?** ANSWERED 2026-08-22. No.
  The `ToolSpec` type supports it; no entry is registered. Add it the day
  a real script exists, with its own test.
- **OQ-04 — May Friday store raw transcripts?** ANSWERED 2026-08-22.
  In-memory ring buffer, last 20 turns, off by default, cleared on exit,
  never written to disk. See ADR-028.
- **OQ-15 — Where do runtime files live?** ANSWERED 2026-08-22. XDG dirs.
  See ADR-023.
- **OQ-16 — Task runner?** ANSWERED 2026-08-22. `just`. See ADR-025.
- **OQ-17 — Hardware identifiers in git?** ANSWERED 2026-08-22. Never;
  `laptop-specifications.md` is gitignored. See ADR-024.
- **OQ-18 — Preference key vocabulary?** ANSWERED 2026-08-23. Option (d):
  model supplies a free key, code slugifies it, a curated alias map folds
  common synonyms onto canonical keys, and every write is confirmed. Free
  enough to learn, deduped enough not to crash. See ADR-035.
- **OQ-19 — forget/reset: hard vs soft?** ANSWERED 2026-08-23. Split:
  `forget_preference` (voice-reachable) soft-expires; the `prefs` CLI
  hard-deletes only with `--hard` / `reset --yes`. See ADR-036.
- **OQ-20 — Confirm a spoken preference first?** ANSWERED 2026-08-23. Yes.
  A deterministic UI handshake (not a second model turn) writes only on an
  explicit yes; `source='user_confirmed'`. See ADR-037.
- **OQ-21 — Do preferences auto-expire by age?** ANSWERED 2026-08-23. No.
  Retention purges audit rows + session summaries only; preferences live
  until forgotten. `pinned` kept but inert. See ADR-038.
- **OQ-22 — Which Kokoro voice preset?** ANSWERED 2026-08-23. `af_bella`
  primary, `af_heart` fallback (heart/sky indistinct on audition). See
  ADR-005, ADR-040.
- **OQ-03 — PTT key + bind path?** REOPENED + RE-RESOLVED 2026-08-23 (ADR-044).
  The bind path (ADR-013, no evdev) stands; the KEY and press/release model
  changed after live testing. The Copilot key (`XF86Assistant`) was dropped —
  its firmware leaks Super into every press, mis-triggering the launcher (the
  reported "glitch") and never dispatching the chord reliably. The 3 s-hold
  "confirmation" recorded earlier was contaminated (the user was holding
  SUPER+SHIFT during the `wev` check). SHIPPED: **one bind on plain
  `XF86Presentation` → `friday-ptt toggle`** (tap on / tap off, 0.4 s
  debounce). The key is clean (modmask 0) but tap-only, so it drives toggle,
  not hold. Live-proven: tap→"open vlc"→tap launched VLC, capture 3.4 s.
  `press`/`release` remain for a future holdable key. See ADR-044.
- **OQ-07 — whisper CPU latency?** ANSWERED 2026-08-23. Yes with `small.en`
  (p95 741 ms); `large-v3-turbo` failed (2.7 s). CPU STT viable, no GPU.
  See ADR-042.
- **OQ-23 — mic device for capture?** ANSWERED 2026-08-23. Default
  PipeWire source (currently analog `Mic1`), config-overridable; not the
  `DMIC Raw` array (index can move). Recorded here to close the
  docs/"DMIC array" mismatch. (The *voice* preset was a different question,
  closed by OQ-22 — do not confuse the two. It was referred to as "OQ-06" in
  passing during Phase 1 and never had an entry of its own; that id is
  retired, and this is the only place it is mentioned.)
- **OQ-25 — Habit pattern categories and threshold?** ANSWERED 2026-08-23.
  Mined deterministically from `action_audit` table; sequential transitions
  ($A \rightarrow B \le 30\text{ min}$) + granular time-of-day slots (sunrise/early
  morning 05-08, morning 08-12, afternoon 12-17, sunset/early evening 17-20, evening
  20-23, late night 23-05); threshold $\ge 2$. Rendered as `<user_habits>` DATA.
  See ADR-049.
- **OQ-26 — Distilled long-term memory trigger and context limit?** ANSWERED 2026-08-23.
  Distilled at session shutdown when $\ge 2$ in-RAM dialogue turns exist; 1-2 concise
  sentences saved in SQLite `session_summaries`; the 2 most recent summaries are
  injected as `<past_sessions>` DATA in future chat turns. See ADR-050.
- **OQ-27 — App launch vs focus behavior:** ANSWERED 2026-08-24. If the active
  window is that app, focus it; if not on that app/workspace, open a new window
  even if another instance exists, and announce via speech.
- **DND Timers/Reminders Policy (G11):** ANSWERED 2026-08-24. Explicitly scheduled
  timers and reminders fire anyway (speak + notify-send) during Conversational DND
  because they are time-critical and set by the user.
- **File-Open Registry Placeholders (G12):** ANSWERED 2026-08-24. Keep dictionary/list
  structure as placeholders in code; user will provide explicit alias-to-path mappings later.
- **Voiceprint Enrollment Samples (G13):** ANSWERED 2026-08-24. Collect 10 sample
  utterances during voice enrollment to capture vocal variation.
- **OQ-21 — AEC library choice (G10):** ANSWERED 2026-08-24. `pywebrtc-audio` (WebRTC APM
  EchoCanceller) adopted on CPU (73.3 µs/frame, RTF 0.0073). See ADR-060.
- **OQ-22 — Wayland typing backend (G12):** ANSWERED 2026-08-24. `ydotool` / `wtype` fail-soft
  in `friday/tools/typer.py` with standard punctuation formatting. See ADR-058.
- **OQ-23 — Speaker embedding model choice (G13):** ANSWERED 2026-08-24. `sherpa-onnx`
  3D-Speaker/CAM++ ONNX model (`3dspeaker_campplus.onnx`, 512-dim, 31.9 ms/2s audio on CPU, 0 torch/CUDA). See ADR-063.
- **OQ-24 — VAD library choice (G10):** ANSWERED 2026-08-24. `webrtcvad` mode 2 paired with
  pure `SpeechGate` debouncer (4.0 µs/frame, RTF 0.00020). See ADR-062.
- **OQ-62 — Selftest WARN exit semantics (Phase 1, F20):** ANSWERED 2026-09-02. When any
  check returns `Status.WARN`, `run_selftest()` prints `[DEGRADED]` and exits with code `2`,
  reserving `0` / `[PASSED]` strictly for all-clean checks. See ADR-108.





