# Optimization audit — the prompt

Paste everything below the line into the LLM. It assumes shell access on this
machine and read access to the repo.

---

You are auditing a single-machine local voice assistant called **Friday** for
**deep optimization**. Repo: `~/Projects/Personal/Intern/friday`. Read
`CLAUDE.md` first, then `gemma-brief.md`, then `progress.md`'s
`>>> START HERE <<<` block.

## What I actually want

**Maximum breathing room, everywhere, at the best quality this hardware can
deliver.** Two goals, in strict priority order:

1. **Quality wins over everything.** A change that buys memory or speed by
   degrading what the user hears or how correctly Friday acts is a loss, not a
   trade. Say so and reject it.
2. **Subject to that: free every resource you can, on every piece of silicon in
   this laptop.**

Then, and this is the part I care most about:

3. **Divide and rule.** This machine has more compute units than Friday uses.
   Inventory **all** of them and work out what should run where, so that every
   component runs on the hardware best suited to it and nothing contends with
   anything else. I want a proposed *placement* of the whole workload across the
   whole machine, with the cost of each move.

**Be as ambitious as you like.** If a route is unconventional, involves a
different runtime, a recompile, a model conversion, a scheduler change, a
kernel/driver knob, or rearchitecting where a stage runs — **if it is feasible
on this machine, investigate it and write it up.** I would rather read a hard
idea with its costs stated than five safe ones. Crazy is fine. Unmeasured is
not.

## The one rule that overrides your instincts

**Measure. Do not calculate.**

This project has been burned by arithmetic repeatedly and recently:

- A weights+KV VRAM model was wrong by 380–390 MiB on all five benched models,
  in unpredictable directions.
- On 2026-08-30 three separate analyses ranked `--ctx-size 8192→4096` as "the
  biggest single saving, 600–900 MiB". Measured: **38 MiB**. Wrong by ~20×.
  (The fourth estimated ~140 MiB — still 3.7× off, in the same direction.)
- Those same analyses guessed `--parallel 1` was a no-op. Measured: **+514 MiB**.
- Two models were ruled out on paper as too big for the VRAM. Both fit, and the
  larger one fit with *more* headroom than the smaller.

So: load it, run it, and read the number off the system. `nvidia-smi`, `-lv 5`
server logs, `/proc`, `perf`, `ps`, actual wall clocks. **A number you computed
is a hypothesis. Label it as one.** Every claim in your report must say whether
it is measured, cited to a primary source, or inferred — and inferences must be
marked as such even when you are confident.

A corollary that has cost this project real time: **a green test suite is not a
working feature**, and **a passing health check is not a healthy system**. One
health check here passed through an entire GPU outage because it asked "does a
GPU exist" rather than "is the model on it".

## Hardware — verified on this machine 2026-08-30, use these, do not re-derive

```
CPU    Intel Core Ultra 9 275HX — 24 cores, 1 thread/core (no SMT)
       max-freq buckets: 2 @ 6.5 GHz, 2 @ 5.4, 6 @ 5.3, 14 @ 4.7
       L2 40 MiB (12 instances), L3 36 MiB
RAM    16 GB DDR5  (~15.4 GiB addressable)
dGPU   NVIDIA RTX 5070 Laptop, Blackwell sm_120, 8151 MiB VRAM
       usable ~7745 MiB; 406 MiB reserved and NOT attributable to a process
       measured 2 MiB used with NO model loaded — the desktop is not on it
iGPU   Intel Arrow Lake-S [8086:7d67], driver i915, own /dev/dri render node
       LIVE, and Friday uses it for NOTHING
NPU    Intel Core Ultra 200 Series NPU [8086:ad1d] at 00:0b.0
       driver intel_vpu LOADED, /dev/accel/accel0 present, mode crw-rw-rw-
       Friday uses it for NOTHING
       OpenVINO 2026.3.0 installed system-wide, including
       libopenvino_intel_npu_compiler.so
```

**Where Friday's work runs today:**

| stage | library | placement | note |
| :-- | :-- | :-- | :-- |
| LLM | `llama-server` (CUDA) | **dGPU** | 4696 MiB VRAM, 769 MB RSS |
| STT | `faster-whisper` / CTranslate2 | **CPU** | `friday/audio/stt.py:97` `device="cpu"` |
| TTS | `kokoro-onnx` / onnxruntime | **CPU** | `tts.py:86` `providers=["CPUExecutionProvider"]`, `intra_op_num_threads=8` |
| wake | `openwakeword` | **CPU** | streaming, every frame |
| speaker verify | `sherpa-onnx` | **CPU** | `speaker.py:85` `num_threads=2` |
| AEC / VAD | WebRTC APM, `webrtcvad` | **CPU** | in the turn's critical path |

The project venv's onnxruntime reports **`['AzureExecutionProvider',
'CPUExecutionProvider']`** — no OpenVINO execution provider, no iGPU, no NPU.

**Two whole accelerators are idle while the CPU does all the audio work.** That
is the "divide and rule" question. I am not telling you the answer — measure
whether moving any stage to the iGPU or NPU is actually faster, actually lower
latency, and actually better quality, and tell me where each stage belongs. Some
moves may lose; report those too, with the numbers.

**Important: the NPU is not an undiscovered opportunity. This project already
knew, and then never acted.** Read these before you start, so you build on the
record instead of repeating it:

- **ADR-019 — "The Intel NPU is excluded, but the claim must be verified."**
  It anticipated exactly this and said that if the device exists, file it as a
  **Phase 2 option for offloading whisper, freeing P-cores.**
- **OQ-10 — ANSWERED 2026-08-22, "device PRESENT".** `/dev/accel/accel0` exists,
  `intel_vpu` loaded, and it records the blueprint's "NPU dead on Linux" claim as
  **false**. Its closing line is the whole gap: *"presence is confirmed,
  throughput is not."*
- **`tech-stack.md:194`** files NPU inclusion as *"resolved — ADR-019, Phase 2
  option"*. Phase 2 shipped. The option was never taken.
- **`~/npu-test/model.onnx`** (14 MB, dated 2026-08-19) is a leftover from an
  earlier NPU experiment. `tech-stack.md:216` lists it.

So the open question is **throughput and quality, not existence** — which is
precisely what nobody has measured. This project has a documented failure mode of
an ADR deciding something that then never gets implemented (it has happened at
least three times: `cancel_reminder`/ADR-070, both Hyprland tools/ADR-074, the
wake-pause/ADR-058). **ADR-019 looks like a fourth.** Say so in your report if
you agree.

### An environment is already built for you — use it

I set this up on 2026-08-30 so you do not have to ask permission or wait:

```
~/.cache/friday-accel-eval/venv        (uv, Python 3.12)
  openvino               2026.3.1
  openvino-genai         2026.3.1.0    <- WhisperPipeline, for STT on NPU/iGPU
  openvino-tokenizers    2026.3.1.0
  onnxruntime-openvino   1.24.1        <- carries BOTH EPs, see below
```

`onnxruntime-openvino` reports:

```
['OpenVINOExecutionProvider', 'CPUExecutionProvider']
```

**This is deliberately not a replacement.** One package provides both providers,
so the intended design — my decision, treat it as a constraint — is:

> **`OpenVINOExecutionProvider` is the default. `CPUExecutionProvider` is the
> fallback.** Nothing is ripped out. If OpenVINO fails to compile a graph, is
> unavailable, or loses on measurement, the CPU path must still be there and
> must still work. Any placement you propose has to degrade to CPU cleanly.

Note `onnxruntime-openvino` is **1.24.1** where the project venv runs
**1.29.0** — a downgrade. Whether `kokoro-onnx`, `sherpa-onnx` and
`openwakeword` all work correctly on 1.24.1 is **unverified and is part of your
job**. Do not assume it.

**Devices, enumerated and smoke-tested by me:**

```
CPU     Intel(R) Core(TM) Ultra 9 275HX
GPU.0   Intel(R) Graphics (iGPU)
GPU.1   NVIDIA GeForce RTX 5070 Laptop GPU (dGPU)
NPU     Intel(R) AI Boost
```

A trivial 256x256 matmul compiled and executed on CPU, GPU.0 and NPU:

```
CPU    compile   56.4 ms | infer   2.85 ms | ok
GPU.0  compile 1319.9 ms | infer   8.40 ms | ok
NPU    compile  296.6 ms | infer 151.33 ms | ok
```

**Read that table for exactly what it proves: the devices compile and execute.
It says NOTHING about whether they are fast.** The graph is far too small to
mean anything, and the NPU's 151 ms is almost certainly first-call dispatch
overhead. Do not quote these numbers as performance. Compile time is worth
noting though — a 1.3 s iGPU compile matters for cold start, and both devices
support caching compiled blobs.

**`GPU.1` being the NVIDIA card is unexpected and I have not investigated it.**
OpenVINO reaching an NVIDIA GPU would be through OpenCL, not CUDA — so whether
that conflicts with invariant #6 is a genuine question and not one I have
answered. Work it out and tell me; do not assume either way.

## Hard constraints — a design that breaks one of these is wrong, not clever

These are non-negotiable and long-settled. Read `CLAUDE.md`'s "Hard invariants"
section in full; the ones most likely to bite an optimizer:

1. **Only `llama-server` touches CUDA.** STT and TTS do not. **Read ADR-018
   yourself before building on my reading of it** — I checked and it is more
   nuanced than the one-line summary:
   - Its *decision text* says "Only `llama-server` touches CUDA", and its
     rationale is per-process **CUDA context** overhead, no inter-process
     contention, and cheap VRAM accounting. None of that applies to an Intel
     device.
   - But its *title* says "`llama-server` is the only **GPU** consumer" — and
     the Intel iGPU is a GPU. So the NPU case is clean; **the iGPU case is
     genuinely arguable** and you should argue it rather than assume it.
   - Its enforcement is a CPU-only torch wheel, aimed at stopping Kokoro
     silently allocating **VRAM**.
   - **FR-71**'s test is *"`nvidia-smi` shows exactly one compute process
     (llama-server) during a spoken turn"*. An Intel NPU/iGPU process does not
     appear in `nvidia-smi`, so moving a stage there appears not to violate it —
     **verify that, do not take my word for it.**
2. **One turn in flight, ever** (FR-5). Any parallelism you propose lives
   *inside* a turn or between stages, never across turns.
3. **Nothing binds beyond 127.0.0.1.**
4. **Raw transcripts, raw model output, and `thought` are NEVER written to
   disk** (FR-26/57). If you benchmark STT, do not let a transcript land in a
   log, a file, or journald. Under systemd, stderr *is* journald and it
   persists.
5. **The model never supplies a path, URL, shell string, or argv element.**
6. **Execute first, then speak.** No optimization may reorder this.
7. **No irreversible tools; destructive command classes are permanently banned.**

If an optimization seems to require breaking one, it does not — write up the
conflict and stop there.

## Already settled — do not re-measure, do not re-derive

All of this is in `gemma-brief.md` with the evidence. Re-deriving it wastes your
budget and mine:

- Prompt-prefix caching is **already on** (1222 of 1235 tokens cached per turn).
- Grammar compilation costs **0.3 ms**. Dead hypothesis.
- Flash attention is **on**.
- Gemma 4 12B is 48 layers: **40 sliding-window @1024 + 8 global**,
  `n_ctx_train` 262144. Its SWA KV cache is sized
  `n_seq_max × n_swa + n_ubatch`, which is why `--parallel` matters and
  `--ctx-size` mostly does not.
- Decode obeys `tok/s ≈ 272 / weights_GB` on the dGPU. That arithmetic *does*
  hold. Memory arithmetic does not.
- Measured headroom table for both candidate models: `gemma-brief.md` §4.
- The multimodal projector is never loaded and costs nothing.

## Open threads worth your attention

- **~154 MiB of dGPU VRAM is an unexplained residual** in the accounting
  (model + KV + compute buffer ≠ total held). Nobody has identified it.
- **540 MiB of the Gemma weights stay on the host** (`CPU_Mapped model buffer`).
  Unexplained. It currently *saves* VRAM, so it may be a feature.
- **A 193.6 ms fixed per-request cost** in every LLM turn that is not prompt
  processing (only 13 tokens are new per turn) and not grammar. Unprofiled —
  suspected graph setup, sampler construction, HTTP/serialization. That is ~21%
  of the 916 ms planner p50, and 26% of the specific turn the breakdown was
  taken from.
- **`--ctx-checkpoints` defaults to 32 per slot.** Never examined.
- **Friday's real RAM footprint under load has never been measured**, and 16 GB
  is shared with the user's browser and editor.
- **Thermals and power.** 70 W TGP laptop. Nobody has looked at whether Friday
  causes throttling or fan noise, or what clock/power caps would cost.
- **CPU contention.** Every audio stage is CPU and in the critical path. There
  is a known class of blocking `subprocess.run` calls on the single event loop;
  one fix round moved most to `to_thread` but `CLAUDE.md` records that dictation
  still types on the loop. **The line number in `CLAUDE.md` is stale — I checked
  and it now points at unrelated code — so grep for the pattern, do not trust
  the citation.** While the loop blocks, Friday is deaf.

## Deliverable — ONE new markdown file, and nothing else

**Write exactly one new `.md` file in the repo root**, named after yourself so
four reports never collide again:
`<your-model-name>-optimization-analysis.md`.

**Change nothing else in the repository. Nothing.** To be explicit, because the
last round was not:

- **No code.** No `.py`, no `justfile`, no `deploy/systemd/*.service`.
- **No documentation.** Do **not** edit `CLAUDE.md`, `progress.md`, `adr.md`,
  `spec.md`, `open-questions.md`, `gemma-brief.md`, `tech-stack.md`,
  `docs/reality-check.md`, `architecture.md`, or anything under `docs/`. If you
  believe an ADR should be written, an OQ opened or closed, or a doc corrected,
  **say so inside your one file** and let me apply it. Recording decisions in the
  docs is my job, not yours — a decision I did not make must not appear in them.
- **No model or service configuration.** Propose; do not apply.
- **No git operations.** Do not commit, stage, branch, or stash. I will read
  `git status` when you are done and it should show exactly one new untracked
  file.

Everything you install, download, convert or benchmark goes **outside the repo**
(`~/.cache/friday-accel-eval/` or a scratch dir of your own), so that one new
`.md` really is the whole footprint.

Structure the file however serves the content, but it must contain:

1. **A hardware placement table** — every Friday stage, where it runs now, where
   you propose it runs, the measured effect on latency / memory / quality, and
   what the move costs. Include the moves you *rejected* and why.
2. **A ranked lever list.** For each: what it frees or speeds up, measured or
   inferred (say which), what it costs, what quality gate it must pass, and
   whether it needs my authorization.
3. **The ambitious section.** Ideas that are unconventional but feasible here.
   Rank by expected value, be explicit about risk and about what you could not
   verify. Do not self-censor for being too aggressive — self-censor only for
   being unmeasured or invariant-breaking.
4. **A "did not fit / does not work" section.** Things you tested that lost.
   These are as valuable as the wins and they stop the next person repeating you.
5. **Explicit uncertainty.** Anything you could not measure, said plainly. "I
   could not test this" is a perfectly good answer; a confident guess dressed as
   a measurement is the failure mode I am trying to avoid.

## How I will judge your report

I will check it against the machine. A previous round produced four analyses of
the same question; one invented a VRAM table and analysed the wrong model
generation, and one cited a real source and then asserted the opposite of what
that source said. Both read as the most confident of the four.

So: **cite what you measured, mark what you inferred, and link primary sources
you actually read.** If you find yourself writing a number you did not observe,
stop and go observe it. I would much rather have a short report that is entirely
true than a long one I have to re-verify line by line.

## Ground rules for touching the machine

- **Change nothing in the repo except your one new `.md` file** — no code, no
  service file, no model configuration, and no documentation. See "Deliverable"
  above; it is the rule I care most about. This is an audit. Propose; do not
  apply.
- You may stop `friday-llm` to run experiments **if you restart it afterwards
  and prove it** with `just selftest` (must be 8/8, `llm_on_gpu` PASS).
- Never run `just voice` while the `friday` service is up — two daemons fight
  over the microphone and the PTT socket.
- `pgrep -f foo` matches its own command line. Bracket it: `pgrep -f "[f]oo"`.
- `just test-egress` **cannot detect egress** — it inspects listening sockets.
  Do not cite it as proof of anything.
- **Installing is pre-authorised. Do not ask.** If you need a package, a
  runtime, a converted model or a different build to measure something, install
  it and say so in the report. My standing instruction: *"whatever they want
  installed, install them right now. We can just delete if useless."* Put new
  work in `~/.cache/friday-accel-eval/` or a scratch venv of your own.
- **The one exception: do not install into or modify the project venv**
  (`~/Projects/Personal/Intern/friday/.venv`) or `pyproject.toml`. The live
  assistant runs from it, and `onnxruntime-openvino` would displace the
  `onnxruntime` it depends on. Benchmark in a scratch environment; if a move
  wins, propose the migration and let me run it.
- Downloading models is fine. Say what you downloaded and where it landed.
- Outbound network beyond package installs and documentation: tell me what and
  why. There is an open defect (D13/D15) about this repo phoning home, so I care
  about the distinction.
