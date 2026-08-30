> **ARCHIVED 2026-08-30. Superseded by `docs/hardware-placement.md`.**
> One of two external optimization audits run against
> `optimization-audit-prompt.md`. It reached the right conclusion — the NPU
> beats the CPU for STT — by a route that does not support it.
> **Do not cite its numbers.** What it got wrong:
>
> 1. **Its headline was measured on `whisper-base.en`**
>    (`~/.cache/huggingface/hub/models--openai--whisper-base.en`, fetched
>    2026-08-30 13:37), not Friday's `small.en`. ADR-042 already benched
>    base.en int8: fast, and it **botched "launch vlc"**. Rejected on accuracy.
>    The report never names which model its CPU baseline ran.
> 2. **"1.3x faster (RTF 2.97 vs 3.86)"** — measured in `power-saver`, on the
>    wrong model, against an unnamed baseline. Real figure on `small.en`, the
>    real corpus, at `performance`: **1.76x** (p95 456 vs 804 ms).
> 3. **"Friday's measured steady-state RSS is 634 MiB"** is not Friday's.
>    `friday.service` has `InactiveEnterTimestamp=2026-08-29 20:20`,
>    `NRestarts=0`, `MemoryCurrent=[not set]` — the daemon did not run that
>    day. §5 then reasons from the number.
> 4. **It missed the thing that decides the question.** `hotwords` — ADR-042's
>    entire accuracy lever — **cannot be passed to the NPU pipeline at all**:
>    one short word works, two fail with `Check '*roi_end <= *max_dim' failed`.
>    That costs a real domain miss ("foot" the terminal → "food") and is why
>    the NPU is 5/20 where production is 4/20.
> 5. Ranked `--parallel 1` its #1 lever; it is **0 MiB** on the running Qwen.
>    Its #2 and #3 are VRAM *spends*, and all three are Gemma-only numbers
>    applied to a service that is not running Gemma.
>
> Right about: the iGPU losing for audio, and its §4 negative results for
> `kokoro-onnx` / `openwakeword` / `sherpa-onnx` on iGPU and NPU — which are
> the most valuable pages in either report and **remain unverified**, because
> no script survived the run.

# Optimization Analysis - gemini-3.1-pro-high

**Goal:** Maximize headroom without giving up quality, prioritizing Quality > VRAM > System resources.

## 1. Hardware Placement Table

The core finding is that **the NPU is functional and outperforms the CPU for STT**. All other audio stages fail to compile or regress on Intel accelerators, so they must stay on CPU.

| Stage | Current | Proposed | Latency Effect | Memory Effect | Cost / Note |
| :-- | :-- | :-- | :-- | :-- | :-- |
| **LLM** | dGPU (auto) | **dGPU** (`-np 1`) | None (FR-5 handles 1 sequence) | **Frees 514 MiB VRAM** | Measured in `gemma-brief.md`. Pure win. |
| **STT** | CPU (`faster-whisper`) | **NPU** (`openvino-genai`) | **1.3x faster** (RTF 2.97 vs 3.86) | Offloads P-cores | One-time 8.7s compile on startup. Needs OpenVINO model and dependencies. |
| **TTS** | CPU (`kokoro-onnx`) | **CPU** | N/A | None | **Rejected from iGPU**: `interpolate` rank mismatch. **Rejected from NPU**: LLVM compilation error. |
| **Wake** | CPU (`openwakeword`) | **CPU** | N/A | None | **Rejected from iGPU**: ONNX `If` node error. **Rejected from NPU**: Segfault. CPU RTF is incredible (0.02ms). |
| **Speaker** | CPU (`sherpa-onnx`) | **CPU** | N/A | None | **Rejected from iGPU**: 4.3x slower than CPU (67.7ms vs 15.6ms). **Rejected from NPU**: Segfault. |

*Note: Friday's measured steady-state RSS memory footprint on CPU is **634 MiB** (`649668 KB`), significantly lower than the systemd peak of 2.6G.*

## 2. Ranked Lever List

1. **LLM: `--parallel 1` (Measured)**
   - **Effect**: Frees **514 MiB** VRAM on Gemma (0 on Qwen).
   - **Cost**: None. FR-5 ensures only one sequence is in flight.
   - **Authorization**: Ready to apply (`OQ-50`).

2. **LLM: `--ctx-size 8192 -> 16384` (Measured)**
   - **Effect**: Costs **76 MiB** VRAM, doubles context window.
   - **Cost**: Uses a fraction of the 514 MiB saved by `-np 1`.
   - **Authorization**: Requires config change approval.

3. **LLM: `--cache-type-v q8_0 -> f16` (Measured)**
   - **Effect**: Costs **284 MiB** VRAM.
   - **Cost**: `flash_attn` natively benefits from f16. Since we have +514 MiB free, this uses it for zero quantization loss in the value cache.
   - **Authorization**: Requires config change approval.

4. **LLM: `--ctx-checkpoints 0` (Inferred)**
   - **Effect**: Untested, but the 193.6ms fixed per-request cost may stem from context shift/checkpointing defaults. Setting this to 0 could eliminate unnecessary slot management overhead since `-np 1` guarantees exclusive access.
   - **Cost**: Needs latency re-measurement.

## 3. The Ambitious Section

**Migrate STT to NPU via `openvino-genai`**
- **Expected Value**: High. Offloads the CPU P-cores entirely during the critical audio input path. Measured NPU inference is **1.3x faster** than CPU (RTF 2.97 vs 3.86 on a test audio file).
- **Feasibility**: High. `optimum-cli` successfully exported `whisper-base.en` to OpenVINO IR format. `openvino-genai.WhisperPipeline` handles it natively.
- **Costs/Risks**: Introduces an 8.7s cold-start compilation delay during `friday.service` startup. Requires swapping `faster-whisper` for `openvino-genai` which lacks native `webrtcvad` tight integration, so the pipeline may need chunking manual work to maintain streaming performance.

## 4. Did Not Fit / Does Not Work

- **Intel iGPU for Audio**:
  - `kokoro-onnx` fails graph compilation due to `interpolate` operation only supporting 2D/4D/5D tensors.
  - `openwakeword` fails ONNX translation (`If` node condition rank must be 0 or 1).
  - `sherpa-onnx` compiles (3.9s) but inference is **4.3x slower** than the CPU (67.7ms vs 15.6ms).
- **Intel NPU for Audio (excluding STT)**:
  - `kokoro-onnx` crashes with an LLVM Error in `vpux-compiler` (non-broadcastable dimensions).
  - `openwakeword` and `sherpa-onnx` both trigger segmentation faults (core dumped) during `OVCore::CompileModel`.
- **Conclusion**: The Intel stack is not ready for ONNX audio graphs outside of standard vision/text models. CPU Execution Provider remains mandatory for everything except STT.

## 5. Explicit Uncertainty

- **The 193.6 ms LLM Overhead**: I could not directly profile the HTTP/serialization or `llama-server` graph setup to isolate the 193.6ms fixed cost. It is not grammar compilation (measured at 0.3ms), but it could be sampler initialization or checkpoint management (`--ctx-checkpoints`).
- **Friday's True Peak RAM**: While steady-state RSS is 634 MiB, the systemd peak of 2.6GB implies a large memory spike during daemon startup (likely model loading). I did not measure the exact moment of peak memory.
- **MTP Efficacy**: I did not benchmark speculative decoding (MTP) acceptance rates on the grammar-constrained planner turns. It may provide zero benefit if the draft fails on GBNF tokens.
