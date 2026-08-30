# Hardware placement — where every Friday stage belongs, measured

Written 2026-08-30. Answers the "divide and rule" question in
`optimization-audit-prompt.md`, and closes ADR-019 / OQ-10, which have sat at
*"presence is confirmed, throughput is not"* since 2026-08-22.

Two external audits (`docs/archive/2026-08-30-optimization-*.md`) reached
opposite conclusions from each other, and neither used the real corpus. This
does. Harnesses:
[`scripts/stt_accel_bench.py`](../scripts/stt_accel_bench.py) (STT) and
[`scripts/accel_stage_bench.py`](../scripts/accel_stage_bench.py) (TTS,
speaker, wake).

## The answer

| stage | now | belongs on | measured effect | why |
| :-- | :-- | :-- | :-- | :-- |
| **LLM** | dGPU | **dGPU** — unchanged | — | already right |
| **STT** | CPU `faster-whisper` | **CPU, via OpenVINO** | p95 804 → 544 ms, accuracy unchanged | 1.48x, no new silicon, no new failure mode |
| STT (alternative) | — | *NPU* | p95 804 → 456 ms, **4/20 → 5/20 misses** | 1.76x, but loses hotwords — see below |
| STT (forbidden) | — | *dGPU/CUDA* | p95 804 → **107 ms**, accuracy unchanged | 7.5x. **Breaks invariant #6 / FR-71.** Decision below |
| **TTS** | CPU | **CPU** — cannot move | — | NPU **dumps core**; iGPU refuses the graph |
| **speaker verify** | CPU | **CPU** — must not move | 18.3 → 9.1 ms when it works | **SIGSEGV on utterances ≤1.9 s** |
| **wake** | CPU | **CPU** — nothing to gain | already 0.78 ms per 80 ms frame | ~1% of one core; iGPU is 20x slower, NPU crashes |
| **AEC / VAD** | CPU | **CPU** | — | WebRTC C code, no ONNX graph, no accelerator path |

Net: **one stage can move, and the biggest win is on silicon Friday already
owns.** The two idle accelerators are idle for better reasons than neglect —
but ADR-019 is still a fourth ADR that decided something and never checked it.

## Read the power profile first, or throw the run away

**Both external audits benchmarked in `power-saver` and neither noticed.** All
cores pin at ~2.2 GHz against 5.3–6.5 GHz buckets. Same clips, same config:

| profile | p50 | p95 |
| :-- | --: | --: |
| `power-saver` | 1214 ms | **1310 ms** |
| `performance` | 750 ms | **804 ms** |

1.6x, invisible, and it silently reversed one audit's iGPU verdict. Both
scripts print `powerprofilesctl get` and shout when it is not `performance`.

```bash
powerprofilesctl set performance
```

## "It ran on the NPU" is a check that can fail

`sess.get_providers()` reports what was **registered**, not what executed — the
OpenVINO EP silently partitions unsupported subgraphs back to the CPU. The
kernel exposes a counter that cannot lie:

```
/sys/devices/pci0000:00/0000:00:0b.0/npu_busy_time_us
```

It moves ~230 ms across an NPU run of the speaker model and **exactly 0** across
the same run on CPU. `accel_stage_bench.py` prints the delta on every run and
says `<-- ZERO: this did NOT run on the NPU` when it is flat. Without it, three
of the results on this page would have been wrong in the flattering direction.

## STT — how the numbers are made comparable

It reuses, verbatim, the three things that produced ADR-042's winning row:

- the **20 real DMIC clips** in `~/.cache/whisper-bench/clips/` with their
  reference sentences (`record.sh` re-records them if they are ever lost),
- `sweep3.py`'s **miss rule**, copied character for character, so a miss count
  here means what `miss 4/20` meant in ADR-042,
- the **production config** — `small.en`, int8, 8 threads, `beam_size=1`,
  `vad_filter=True`, `friday.config.STT_HOTWORDS`.

It cannot `import friday`: `faster-whisper` and `openvino-genai` do not
coexist in one venv (`onnxruntime-openvino` displaces `onnxruntime`, and the
project venv is off-limits). So it runs twice, under two interpreters, and
`HOTWORDS` is a literal that must be kept equal to `config.STT_HOTWORDS`.

```bash
~/.cache/whisper-bench/.venv/bin/python scripts/stt_accel_bench.py fw
```

```bash
~/.cache/friday-accel-eval/venv/bin/python scripts/stt_accel_bench.py ov NPU --hotwords
```

`ov` takes any OpenVINO device: `CPU`, `NPU`, `GPU.0` (Intel iGPU), `GPU.1`
(the NVIDIA card via OpenCL — untested, see invariant #6).

## Read the power profile first, or throw the run away

**Both external audits benchmarked in `power-saver` and neither noticed.** All
cores pin at ~2.2 GHz against 5.3–6.5 GHz buckets. Same clips, same config:

| profile | p50 | p95 |
| :-- | --: | --: |
| `power-saver` | 1214 ms | **1310 ms** |
| `performance` | 750 ms | **804 ms** |

1.6x, invisible, and it silently reversed one audit's iGPU verdict. The script
prints `powerprofilesctl get` on every run and shouts when it is not
`performance`. Fix it before believing anything:

```bash
powerprofilesctl set performance
```

## Numbers to beat

Measured 2026-08-30, `performance`, 20 clips / 94.2 s audio, 2–3 runs each,
`friday.service` stopped, `llama-server` live on the dGPU. Run-to-run spread
is under 2% except where noted.

| backend | device | p50 | p95 | miss | peak RSS | construct |
| :-- | :-- | --: | --: | --: | --: | --: |
| faster-whisper int8 +hotwords **(production)** | CPU | 750 ms | **804 ms** | **4/20** | 754 MB | 1336 ms |
| openvino-genai `small.en-int8-ov` | CPU | 482 ms | 529 ms | 6/20 | 899 MB | 510 ms |
| openvino-genai `small.en-int8-ov` **+hotwords** | CPU | 492 ms | **544 ms** | **5/20\*** | 905 MB | 514 ms |
| openvino-genai `small.en-int8-ov` | **NPU** | 388 ms | **456 ms** | **5/20** | 1078 MB | 5443 ms cold / 1792 ms cached |
| openvino-genai `small.en-int8-ov` | iGPU `GPU.0` | 1631 ms | **1959 ms** | 6/20 | 467 MB | 1661 ms |

\* four real misses plus `clip_18`, where OpenVINO emits commas the reference
does not have. The miss rule strips only leading/trailing punctuation, so that
one is a scorer artifact. **On real errors it is 4/20 — production parity.**

Model: `OpenVINO/whisper-small.en-int8-ov` in
`~/.cache/friday-accel-eval/whisper-small.en-int8-ov/` (257 MB), the INT8
OpenVINO IR conversion of the same `small.en` weights.

## What the numbers say

**The win is OpenVINO on the CPU, not the NPU.** 1.48x faster than production
at identical accuracy, on silicon Friday already uses, for +151 MB RSS and a
822 ms shorter construct.

**The NPU is genuinely faster — 1.76x — and it costs the hotwords lever.**
`hotwords` cannot be passed to the NPU pipeline. One short word works; two
fail:

```
RuntimeError: Check '*roi_end <= *max_dim' failed at make_tensor.cpp:35
```

Confirmed by sweep: `"foot"` generates, `"foot, Brave"` and everything longer
does not, and `initial_prompt` fails the same way. The NPU compiles with
static shapes and Friday's 14-item vocab does not fit. The cost is not
abstract — the miss it adds is `clip_20`, *"remember my terminal is **food**"*,
which is `foot`, one of the five apps. **Under quality-first, the NPU loses as
a drop-in.**

**The iGPU loses outright.** p95 1959 ms, the only backend that fails the
800 ms gate. It is 2.4x slower than production, not the "near-tie" the codex
audit reported from one LibriSpeech clip in `power-saver`.

**ADR-019 was a fourth dead ADR** — decided, filed as a Phase-2 option, never
implemented. Phase 2 shipped without it. It joins `cancel_reminder`/ADR-070,
both Hyprland tools/ADR-074, and the wake-pause/ADR-058.

## The finding nobody was looking for

**Production STT no longer passes its own gate.** ADR-042 recorded
`p95 741 ms` against an 800 ms limit (FR-11, OQ-07). Reproduced today on the
same clips, same config, same `ctranslate2 4.8.1`, at `performance`:

```
run 1  p95 722 ms      (immediately after the profile switch, clocks cold)
run 2  p95 804 ms
run 3  p95 804 ms
run 4  p95 803 ms
```

Steady state is **~804 ms — over the limit**. The 741 ms in ADR-042 was
measured 2026-08-23, before an Arch upgrade, and is not what this machine
does now. `miss 4/20` still reproduces exactly, so the model and the scorer
are unchanged; only the latency moved.

This is not a reason to swap backends by itself, but it does mean **the CPU
baseline both audits were trying to beat is not the number in the docs**, and
FR-11's acceptance test would fail if anyone re-ran it.

## TTS — cannot move, on either device

Kokoro fp32, `af_bella`, kokoro-bench's texts so the numbers stay comparable
to ADR-040.

| device | result |
| :-- | :-- |
| **CPU** | short `"Opening Brave."` **183 ms**, paragraph RTF **0.124**, RSS 870 MB |
| **NPU** | `LLVM ERROR: Failed to infer result type(s)` in `vpux-compiler`, *"Got non broadcastable dimensions pair : '2' and -9223372036854775808"* — **core dumped** |
| **iGPU** | `Check 'inputRank == 2 \|\| inputRank == 4 \|\| inputRank == 5' failed at interpolate.cpp:37: Mode 'linear_onnx' supports only 2D or 4D, 5D tensors` |

Both failures are structural, not tuning. Kokoro's `input_ids` is `[1,?]` and
the failing `Add` is `(1,256,2) + (1,256,?)` — the NPU compiler needs static
shapes and cannot resolve the dynamic bound. The iGPU's `interpolate` is 3D and
its `linear_onnx` kernel only takes 2D/4D/5D.

The archived gemini report claimed both of these without leaving a script. They
are **now verified**, with the exact errors and a reproducible core dump.

## Speaker verification — the trap

`3dspeaker_campplus` on the NPU is genuinely ~2x faster than the CPU
(18.3 → 9.1 ms, `npu_busy_time` +230 ms, so it really ran). Then it depends on
the input length, because the NPU needs static shapes and Friday's utterances
are not:

| input `T` (10 ms frames) | audio | result |
| --: | :-- | :-- |
| 100 / 150 / 180 / 190 | 1.0–1.9 s | compile fails → `Falling back to OV CPU` → **SIGSEGV, exit 139** |
| 200 / 250 / 300 / 500 / 800 | 2.0–8.0 s | runs on NPU, 6.2–15.2 ms |

Reproducible: 190 crashes every time, 200 never does. **The failing zone is
Friday's shortest and commonest utterances** — a confirmation "yes" is about a
second. And it does not fail closed: the CPU fallback that exists precisely to
make this safe is the thing that segfaults, which in the daemon means Friday
dies mid-turn rather than degrading.

Intel's own guidance for an NPU crash is to reload the driver
(`rmmod intel_vpu; modprobe intel_vpu`) — not a foundation for a fallback path.
See the [OpenVINO NPU device docs](https://docs.openvino.ai/2024/openvino-workflow/running-inference/inference-devices-and-modes/npu-device.html)
and [Applying Dynamic Shapes](https://docs.openvino.ai/2024/openvino-workflow/running-inference/dynamic-shapes.html):
*only models with static shapes are supported on NPU.* That one sentence
explains this table, the Whisper hotword cap, and the Kokoro failure.

## Wake — already free

openwakeword is a three-model chain, scored on every 80 ms frame:

| model | CPU | iGPU |
| :-- | --: | --: |
| melspectrogram | 0.050 ms | 4.026 ms |
| embedding | 0.719 ms | 12.255 ms |
| `hey_jarvis` classifier | 0.014 ms | **will not convert** |

**0.78 ms per 80 ms frame — under 1% of one core.** There is no win to take.
The iGPU is 20x slower on the two stages it can run, and the classifier fails
conversion outright: `Rank of If condition input must be equal to 0 or 1`
(the ONNX `If` node's condition is `[1,1]`). On the NPU the chain compiles,
falls back, and core dumps. Verified — again, the gemini report was right and
had no evidence.

## The NVIDIA card through OpenVINO (`GPU.1`) — closed, twice over

The audit prompt flagged this as genuinely open. It is not, on two independent
grounds measured together:

1. **It violates FR-71.** Watching `nvidia-smi --query-compute-apps` during the
   run shows a **second compute process** holding 128–158 MiB alongside
   `llama-server`. FR-71's test is "exactly one compute process during a spoken
   turn". The prompt's guess was right for Intel devices — an NPU/iGPU process
   never appears — but `GPU.1` is the NVIDIA card reached over OpenCL, and it
   does appear.
2. **It does not work anyway.**
   `[GPU] clEnqueueMapBuffer, error code: -30 CL_INVALID_VALUE`.

No further experiment needed.

## The forbidden prize, measured

Invariant #6 says only `llama-server` touches CUDA, and STT does not. That is
settled policy and this changes none of it. But the size of what it costs was
never a number, so here it is — `scripts/stt_accel_bench.py fw cuda`, same
clips, same scorer:

| STT placement | p50 | p95 | miss | VRAM | LLM contention |
| :-- | --: | --: | --: | --: | :-- |
| CPU, `faster-whisper` (production) | 750 ms | 804 ms | 4/20 | 0 | — |
| CPU, OpenVINO +hotwords | 492 ms | 544 ms | 4/20\* | 0 | — |
| NPU, OpenVINO | 388 ms | 456 ms | **5/20** | 0 | — |
| **dGPU, CUDA** | **81 ms** | **107 ms** | 4/20\* | **556 MiB** | **none measured** |

**7.5x, at unchanged accuracy.** TTFA p50 is 2172 ms with ~804 ms of it STT
(OQ-45: 0 of 77 turns met the 1400 ms target). Removing ~720 ms puts the target
in reach for the first time.

ADR-018's three stated reasons, tested rather than argued:

- **Inter-process contention** — `llama-server` p50 over 15 requests:
  **359 ms alone / 357 ms with a resident CUDA whisper / 359 ms alone again.**
  No measurable cost. FR-5 (one turn in flight) already guarantees STT and the
  planner never compute at the same instant.
- **VRAM accounting** — it is exactly as legible as before: a second row in
  `nvidia-smi`, 556 MiB peak.
- **Per-process CUDA context** — real, and it is a startup cost:
  construct 1234 ms, first transcription 5566 ms. Once per daemon start.

The cost that is not free is **headroom, and it couples to OQ-47**:

| LLM | free VRAM | after a 556 MiB CUDA whisper |
| :-- | --: | --: |
| Qwen2.5-7B (live) | 3042 MiB | 2486 MiB — comfortable |
| Gemma 4 12B, `-np 1` | 740 MiB | **184 MiB — very tight** |
| Gemma 4 12B, stock slots | 226 MiB | **does not fit** |

So CUDA STT and the Gemma swap are spending the same budget, and together they
require `-np 1`. **This is a decision, not a finding** — invariant #6 would
need an ADR amendment, and that is the owner's call. Nothing here changes it.

## Open, and not measured here

- **Streaming.** Every STT number is one-shot over a captured buffer, which is
  what Friday does today. Nothing here says how `openvino-genai` behaves inside
  the live `webrtcvad` capture path.
- **Cold start.** The NPU's 5443 ms first Whisper compile drops to 1792 ms with
  `CACHE_DIR`, at the cost of an **838 MB** on-disk blob cache — still 456 ms
  worse than faster-whisper's construct, on every daemon start.
- **RAM.** The NPU STT path peaks at 1078 MB against production's 754 MB, and
  the CUDA path at 1154 MB, on a 16 GB machine shared with a browser.
- **Determinism across devices.** The same model on CPU and NPU produced
  different transcripts for `clip_15`. Neither is wrong; a fallback design has
  to tolerate it.
- **A Whisper re-export with a larger static prompt length** might let the NPU
  take the full hotword list. **Inference, untested** — the one route that
  would turn the NPU into a win rather than a trade.
- **Squeezing the `If` condition** in `hey_jarvis.onnx` would probably make it
  convert. Pointless: wake already costs 0.78 ms.
- **The 193.6 ms fixed per-request LLM cost** is still unprofiled. The 359 ms
  floor measured above is consistent with it and does not explain it.

---

# Part 2 — the software drill

Placement asks *where a stage runs*. This asks the other half: **is the library
still the right one?** It is CLAUDE.md rule 7 / ADR-041 applied to every stage —
enumerate the real options, check the footprint before installing, benchmark on
this laptop, and record the rejected alternatives.

Target profile is **`balanced`** — what the machine normally runs. `performance`
may only ever be better (measured: indistinguishable, see below). `power-saver`
is a capability cap, not a baseline.

Harnesses: [`scripts/vad_bench.py`](../scripts/vad_bench.py),
[`scripts/tts_bench.py`](../scripts/tts_bench.py), and the `moonshine` mode of
[`scripts/stt_accel_bench.py`](../scripts/stt_accel_bench.py).

## Result

| stage | incumbent | benched against | verdict |
| :-- | :-- | :-- | :-- |
| **VAD** | `webrtcvad` mode 2 | Silero v4, Silero current, Silero If-free | **REPLACE — incumbent is the cause of D3** |
| STT | whisper `small.en` | moonshine, **tuned over 3 rounds** | keep — 4x faster, 2.5x wrong |
| TTS | kokoro-82M `af_bella` | supertonic-3 (10 voices) | keep on latency; **audition pending** |
| wake | `openwakeword` | — | keep — 0.78 ms/frame, nothing to reclaim |
| speaker | sherpa `campplus` | — | keep — 18 ms once per turn |
| AEC | WebRTC APM | DTLN-aec 128/256/512 | **candidate validated offline; live run owed** |

## VAD — the incumbent is why hands-free does not work

This is the OQ-39 probe, and it root-causes **D3**. Driven through the real
`friday.audio.vad.SpeechGate`, on the 20 real DMIC clips, each with 2 s of that
clip's **own quietest room noise** appended — digital silence flatters every
detector and proves nothing.

| detector | voiced fraction p50 | start | **end** | cost/frame |
| :-- | --: | --: | --: | --: |
| webrtcvad mode 0 | 0.500 | 20/20 | 14/20 | 0.0047 ms |
| webrtcvad mode 1 | 0.489 | 20/20 | 14/20 | 0.0033 ms |
| **webrtcvad mode 2 (incumbent)** | 0.444 | 20/20 | **15/20** | 0.0032 ms |
| webrtcvad mode 3 | 0.407 | 20/20 | 16/20 | 0.0032 ms |
| silero v4 (already on disk) | 0.346 | 20/20 | **20/20** | 0.0643 ms |
| silero current | 0.367 | 20/20 | **20/20** | 0.0538 ms |
| **silero current, If-free** | 0.367 | 20/20 | **20/20** | **0.0484 ms** |

**Every detector starts. Only Silero ever ends.** The mechanism, per clip:

```
webrtcvad mode=2  no-end on 5/20:
  clip_01 voiced=0.891   clip_02 voiced=1.000   clip_06 voiced=0.971
  clip_07 voiced=0.996   clip_08 voiced=0.829
silero (both generations)  no-end on 0/20
```

On the failing clips webrtcvad calls **83–100% of frames speech, including the
appended room noise**. Trailing silence never accumulates, `SpeechGate` never
emits `end`, and the capture runs to the 15 s cap. That is exactly D3's reported
symptom — *"all three wake captures ran the full 15 s cap"* — reproduced offline
on real microphone audio. Silero's voiced fraction never exceeds 0.482 on any
clip; it does not saturate.

Cost of the swap: **0.048 ms per 32 ms frame, 0.15% of one core.** Silero is
~15x more expensive than webrtcvad in relative terms and both are free in
absolute terms. `friday.audio.vad.Vad` is already a `Protocol`, so a Silero
backend drops in behind it; the only integration change is 32 ms frames instead
of 20 ms, and `SpeechGate` already takes `frame_ms` as a parameter.

Three variants all score identically, so pick on other grounds:
`silero_vad_op18_ifless.onnx` is the fastest **and** is built without the ONNX
`If` op — the exact operator that made openwakeword's classifier unconvertible
on both Intel devices. It is the accelerator-portable choice for free.

**Caveat, stated plainly:** this is offline, on clips recorded through the real
microphone but **not through the AEC path**. OQ-39 asks for live frames through
`wake.py:_on_frame`. This does not close OQ-39; it identifies the mechanism and
makes the live run a confirmation rather than an exploration.

### The trap in this measurement

Silero v5+ prepends a **64-sample context**, so the graph must see 576 samples,
not 512. Feed it a bare 512 and it returns `p≈0.001` on obvious speech —
silently, with no error, on every frame. The first run of this bench scored the
current model at **0/20 starts** and would have "proved" the new model was
useless. The bundled v4 needs no context and worked immediately, which made the
wrong result look even more credible. `scripts/vad_bench.py` carries the context
handling and a comment saying why.

## STT — Moonshine is genuinely fast and not accurate enough

Moonshine uses variable-length windows instead of Whisper's fixed 30 s chunks,
which is why it targets exactly Friday's workload: short commands.

| model | p50 | p95 | miss | RSS |
| :-- | --: | --: | --: | --: |
| whisper `small.en` int8 +hotwords (incumbent) | 686–760 ms | 714–804 ms | **4/20** | 748 MB |
| moonshine/tiny | 150 ms | **200 ms** | 10/20 | 491 MB |
| moonshine/base | 322 ms | 436 ms | 11/20 | 773 MB |

**4x faster than the incumbent and faster than Whisper on the NPU** — and it
mangles the domain: `launch vlc` → `"Longe beals."`, `neovim` → `"Neo-Wim"`,
`tell me` → `"Turn me"`. There is no hotword biasing to recover it with. Under
quality-first this is a straightforward reject, and the paper's own documented
weakness (>100% WER on sub-1-second clips, repeated tokens) lands on exactly the
utterance Friday hears most: `"yes"`.

**Measurement note:** `moonshine_onnx.transcribe(path, "moonshine/base")`
**rebuilds the model on every call**. Timed that way, tiny reports p95 2101 ms
and looks 3x slower than Whisper. Passing the model object gives 200 ms. The
first numbers were wrong in the direction that would have made the reject look
easy.

### Moonshine, tuned — the rounds Whisper got

Rejecting a stock model against a Whisper that had already had three rounds of
tuning (ADR-042: model choice, then beam, then hotwords) was not a fair test.
[`scripts/moonshine_tune.py`](../scripts/moonshine_tune.py) runs the equivalent.
Moonshine's ONNX package has no beam search, no hotwords and no
`initial_prompt` — `generate()` is a plain greedy argmax — so the levers are
model/precision, audio preprocessing, and a **domain logit bias implemented
here**, which is what `hotwords` does inside faster-whisper.

| round | configuration | p50 | p95 | miss |
| :-- | :-- | --: | --: | --: |
| R1 | tiny float | 117 ms | **182 ms** | 10/20 |
| R1 | tiny quantized | 114 ms | 172 ms | 13/20 |
| R1 | base float | 236 ms | 318 ms | 11/20 |
| R1 | base quantized | 204 ms | 299 ms | 10/20 |
| R2 | base +normalize | 307 ms | 485 ms | 10/20 |
| R2 | base +trim | 290 ms | 387 ms | 11/20 |
| R2 | base +normalize +trim | 287 ms | 468 ms | 11/20 |
| R3 | base +bias 2 | 281 ms | 362 ms | 11/20 |
| R3 | base +bias 5 | 261 ms | 516 ms | 12/20 |
| R3 | base +bias 10 | 1390 ms | 1449 ms | **9/20** |
| R3 | base +bias 5 +normalize +trim | 389 ms | 1535 ms | 12/20 |
| — | **whisper `small.en` +hotwords** | 686–760 ms | 714–804 ms | **4/20** |

**Three rounds moved it from 11/20 to 10/20.** The one configuration that
reached 9/20 did so by over-biasing into runaway decoding — p50 1390 ms, seven
times its untuned latency and slower than Whisper, for a result still more than
twice as wrong.

The bias does work where it can: `neovim` and `lo-fi` are recovered at bias 2.
It cannot recover the rest, because Moonshine's errors are not near-misses on
rare words — `launch vlc` decodes as `"Lance vs."` and `"Longe beals."`, and no
amount of logit bonus on `VLC` rescues a decode that never approached it.
`tell me` → `"Turn me"` on every single configuration.

**Rejected fairly.** Whisper stays.

## TTS — Kokoro wins on latency; the voice decision is the owner's

Same texts as kokoro-bench, 8 threads, `balanced`.

| engine | construct | short reply | paragraph | RTF | RSS |
| :-- | --: | --: | --: | --: | --: |
| **kokoro-82M fp32 `af_bella` (incumbent)** | 642 ms | **191 ms** | **1228 ms** | **0.134** | 876 MB |
| supertonic-3 (`F1`) | 515 ms | 596 ms | 1559 ms | 0.149 | 595 MB |

Kokoro is **3.1x faster than Supertonic on a short reply**, which is the number
that reaches TTFA. Published comparisons rank Supertonic as the faster engine;
on this machine, with 8 P-cores, it is not. Supertonic uses ~280 MB less RAM —
the only axis it wins.

**KittenTTS was benched and removed at the owner's instruction** (2026-08-30):
construct 1104 ms, short reply 413 ms, paragraph RTF 0.195 — slower than Kokoro
on every axis. Package uninstalled, samples deleted, bench code deleted. Do not
re-add it without a reason this table does not already answer.

Quality is not a number and is not mine to call. Both engines rendered the same
two lines to `~/.cache/friday-accel-eval/tts-samples/`, and **all ten Supertonic
voices** (`F1`–`F5`, `M1`–`M5`) were rendered for audition — the procedure that
chose `af_bella` at G5 (ADR-005/OQ-22). Re-render with:

```bash
~/.cache/friday-accel-eval/venv/bin/python scripts/tts_bench.py --voices
```

**Kokoro stays unless the owner prefers another voice**; nothing measured here
justifies a swap.

**Measurement note:** `supertonic.TTS.synthesize()` returns
`(audio, duration_seconds)` — the second value is **not** a sample rate.
Treating it as one wrote a `1 Hz` WAV header and produced an audition file that
could not be judged at all.

## wake / speaker — measured and kept

Neither is a bottleneck, so neither justifies a swap:

- **wake** — the openwakeword chain costs **0.78 ms per 80 ms frame**, under 1%
  of one core. There is no headroom to reclaim, on any silicon.
- **speaker** — `campplus` is **18.4 ms**, once per turn.

Both are recorded as *measured and kept* rather than *never examined*, which is
the distinction ADR-019 failed to make.

## `balanced` vs `performance` — no difference for this workload

Alternating runs of the STT baseline:

```
balanced p95=722ms   performance p95=713ms
balanced p95=734ms   performance p95=760ms
```

Indistinguishable. Across 8 runs p95 spans **713–804 ms**, so FR-11 sits *on*
its 800 ms gate rather than under it. Only `power-saver` (1310 ms) changes the
answer. Package temperature stayed 57–69 °C throughout; nothing throttled.

## Proposed, not adopted — profile-aware degradation

The owner's framing on 2026-08-30: *power-saver should cap what Friday attempts,
not just make everything slower.* Friday can read the profile
(`powerprofilesctl get`, or the same D-Bus property) and degrade deliberately —
cheap intents only, heavier work deferred or declined out loud — rather than
running the full path at 2.2 GHz and missing every latency target silently.

This is a **new requirement with no ADR and no OQ**. It is written here so it is
not lost, and deliberately not written into `spec.md`.

## AEC — candidate built and validated, live run owed

The incumbent measures **−52 dB on synthetic echo and −5 to −10 dB in this
room** (`docs/aec-probe.md`). At −6 dB Friday still hears herself at half
volume, the VAD calls it an interruption, and she cuts her own sentence off —
which is why ADR-064 disabled voice barge-in and made PTT the only interrupt.
Delay is not the cause: speaker→mic lag measured 58 ms at envelope correlation
0.53, so the reference content is correct. WebRTC's adaptive filter assumes a
roughly **linear** echo path, and a laptop speaker at volume is not linear.

DTLN-aec was trained on exactly that case (Microsoft AEC-Challenge, 3rd place).
**It ships TF-lite, not ONNX** — OpenVINO reads TFLite directly, so it still
reaches every device.

### Cost — measured

| model | params | CPU / hop | NPU / hop | share of an 8 ms hop |
| :-- | --: | --: | --: | :-- |
| dtln_aec_128 | 1.8M | **0.197 ms** | 1.583 ms | 2.5% CPU / 19.8% NPU |
| dtln_aec_256 | 3.9M | — | — | not benched |
| dtln_aec_512 | 10.4M | **0.448 ms** | 2.278 ms | 5.6% CPU / 28.5% NPU |

**This is the first Friday-relevant workload that runs on the NPU at all** —
every shape is static, it compiles, and `npu_busy_time_us` moves (+242/+351 ms).
It is also 8x slower there than on the CPU: these are tiny per-frame graphs and
the NPU is dispatch-dominated. Even the largest model costs 5.6% of one core on
CPU, so **the upgrade is affordable and belongs on the CPU.**

### Quality — offline validation

Synthetic room built to the measured parameters (58 ms delay, `tanh` speaker
distortion, room noise floor), scored with the Silero VAD because dB alone does
not decide barge-in — speech frames do:

| processor | suppression | VAD speech frames |
| :-- | --: | --: |
| raw echo | — | **252** |
| dtln_aec_128 | −34.8 dB | **0** |
| dtln_aec_512 | −36.7 dB | **0** |

This proved the implementation, not the fix — WebRTC also does −52 dB on
synthetic echo and still fails in this room.

### Live — DTLN wins on both axes, and the harness has a floor

~20 real captures, `friday.service` stopped, speaker at 90 %, `Mic1` default.

**Robust, no exceptions: DTLN-aec 512 suppressed 8–20 dB more than WebRTC APM
on every single capture.** The ordering never inverted.

The decisive run is the preservation test, with a human speaking over the
playback. Suppression is meaningless here — the mic now contains the user and a
correct canceller keeps that energy — so read only the frames:

| processor | quiet (Friday only) | user talking | preserved |
| :-- | --: | --: | --: |
| none (raw mic) | ~235 | 243 | — |
| WebRTC APM | 0 / 0 / 134 | **68** | 28 % |
| DTLN-aec 512 | 5 / 20 / 38 / 46 / 82 | **152** | **63 %** |

**WebRTC's `0 frames` was a gate, not cancellation.** It deletes the room, and
it deletes 72 % of the user with it. That is a complete explanation for why
voice barge-in never worked and why ADR-064 had to disable it — and it is
invisible to any metric that only measures how much echo disappeared.

### What could not be established, and what was ruled out

Absolute suppression is unstable: −11 to −32 dB for DTLN, −1.2 to −14.9 dB for
WebRTC. **Both processors degrade on the same captures**, which no quality
difference between them can cause. Eliminated, each by measurement:

- **Estimator resolution.** The alignment sweep shows 20 ms of error costs
  17 dB (−28.1 → −11.0), so the original 10 ms envelope estimator sat inside
  the error band. Replaced with GCC-PHAT at sample resolution. **Did not fix
  it.**
- **Clock drift** between the DAC and ADC domains. Per-2-second-window lag is
  stable at 0.5–2.5 ms across a capture. **Not drift.**
- **Dropped audio frames.** Both callbacks were discarding sounddevice's
  `status` argument — a real harness defect, since one dropped input block
  shifts everything after it and would hit both processors at once. Fixed, and
  the harness now discards any capture reporting an XRUN. **Zero XRUNs
  observed; the variance remained.**

### D18 — the reference is not what the speaker played

What is left is the signal path itself:

```
  Speaker sink:  s32le 2ch 48000Hz     (SOF HDA DSP, hw:sofhdadsp)
  Mic1 source:   s32le 4ch 48000Hz     front-left,front-right,rear-left,rear-right
  reference fed to the AEC:  16 kHz mono
```

The far reference is a **16 kHz software copy on a 48 kHz device**: resampled
on the way out by PipeWire, processed by the SOF DSP after that, and resampled
again on capture. Neither canceller is being given the signal that actually
reached the room. This explains −52 dB on synthetic echo versus −5 dB in this
room far better than canceller quality does, and `friday/audio/tts.py` has the
same shape — `_resample_16k` converts Kokoro's 24 kHz to 16 kHz for the
reference on a 48 kHz sink.

The 4 microphone channels were checked for a hardware echo reference, which
would have solved this outright. They are a **mic array**
(`front-left,front-right,rear-left,rear-right`), not a reference. No such
channel exists here.

**Fixing the reference path is plausibly worth more than changing the
canceller, and it is cheaper.** OQ-52 holds the decision.

## Still owed

- **D18 first, then the AEC swap.** Feed the canceller a reference at the
  device rate and see whether either processor's variance collapses. Only then
  is a DTLN-vs-WebRTC comparison worth trusting in absolute terms (OQ-52).
- **A live confirmation run** for the VAD swap, through the real AEC path, to
  close OQ-39 properly (OQ-51).
- **A second preservation capture.** The `--talk` result is n=1. It is the
  measurement the whole barge-in question turns on and it deserves more than
  one run.
