# gemma-brief.md — the verified brief

**Written 2026-08-30. Supersedes four analysis files, all now in `docs/archive/`
(`2026-08-30-gemma-{opus,gpt,ling-flash,gemini}.md`).**

This file exists to be the **input to the next analysis round**, not another
analysis. Everything in it is either measured on this machine or verified
against a primary source, and every claim says which. Where the archived files
disagree with this one, this one is right — the disagreements are itemised in
each archived file's header.

**Read this before analysing the model question. Do not re-derive it.**

---

## 0. The question for the next round

The first round was framed on **MTP**, and every analyst optimised for that. The
user has re-framed it:

> "MTP is not the important part, the most available breathing room this laptop
> can get is. The better the breathing room, the smoother the workflow."
> …
> "VRAM is primary, but if we can also optimize others, then even better.
> However, quality is our top priority and so is VRAM. **Though quality wins in
> all.**"

So the question to answer is:

> **How much headroom can this laptop be given, on which model, without giving
> up quality — where quality outranks headroom, and headroom outranks
> everything else?**

MTP is one possible use of headroom. It is not the goal, and it may not be the
best use. Any lever — llama.cpp flags, model choice, quantization, scheduling,
CPU/RAM/thermal work — is in scope, and a lever that buys memory by costing
quality loses by definition.

**Two things every previous round got wrong, so start from them:**

1. **Do not size anything with arithmetic.** ADR-084's weights+KV model was
   wrong by 380–390 MiB on all five benched models, in unpredictable
   directions. Today it was wrong by **20×** on the context lever. Load it and
   read `nvidia-smi`.
2. **Do not reason about this model as if attention were dense.** 40 of its 48
   layers are sliding-window. That single fact inverts the lever ranking (§3).

---

## 1. The hardware envelope — measured

```
GPU              NVIDIA GeForce RTX 5070 Laptop (Blackwell, sm_120 / compute 12.0)
VRAM total       8151 MiB
VRAM usable      7745 MiB      <- 406 MiB reserved, not attributable to a process
desktop VRAM     ~0 MiB        <- MEASURED: 2 MiB used with no model loaded
memory bandwidth ~272 GB/s     (ADR-084)
CPU              Intel Core Ultra 9 275HX (24 cores)
RAM              16 GB DDR5
llama.cpp        build b1-b21e4de, 2026-08-22, CUDA, sm_120a kernels (ADR-021)
```

**Correction to the archived record.** The opus file's §3 says "~406 MiB held by
the desktop with no model loaded". The *number* is right (8151 − 7745); the
*attribution* is not. **Measured:** with no model loaded `memory.used` is
**2 MiB**, so nothing is allocated to the desktop. The 406 MiB is the gap between
total and free — reserved, not held by any process. **I did not determine what
reserves it**; "driver/context overhead" is the usual explanation and is
inference, not a measurement here.

Supporting, and also measured: an Intel Arrow Lake-S iGPU is present
(`00:02.0`, with its own `/dev/dri` render node), and `nvidia-smi` shows the
NVIDIA card carrying a single **compute** client (`llama-server`) and no graphics
clients. That is consistent with the desktop rendering on the iGPU, though I did
not read Hyprland's render node directly. Either way the practical fact is
measured: **the dGPU is not being used by anything but Friday.**

Decode is bandwidth-bound and obeys a law that has held on every model measured:

```
decode tok/s  ~=  272 / weights_GB
```

Predicted 40 tok/s for Gemma 4; measured 41.0. **The memory half of that
arithmetic does not hold. Only the decode half does.**

---

## 2. Model identity — pinned

```
repo    unsloth/gemma-4-12B-it-qat-GGUF        (HF lastModified 2026-07-17)
quant   UD-Q4_K_XL   (Unsloth Dynamic QAT, not a stock Q4_K_M)
file    gemma-4-12B-it-qat-UD-Q4_K_XL.gguf
bytes   6,716,356,800   (6405 MiB)
sha256  90fd44e29e0d7cffeb0fd00dc73cfdab9ed0b0e95306ecf7821ea634c940c370
path    ~/.cache/friday-model-eval/gguf/       (outside the repo: 6.3 GB)
gguf name metadata: "Gemma-4 12B IT (smart Q4_0, QAT-lossless)"
```

Incumbent, pinned the same way:

```
file    Qwen2.5-7B-Instruct-Q4_K_M.gguf
sha256  65b8fcd92af6b4fefa935c625d1ac27ea29dcb6ee14589c55a8f115ceaaa1423
path    ~/.local/share/friday/models/
```

`/props` reports `model_ftype: Q4_0` for the UD-Q4_K_XL file — the base type of
the dynamic mix. Do not "correct" the filename to match.

**QAT is load-bearing, not marketing.** The 6405 MiB QAT Q4 fits and performs;
bartowski's ordinary Q4_K_M of the same 12B is 7305 MiB and does not fit at all.

**MTP drafter files, verified against the HuggingFace API 2026-08-30:**

```
mtp-gemma-4-12B-it.gguf                    253,708,800   (repo root; -hf auto-discovers)
MTP/mtp-gemma-4-12B-it-Q4_0.gguf           253,708,800
MTP/mtp-gemma-4-12B-it-Q8_0.gguf           465,127,936
MTP/mtp-gemma-4-12B-it-{BF16,F16}.gguf     861,538,816
MTP/README.md
```

Nothing is downloaded. Any other spelling of these filenames in an archived file
is fabricated.

---

## 3. Architecture — and why it inverts the lever ranking

Read off our own `-lv 5` load, 2026-08-30. This closes the "unresolved
contradiction" the opus file flagged in its §10.3: **both vendor claims are true
simultaneously.**

```
n_ctx_train            = 262144        <- 256K context, as the vendor says
n_layer                = 48
n_swa                  = 1024
is_swa_any             = 1
sliding_window_pattern = [true,true,true,true,true,false, ...]   (48 entries)
```

Five sliding-window layers then one global, repeating: **40 SWA layers @1024
window, 8 global layers.** The 5:1 local-to-global ratio is real.

### The KV cache is two caches, and they scale differently

Stock flags (ctx 8192, `q8_0` KV, `--parallel` auto):

```
llama_kv_cache_iswa: creating non-SWA KV cache, size = 8192 cells
llama_kv_cache: size =   68.00 MiB ( 8192 cells,  8 layers, 4/1 seqs)
llama_kv_cache_iswa: creating     SWA KV cache, size = 4608 cells
llama_kv_cache: size =  765.00 MiB ( 4608 cells, 40 layers, 4/1 seqs)   <- 92% of KV
```

Full accounting, which reconciles to the megabyte:

```
model (CUDA0)      6390 MiB      (+ 540 MiB kept on host, mmap'd)
KV                  833 MiB
compute buffer      135 MiB
residual           ~154 MiB      <- NOT identified; the unexplained remainder
                  --------
                   7512 MiB      measured: 7512
```

**`4608 = 4 × 1024 + 512` — that is `n_seq_max × n_swa + n_ubatch`.**
The sliding-window cache grows with the number of sequences, and `--parallel`
auto resolved to 4. Confirmed against every probe: at `-np 1` it is
`1 × 1024 + 512 = 1536` cells in all five single-slot configurations, at the same
0.166 MiB/cell. `kv_unified = true` applies to the global
cache; it does **not** make the SWA cache shared.

Therefore:

- **`--ctx-size` scales only the 68 MiB global cache.** The 765 MiB SWA cache is
  `n_seq_max x n_swa + n_ubatch` cells and does not depend on `--ctx-size` at all.
- **`--parallel` scales the 765 MiB one.**

Every previous analysis had this backwards.

---

## 4. THE HEADROOM TABLE — measured, nine loads, `nvidia-smi` at steady state

Card usable: **7745 MiB**. `friday-llm` stopped, throwaway server on `:8081`.
`held` and `free` are `nvidia-smi` **total** figures; the per-process figure runs
~10 MiB lower (G1: 7512 process vs 7522 total). The §3 accounting uses the
per-process number.

### Gemma 4 12B QAT

| # | configuration | held | **free** | KV | cost to quality |
| :-- | :-- | --: | --: | --: | :-- |
| G1 | stock — auto slots, `q8_0` KV, ctx 8192 | 7522 | **226** | 833 | *(status quo)* |
| **G2** | **`-np 1`** | 7008 | **740** | 323 | **none** |
| **G9** | **`-np 1 --ctx-size 16384`** | 7084 | **664** | 391 | **none — and doubles context** |
| G3 | `-np 1 --ctx-size 4096` | 6970 | 778 | 289 | halves the context window |
| G5 | `-np 1` + `q4_0` KV | 6856 | **892** | 171 | KV precision — **UNTESTED** |
| G7 | `-np 1` + f16 KV | 7292 | 456 | 608 | none, but costs 284 MiB |

### Qwen2.5-7B-Instruct Q4_K_M (incumbent, = live `friday-llm.service`)

| # | configuration | held | **free** | KV | note |
| :-- | :-- | --: | --: | --: | :-- |
| Q1 | stock | 4706 | **3042** | 238 | |
| Q2 | `-np 1` | 4706 | **3042** | 238 | **no change whatsoever** |
| Q3 | `-np 1` + `q4_0` KV | 4594 | 3154 | 126 | +112 MiB |

### Why the lever works on one model and not the other

Qwen is full GQA — one unified 238 MiB cache at `4/1 seqs` and at `1/1 seqs`
alike. Gemma is hybrid sliding-window and the SWA half is per-sequence.
**`-np 1` is a sliding-window-architecture lever.** It exists because of the
same design that let a 12B fit on an 8 GB card at all.

Friday is strictly one turn in flight (**FR-5**), so slots 1–3 can never be used
under any circumstance. Setting `-np 1` gives up nothing that exists.

### Verified free levers, in order of value

| lever | worth | cost | status |
| :-- | --: | :-- | :-- |
| `-np 1` | **+514 MiB** (Gemma) / 0 (Qwen) | none | **measured** |
| `--ctx-size 8192 → 16384` | −76 MiB | none, and doubles the window | measured |
| `-fa on` explicit | 0 MiB | none | measured; see below |
| `--ctx-size 8192 → 4096` | +38 MiB | halves the window | measured — **the worst lever** |
| `q8_0 → q4_0` KV | +152 MiB | **unknown quality cost** | measured size, untested quality |
| `q8_0 → f16` KV | −284 MiB | none | measured |

**Flash attention.** With a quantized V cache it is force-enabled and the log
says so explicitly (`enabling flash_attn since it is required for quantized V
cache`). With f16 KV the log prints `flash_attn = auto` and only a debug line
(`resolve_fused_ops: Flash Attention enabled`) proves it resolved on. It is on
either way. `-fa on` buys no memory but removes the ambiguity, for the same
reason `--n-gpu-layers 99` is explicit — a silent auto-downgrade is exactly how
the CPU-serving incident of 2026-08-25 happened.

**Levers that are already spent — do not re-litigate:**

| lever | status |
| :-- | :-- |
| Prompt-prefix caching | **Already on.** `cache_n 1222` of 1235; 13 new tokens per turn. `--cache-prompt` is on by default. Measured. |
| Grammar compilation | **Not a cost.** 1012 chars of GBNF = **0.3 ms**. Hypothesis raised and killed; do not re-test. |
| Multimodality | **Zero.** `/props`: `modalities: {vision:false, video:false, audio:false}`. No `mmproj` loaded. Measured. |
| Reasoning suppression | Correct with `--reasoning off`. Measured both ways. |
| Sampling defaults | Already Google's recommendation (temp 1.0, top_k 64, top_p 0.95), straight from the GGUF metadata. |
| `--spec-draft-backend-sampling` | **On by default.** Not a lever. |

---

## 5. Where a Gemma turn's milliseconds go — measured

System prompt: **4627 characters = 1222 tokens**, cached after the first turn.

```
planner:  742.6 ms  =  prompt 193.6 + decode 538.6 (22 tok) + 10.5 unaccounted
                       -> DECODE IS 72% OF THE TURN
chat:     1798 / 2166 / 1959 ms, decode 86-89% of each turn, 62-77 tokens
```

Planner p50 over 15 utterances: **915.7 ms** (min 729, max 1183), decode 41.4
tok/s. ADR-084 recorded 891 ms — reproduced.

The 193 ms is **not** prompt processing (only 13 tokens are new). It is fixed
per-request overhead — graph setup, sampler construction, HTTP. Nothing on the
prompt side can reduce it. It is unattributed and remains an open thread.

---

## 6. The five-model bench (ADR-084) — the correctness record

Identical flags matching `friday-llm.service`, Friday's **real** `plan.gbnf` and
`assemble_system`.

| metric | **Qwen2.5-7B** (current) | **Gemma 4 12B QAT** | Qwen3-8B | Ministral 3 8B | Ministral 3 14B Q3 |
| :-- | --: | --: | --: | --: | --: |
| weights | 4506 | 6405 | 4795 | 4958 | 6610 MiB |
| decode | **61.3** | 41.0 | 58.7 | 54.8 | 36.8 tok/s |
| planner p50 | **373** | 891 | 389 | 423 | 615 ms |
| chat p50 | **854** | 2340 | 1159 | 1990 | 2336 ms |
| `just eval` | **28/28** | **28/28** | 27/28 | 26/28 | **28/28** |

Three were deleted (16.4 GB reclaimed). **Gemma 4 is the sole retained
candidate.** Live TTFA p50 is 2172 ms (n=77, 2026-08-29); ADR-080's re-baselined
target is 2200 ms.

**Two paper predictions were falsified in this bench and are worth remembering:
a 12B fits, and a 14B fits BETTER than the 12B.**

---

## 7. Gemma 4 for this role — the honest ledger

### Measured strengths

1. **Ties the incumbent on correctness** — `just eval` 28/28, 0 regressions; the
   only challenger of four to manage it.
2. **Stays inside the closed enum.** Qwen3-8B emitted `app='mpv'`, outside
   `PARAM_SCHEMA`. Gemma does not need the net.
3. **Chat is clearly better** — richer, concrete, a specific follow-up every
   time, no padding. **The strongest argument for the swap**, because chat is
   G8 (the primary goal) and is the one thing `just eval` structurally cannot
   measure. **This one row is a human judgement recorded by the 2026-08-30
   evaluation session, not a measurement** — which is exactly why it cannot be
   re-checked by a fixture, and why OQ-49 needs an ear.
4. **Fixes D4's symptom for free** — "open my todo" → alias `todo` (incumbent
   emits `my todo` and the lookup fails).
5. **Survives a 6035-token prompt**, VRAM flat across a whole bench run.
6. **256K trained context** and, at `-np 1`, a 16384-token window costs 76 MiB.

### Measured liabilities

1. **Latency.** Planner p50 891–916 ms vs 373; chat 2340 vs 854. Projected TTFA
   ~2690 ms against a 2200 ms target. **This is now the primary objection.**
2. **A real planner regression** — "copy that to the clipboard" → `action=none`,
   where the incumbent dispatches `clipboard_set`. **The 28 fixtures cannot see
   it. That is D16, and it is a hard precondition for any swap.**
3. **"set brightness to fifty percent" → `direction: down`.** Both models are
   wrong (no absolute-level param exists in `PARAM_SCHEMA`), but "down" for a
   brighten-ish request is the class of bug that dimmed the screen on
   2026-08-25 while announcing the opposite.
4. **It is a reasoning model by default.** Without `--reasoning off` it burns
   ~63 of 85 tokens thinking. The *wrong* fix, `reasoning_format: "none"`, moves
   raw thought **into** `message.content` and would break invariant #7
   (FR-26/57). Use `--reasoning off` or
   `chat_template_kwargs: {"enable_thinking": false}`.
5. **VRAM margin.** At stock flags 226 MiB, which is why llama.cpp warns
   `failed to fit params to free device memory: n_gpu_layers already set by user
   to 99, abort` and proceeds only because `99` is explicit. **`-np 1` moves
   this to 740 MiB and largely retires the objection.**

### What is NOT an objection any more

The loudest argument against Gemma was "214 MiB headroom on a machine that also
drives a display". Both halves were wrong: the display is on the iGPU, and the
214/226 MiB was an artefact of an unset `--parallel`. **Real headroom is 740 MiB
at the same context, or 664 MiB at double the context.**

---

## 8. MTP — demoted to a footnote, with the facts kept

Not the goal any more. Recorded so nobody re-researches it.

- **The drafter exists for our exact file** (§2) and **our llama.cpp already
  supports it** — `--spec-type draft-mtp` and `--spec-draft-n-max` are in this
  binary's help. **No rebuild.**
- `--spec-draft-n-max` **defaults to 3**.
- **The drafter has its own KV cache.** From `/opt/llama.cpp/src/llama-model.cpp`
  (lines 2154, 2207, 2326): the MTP draft context builds a separate
  `llama_kv_cache` filtered to the nextn layer(s) — a plain attention cache, not
  the hybrid SWA wrapper — and it is passed `cparams.n_seq_max`, so `-np 1`
  helps it too. It is small (one layer).
- **It now plausibly fits**, where at 226 MiB it could not: 740 − 242 = ~500 MiB
  for the Q4_0 drafter's weights plus its small KV. Unsloth's generic "~2 GB
  headroom" guidance is not specific to this configuration.
- **Its upside is concentrated in chat** (62–77 free-text tokens), not the
  planner (~22 grammar-constrained tokens). Nobody has benchmarked speculative
  decoding under a GBNF grammar; planner upside could be near zero.
- **Primary source, verified real:** `ggml-org/llama.cpp` discussion **#25357** —
  "MTP speculative decoding on 8GB GPUs: head quantization sweep + the KV-budget
  recipe (40 tok/s, Gemma 4 12B)", 2026-07-06. Contains "never trade layers for
  the draft", the `--parallel 1` KV-funding recipe (independently reproduced
  here), the Q6_K drafter recommendation, and "Q8→Q2 acceptance only drops
  55%→49% (n_max=2)". Its recommended command **uses `q8_0` KV and `-c 16384`.**
- **A claim in the archived ling-flash file that q8_0 KV causes 0% draft
  acceptance is fabricated and inverts that source.** Do not act on it.

---

## 9. What is settled, and what is open

### Settled — do not re-measure

| claim | answer |
| :-- | :-- |
| `-np 1` frees KV? | **Yes — 514 MiB on Gemma, 0 on Qwen.** |
| ctx 8192→4096 frees 600–900 MiB? | **No — 38 MiB.** |
| Layer census | 48 layers: **40 SWA @1024 + 8 global**, 5:1 |
| `n_ctx_train` | **262144** |
| Flash attention | **on**, both KV precisions |
| Dense or sliding-window? | **Hybrid.** Both vendor claims true. |
| Grammar compile cost | **0.3 ms.** Dead hypothesis. |
| Prefix caching | **already on**, 1222 of 1235 cached |
| MTP drafter filenames | §2, from the HF API |
| Drafter owns its KV? | **Yes**, filtered to the nextn layer |

### Open

| id | question | what settles it |
| :-- | :-- | :-- |
| **D16** | `just eval`'s 28 fixtures cannot see a planner emitting `action=none` on a plain command | Add fixtures for "copy that to the clipboard" and "close this window". **Hard precondition for any swap** — the gate that would approve Gemma cannot see the regression it would admit. Code change. |
| **OQ-47** | Swap to Gemma 4 12B? | D16 first. Memory objection now much weaker; **latency is the live objection** (891 vs 373 ms planner). User's call. |
| **OQ-48** | Adopt MTP? | Now plausible. Needs the download, then acceptance measured **separately under `plan.gbnf` and on chat**. |
| **OQ-49** *(new)* | Does `q4_0` KV hold quality? | G5's +152 MiB is measured; the quality is not. `just eval` must stay 28/28 **and** chat judged by ear — eval cannot see chat, which is Gemma's whole reason for existing here. **Quality wins, so this is a real gate, not a formality.** |
| **OQ-50** *(new)* | Adopt `-np 1` on `friday-llm.service`? | One-line change. No-op for Qwen today, correct by FR-5 either way, worth 514 MiB the day Gemma lands. Needs restart + `just selftest` 8/8. |
| open | the unattributed 193 ms fixed per-request cost | Not prompt processing, not grammar. Unprofiled. |
| **OQ-46(a)** | D13/D15 — STT phones Hugging Face at daemon start; `just test-egress` cannot detect egress | Independent of the model, but it is why no offline claim here can be trusted. |

### Not yet examined at all — the "if we can also optimize others" surface

VRAM is primary and is now well characterised. These are untouched and are where
the next round has room to be original:

- **System RAM.** 16 GB shared by Whisper STT, Kokoro TTS, wake, speaker verify,
  the daemon, plus the user's browser and editor. Friday's real RSS under load
  has never been measured.
- **Thermals and power.** 70 W TGP laptop. `nvidia-smi -lgc` / `-pl` trade decode
  speed for heat and fan noise. If "smoother workflow" includes the fan, this is
  in scope. Untested.
- **CPU contention.** STT, TTS, AEC and VAD are all CPU and all in the turn's
  critical path. Contention with the user's own work is felt as latency. Note
  H6 was a whole class of blocking calls on the event loop, and
  `daemon.py:337` still types dictation on the loop.
- **The 540 MiB of Gemma kept on host** (`CPU_Mapped model buffer`). Not
  investigated. It is currently saving VRAM, so it may be a feature.
- **`--ctx-checkpoints` defaults to 32 per slot** (`min spacing = 8192`).
  Unexamined.
- **Compute buffer is 135 MiB** at `n_ubatch 512`. `-ub 256` would shrink it but
  slows prompt processing — which is TTFA. Prompt work is only 193 ms of a
  916 ms turn, so this trades the cheap leg for the expensive one. Last resort.

---

## 10. Rules this round paid for

- **Load it and read `nvidia-smi`.** Arithmetic was wrong by 380–390 MiB on five
  models and by **20×** on the context lever. The decode law
  (`272 / weights_GB`) is the only arithmetic that has held.
- **Check which architecture you are reasoning about.** Every wrong lever
  ranking here came from treating a 40/48 sliding-window model as dense.
- **Real citations do not make the surrounding sentences true.** The archived
  ling-flash file cites a real discussion and then states the opposite of what
  it says. Check the claim against the source.
- **A flag left at `auto` is a decision you did not make.** `--parallel` auto
  cost 514 MiB silently. Same family as the CPU-serving incident.
- **`pgrep -f foo` matches its own command line.** Bracket it: `pgrep -f "[f]oo"`.
- **A green health check is not a healthy system.** Confirm `llm_on_gpu`, not
  just `/health`, before trusting any latency number.

---

## 11. Provenance

Verification run, nine `llama-server` loads, VRAM at steady state:
`docs/archive/2026-08-30-gemma-verification-run.md`.
Superseded analyses, each with a header stating what it got wrong:
`docs/archive/2026-08-30-gemma-{opus,gpt,ling-flash,gemini}.md`.
Bench artefacts (6.3 GB, outside the repo on purpose):
`~/.cache/friday-model-eval/` — `bench.py`, `PREDICTIONS.md`,
`PREDICTIONS-mtp.md`, `RESULTS-gemma4-12b.md`, `RESULTS-mtp-feasibility.md`,
`logs/`, and the retained `gguf/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf`.

**No code, service file, or model configuration was changed in this round.
`just selftest` 8/8 before and after.**
