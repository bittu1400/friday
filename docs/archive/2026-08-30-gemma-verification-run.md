> **ARCHIVED 2026-08-30. This is the RAW EVIDENCE for the verification round,
> not an analysis.** Its findings are carried into `gemma-brief.md` (repo root)
> and the 2026-08-30 verification block in `progress.md`. Kept because the
> headroom table here is the primary measurement record -- nine `llama-server`
> loads, VRAM read from `nvidia-smi` at steady state.

---

# gemma-experiments-todo.md — check-phase run list and RESULTS

**Written and executed 2026-08-30. Check phase: NO CODE CHANGED, NOTHING DOWNLOADED.**
Scratch/working file, untracked. Fold into `progress.md` + `opus-gemma-analysis.md`
when the round closes.

## The question this round answers

**REFRAMED by the user mid-round:**

> "MTP is not the important part, the most available breathing room this laptop
> can get is. The better the breathing room, the smoother the workflow."

So the deliverable is **how much VRAM headroom this card can be given, with which
model, at what cost to quality.** MTP demotes to one possible use of headroom.

**Answer: Gemma 4 12B goes from 226 MiB free to 740 MiB free by changing one
flag, at zero cost to anything. At 664 MiB free it also gets double the context
window it has now.** Details below.

---

## Status

| id | task | status |
| :-- | :-- | :-- |
| E0 | baseline captured | **DONE** — 4720/3028 MiB, selftest 8/8 |
| E1 | Gemma `-lv 5` load, read layers/KV/flash-attn | **DONE** — see §1, §2 |
| E2 | Gemma headroom sweep, 6 configs | **DONE** — see §3 |
| E3 | Qwen headroom sweep, 3 configs | **DONE** — see §3 |
| E4 | the headroom table | **DONE** — §3 is the deliverable |
| E5 | llama.cpp source: does the drafter own its KV? | **DONE** — yes, §5 |
| E6 | HF API: real MTP filenames | **DONE** — opus right, ling-flash wrong |
| E7 | llama.cpp #25357 verification | **DONE** — real, §6 |
| E8 | architecture claims vs vendor | **DONE** — settled from our own log, §1 |
| E9 | restore + prove | **DONE** — 4706/3042, selftest 8/8, `llm_on_gpu` PASS |
| E10 | write-up + disposition of the four analyses | **DONE** — §7 |

Method: throwaway `llama-server` on `:8081`, `friday-llm` stopped for the
duration, `-lv 5`, VRAM read from `nvidia-smi` at steady state after `/health`
returned. Gemma file already on disk. Nine loads total.

---

## 1. Architecture — opus §10.3 is SETTLED, read off our own load

The contradiction opus flagged (vendor says "dense, 256K"; our own
`PREDICTIONS.md` assumed 40/48 sliding-window) is resolved: **both are true.**

```
n_ctx_train            = 262144            <- P2 CONFIRMED, 256K
n_layer                = 48
n_swa                  = 1024
is_swa_any             = 1
sliding_window_pattern arr[bool,48] = [true,true,true,true,true,false,...]
```

Five sliding then one global, repeating: **40 SWA layers @1024, 8 global.** The
5:1 local-to-global ratio both opus and ling-flash cited is correct. ling-flash's
"only 3 of 48 layers cache a full 1024-window, the rest use 512" is not.

**Flash attention (P3) — CONFIRMED ON, but read the mechanism:**

```
llama_init_from_model: enabling flash_attn since it is required for quantized V cache
llama_context: flash_attn = enabled
```

It is force-enabled *as a side effect of `--cache-type-v q8_0`*. With an f16 V
cache the log prints `flash_attn = auto` and only a debug line
(`resolve_fused_ops: Flash Attention enabled`) proves it resolved on. Setting
`-fa on` explicitly costs nothing and removes that ambiguity.

---

## 2. Where the VRAM actually goes — the finding that reorders everything

Gemma 4 12B, stock flags (ctx 8192, q8_0 KV, `--parallel` auto):

```
llama_kv_cache_iswa: creating non-SWA KV cache, size = 8192 cells
llama_kv_cache: size =   68.00 MiB ( 8192 cells,  8 layers, 4/1 seqs)
llama_kv_cache_iswa: creating     SWA KV cache, size = 4608 cells
llama_kv_cache: size =  765.00 MiB ( 4608 cells, 40 layers, 4/1 seqs)   <- 92% of KV
```

Full accounting: model 6390 MiB (+540 MiB kept on host) + KV 833 + compute 135
+ ~153 CUDA context = 7511. Measured 7512. Reconciles.

**`4608 = 4 × 1024 + 512` (`n_seq_max × n_swa + n_ubatch`).** The SWA cache grows with sequence count, and
`--parallel` auto gave us four. `kv_unified = true` did **not** make the slots
share — it applies to the global cache, not the sliding-window one.

Two consequences, both of which invert the existing record:

- **`--ctx-size` scales only the 68 MiB global cache.** The 765 MiB SWA cache is
  fixed at `n_swa + n_ubatch` per seq and does not care about `--ctx-size` at all.
- **`--parallel` scales the 765 MiB one.**

---

## 3. THE HEADROOM TABLE — the deliverable

Card total 8151 MiB; **7745 MiB usable** (406 MiB is driver/context reserve —
the desktop holds ~0, the display is on the Intel iGPU, measured: 2 MiB used with
no model loaded). Every row measured, not computed.

### Gemma 4 12B QAT (UD-Q4_K_XL)

| # | configuration | held | **free** | KV | what it costs |
| :-- | :-- | --: | --: | --: | :-- |
| G1 | stock — auto slots, q8_0 KV, ctx 8192 | 7522 | **226** | 833 | *(the status quo)* |
| **G2** | **`-np 1`** | 7008 | **740** | 323 | **nothing** |
| **G9** | **`-np 1 --ctx-size 16384`** | 7084 | **664** | 391 | **nothing — and doubles context** |
| G3 | `-np 1 --ctx-size 4096` | 6970 | 778 | 289 | half the context window |
| G5 | `-np 1` + `q4_0` KV | 6856 | **892** | 171 | KV precision (needs eval + ear) |
| G7 | `-np 1` + f16 KV (no `--cache-type`) | 7292 | 456 | 608 | −284 MiB vs q8 |

### Qwen2.5-7B-Instruct Q4_K_M (the incumbent)

| # | configuration | held | **free** | KV | note |
| :-- | :-- | --: | --: | --: | :-- |
| Q1 | stock (= live `friday-llm.service`) | 4706 | **3042** | 238 | |
| Q2 | `-np 1` | 4706 | **3042** | 238 | **no change at all** |
| Q3 | `-np 1` + `q4_0` KV | 4594 | 3154 | 126 | +112 MiB |

**Why the lever works on one model and not the other:** Qwen is full GQA — one
unified 238 MiB cache regardless of `4/1 seqs` or `1/1 seqs`. Gemma is hybrid
sliding-window, and the SWA half is per-sequence. **`-np 1` is a Gemma-specific
lever and it exists precisely because of the architecture that let a 12B fit at
all.** Friday is strictly one turn in flight (FR-5), so the other three slots can
never be used under any circumstance.

### Two corrections to the existing record

1. **P4 was falsified in the opposite direction from the guess.** opus §10.2 and
   ling-flash §6.2(c) both reasoned "`kv_unified = true` suggests they share one
   cache, so `-np 1` is probably a no-op." It is worth **514 MiB**.
2. **P8 is wrong by roughly 20×.** Both files rank `--ctx-size 8192→4096` as
   "**(a)** the biggest single saving, estimated 600–900 MiB." Measured: **38 MiB**,
   and it costs half the context window. It is the *worst* lever on the list, not
   the best. `--ctx-size` was estimated by arithmetic on a dense-attention mental
   model; this model is 40/48 sliding-window.

The project's own rule caught this one: *"Do not size a model with arithmetic.
Load it and read `nvidia-smi`."*

---

## 4. What this does to the Gemma question (OQ-47)

The single loudest argument against the swap was **"214 MiB headroom on a machine
that also drives a display."** That number was an artifact of an unset flag.

- Real headroom at the same context: **740 MiB, 3.3×**.
- Or **664 MiB with a 16384-token window** — double what Friday runs today, which
  retires the "web-search turn overflows the context" worry outright.
- Or **892 MiB** if q4_0 KV survives `just eval` and a listening test.

Nothing about latency changed: planner p50 891–916 ms vs 373 ms stands, and
**D16 is still a hard precondition.** But the memory objection is materially
smaller than the record says.

---

## 5. MTP, as a footnote (E5)

From `/opt/llama.cpp/src/llama-model.cpp:2154,2207,2326` — the draft context
builds its **own** `llama_kv_cache`, filtered to the nextn layer(s) only, a plain
attention cache rather than the hybrid SWA wrapper, and it is passed
`cparams.n_seq_max` too. So:

- ling-flash §11 — "the drafter does not have its own KV; it borrows the
  target's" — is **wrong**. Its §4.3 ("before its own KV cache") is right. The
  file contradicts itself and the source settles it.
- The draft KV is small (one layer), so `740 − 242 = ~500 MiB` for weights leaves
  real room. **MTP now looks plausible where it was impossible.** Unmeasured, and
  still gated on OQ-47/OQ-48 and the user's download decision.

---

## 6. Verification of the citations (E6, E7)

**E6 — HF API, `unsloth/gemma-4-12B-it-qat-GGUF`, lastModified 2026-07-17:**
`mtp-gemma-4-12B-it.gguf`, `MTP/mtp-gemma-4-12B-it-{Q4_0,Q8_0,BF16,F16}.gguf`.
**opus is exactly right. ling-flash's `MTP/gemma-4-12B-it-Q8_0-MTP.gguf` does not
exist** — it rewrote a fact this repo had already captured correctly.

**E7 — `ggml-org/llama.cpp` discussion #25357 is REAL:** *"MTP speculative
decoding on 8GB GPUs: head quantization sweep + the KV-budget recipe (40 tok/s,
Gemma 4 12B)"*, 2026-07-06. It really does contain "never trade layers for the
draft", the `--parallel 1` KV-funding recipe, the Q6_K drafter, and
"Q8→Q2 acceptance only drops 55%→49% (n_max=2)".

**Its recommended command uses `--cache-type-k q8_0 --cache-type-v q8_0` and
`-c 16384`.** Therefore ling-flash §4.6 — *"A critical Gotcha: Q8 KV cache kills
draft acceptance… 0% acceptance… fixed in b9551+"* — is **fabricated**, and it
inverts what its own cited source says. Acting on it would have cost 284 MiB
(G2→G7) for nothing.

Independent corroboration worth noting: the source's `--parallel 1` recipe and my
G2 measurement were arrived at separately and agree.

---

## 7. Disposition of the four analyses

| file | verdict | action |
| :-- | :-- | :-- |
| `opus-gemma-analysis.md` | The only measurement record. Two lever *rankings* now falsified (§3), everything else stands. | **Keep tracked, in place.** Patch §7.2 and §10.2 with the measured numbers, add the SWA/per-seq mechanism, mark P2/P3/P4/P8 resolved. `CLAUDE.md` already points here by name. |
| `gpt-gemma-analysis.md` | Zero fabrication, zero new information. Faithful. Inherited opus's wrong lever ranking (its priority-7 "set one request slot only if measurement shows…" was the right instinct, ranked too low). One stale claim: "`nvidia-smi` cannot communicate with the driver" — it works. | **Fold its priority table into opus §7 and archive.** It is a summary of a file we keep. |
| `ling-flash-gemma-analysis.md` | Real citations, real central insight, **unreliable in the details**: fabricated filenames, self-contradicting KV claim, and a fabricated "critical gotcha" that inverts its own source. ~70% is verbatim opus. | **Harvest, then archive with a header.** Worth keeping from it: #25357 as a source, the Q6_K drafter, "never trade layers for the draft", `-c 16384`. Everything harvested must be re-checked against the source, not copied. |
| `gemini-gemma-analysis.md` | Wrong model generation (Gemma 2 traits on a Gemma 4 file), VRAM table invented, prompt size wrong by 2.2×, drafter size wrong by 2.7×, fabricated CPU-core partition, and a proposed service file that names a nonexistent GGUF and would not start. | **Archive with a `WRONG — DO NOT CITE` header. Do not delete.** |

**Why archive rather than delete.** `docs/archive/` already holds
`review-gemini.md` and `review-gpt.md`, which `CLAUDE.md` labels *"archived inputs
and contain wrong technical claims — do not cite them as current."* Same
situation, same treatment. The failure mode is worth keeping: gemini sized a
model with arithmetic and got a "+971 MiB slack, MTP fits" answer, which is the
exact mistake ADR-084 was written to prevent — and today's round is the second
time that rule has paid. Deleting the evidence deletes the lesson. Leaving them
at repo root is the actual hazard: a future session greps four
`*gemma-analysis.md` files and cannot tell which one to believe.

Suggested: `docs/archive/2026-08-30-gemma-{gemini,gpt,ling-flash}.md`, each with a
one-paragraph header saying what it got wrong and pointing at
`opus-gemma-analysis.md`.

---

## 8. Open, and what would settle it

| id | question | status |
| :-- | :-- | :-- |
| **P4** | does `-np 1` free KV? | **CLOSED — yes, 514 MiB on Gemma, 0 on Qwen.** |
| **P8** | does ctx 8192→4096 free 600–900 MiB? | **CLOSED — no, 38 MiB.** |
| **P1/P2/P3** | layers, `n_ctx_train`, flash attention | **CLOSED** — 40 SWA + 8 global; 262144; enabled. |
| §10.3 | dense or sliding-window? | **CLOSED — hybrid; both vendor claims true.** |
| **D16** | eval cannot see `action=none` on a plain command | **still open, still the hard precondition.** Code change. |
| **OQ-47** | swap to Gemma? | Memory objection is much weaker. Latency objection unchanged. User's call. |
| **OQ-48** | adopt MTP? | Now plausible (~500 MiB for a 242 MiB drafter). Needs the download and an acceptance measurement under `plan.gbnf`. |
| new | does `q4_0` KV hold quality? | G5's 892 MiB is real; the quality is untested. Needs `just eval` + a listening test. |
| new | `-np 1` on the live service | One-line change to `friday-llm.service`. No-op for Qwen today, correct by FR-5, and worth 514 MiB the day Gemma lands. **Code change — not this phase.** |
