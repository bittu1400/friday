> **ARCHIVED 2026-08-30. Superseded by `docs/hardware-placement.md`.**
> One of two external optimization audits run against
> `optimization-audit-prompt.md`. Kept for its labelling discipline, which was
> exemplary. **Do not cite its numbers.** What it got wrong:
>
> 1. **It never ran the NPU** — the single question the audit existed to answer
>    (ADR-019 / OQ-10). Correctly says so; the gap is still the point.
> 2. **It benchmarked one LibriSpeech clip.** The 20 real DMIC clips that
>    produced ADR-042's `p95 741 ms / miss 4/20`, their reference transcripts,
>    and the whole harness were already on disk at `~/.cache/whisper-bench/`.
>    It did not find them, so none of its numbers are comparable to the
>    baseline they would have to beat.
> 3. **Every CPU number was measured in `power-saver`** (all cores pinned
>    ~2.2 GHz against 5.3–6.5 GHz buckets) and it did not notice. Same clips,
>    same config, measured 2026-08-30: p95 **722 ms at `performance`, 1310 ms
>    at `power-saver`**. Its CPU-vs-iGPU comparison is invalid.
> 4. **"iGPU Whisper is a measured near-tie" is false.** On the real corpus at
>    `performance`, `GPU.0` is p95 **1959 ms** — 2.4x slower than production
>    and the only backend that FAILS the 800 ms gate.
> 5. Ranked `--parallel 1` its #1 lever; it is **0 MiB** on the Qwen service
>    that is actually running (it says so in fine print).
>
> Right about: refusing to overturn ADR-042 on one sample, the MobileNet table
> proving nothing about voice, and rejecting memory arithmetic.

# Friday optimization audit — partial measured report

**Scope and stop point.** This is the one report-only deliverable requested by
`optimization-audit-prompt.md`. No Friday code, service unit, model
configuration, project environment, or existing documentation was changed. The
live NPU Whisper run was interrupted before it began; it is deliberately not
represented as a result. Downloads and helper packages went only to
`~/.cache/friday-accel-eval/`.

**Evidence labels.** “Measured” means observed on this laptop in this audit.
“Recorded measurement” is an earlier measurement in `gemma-brief.md` / the
prompt that I did not re-run. “Primary-source fact” links its source.
“Inference” is a proposal, not a measured claim.

## Executive result

1. **Do not move Friday's current STT to the Intel iGPU.** On the actual
   Whisper `small.en` INT8 OpenVINO pipeline and one 5.86-second known speech
   sample, the iGPU's warm runs were 1.184, 1.233, and 1.306 s versus the CPU
   baseline's 1.340 s first run. That is an encouraging but insufficient and
   not clearly material result; it also adds a 3.288 s cold construction cost.
   Quality was textually identical on this one sample, but one sample does not
   validate Friday's hotwords, VAD behavior, live microphone quality, or its
   741 ms p95 gate. **Measured; reject as an adoption today.**
2. **The NPU is real and usable by OpenVINO, but its real Whisper throughput is
   still unmeasured.** The audit verified the NPU node and OpenVINO device
   enumeration, then measured an existing MobileNet artifact on it. This
   closes neither the STT performance nor quality question. **Measured
   availability; unmeasured placement decision.**
3. **The present live baseline has substantial dGPU headroom with Qwen:**
   `llama-server` alone held 4,696 MiB and `nvidia-smi` reported 3,042 MiB
   free. There was no second NVIDIA compute process. **Measured.** This is
   consistent with FR-71 and ADR-018.
4. **The best already-proven future-Gemma memory lever remains `--parallel 1`,
   not a smaller context.** It is a recorded measurement: +514 MiB for Gemma,
   no quality cost under FR-5. It has no measured effect on the live Qwen
   service. Adoption is a configuration decision and requires the owner's
   authorization; this audit did not change it.

## Hardware placement

| Friday stage | Now | Proposed placement | Effect / evidence | Cost and decision |
| :-- | :-- | :-- | :-- | :-- |
| LLM (`llama-server`) | NVIDIA dGPU/CUDA | Keep dGPU/CUDA exclusively | **Measured:** 4,696 MiB process VRAM; 3,042 MiB free at audit baseline; only compute client. **Recorded:** Qwen has 3,042 MiB headroom and Gemma `-np 1` has 740 MiB. | No move. This is the quality-critical model path and ADR-018's CUDA isolation remains sound. |
| STT (`faster-whisper`, `small.en`, CPU int8) | CPU, 8 threads | Keep CPU as default and fallback. Phase-2 candidate: NPU via OpenVINO GenAI, only after live corpus and microphone comparison. | **Measured:** OpenVINO Whisper `small.en` INT8 CPU init 1.206 s, first generation 1.340 s on a 93,680-sample/16 kHz LibriSpeech sample; correct text. NPU pipeline run was **not completed**. | CPU path has Friday's established quality/latency record. NPU changes runtime and model artifact; needs authorization, fallback proof, no-disk transcript proof, p50/p95 and WER/live-command gates. |
| STT on Intel iGPU | CPU | Rejected for now | **Measured:** pipeline init 3.288 s; first 1.829 s; warm 1.184/1.233/1.306 s on the same sample; output matched CPU exactly. | A single short sample cannot establish a quality win, and the cold cost is 2.082 s above CPU. The apparent warm speed is too small and variable to justify an iGPU policy change. It is also the arguable case under ADR-018's title (“only GPU consumer”); do not take that policy ambiguity for this result. |
| TTS (Kokoro ONNX, fp32, 8 threads) | CPU | Keep CPU pending a real end-to-end synthesis benchmark | **Recorded:** 8 P-cores are its measured optimum; int8 was about 4x slower and fp16 returned zero audio on CPU (ADR-040). | No measured OpenVINO/Kokoro run in this audit. An NPU/iGPU move needs waveform and intelligibility/voice-quality comparison, cancellation/barge-in verification, and CPU fallback. |
| Wake (`openwakeword`) | CPU | Keep CPU | No stage-specific accelerator benchmark was run. | It scores continuously in the audio callback; dispatch/transfer latency risks wake reliability. No move without false-accept/false-reject and frame-budget measurements. |
| Speaker verification (`sherpa-onnx`) | CPU | Keep CPU | No stage-specific accelerator benchmark was run. | It is not the continuous critical path and must preserve identity accuracy. No quality result, no move. |
| AEC / VAD | CPU | Keep CPU | No accelerator implementation was tested. | Audio callback latency and AEC correctness outrank any speculative offload. |
| Dictation typing / orchestration | CPU/event loop | Keep placement; fix scheduling only after measurement | **Recorded source fact:** dictation typing still occurs on the event loop (`gemma-brief.md`), which can make Friday deaf. | This is not a silicon-placement optimization yet. Profile actual loop stalls before proposing a `to_thread` change; authorization required for code. |

## Measurements performed in this audit

### Live service and accelerator inventory

At the measurement point:

```text
friday: inactive
friday-llm: active
friday-searxng: active
NVIDIA GeForce RTX 5070 Laptop GPU: 8151 MiB total, 4706 MiB used,
3042 MiB free; 3.57 W; 37 C
llama-server PID 536902: 4696 MiB
OpenVINO devices: CPU, GPU.0, GPU.1, NPU
/dev/accel/accel0: present and world read/write
/dev/dri/renderD128 and renderD129: present
```

**Measured interpretation:** the live LLM was actually on the dGPU, not merely
health-check reachable. The OpenVINO dGPU identifier is `GPU.1`, not an
assumption: its enumeration was measured. No experiment was run on it because
placing a second workload on the CUDA LLM device would need a specific
contention experiment and ADR-018 review.

### Existing NPU test artifact: MobileNet v2

The pre-existing `~/npu-test/model.onnx` is MobileNet-shaped (input
`1x3x224x224`, 1,000-class output, 566 operations), not a Friday model. It is
useful only to establish device execution, not voice performance. Each device
was warmed ten times then measured for 100 synchronous inferences.

| Device | Compile | p50 inference | p95 | Mean | Status |
| :-- | --: | --: | --: | --: | :-- |
| CPU | 203.3 ms | 6.49 ms | 8.05 ms | 6.60 ms | Measured |
| Intel iGPU (`GPU.0`) | 2,315.5 ms | 1.54 ms | 8.90 ms | 2.69 ms | Measured |
| NVIDIA (`GPU.1` via OpenVINO) | 2,225.1 ms | 2.63 ms | 2.82 ms | 2.63 ms | Measured |
| Intel NPU | 477.3 ms | 1.99 ms | 2.73 ms | 2.05 ms | Measured |

This proves all four OpenVINO targets compiled and executed this graph in this
environment. It **does not** predict Whisper, Kokoro, wake, or speaker
performance. The iGPU and NVIDIA OpenVINO compilation costs are material for
cold start; OpenVINO blob caching must be measured before a persistent
accelerated path is proposed.

### Real Whisper `small.en` pipeline: CPU versus Intel iGPU

Downloaded to scratch: `OpenVINO/whisper-small.en-int8-ov` (257 MB). It is an
INT8 OpenVINO IR conversion of Whisper `small.en`; the model publisher documents
OpenVINO GenAI use and compatibility with OpenVINO 2025.2+.
[Model card](https://huggingface.co/OpenVINO/whisper-small.en-int8-ov)

Input: public LibriSpeech dummy validation sample, 93,680 samples at 16 kHz,
reference “MISTER QUILTER IS THE APOSTLE OF THE MIDDLE CLASSES AND WE ARE GLAD
TO WELCOME HIS GOSPEL.” The CPU and iGPU both returned “Mr. Quilter is the
apostle of the middle classes, and we are glad to welcome his gospel.”

| Target | Pipeline construction | First generation | Warm generations | Quality observation |
| :-- | --: | --: | :-- | :-- |
| CPU | 1.206 s | 1.340 s | Not separately sampled | Correct wording on this sample |
| Intel iGPU (`GPU.0`) | 3.288 s | 1.829 s | 1.184, 1.233, 1.306 s | Identical output on this sample |
| Intel NPU | Not run (interrupted) | Not run | Not run | Unmeasured |

The source latency measurements are not comparable to Friday's existing STT
benchmark without a shared corpus, equivalent decode options, repeated samples,
and process-RSS measurement. They therefore do **not** overturn ADR-042.

## Ranked levers

| Rank | Lever | Benefit | Cost / quality gate | Authority |
| :-- | :-- | :-- | :-- | :-- |
| 1 | Future Gemma: `--parallel 1` | **Recorded measurement:** frees 514 MiB with no quality loss under one-turn-in-flight FR-5. | Re-run `nvidia-smi` under the actual service/model, then full LLM regression. It is 0 MiB for live Qwen. | Owner authorization; service config change. |
| 2 | Retain Qwen unless Gemma passes D16 and quality gates | **Measured baseline:** 3,042 MiB dGPU free today. | A model swap can change correctness and latency; no swap from memory arithmetic. | Owner authorization. |
| 3 | NPU Whisper Phase-2 benchmark | **Inference:** may free P-cores during STT without touching CUDA. **Measured:** NPU works for OpenVINO MobileNet. | Must measure complete Whisper pipeline on a Friday-relevant corpus and microphone, transcript quality, p50/p95, cold start, RAM, and fallback. | Owner authorization for runtime/model integration. |
| 4 | OpenVINO compiled-model cache | **Inference:** could remove part of measured 477 ms NPU / 2.316 s iGPU generic-graph compilation cost. | Measure cache correctness, startup latency, cache location/perms, invalidation, and no transcript exposure. | Owner authorization; code/config. |
| 5 | Profile LLM fixed request overhead | **Recorded measurement:** 193.6 ms per planner request is unattributed. | Must use server logs/perf/traces and preserve raw-output no-disk rule. No claimed saving. | Investigation is safe; any runtime change needs authorization. |
| 6 | Profile real Friday RSS and CPU contention | **Recorded gap:** it has never been measured under an actual voice turn. | Capture process RSS, CPU scheduling, thermals, dGPU power/clock and user-workload contention; do not log raw transcripts. | Measurement safe; changes require authorization. |

## Ambitious but feasible routes

1. **NPU-first Whisper with CPU fallback — highest upside, unproven.** Intel
   documents that the Whisper GenAI pipeline supports NPU and Whisper
   tiny/base/small/large models; its guide calls out NPU driver compatibility
   and a Level Zero memory workaround. [OpenVINO NPU Whisper guide](https://docs.openvino.ai/2025/openvino-workflow-generative/inference-with-genai/inference-with-genai-on-npu.html)
   The proposed architecture is not “replace faster-whisper”: attempt an
   OpenVINO NPU backend at startup, select it only if its verification suite
   wins, and retain today’s CTranslate2 CPU backend as a tested fallback.
   This respects ADR-018's actual CUDA-context rationale and does not add an
   NVIDIA compute client. It cannot be accepted until its quality and real-time
   measurements exist.
2. **iGPU Whisper is a measured near-tie, not an optimization yet.** It can be
   revisited if a broader corpus shows reliably lower p95 and low shared-memory
   pressure. Its measured construction penalty, possible display contention,
   and ADR-018 title ambiguity make it lower value than NPU.
3. **OpenVINO on `GPU.1` is feasible but rejected pending a contention test.**
   It compiled and ran the generic artifact, while `llama-server` was live on
   CUDA. That does not establish whether OpenVINO's OpenCL route affects the
   CUDA workload, VRAM accounting, latency, or FR-71. It also gives no reason
   to consume dGPU headroom while CPU and NPU are available.
4. **Core-class scheduling, only after tracing.** The processor has 8 P-cores
   and 16 E-cores (recorded hardware fact). An experiment could reserve P-core
   capacity for latency-sensitive audio and isolate non-critical background
   work. This is an inference, not a recommendation: affinity can worsen
   scheduling/thermals, so it needs `perf`, p95 audio latency, and interactive
   workload measurements.

## Did not fit / does not work

- **NPU Whisper measurement:** not run. The session was interrupted after the
  real CPU and iGPU runs. No NPU STT latency, RSS, quality, or cold-start claim
  is made here.
- **iGPU STT adoption:** rejected for now, not because it failed, but because
  its one-sample warm result is not enough to overcome the measured cold cost,
  unmeasured live quality, and policy/display risks.
- **NVIDIA OpenVINO co-location:** only a MobileNet execution succeeded. It is
  not evidence that Friday may safely share the dGPU with `llama-server`.
- **TTS, wake, speaker, AEC/VAD accelerator moves:** not tested. No claim of a
  performance or quality improvement is justified.
- **Memory arithmetic:** explicitly rejected. The recorded Gemma evidence shows
  it has already produced 20x errors here; all future memory claims must load
  the target and read the machine.

## Explicit uncertainty and next measurement packet

The following are unknown: NPU Whisper p50/p95/cold start/RSS/quality; iGPU
Whisper live p95/RSS/display contention; OpenVINO EP compatibility with
`kokoro-onnx`, `sherpa-onnx`, and `openwakeword` under the scratch runtime;
whether OpenVINO `GPU.1` contends with CUDA; Friday's turn-level RAM, thermal,
and CPU contention; and the 193.6 ms LLM fixed overhead.

The next bounded run should use the already downloaded artifact and one shared,
known-transcript corpus plus microphone commands:

1. Run OpenVINO Whisper on **NPU**, CPU, and iGPU with five warm repetitions
   per sample; record construction, first-token/complete-transcript latency,
   RSS, and device utilization.
2. Compare WER and Friday command/hotword correctness against the existing
   CPU CTranslate2 `small.en` path. Do not persist raw transcripts.
3. Test CPU fallback on unsupported graph/device failure, then separately
   verify OpenVINO cache behavior.
4. Only if NPU wins both quality and latency, present an integration plan; do
   not alter the project venv or service unit without owner approval.

## Repository footprint

The audit created this file only. Scratch additions outside the repository:

- `~/.cache/friday-accel-eval/whisper-small.en-int8-ov/` — public OpenVINO
  Whisper model (257 MB).
- Dataset/audio helper packages in `~/.cache/friday-accel-eval/venv`.
- Disposable compiled-model cache in `/tmp/friday-ov-cache`.

