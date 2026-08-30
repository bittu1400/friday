> **ARCHIVED 2026-08-30. SUPERSEDED by `gemma-brief.md` in the repo root.**
>
> This was the measurement record of the Gemma 4 evaluation and MTP feasibility
> session, and **most of it was right** — the five-model bench, the SHA256 pins,
> the turn anatomy, the killed grammar-compile hypothesis, and the decisions
> ledger all survived verification and have been carried into the brief.
>
> **What it got wrong, and why it is archived rather than patched:** its lever
> ranking is inverted. §7.2(a) calls `--ctx-size 8192->4096` "the biggest single
> saving, estimated 600-900 MiB" (measured: **38 MiB**), and §10.2 guesses
> `-np 1` is probably a no-op because `kv_unified = true` (measured: **514 MiB**).
> Both estimates came from a dense-attention model of a 40/48 sliding-window
> architecture. Its §10.3 "unresolved contradiction" is also resolved: both
> vendor claims are true at once.
>
> It is also framed around MTP, which the user has since demoted -- headroom is
> the goal, MTP was only ever one way to spend it.
>
> Verification run: `2026-08-30-gemma-verification-run.md` (same directory).
> Do not cite this file as current. Cite `gemma-brief.md`.

---

# opus-gemma-analysis.md — Gemma 4 12B on this laptop: everything measured, everything decided

**Written 2026-08-30 (night). Author: the Opus 5 session that ran the MTP
feasibility bench.** This file is the complete record of the Gemma 4 question:
what the model is, what it costs on this exact machine, whether Unsloth's MTP
drafter changes that, what can be traded to make room for it, and every
decision taken or deliberately deferred along the way.

**How to read this file.** Unlike `Alpha-ox-analysis.md`, nothing here is a
snapshot of code that later moved — it is a record of *measurements* and the
reasoning built on them. The numbers stay true unless the hardware or the
model files change. The line numbers it does cite are cited as of commit
`2faf159`. Where a claim is inference rather than measurement, it says so.

**Status: no model swap has happened. Qwen2.5-7B-Instruct Q4_K_M is still
Friday's model.** Gemma 4 12B is a retained candidate with two open questions
in front of it (OQ-47 swap, OQ-48 MTP) and one hard precondition (D16).

---

## 1. The question, and the constraints the user set

Three sessions on 2026-08-30 fed into this:

1. **The offline challenge** — "is the model really local?" It is. That
   investigation found D13/D14/D15 and is recorded in `progress.md`.
2. **The model evaluation** (ADR-084) — five models benched with identical
   flags and Friday's real planner prompt. The user overruled a paper-only
   analysis twice, and was right both times: *"We need real evaluations, not
   speculation."*
3. **This session** — the user asked for the exact Gemma file name, then:
   > "check if MTP (Multi-Token Prediction) variant if available … it can
   > actually increase your generation speed by 1.5x to 2x without increasing
   > VRAM usage. And then find the ways to reduce the load on the hardware
   > without compromising quality … We are about to use gemma as our model, it
   > has all the qualities that a local voice agent should have, i think.
   > Check all the qualities that it has too."

**Constraints the user set for the measurement round**, and which this document
obeys:

- **Do not download the drafter yet.**
- **Change no configuration** — "let's just test on what it currently is."
- Stopping `friday-llm` for the bench was authorised.
- On the VRAM trades: *"Ask again later. With more explanation of what each
  would do and cost."* — §7 of this file is that explanation.

---

## 2. Model identity — the exact artefact

The user asked for the full name. It is **not** `Q4_K_M`, which is the loose
shorthand `CLAUDE.md` and the ADR-084 tables have been using:

```
repo    unsloth/gemma-4-12B-it-qat-GGUF
quant   UD-Q4_K_XL          (Unsloth Dynamic, not a stock Q4_K_M)
file    gemma-4-12B-it-qat-UD-Q4_K_XL.gguf
bytes   6,716,356,800       (6405 MiB)
sha256  90fd44e29e0d7cffeb0fd00dc73cfdab9ed0b0e95306ecf7821ea634c940c370
path    ~/.cache/friday-model-eval/gguf/   (outside the repo on purpose: 6.3 GB)
```

For comparison, the incumbent, pinned the same way:

```
file    Qwen2.5-7B-Instruct-Q4_K_M.gguf
sha256  65b8fcd92af6b4fefa935c625d1ac27ea29dcb6ee14589c55a8f115ceaaa1423
path    ~/.local/share/friday/models/
```

Both hashes are recorded here because ADR-039/ADR-041's dependency drill
requires weights to be pinned by SHA256, and until now the Gemma candidate had
no pin at all. `model_ftype` as reported by `llama-server /props` for the
UD-Q4_K_XL file is the string `Q4_0` — the base type of the dynamic mix, not a
contradiction, but worth knowing so nobody "corrects" the filename to match.

**Why QAT matters here and is not marketing.** Google's QAT (quantization-aware
training) checkpoint quantizes *better* than post-training quantization of the
same model: the 6405 MiB QAT Q4 both **fits** and outperforms bartowski's
ordinary Q4_K_M of the same 12B, which is **7305 MiB and does not fit at all**
on this card. The QAT variant is the only reason a 12B is even in the
conversation.

---

## 3. The hardware envelope — read from the machine, not a datasheet

```
GPU            NVIDIA GeForce RTX 5070 Laptop (Blackwell, sm_120 / compute 12.0)
VRAM total     8151 MiB
VRAM baseline  ~406 MiB held by the desktop with no model loaded
memory b/w     ~272 GB/s  (measured, ADR-084)
llama.cpp      build b1-b21e4de, 2026-08-22, CUDA, sm_120a kernels (ADR-021)
```

The bandwidth number matters because decode on this card is bandwidth-bound and
obeys a verified law:

```
decode tok/s  ~=  272 / weights_GB
```

Predicted 40 tok/s for Gemma 4; measured 41.0. That half of the model is
**reliable**. The memory half is not — see §10.

---

## 4. What was measured, five models, one machine

From ADR-084. Identical flags on every run, matching `friday-llm.service`
exactly: `--ctx-size 8192 --n-gpu-layers 99 --cache-type-k q8_0
--cache-type-v q8_0`, candidate on `127.0.0.1:8081` with `friday-llm` stopped.
The bench imports Friday's **real** `plan.gbnf` and `assemble_system`, so these
are the actual hot path, not a synthetic prompt.

| metric | **Qwen2.5-7B** (current) | **Gemma 4 12B QAT** | Qwen3-8B | Ministral 3 8B | Ministral 3 14B Q3 |
| :-- | --: | --: | --: | --: | --: |
| weights | 4506 | 6405 | 4795 | 4958 | 6610 MiB |
| VRAM held | 4710 | 7534 | 5324 | 5508 | 7208 MiB |
| VRAM free | **3441** | **214** | 2404 | 2230 | 530 MiB |
| decode | **61.3** | 41.0 | 58.7 | 54.8 | 36.8 tok/s |
| prompt proc @6k | **2467** | 1454 | 2241 | 2152 | 1308 tok/s |
| planner p50 (n=15) | **373** | 891 | 389 | 423 | 615 ms |
| chat p50 (n=3) | **854** | 2340 | 1159 | 1990 | 2336 ms |
| `just eval` | **28/28** | **28/28** | 27/28 | 26/28 | **28/28** |
| regressions | 0 | 0 | E24 | E04, E20 | 0 |
| 6035-token prompt | OK | OK | OK | OK | OK |

Projected TTFA p50 — only the planner leg changes, current live p50 is 2172 ms
(n=77, 2026-08-29): Qwen3-8B ~2188, Ministral 8B ~2222, Ministral 14B ~2414,
**Gemma 4 ~2690 ms**. ADR-080's re-baselined target is **2200 ms**; only
Qwen3-8B stays under it.

Three of the five are deleted (16.4 GB reclaimed). Gemma 4 is retained as the
sole candidate.

---

## 5. Anatomy of a Gemma 4 turn — measured this session

This is new, and it is the most decision-relevant thing in the document,
because it says *which* millisecond to attack.

Friday's planner system prompt is **4627 characters = 1222 tokens**. The
critical finding:

```
=== prefix reuse across turns (same system prompt, different user text) ===
  turn 0: wall 2536.2 ms | prompt_n 1233 prompt_ms 1604.6 | cache_n    0 | predicted_n 22
  turn 1: wall  875.2 ms | prompt_n   13 prompt_ms  353.4 | cache_n 1222 | predicted_n 22
  turn 2: wall  899.6 ms | prompt_n   12 prompt_ms  356.3 | cache_n 1222 | predicted_n 23
  turn 3: wall  889.9 ms | prompt_n   13 prompt_ms  350.4 | cache_n 1222 | predicted_n 23
```

**llama-server already reuses the constant system prefix.** 1222 of 1235 tokens
come from cache; only 13 are new per turn. Every "the prompt is expensive"
intuition about Friday is therefore wrong after the first turn of a session,
and `--cache-reuse` is a **lever already spent**, not one available to us.

With the prefix cached, the remaining time splits like this (representative
turn, repeated identical text so the user tokens cache too):

```
planner:  wall 742.6 ms = prompt 193.6 ms + decode 538.6 ms (22 tok) + 10.5 ms unaccounted
                          -> DECODE IS 72% OF THE TURN
chat:     wall 1798 / 2166 / 1959 ms
          decode 1548.7 / 1920.9 / 1723.3 ms for 62 / 77 / 69 tokens
                          -> DECODE IS 86-89% OF THE TURN
```

Planner p50 over the full 15-utterance set re-measured this session: **915.7 ms**
(min 729, max 1183), decode 41.4 tok/s. ADR-084 recorded 891 ms — **reproduced**.

### A hypothesis raised and killed in the same session

`plan.gbnf` is sent on every planner request, so grammar compilation was the
obvious suspect for that 193 ms of fixed cost. It is not:

```
  with plan.gbnf   wall 742.6 | prompt_ms 193.6 (n=13) | predicted_ms 538.6 (n=22)
  no grammar       wall 748.6 | prompt_ms 193.9 (n=13) | predicted_ms 541.5 (n=22)
```

1012 characters of GBNF cost **0.3 ms**. Recorded so nobody pays to re-test it.
The 193 ms remains unattributed; it is per-request overhead (graph setup,
sampler construction, HTTP/serialization), not anything Friday controls from
the prompt side.

---

## 6. MTP — the drafter exists, the toolchain runs it, the VRAM does not

### 6.1 Availability, verified from the HuggingFace API, not a blog

`unsloth/gemma-4-12B-it-qat-GGUF`, repo last modified **2026-07-17**:

| file | bytes |
| :-- | --: |
| `mtp-gemma-4-12B-it.gguf` (repo root; the native 4-bit QAT drafter `-hf` auto-discovers) | 253,708,800 |
| `MTP/mtp-gemma-4-12B-it-Q8_0.gguf` | 465,127,936 |
| `MTP/mtp-gemma-4-12B-it-Q4_0.gguf` | 253,708,800 |
| `MTP/mtp-gemma-4-12B-it-BF16.gguf` | 861,538,816 |
| `MTP/mtp-gemma-4-12B-it-F16.gguf` | 861,538,816 |
| `mmproj-{BF16,F16,F32}.gguf` | (vision projector — we do not load it) |

The root file and `MTP/…-Q4_0.gguf` are byte-identical in size and are almost
certainly the same artefact.

### 6.2 Our toolchain is already capable — no rebuild

MTP was merged into llama.cpp on **2026-06-07** (PR #23398). Ours:

```
$ /opt/llama.cpp/build/bin/llama-server --version
version: 0.2.0-dev (build 1, commit b21e4de)
$ git -C /opt/llama.cpp log -1
b21e4de  Sat Aug 22 16:33:47 2026 +0200  mtmd: use ggml_rope_set_offset (#27521)
$ llama-server --help | grep spec-type
--spec-type none,draft-simple,draft-eagle3,draft-mtp,draft-dflash,…
```

Post-merge by two and a half months, with `--spec-type draft-mtp` and
`--spec-draft-n-max` both present. **Nothing needs building.**

Invocation, from the drafter's own README:

```bash
llama-server -m gemma-4-12B-it-qat-UD-Q4_K_XL.gguf \
  --model-draft MTP/mtp-gemma-4-12B-it-Q8_0.gguf \
  --spec-type draft-mtp --spec-draft-n-max 4 -ngl 999 -fa on
```

Unsloth's MTP page recommends starting at `--spec-draft-n-max 2` and sweeping
1–6, explicitly warning the optimum is hardware-dependent.

### 6.3 The premise "without increasing VRAM usage" is false here

This is the finding that decides the matter today.

- Unsloth's own MTP documentation: **"plan for ~2 GB additional RAM/VRAM
  headroom."**
- Measured this session, stock flags: Gemma 4 12B holds **7534 MiB and leaves
  214 MiB free** of 8151. Identical to ADR-084's number, to the megabyte.
- The drafter's weights alone are **242 MiB**, before its own KV cache and the
  larger verification graph.

**MTP cannot be loaded on top of the current Gemma configuration.** It is not a
free 1.5–2× — it is a speedup we would have to buy VRAM for.

### 6.4 What it would be worth if we could afford it

Because decode is 72% (planner) and 86–89% (chat) of a turn, MTP attacks
exactly the right leg. Applying the claimed 1.4–2.2× to the decode leg only:

| | now | 1.4× decode | 2.0× decode |
| :-- | --: | --: | --: |
| planner turn | 916 ms | 762 ms | 647 ms |
| chat turn | 1959 ms | 1466 ms | 1097 ms |
| projected TTFA p50 | ~2690 ms | ~2536 ms | ~2421 ms |

Even at 2×, **Gemma 4 with MTP does not reach ADR-080's 2200 ms target** — the
planner leg is only part of TTFA, and STT plus TTS make up the rest. MTP would
narrow the gap to the incumbent, not close it.

### 6.5 The second obstacle nobody has measured: acceptance under a grammar

Speculative decoding only pays when drafted tokens are *accepted*.

- Unsloth's benchmark for this model: **0.70** acceptance (on a B200,
  52 → 162 tok/s).
- The drafter's own README, same model: **0.51**.

Friday's planner emits ~22 tokens under `plan.gbnf`. Short generations amortize
a drafter poorly, and **grammar-constrained sampling can reject drafts the
drafter was confident about** — the draft must satisfy the GBNF, and the
verifier's constrained distribution is not the drafter's. Nobody in the sources
above benchmarks MTP *under a grammar*. So the honest position is:

> MTP's upside for Friday is concentrated in the **chat** path (62–77 free-text
> tokens), which happens to be G8, the primary goal. Its upside for the
> **planner** path is unknown and could be near zero.

---

## 7. Reducing hardware load without compromising quality — the full lever table

The user asked to be re-asked on these "with more explanation of what each would
do and cost". This section is that explanation. Every row states what it frees,
what it costs, and — importantly — whether the claim is measured or inferred.

### 7.1 Levers that are already spent (do not re-litigate)

| lever | status |
| :-- | :-- |
| **Prompt-prefix caching** | **Already on.** `cache_n 1222` of 1235. `--cache-reuse` would add nothing for our access pattern. Measured. |
| **Grammar compilation cost** | **Not a cost.** 0.3 ms. Measured. |
| **Multimodality overhead** | **Zero.** `/props` reports `modalities: {vision:false, video:false, audio:false}` — the `mmproj` file is never loaded. Measured. |
| **Reasoning suppression** | **Already correct with `--reasoning off`.** 20 completion tokens, no `reasoning_content`, clean prose. Without it Gemma 4 spends ~63 of 85 tokens thinking (ADR-084). Measured both ways. |
| **Sampling defaults** | Already match Google's recommendation for Gemma 4 — temp 1.0, top_k 64, top_p 0.95, straight out of the GGUF's own metadata. Nothing to tune. Measured via `/props`. |

### 7.2 Levers available, ranked by cost to quality

**(a) `--ctx-size 8192 → 4096` — the biggest single saving.**
*Frees:* estimated 600–900 MiB. **Untested, and the estimate deserves
suspicion** — the weights+KV model was wrong by 380–390 MiB on every model in
ADR-084, in unpredictable directions.
*Costs:* nothing until a prompt exceeds 4096 tokens. Our system prompt is 1222;
a web-search turn adds sanitized results on top. The 6035-token case in ADR-084
was a deliberate stress test, not real traffic. **The real risk is not
truncation but context shift**: when the window fills, llama.cpp discards the
oldest tokens — which for Friday are the *system prompt itself*, i.e. the tool
enum and the rules. That is a correctness failure, not a performance one. If
this lever is taken, `--no-context-shift` should be taken with it so the server
errors instead of silently amputating the contract, and the error must map to a
taxonomy code that fails closed.

**(b) `--cache-type-k/v q8_0 → q4_0`.**
*Frees:* moderate; roughly 150–250 MiB at ctx 8192. Inferred, not measured.
*Costs:* KV quantization error accumulates with context depth. At our 1235-token
working set it should be near-nil — but "should" is precisely what this project
punishes. Taking this lever obliges a `just eval` re-run to confirm 28/28, and
eval **cannot see chat quality**, which is exactly Gemma's reason for existing
here (and is D16's blind spot). Chat would need human judgement.

**(c) `-np 1` (currently `--parallel -1`, auto).**
*Frees:* **unknown, possibly zero.** This session found the server resolves auto
to **4 slots**, `n_ctx_slot = 8192`, `kv_unified = true`. If unified means one
shared KV cache, four slots cost nothing and this lever is a no-op; if it does
not, the KV allocation may be four times what is needed. **This is the cheapest
thing left to find out** and it is a single reload with higher verbosity.
*Costs:* nothing. Friday is strictly one turn in flight (FR-5); the other three
slots can never be used.

**(d) `-fa on` (currently unset, i.e. `auto`).**
*Frees:* unknown; probably nothing, because auto very likely already enables it
on CUDA with a supported head size. Unverified — this build prints no
flash-attention line at default verbosity.
*Costs:* none. Worth setting explicitly for the same reason `--n-gpu-layers 99`
is explicit: so a silent auto-downgrade cannot happen unobserved, which is
exactly how the CPU-serving incident of 2026-08-25 happened.

**(e) `-ub 512 → 256` (physical batch).**
*Frees:* a small compute buffer.
*Costs:* slows prompt processing — which is TTFA. Given prompt work is already
only 193 ms of a 916 ms turn, this trades the cheap leg to buy the expensive
one. **Last resort.**

### 7.3 Levers outside llama.cpp worth knowing about

- **GPU clock/power capping** (`nvidia-smi -lgc`, `-pl`). Reduces heat and fan
  noise on a laptop at a small throughput cost. Relevant if "load on the
  hardware" means thermals rather than memory. Untested here; it would trade
  decode tok/s, which is the leg we are trying to protect.
- **Keeping the model resident.** Already the case — `friday-llm` is a
  long-running unit, so there is no per-turn load cost. Measured indirectly:
  4710 MiB held continuously, 0% GPU between turns, 6 minutes of CPU over two
  days.
- **Not loading `mmproj`.** Already the case (§7.1).

---

## 8. Gemma 4 12B's qualities for a local voice agent — the full account

The user's hypothesis was that Gemma "has all the qualities that a local voice
agent should have". Here is the audit, separated into what is measured on this
machine and what is claimed by the vendor.

### 8.1 Measured strengths

1. **It ties the incumbent on correctness.** `just eval` **28/28, 0
   regressions** — the only candidate of four challengers to do so. Qwen3-8B
   scored 27/28 and Ministral 3 8B 26/28.
2. **It stays inside the closed enum.** Qwen3-8B's single regression was
   emitting `app='mpv'`, a value **outside** `PARAM_SCHEMA`'s enum. For a
   planner whose entire job is picking from a closed set, that is
   disqualifying; invariant #5 caught it, but the incumbent and Gemma 4 both get
   it right without needing the net.
3. **Chat is clearly better** — richer answers, concrete analogies, and a
   specific offered follow-up every time, without padding. **This is the single
   strongest argument for the swap**, because chat is G8, the primary goal, and
   is the one thing `just eval` structurally cannot measure.
4. **It fixes D4's symptom for free.** "open my todo" → alias `todo`, where the
   incumbent emits `my todo` and the lookup fails. Also "play some music on
   youtube" → query `music` vs the incumbent's `some music`.
5. **QAT is a real, measurable win, not a label.** 6405 MiB Q4 that fits and
   performs, against 7305 MiB of ordinary Q4_K_M that does not fit at all.
6. **It survives a 6035-token prompt** with no OOM, and held VRAM flat across
   an entire bench run.
7. **`--reasoning off` works cleanly on this build**, verified this session.

### 8.2 Vendor claims, relevant but unverified here

- **140+ languages.** Friday is single-user and English-driven today; this is
  headroom, not a present benefit.
- **Native multimodality** — text, image, and audio in one model (audio ≤30 s,
  video ≤60 s at 1 fps). Interesting for a *voice* agent in principle: a future
  where Gemma consumes audio directly would collapse the STT stage. But that
  would put audio on the GPU path and cross invariant #6 ("only llama-server
  touches CUDA" — which it would still satisfy) while making the model
  responsible for transcription quality. Not a Phase-2 concern; worth an ADR if
  ever pursued.
- **Apache-2.0.** Permissive, commercial use allowed. No worse than the
  incumbent.
- **256K context, dense attention** — *this claim is in conflict with our own
  observation* (§10.3) and must not be relied on.

### 8.3 Measured liabilities — the honest other half

1. **Latency.** Planner p50 891–916 ms vs the incumbent's 373 ms; chat p50
   2340 vs 854 ms. Projected TTFA ~2690 ms against a 2200 ms target that was
   itself re-baselined only a day earlier to match reality.
2. **VRAM margin of 214 MiB** on a machine that also drives a display. It ran
   stably, but llama.cpp warned at load that it *wanted* to reduce GPU layers
   and proceeded only because `99` was explicit:
   `W common_fit_params: failed to fit params to free device memory: n_gpu_layers already set by user to 99, abort`
3. **A real planner regression.** "copy that to the clipboard" → `action=none`,
   where the incumbent dispatches `clipboard_set`. **The 28 fixtures cannot see
   this** — that is D16, and it is the reason no swap may happen yet.
4. **"set brightness to fifty percent" → `direction: down`.** Both models are
   wrong (there is no absolute-level param in `PARAM_SCHEMA`), but "down" for a
   brighten-ish request is precisely the class of bug that dimmed the screen on
   2026-08-25 while announcing the opposite.
5. **It is a reasoning model by default**, which is a live trap: without
   `--reasoning off` it burns ~63 of 85 tokens thinking, and the *wrong* fix —
   `reasoning_format: "none"` — moves raw `<|channel>thought` text **into**
   `message.content`, which would write model thought into Friday's history and
   audit rows and break invariant #7 (FR-26/57). The right switches are
   `--reasoning off` or `chat_template_kwargs: {"enable_thinking": false}`.

### 8.4 The verdict on the user's hypothesis

Gemma 4 12B has the *cognitive* qualities a local voice agent wants — closed-set
discipline, better conversation, better alias extraction — and it has them at a
**2.4× planner latency penalty and a 94% cut in VRAM headroom**. Whether those
qualities are worth that price is a values question, which is why it is OQ-47
and belongs to the user, not to this analysis.

---

## 9. Decisions taken in this session, and why

Recorded here in full because the working agreement requires the reasoning to
be durable, not conversational.

**D-1. Do not download the drafter.** *User's decision*, asked explicitly and
answered "Don't download yet". Consistent with the safety rule that downloads
are confirmed first, and correct on the merits: with 214 MiB free there is
nothing to load it into.

**D-2. Change no configuration this round.** *User's decision* — "let's just
test on what it currently is". This is why §7 is an explained menu rather than a
set of measurements: **the only honest number for an untaken lever is
"untested"**, and this document says so rather than estimating and rounding the
estimate into fact.

**D-3. Pre-register predictions before loading.** *My decision*, following the
precedent of `PREDICTIONS.md` from the model evaluation. Written to
`~/.cache/friday-model-eval/PREDICTIONS-mtp.md` *before* the server was started.
The reason is that ADR-084's most valuable output was not a benchmark but a
falsified belief, and you cannot falsify a belief you recorded afterwards. See
§10 for the ledger.

**D-4. Test the grammar-compile hypothesis before proposing it as a lever.**
*My decision.* It looked like a plausible source of the 193 ms fixed cost and it
would have been a tidy, quotable optimisation. It is 0.3 ms. Recording the dead
hypothesis is worth more than the ten minutes it cost, because the next session
will have the same idea.

**D-5. Report the MTP premise as false rather than quietly working around it.**
*My decision.* The request contained "without increasing VRAM usage", which is a
reasonable reading of the marketing but is contradicted by Unsloth's own
documentation ("~2 GB additional headroom") and by our 214 MiB. Saying so first
is the whole job.

**D-6. Raise OQ-48 rather than an ADR.** *My decision.* No decision has been
made about MTP, so there is nothing for an ADR to record. `adr.md` holds
decisions; `open-questions.md` holds undecided things and what they block. An
ADR here would be ceremony.

**D-7. Pin both models by SHA256 in this document.** *My decision.* ADR-039/041's
dependency drill requires weights to be pinned, and the Gemma candidate had no
pin anywhere in the repo. It has one now.

**D-8. Restore the baseline and prove it.** *My decision, non-negotiable by
convention.* `friday-llm` restarted, `just selftest` 8/8, `llm_on_gpu` PASS at
4696 MiB. A bench that leaves the machine in a different state than it found it
is not finished.

---

## 10. The predictions ledger — what I got right and wrong

Written before loading, in `~/.cache/friday-model-eval/PREDICTIONS-mtp.md`.

| # | prediction | outcome |
| :-- | :-- | :-- |
| P1 | load log shows ~40/48 sliding-window layers | **UNRESOLVED** — this build prints no layer detail at default verbosity |
| P2 | `n_ctx_train` ≥ 128K | **UNRESOLVED** — not exposed by `/props` |
| P3 | flash attention auto-resolves ON | **UNRESOLVED** — not printed |
| P4 | `--parallel -1` resolves to 1 slot | **FALSIFIED — 4 slots**, `kv_unified = true` |
| P5 | free VRAM 214 ± 60 MiB | **EXACT — 214 MiB** |
| P6 | MTP cannot fit at these settings | **HOLDS** |
| P7 | the constant system prefix is already reused | **CONFIRMED** — and this is the *bad* outcome: it spends the lever instead of granting it |
| P8 | ctx 8192→4096 frees 600–900 MiB | **UNTESTED** (no config trades this round) |

### 10.1 The one that mattered most was the one I hoped to be wrong about

P7. If the prefix had *not* been cached, `--cache-reuse` would have been a large
free win with zero quality cost — the best possible answer to "reduce load
without compromising quality". It is already on. The honest consequence is that
**there is no free lunch left on the prompt side**; everything remaining costs
something.

### 10.2 P4 is the cheapest open thread

Four slots at 8192 context each *sounds* like four times the KV, which would be
an enormous saving. `kv_unified = true` suggests they share one cache — but
that is my inference from a flag name, not a measurement, and this project has
a documented history of exactly that mistake. One reload at higher verbosity
settles it.

### 10.3 An unresolved contradiction, stated rather than guessed

Unsloth's docs page says the 12B is **dense with 256K context**. Our own
`PREDICTIONS.md` from the model evaluation assumed — and the successful load
appeared to confirm — **40 of 48 layers sliding-window @1024, 8 full**, and
noted that without that trimming the model needs ~8.2 GB and *would not load at
all*. Since it loaded, something trimmed. But the log line proving it was not
captured, and this build does not print it by default.

**The difference is worth roughly a gigabyte of KV, i.e. exactly the amount MTP
needs.** It is therefore the first thing to establish, and it must be read off
`llama-server -lv N`, not off either document.

---

## 11. What is open, and exactly what would settle it

| id | question | what settles it |
| :-- | :-- | :-- |
| **D16** | `just eval`'s 28 fixtures cannot see a planner emitting `action=none` on a plain command | Add fixtures for "copy that to the clipboard" and "close this window". **Hard precondition for any swap** — the gate that would approve Gemma cannot currently see the regression it would admit. |
| **OQ-47** | Do we swap to Gemma 4 12B? | D16 first, then a values call on 891 ms vs 373 ms planner latency and 214 MiB vs 3441 MiB headroom, against clearly better chat. |
| **OQ-48** | Do we adopt MTP, and what do we spend to fit it? | Free ~2 GB by an authorised trade, load the drafter, measure **acceptance under `plan.gbnf`** and wall time on both paths. |
| **OQ-46(a)** | D13/D15 — the STT path phones Hugging Face at every daemon start, and `just test-egress` cannot detect egress | Independent of Gemma, but it is the reason no offline claim in this repo can currently be trusted. |

### The cheapest honest sequence, if MTP is wanted

1. Reload Gemma with `-lv 5` and **read** the KV allocation, layer types, flash
   attention state, and per-slot cost. Free. Settles P1–P4 and §10.3.
2. If slots do split KV, set `-np 1`. Free.
3. Take `--ctx-size 4096` (+ `--no-context-shift`) if steps 1–2 leave a gap.
   Costs the long-prompt ceiling.
4. Only then download the 254 MB drafter and sweep `--spec-draft-n-max 1..6`,
   reporting acceptance separately for the grammar path and the chat path.
5. Re-run `just eval` at every configuration that touches KV precision or
   context, and judge chat by hand, because eval cannot.

**Nothing in steps 3–5 may proceed on my judgement alone** — each spends
something the user owns.

---

## 12. Cross-cutting notes for whoever picks this up

- **`just eval` is not a swap gate today.** Two models scored 28/28 while
  refusing a plain command. Fix D16 before trusting the number.
- **Do not size a model with arithmetic.** ADR-084's weights+KV model was wrong
  by 380–390 MiB on every single model, in unpredictable directions. Load it
  and read `nvidia-smi`. The *decode* law (`272 / weights_GB`) does hold.
- **`reasoning_format: "none"` is a trap, not an option** — it moves raw thought
  into `message.content` and would break invariant #7. Use `--reasoning off`.
- **A green health check is not a healthy system** — `gpu_arch` passed through
  an entire GPU outage. When benching, confirm `llm_on_gpu`, not just `/health`.
- **`pgrep -f foo` matches its own command line.** Bracket the pattern:
  `pgrep -f "[f]oo"`. This bit twice on 2026-08-30.
- The bench artefacts live in `~/.cache/friday-model-eval/` (6.3 GB, outside the
  repo on purpose): `bench.py`, `PREDICTIONS.md`, `PREDICTIONS-mtp.md`,
  `RESULTS-gemma4-12b.md`, `RESULTS-mtp-feasibility.md`, `logs/`, and the
  retained `gguf/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf`.
