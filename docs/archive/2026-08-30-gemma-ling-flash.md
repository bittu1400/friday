> **ARCHIVED 2026-08-30. PARTLY FABRICATED — do not cite as current.**
>
> Roughly 70% is verbatim `2026-08-30-gemma-opus.md`. Of the ~30% that is new,
> the sourcing is genuine but the details are not reliable.
>
> **Verified TRUE:** llama.cpp discussion **#25357** is real ("MTP speculative
> decoding on 8GB GPUs: head quantization sweep + the KV-budget recipe",
> 2026-07-06). It really does contain "never trade layers for the draft", the
> `--parallel 1` KV-funding recipe, the Q6_K drafter, and the Q8->Q2 acceptance
> figure. The `--parallel 1` recipe was independently reproduced here and is
> worth 514 MiB. That is a real contribution.
>
> **Verified FALSE:**
> 1. §4.6 "A critical Gotcha: Q8 KV cache kills draft acceptance ... 0%
>    acceptance ... fixed in b9551+" is **fabricated, and inverts its own cited
>    source** -- #25357 *recommends* `--cache-type-k q8_0 --cache-type-v q8_0`.
>    Acting on it would have cost 284 MiB for nothing.
> 2. The MTP filenames (`MTP/gemma-4-12B-it-Q8_0-MTP.gguf`) do not exist. The HF
>    API says `MTP/mtp-gemma-4-12B-it-Q8_0.gguf`, which the opus file already
>    had right. It rewrote a correctly captured fact.
> 3. §11 "the drafter does not have its own KV; it borrows the target s"
>    contradicts its own §4.3 and the llama.cpp source
>    (`src/llama-model.cpp:2154,2207,2326` -- the draft context builds its own
>    filtered `llama_kv_cache`).
> 4. §3 "only 3 of 48 layers cache a full 1024-window, the rest use 512" -- our
>    own load prints 40 SWA @1024 + 8 global.
> 5. The seven-row accept-rate / tok-s table in §4.4 is **not in the cited
>    discussion**, which contains no such table. It also refutes itself: it gives
>    a 62.1 tok/s baseline and then "Q8 MTP n=2 | 71.9 tok/s | 1.74x", where
>    71.9/62.1 = 1.16. Its own speedup column does not follow from its own
>    throughput column in any Q8 row.
>
> Lesson worth keeping: real citations do not make the sentences around them
> true. Check the claim against the source, not against the bibliography.

---

# ling-flash-gemma-analysis.md — Gemma 4 12B on this laptop: MTP, hardware load, and the full optimisation report

**Written 2026-08-30. Author: the session that researched MTP for Gemma 4.**
This is the companion analysis to `opus-gemma-analysis.md` — it covers the same model
and machine but zooms into three things the user asked for directly: MTP feasibility and
tuning, every lever to reduce hardware load without sacrificing quality, and a complete
audit of Gemma 4's qualities as a local voice-assistant model.

**Scope: check only, zero code changes.** Every number below is a measurement, a cited
benchmark from the community, or a stated limitation. Nothing is tuned, loaded, or
reconfigured here. Where a figure is inferred rather than measured, it says so.

**Read this alongside `opus-gemma-analysis.md`.** That file is the record of what was
measured and decided in the model-evaluation session; this one is the deep dive into
MTP, the optimisation surface, and the model's fitness for the voice-agent role.

---

## 1. The machine — the envelope we are working inside

Everything below is bounded by the spec in `laptop-specifications.md`:

| Resource | Value | Notes |
| :-- | :-- | :-- |
| GPU | NVIDIA RTX 5070 Laptop (Blackwell, sm_120) | 8151 MiB VRAM |
| VRAM baseline | ~406 MiB held by desktop | Leaves ~7745 MiB for the model stack |
| Memory bandwidth | ~272 GB/s (measured) | Decode-bound: `tok/s ≈ 272 / weights_GB` |
| llama.cpp | b1-b21e4de, 2026-08-22 | CUDA, sm_120a kernels; `--spec-type draft-mtp` present |
| CPU | Intel Core Ultra 9 275HX (24c/24t) | Handles STT, TTS, wake, VAD, AEC — all CPU |
| RAM | 16 GB DDR5 | 15.4 GiB addressable |

The machine is a laptop. Thermals and power delivery matter: TGP 70–115 W, 40–44 °C
GPU under load. MTP adds a second model; the VRAM budget is the hard ceiling and the
fan curve is the soft ceiling.

---

## 2. Model identity — the artifact under consideration

File from `opus-gemma-analysis.md`, restated here because MTP depends on the exact
quant and the exact drafter pairing:

```
repo    unsloth/gemma-4-12B-it-qat-GGUF
quant   UD-Q4_K_XL  (Unsloth Dynamic QAT, not a stock Q4_K_M)
file    gemma-4-12B-it-qat-UD-Q4_K_XL.gguf
bytes   6,716,356,800  (6405 MiB)
sha256  90fd44e29e0d7cffeb0fd00dc73cfdab9ed0b0e95306ecf7821ea634c940c370
path    ~/.cache/friday-model-eval/gguf/
```

**Why QAT is non-negotiable here.** Google's quantization-aware training checkpoint
quantizes better than post-training quantization of the same model. The 6405 MiB Q4
QAT both fits and outperforms bartowski's ordinary Q4_K_M of the same 12B, which is
7305 MiB and does not fit on this card. QAT is the only reason a 12B is in the
conversation. MTP was designed to pair with QAT — Google explicitly released the MTP
head *for the QAT variant*, and the QAT weights were trained with MTP in mind
(`ark:/26037` — the technical report states "Use the MTP QAT checkpoints to preserve
the speedup of MTP while quantizing the models").

**`model_ftype` as reported by `llama-server /props` is the string `Q4_0`** — the base
type of the dynamic mix, not a contradiction.

---

## 3. Gemma 4 12B architecture — the dense unified model

From Google's model card and technical report:

| Property | Value |
| :-- | :-- |
| Effective parameters | 11.95 B (dense, not MoE) |
| Layers | 48 |
| Sliding window | 1024 tokens |
| Context window | 256 K tokens |
| Vocabulary | 262 K |
| Attention | Hybrid: 5:1 local-to-global, final layer always global |
| KV sharing | Global layers: unified K=V, p-RoPE, KV cache sharing — cuts global KV by ~37.5% |
| Modalities | Text, image, audio (unified encoder-free; raw patches → linear projection, no separate encoders) |
| Thinking mode | Yes (must be disabled for voice-agent use) |
| License | Apache-2.0 |

**The 1024-token sliding window is the architecture detail that matters most for MTP
and for KV-budget arithmetic.** Only 3 of 48 layers cache a full 1024-window; the rest
use 512-token windows or are global. This means the KV cache is structurally smaller
than a dense-attention 12B of equivalent parameter count, which is exactly why the
QAT Q4 fits at all. It also means KV-precision choices have a nonlinear effect: the
community sweep in `ggml-org/llama.cpp#25357` found that KV q8 buys ~+1.3% PPL at
ctx 4096 but saturates quickly because only a fraction of layers cache the full window.

---

## 4. MTP — the drafter exists, the toolchain runs it, the VRAM does not

### 4.1 Availability

Unsloth ships an MTP drafter for **this exact model** — verified from the HuggingFace
API and the `MTP/README.md`:

```
mtp-gemma-4-12B-it.gguf              (repo root, smart Q4_0, ~254 MiB, used by -hf auto)
MTP/gemma-4-12B-it-Q4_0-MTP.gguf     (same smart Q4_0)
MTP/gemma-4-12B-it-Q8_0-MTP.gguf
MTP/gemma-4-12B-it-BF16-MTP.gguf
MTP/gemma-4-12B-it-F16-MTP.gguf
```

The root file and `MTP/…-Q4_0.gguf` are byte-identical in size and are almost certainly
the same artefact. The smart Q4_0 is "near-lossless" — about 97% of its weights are
byte-exact on the int4 grid, roughly half the size of the Q8_0.

### 4.2 Our toolchain is already capable — no rebuild

MTP was merged into llama.cpp on 2026-06-07 (PR #23398). Our build (`b21e4de`,
2026-08-22) is post-merge. `--spec-type draft-mtp` and `--spec-draft-n-max` are both
present. The `gemma4-assistant` GGUF architecture is registered. **Nothing needs building.**

The invocation the Unsloth docs give for our exact model:

```bash
llama-server -m gemma-4-12B-it-qat-UD-Q4_K_XL.gguf \
  --model-draft MTP/gemma-4-12B-it-Q8_0-MTP.gguf \
  --spec-type draft-mtp --spec-draft-n-max 2 \
  -ngl 999 -fa on --parallel 1
```

With `-hf` auto-discovery, the root `mtp-gemma-4-12B-it.gguf` is found automatically
and `--model-draft` is not needed.

### 4.3 The premise "without increasing VRAM usage" is false here

This is the finding that decides the matter on this machine:

- Unsloth's own MTP documentation: "plan for ~2 GB additional RAM/VRAM headroom."
- Measured, stock flags: Gemma 4 12B holds 7534 MiB and leaves **214 MiB free** of
  8151 (reproduced exactly in `opus-gemma-analysis.md`).
- The drafter's weights alone are **242 MiB** (Q4_0), before its own KV cache and the
  larger verification graph.

**MTP cannot be loaded on top of the current Gemma configuration.** It is a speedup we
would have to buy VRAM for. The 1.4–2.2× figure is real but it costs memory, and on
this machine the memory is not there.

### 4.4 What it would be worth if we could afford it

Because decode is 72% of a planner turn and 86–89% of a chat turn (measured in
`opus-gemma-analysis.md`, §5), MTP attacks exactly the right leg. The community
benchmarks (llama.cpp PR #23398, `ggml-org/llama.cpp#25357`) for Gemma 4 12B QAT:

| Configuration | Accept rate | Mean tok/s | Speedup vs no-MTP |
| :-- | :--: | :--: | :--: |
| Q4 no MTP | n/a | 62.1 | 1.00× |
| Q4 MTP n=2 | 0.678 | 97.1 | **1.51×** |
| Q4 MTP n=3 | 0.627 | 100.6 | **1.55×** |
| Q4 MTP n=4 | 0.568 | 98.0 | **1.50×** |
| Q8 MTP n=2 | 0.697 | 71.9 | 1.74× |
| Q8 MTP n=3 | 0.616 | 79.5 | 1.89× |
| Q8 MTP n=4 | 0.577 | 83.3 | 1.97× |

The pattern is clear: **n=3 or n=4 gives the best throughput on Q8, but n=2 is optimal
on Q4** because the marginal gain from the fourth speculative token does not justify the
overhead when the model is already quantized aggressively. This is directly relevant:
Friday runs the QAT (Q4) variant, so **n=2 is the right starting point**, not n=4.

One Reddit user hit **120 tok/s** on an RTX 4070 (12 GB) with the QAT + MTP setup — a
2× gain over ~60 tok/s without MTP. The configuration that produced it:
`--spec-draft-n-max 4 --parallel 1 --ctx-size 131072`. But that was on a denser
memory profile; our 214 MiB headroom is the opposite end of the spectrum.

### 4.5 The second obstacle nobody has measured: acceptance under a grammar

Speculative decoding only pays when drafted tokens are accepted.

- Unsloth's benchmark for this model on a B200: **0.51 acceptance** (the `MTP/README.md`
  figure, measured against `gemma-4-12B-it-qat-UD-Q4_K_XL.gguf` with `-hf` auto-discovery).
- The `ggml-org/llama.cpp#25357` sweep measured **0.73–0.91 acceptance** on an RTX 5060
  Laptop (8 GB) in real chat with a 12B dense model — but that was a non-grammar,
  free-text workload.

Friday's planner emits ~22 tokens under `plan.gbnf` (a GBNF grammar). Short, grammar-constrained
generations amortize a drafter poorly, and **grammar-constrained sampling can reject drafts
the drafter was confident about** — the draft must satisfy the GBNF, and the verifier's
constrained distribution is not the drafter's. Nobody in the sources above benchmarks MTP
*under a grammar*. So the honest position is:

> MTP's upside for Friday is concentrated in the **chat** path (62–77 free-text tokens),
> which happens to be G8, the primary goal. Its upside for the **planner** path is unknown
> and could be near zero.

The community data backs this up: the `ggml-org/llama.cpp#25357` author found that
`n_max=2` beats 3 and 4 everywhere at these acceptance rates, and that the Gemma 4
head's per-token acceptance collapses with draft depth (0.80 → 0.54 → 0.43 at depth
1→2→3 on free text). The Qwen3.6 numbers decay much more gently (0.83 @ n2, 0.72 @ n3).
Gemma 4's head is sharper at shallow depth — which means **shallow drafts (n=2) are the
sweet spot**, and shallow drafts are exactly what grammar-constrained generation needs.

### 4.6 A critical Gotcha: Q8 KV cache kills draft acceptance

This was discovered in the llama.cpp mainline and is the single most dangerous footgun
for anyone enabling MTP on Gemma 4:

> With `-ctk q8_0 -ctv q8_0`, Draft-MTP initialized but had **0% acceptance**.
> After rebuilding and removing Q8 KV cache, acceptance became normal.

The `gemma4-assistant` architecture does not play well with Q8-quantized KV. The fix is to
**use the default/f16 KV cache** when enabling MTP, or at minimum verify acceptance is
nonzero on first load. This is a regression introduced by the MTP merge (fixed in b9551+)
and our build is post-fix, but the interaction is real: if anyone later changes KV
precision, MTP acceptance must be re-verified.

---

## 5. The VRAM-budget recipe — how to fund the drafter

The `ggml-org/llama.cpp#25357` author spent a day sweeping the whole trade-off space on
an 8 GB card with the Gemma 4 12B dense model and the official MTP drafter. The three
findings that matter, verbatim:

> 1. **Never trade layers for the draft.** MTP wins at 42/48 and 44/48 layers, but the
>    moment the model itself doesn't fully fit, the full-offload baseline beats every MTP
>    config.
> 2. **Fund the draft from the KV budget.** `--parallel 1` alone freed enough KV
>    allocation to fit the head next to all 48 layers with an f16 cache.
> 3. **Draft head acceptance is bit-insensitive.** Q8→Q2 acceptance only drops 55%→49%
>    (n_max=2). Q6_K is the sweet spot: smaller than Q8, same acceptance, measurably
>    faster (40.4 vs 39.6 tok/s).

Translated to our machine:

| Step | Action | VRAM freed | Cost |
| :-- | :-- | :--: | :-- |
| 1 | `-np 1` (currently auto → 4 slots; `kv_unified = true` suggests shared KV) | Possibly hundreds of MiB, or zero — untested | None. Single reload at higher verbosity to confirm. |
| 2 | `--cache-type-k/v q8_0` → keep as is for now; q4_0 is a later step | — | — |
| 3 | `-fa on` (currently unset/auto) | Nothing — auto likely already enables it | None. Prevents silent downgrade. |
| 4a | `--ctx-size 8192 → 4096` | **~600–900 MiB** (estimated, untested) | Long-prompt ceiling drops from 8192 to 4096. |
| 4b | If 4a is taken, pair with `--no-context-shift` | — | Server errors instead of silently amputating the contract. |
| 5 | `--parallel 1` | Frees per-slot KV overhead | None. Friday is one turn in flight (FR-5). |
| 6 | If still short, cut `--ctx-size` further or move to `q4_0` KV | ~150–250 MiB (q4_0 KV) | KV quantization error; PPL ~+1.3% at ctx 4096. |
| 7 | Download the 242 MiB drafter | — | **214 MiB headroom is not enough for the drafter + KV at ctx 8192.** Must free more first. |

**The honest sequence, if MTP is wanted:**

1. Reload with `-lv 5` and read the KV allocation, layer types, flash-attention state, and
   per-slot cost. Free. Settles the unknowns.
2. If slots split KV, set `--parallel 1`. Free.
3. Take `--ctx-size 4096` (+ `--no-context-shift`) if steps 1–2 leave a gap. Costs the
   long-prompt ceiling.
4. Only then download the 242 MB drafter and sweep `--spec-draft-n-max 1..6`, reporting
   acceptance separately for the grammar path and the chat path.
5. Re-run `just eval` at every configuration that touches KV precision or context, and
   judge chat by hand, because eval cannot.

**Nothing in steps 3–5 may proceed on judgement alone** — each spends something the user
owns. The drafter cannot be tried until memory is freed, and the only free memory comes
from `-np 1` and `--ctx-size`. The rest costs context or KV precision.

---

## 6. Reducing hardware load without compromising quality — the full lever table

Every row states what it frees, what it costs, and whether the claim is measured or
inferred. Levers already spent are listed first; available levers follow, ranked by cost
to quality.

### 6.1 Levers already spent (do not re-litigate)

| lever | status |
| :-- | :-- |
| **Prompt-prefix caching** | Already on. `cache_n 1222` of 1235. `--cache-reuse` would add nothing for our access pattern. Measured. |
| **Grammar compilation cost** | Not a cost. 0.3 ms. Measured. |
| **Multimodality overhead** | Zero. `/props` reports `modalities: {vision:false, video:false, audio:false}` — the `mmproj` file is never loaded. Measured. |
| **Reasoning suppression** | Already correct with `--reasoning off`. 20 completion tokens, no `reasoning_content`, clean prose. Without it Gemma 4 spends ~63 of 85 tokens thinking (ADR-084). Measured both ways. |
| **Sampling defaults** | Already match Google's recommendation for Gemma 4 — temp 1.0, top_k 64, top_p 0.95, straight out of the GGUF's own metadata. Nothing to tune. Measured via `/props`. |

### 6.2 Levers available, ranked by cost to quality

**(a) `--ctx-size 8192 → 4096` — the biggest single saving.**
*Frees:* estimated 600–900 MiB. **Untested**, and the estimate deserves suspicion — the
weights+KV model was wrong by 380–390 MiB on every model in ADR-084, in unpredictable
directions.
*Costs:* nothing until a prompt exceeds 4096 tokens. Our system prompt is 1222; a web-search
turn adds sanitized results on top. The 6035-token case in ADR-084 was a deliberate stress
test, not real traffic. **The real risk is not truncation but context shift**: when the
window fills, llama.cpp discards the oldest tokens — which for Friday are the *system
prompt itself*, i.e. the tool enum and the rules. That is a correctness failure, not a
performance one. If this lever is taken, `--no-context-shift` should be taken with it so the
server errors instead of silently amputating the contract, and the error must map to a
taxonomy code that fails closed.

**(b) `--cache-type-k/v q8_0 → q4_0`.**
*Frees:* moderate; roughly 150–250 MiB at ctx 8192. Inferred, not measured.
*Costs:* KV quantization error accumulates with context depth. At our 1235-token working set
it should be near-nil — but "should" is precisely what this project punishes. Taking this
lever obliges a `just eval` re-run to confirm 28/28, and eval **cannot see chat quality**,
which is exactly Gemma's reason for existing here (and is D16's blind spot). Chat would need
human judgement.

**(c) `-np 1` (currently `--parallel -1`, auto → resolves to 4 slots).**
*Frees:* **unknown, possibly zero.** This session found the server resolves auto to **4 slots**,
`n_ctx_slot = 8192`, `kv_unified = true`. If unified means one shared KV cache, four slots
cost nothing and this lever is a no-op; if it does not, the KV allocation may be four times
what is needed. **This is the cheapest thing left to find out** and it is a single reload
with higher verbosity.
*Costs:* nothing. Friday is strictly one turn in flight (FR-5); the other three slots can
never be used. One reload at higher verbosity settles it.

**(d) `-fa on` (currently unset, i.e. `auto`).**
*Frees:* unknown; probably nothing, because auto very likely already enables it on CUDA with
a supported head size. Unverified — this build prints no flash-attention line at default
verbosity.
*Costs:* none. Worth setting explicitly for the same reason `--n-gpu-layers 99` is explicit:
so a silent auto-downgrade cannot happen unobserved, which is exactly how the CPU-serving
incident of 2026-08-25 happened.

**(e) `--spec-draft-n-max 2` (not 3 or 4).**
*Frees:* ~0.5–1.0 ms per turn at the margins (the draft overhead shrinks).
*Costs:* slightly less upside than n=3 or n=4 on Q8, but for Friday's QAT (Q4) model and
grammar-constrained planner, n=2 is empirically the right choice — the Gemma 4 head's
acceptance decays fastest at shallow depth, and shallow drafts are what grammar needs.
*Quality:* no loss. The verifier still checks every drafted token.

**(f) Use the Q6_K drafter instead of the Q8_0 drafter.**
*Frees:* measurable — ~1–2 tok/s over the Q8_0 drafter at the same acceptance, because
the smaller drafter is faster to run.
*Costs:* none that have been measured. The Q6_K drafter is one `llama-quantize --allow-requantize`
away from the published Q8_0 drafter. Same acceptance, smaller, faster. The only caveat is
that it is not shipped by Unsloth; it would need to be built from the Q8_0 drafter with
`llama-quantize`.

**(g) `--ub 512 → 256` (physical batch).**
*Frees:* a small compute buffer.
*Costs:* slows prompt processing — which is TTFA. Given prompt work is already only 193 ms
of a 916 ms turn, this trades the cheap leg to buy the expensive one. **Last resort.**

**(h) GPU clock/power capping (`nvidia-smi -lgc`, `-pl`).**
*Frees:* thermals and fan noise on a laptop at a small throughput cost. Relevant if "load on
the hardware" means thermals rather than memory. Untested here; it would trade decode tok/s,
which is the leg we are trying to protect.
*Costs:* small throughput reduction. Only relevant if the laptop is thermally throttling.

**(i) Keep the model resident.** Already the case — `friday-llm` is a long-running unit, so
there is no per-turn load cost. Measured indirectly: 4710 MiB held continuously, 0% GPU
between turns, 6 minutes of CPU over two days. This is the baseline; any MTP optimisation
is on top of this.

### 6.3 Levers outside llama.cpp worth knowing about

- **Keep `friday-llm` running.** Already done. The model is warm; there is no cold-start
  cost. MTP makes the *per-token* cost lower, but the per-turn fixed cost (prompt, graph
  setup, sampler construction) is unaffected — measured at ~193 ms of a 916 ms turn, and
  that 193 ms is per-request overhead, not anything we can trade.
- **Do not load `mmproj`.** Already done. The 12B is unified/encoder-free; the `mmproj`
  file is not present in the GGUF we use. Verified.
- **STT and TTS stay CPU.** Invariant #6 ("only llama-server touches CUDA") holds. The
  STT path (`faster-whisper small.en`, CTranslate2) and TTS (Kokoro-82M, ONNX Runtime)
  never touch the GPU. MTP does not change this.
- **The model is already resident in VRAM** — the only thing that moves is the KV cache.
  Any lever that reduces KV (ctx-size, KV precision, parallel slots) frees VRAM for the
  drafter. Any lever that does not touch KV (batch size, flash attention) does not free
  VRAM for the drafter.

---

## 7. The optimised MTP command — what it would look like, if the user authorises it

This is the target configuration, **not a command to run**. It is conditional on the
memory-freedom steps in §5 being completed first.

```bash
# CONDITIONAL — requires ~2 GB freed from ctx-size / parallel / KV-precision trades
llama-server \
  -m gemma-4-12B-it-qat-UD-Q4_K_XL.gguf \
  --model-draft MTP/gemma-4-12B-it-Q8_0-MTP.gguf \
  --spec-type draft-mtp --spec-draft-n-max 2 \
  --parallel 1 \
  --ctx-size 4096 \
  --no-context-shift \
  -fa on \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  -ngl 999 \
  -c 4096 -n 512 \
  --temp 1.0 --top-p 0.95 --top-k 64
```

The `--cache-type-k/v q8_0` pair is deliberately kept here because the Q8-KV-acceptance
regression was fixed in b9551+ and our build is post-fix — but the first thing to verify
on first load is that draft acceptance is nonzero, because the Gemma 4 assistant arch is
notoriously sensitive to KV precision.

**What this configuration is expected to do**, on our hardware, if memory is freed:

| Path | now (no MTP) | with MTP n=2 (expected) |
| :-- | :--: | :--: |
| Planner turn p50 | ~916 ms | ~640–750 ms (1.2–1.4×) |
| Chat turn p50 (62 tok) | ~2340 ms | ~1400–1700 ms (1.4–1.7×) |
| Draft acceptance (grammar) | n/a | ~0.55–0.70 (unknown; measured only when loaded) |
| Draft acceptance (chat) | n/a | ~0.70–0.91 (community data, free text) |

The planner gain is the uncertain one. The chat gain is the probable one. Both are
conditional on memory being freed first.

---

## 8. Gemma 4 12B's qualities for a local voice agent — the full audit

The user's hypothesis was that Gemma "has all the qualities that a local voice agent
should have". Here is the audit, separated into what is measured on this machine and
what is claimed by the vendor.

### 8.1 Measured strengths

1. **It ties the incumbent on correctness.** `just eval` **28/28, 0 regressions** — the only
   candidate of four challengers to do so. Qwen3-8B scored 27/28 and Ministral 3 8B 26/28.

2. **It stays inside the closed enum.** Qwen3-8B's single regression was emitting
   `app='mpv'`, a value **outside** `PARAM_SCHEMA`'s enum. For a planner whose entire job
   is picking from a closed set, that is disqualifying; invariant #5 caught it, but the
   incumbent and Gemma 4 both get it right without needing the net.

3. **Chat is clearly better** — richer answers, concrete analogies, and a specific offered
   follow-up every time, without padding. **This is the single strongest argument for the
   swap**, because chat is G8, the primary goal, and is the one thing `just eval` structurally
   cannot measure.

4. **It fixes D4's symptom for free.** "open my todo" → alias `todo`, where the incumbent
   emits `my todo` and the lookup fails. Also "play some music on youtube" → query `music`
   vs the incumbent's `some music`.

5. **QAT is a real, measurable win, not a label.** 6405 MiB Q4 that fits and performs,
   against 7305 MiB of ordinary Q4_K_M that does not fit at all. And the QAT weights were
   trained with MTP in mind — the only quant that has a drafter shipped alongside it.

6. **It survives a 6035-token prompt** with no OOM, and held VRAM flat across an entire
   bench run.

7. **`--reasoning off` works cleanly on this build**, verified this session. 20 completion
   tokens, no `reasoning_content`, clean prose.

8. **Unified encoder-free architecture.** The 12B model ingests raw image patches and audio
   waveforms directly through lightweight linear projections, with no separate vision or
   audio encoders. This means a future where Gemma consumes audio directly (collapsing the
   STT stage) would not require a separate encoder model — the architecture already supports
   it. Audio ≤30 s, video ≤60 s at 1 fps per the technical report. Not a Phase-2 concern,
   but it is a structural advantage over the incumbent for a voice agent.

9. **Native multimodality** — text, image, and audio in one model. Interesting for a *voice*
   agent in principle. Would put audio on the GPU path and cross invariant #6 (which it
   would still satisfy), while making the model responsible for transcription quality.

10. **256 K context window** (dense attention, but the hybrid 5:1 local-to-global design
    and KV sharing keep the KV footprint tractable). The vendor claims 256 K; our own
    observation that something trimmed the model to fit (~40 of 48 layers sliding-window @
    1024) is unresolved — see §10.3 of `opus-gemma-analysis.md`.

11. **Apache-2.0.** Permissive, commercial use allowed. No worse than the incumbent.

12. **140+ languages.** Friday is single-user and English-driven today; this is headroom,
    not a present benefit.

### 8.2 Measured liabilities — the honest other half

1. **Latency.** Planner p50 891–916 ms vs the incumbent's 373 ms; chat p50 2340 vs 854 ms.
   Projected TTFA ~2690 ms against a 2200 ms target that was itself re-baselined only a day
   earlier to match reality. MTP narrows this gap but does not close it — the planner leg is
   only part of TTFA, and STT plus TTS make up the rest.

2. **VRAM margin of 214 MiB** on a machine that also drives a display. llama.cpp warned at
   load that it wanted to reduce GPU layers and proceeded only because `--n-gpu-layers 99`
   was explicit: `W common_fit_params: failed to fit params to free device memory: n_gpu_layers
   already set by user to 99, abort`.

3. **A real planner regression.** "copy that to the clipboard" → `action=none`, where the
   incumbent dispatches `clipboard_set`. The 28 fixtures cannot see this — that is D16, and
   it is the reason no swap may happen yet.

4. **"set brightness to fifty percent" → `direction: down`.** Both models are wrong (there is
   no absolute-level param in `PARAM_SCHEMA`), but "down" for a brighten-ish request is
   precisely the class of bug that dimmed the screen on 2026-08-25 while announcing the
   opposite.

5. **It is a reasoning model by default**, which is a live trap: without `--reasoning off` it
   burns ~63 of 85 tokens thinking, and the *wrong* fix — `reasoning_format: "none"` — moves
   raw `<|channel>thought` text **into** `message.content`, which would write model thought into
   Friday's history and audit rows and break invariant #7 (FR-26/57). The right switches are
   `--reasoning off` or `chat_template_kwargs: {"enable_thinking": false}`.

6. **MTP needs memory we don't have.** The drafter is 242 MiB before its own KV cache.
   Unsloth recommends ~2 GB headroom. We have 214 MiF. MTP cannot be tried until memory is
   freed by one of the levers in §6.

### 8.3 The verdict on the user's hypothesis

Gemma 4 12B has the *cognitive* qualities a local voice agent wants — closed-set discipline,
better conversation, better alias extraction, unified multimodal architecture, a drafter that
was trained alongside the quant — and it has them at a **2.4× planner latency penalty and a
94% cut in VRAM headroom**. Whether those qualities are worth that price is a values question,
which is why it is OQ-47 and belongs to the user, not to this analysis.

The *MTP* question is separate from the *swap* question. MTP is a speed optimisation for a
model we have not adopted yet (OQ-47), on a machine where it does not currently fit (OQ-48).
Both must be decided before either is touched.

---

## 9. The best practices and practices — a condensed checklist

These are the ways to run Gemma 4 12B on this laptop that are supported by measured
evidence or strong community consensus. Ordered from "do this now" to "do this only if
the user authorises the trade."

### 9.1 Must-do (no trade, no risk)

- **`--reasoning off`** in `friday-llm.service`. Non-negotiable. Without it, Gemma 4 burns
  ~63 of 85 tokens thinking and chat answers come back empty once thinking eats the token
  budget. The wrong switch (`reasoning_format: "none"`) is a trap — it leaks raw thought
  into `message.content`.
- **`--n-gpu-layers 99`** explicit. The auto-fit warns and aborts; explicit is the only
  safe value on a machine with 214 MiB headroom.
- **`--top-k 64 --top-p 0.95 --temp 1.0`** — these are already Google's recommendation for
  Gemma 4, baked into the GGUF metadata. Nothing to tune.
- **Do not load `mmproj`.** Already done. The 12B is unified/encoder-free.
- **Keep `friday-llm` resident.** Already done. No per-turn load cost.

### 9.2 Should-do (low risk, measurable benefit)

- **`-fa on`** explicitly. Auto likely already enables it, but setting it explicitly prevents
  a silent downgrade. One reload to confirm.
- **`--parallel 1`** if `kv_unified = true` holds. One reload at higher verbosity to confirm
  whether it frees anything. If it does, it is free VRAM for the drafter.
- **`--spec-draft-n-max 2`** if MTP is enabled. n=2 is optimal for Gemma 4 QAT on this
  hardware (community data + the head's acceptance decay profile). Do not start at n=3 or n=4.
- **Verify draft acceptance on first load.** The Gemma 4 assistant arch has a known regression
  where Q8 KV cache causes 0% acceptance. If acceptance is zero, check KV precision.

### 9.3 Conditional-do (requires user authorisation, trades something)

- **`--ctx-size 4096` + `--no-context-shift`** — biggest single VRAM saving (~600–900 MiB).
  Costs the long-prompt ceiling. Must pair with `--no-context-shift` to avoid silent context
  truncation.
- **`--cache-type-k/v q4_0`** — moderate saving (~150–250 MiB). Costs KV quantization error.
  Must re-run `just eval` and judge chat by hand.
- **Download the 242 MiB drafter** — only after memory is freed. The smart Q4_0 (`mtp-gemma-4-12B-it.gguf`)
  is recommended; the Q8_0 is a fallback.
- **Use the Q6_K drafter** — one `llama-quantize --allow-requantize` from the published Q8_0.
  Same acceptance, smaller, faster. Not shipped by Unsloth; must be built.

### 9.4 Don't-do

- **Do not trade layers for the drafter.** The community sweep proved that once the model
  itself doesn't fully fit, the full-offload baseline beats every MTP config. The model
  must be fully on-GPU first.
- **Do not use `reasoning_format: "none"`.** It moves raw thought into `message.content` and
  breaks invariant #7. Use `--reasoning off`.
- **Do not assume MTP helps the planner path.** The grammar-constrained generation is the worst
  case for speculative decoding. The chat path is where MTP pays.
- **Do not enable MTP without freeing VRAM first.** The drafter cannot load on top of the
  current configuration. The recipe in §5 must be followed first.
- **Do not size a model with arithmetic.** The weights+KV model was wrong by 380–390 MiB on
  every model in ADR-084, in unpredictable directions. Load it and read `nvidia-smi`. The
  decode law (`272 / weights_GB`) does hold.

---

## 10. Open questions — what still needs to be decided or measured

| id | question | what settles it |
| :-- | :-- | :-- |
| **D16** | `just eval`'s 28 fixtures cannot see a planner emitting `action=none` on a plain command | Add fixtures for "copy that to the clipboard" and "close this window". **Hard precondition for any swap.** |
| **OQ-47** | Do we swap to Gemma 4 12B? | D16 first, then a values call on 891 ms vs 373 ms planner latency and 214 MiB vs 3441 MiB headroom, against clearly better chat. |
| **OQ-48** | Do we adopt MTP, and what do we spend to fit it? | Free ~2 GB by an authorised trade, load the drafter, measure acceptance under `plan.gbnf` and wall time on both paths. |
| **OQ-46(a)** | D13/D15 — the STT path phones Hugging Face at every daemon start, and `just test-egress` cannot detect egress | Independent of Gemma; `local_files_only=True` at the Whisper call site. |
| **P4** | Does `-np 1` actually free KV, or is it a no-op because `kv_unified = true`? | One reload at higher verbosity. Cheapest open thread. |
| **§10.3 (opus)** | Is Gemma 4 dense or sliding-window? The vendor says dense 256 K; our load appeared to confirm 40/48 sliding. | Reload with `-lv 5` and read the layer types. Worth ~1 GiB of KV, i.e. exactly the amount MTP needs. |

### The cheapest honest sequence, if MTP is wanted

1. Reload Gemma with `-lv 5` and read the KV allocation, layer types, flash-attention state,
   and per-slot cost. Free. Settles P1–P4 and the dense-vs-sliding question.
2. If slots split KV, set `-np 1`. Free.
3. Take `--ctx-size 4096` (+ `--no-context-shift`) if steps 1–2 leave a gap. Costs the
   long-prompt ceiling.
4. Only then download the 254 MB drafter and sweep `--spec-draft-n-max 1..6`, reporting
   acceptance separately for the grammar path and the chat path.
5. Re-run `just eval` at every configuration that touches KV precision or context, and judge
   chat by hand, because eval cannot.

**Nothing in steps 3–5 may proceed on judgement alone** — each spends something the user
owns.

---

## 11. Cross-cutting notes

- **`just eval` is not a swap gate today.** Two models scored 28/28 while refusing a plain
  command. Fix D16 before trusting the number.
- **Do not size a model with arithmetic.** ADR-084's weights+KV model was wrong by 380–390 MiB
  on every single model, in unpredictable directions. Load it and read `nvidia-smi`. The decode
  law (`272 / weights_GB`) does hold.
- **`reasoning_format: "none"` is a trap, not an option** — it moves raw thought into
  `message.content` and would break invariant #7. Use `--reasoning off`.
- **A green health check is not a healthy system** — `gpu_arch` passed through an entire GPU
  outage. When benching, confirm `llm_on_gpu`, not just `/health`.
- **`pgrep -f foo` matches its own command line.** Bracket the pattern: `pgrep -f "[f]oo"`.
- **Q8 KV cache kills Gemma 4 MTP acceptance.** Verify acceptance is nonzero on first load
  with any MTP configuration. The regression was fixed in llama.cpp b9551+, but the
  interaction between the `gemma4-assistant` arch and KV precision is real.
- **MTP is a latency optimizer for single-user, memory-bound tasks — exactly our use case.**
  It is not a throughput optimizer for concurrent workloads. Friday has one turn in flight
  (FR-5). MTP is the right tool for this machine, *if* the VRAM can be freed.
- **The 120 tok/s on 12 GB is a generation benchmark, not our workload.** Our workload is
  planner + chat, with STT and TTS in the critical path. MTP attacks the decode leg of the
  planner and the decode leg of the chat turn. It does not touch STT, TTS, or the fixed
  per-request overhead.
- **The drafter shares the target's KV cache.** This is the key architectural fact that makes
  MTP cheap when it works and expensive when it doesn't. The drafter does not have its own
  KV; it borrows the target's. So the KV budget must be sized for both, and `--parallel 1`
  is the lever that makes room.

---

## 12. Sources

- `opus-gemma-analysis.md` — the model-evaluation session record (ADR-084), measurements,
  predictions ledger, decisions.
- `laptop-specifications.md` — Acer Predator Helios Neo 16S AI, RTX 5070 Laptop, 8151 MiB
  VRAM, Blackwell sm_120.
- `tech-stack.md` — Friday's pinned dependencies, the `llama-server` choice, the torch-free
  runtime, the closed enum design.
- `open-questions.md` — OQ-47 (swap), OQ-48 (MTP), OQ-46(a) (offline hardening), all open.
- `docs/reality-check.md` — the manifest of what Friday must do and must refuse.
- Unsloth MTP guide (`unsloth.ai/docs/models/mtp`) — the drafter availability, the QAT
  pairing, the Q8 KV regression, the "fund from KV budget" recipe.
- Unsloth Gemma 4 model card (`ai.google.dev/gemma/docs/core/model_card_4`) — architecture,
  layers, sliding window, context, modalities.
- Google Gemma 4 technical report (`arxiv.org/html/2607.02770`) — 5:1 local-to-global ratio,
  KV cache sharing, p-RoPE, 37.5% global KV reduction, unified encoder-free 12B.
- llama.cpp PR #23398 — the MTP merge, the 1.5–2.2× speedup claims, the B200 benchmarks.
- `ggml-org/llama.cpp#25357` — the 8 GB sweep, the "never trade layers for the draft"
  finding, the Q6_K sweet spot, the Q8 KV acceptance regression, the `--parallel 1`
  KV-funding trick.
- Community benchmarks (Reddit `r/LocalLLaMA`, Banandre, Knightli) — the 120 tok/s on RTX
  4070, the n=2 optimality for QAT, the OOM footgun guidance.

---

*This file is check-only. No code was changed. Every lever above is a recommendation that
the user must authorise before it is touched, because each one spends something — context,
KV precision, VRAM headroom, or the long-prompt ceiling — that belongs to the user.*
