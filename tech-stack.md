# Friday — Tech Stack

The single place that names every technology Friday uses and points at the
decision that put it there. It is a **reference index**, not an authority:
when this file and an ADR disagree, the ADR wins and this file is the bug.
Every row cites the ADR or spec that owns the choice.

Scope: Phase 1. Anything marked _pending_ is locked at the gate named, not
here.

---

## Runtime and tooling

| Piece | Choice | Owner |
| :-- | :-- | :-- |
| Language | Python **3.12** (pinned; never the system 3.14) | ADR-016 |
| Package / env manager | `uv`, committed `uv.lock` | ADR-016 |
| Task runner | `just` | ADR-025 |
| Concurrency | single `asyncio` event loop; CPU work via `asyncio.to_thread` | architecture §5 |
| Process management | `systemd --user` units (no login-shell scripts) | architecture §8 |

Style constraints (from CLAUDE.md): type hints on every public function,
`frozen=True` dataclasses by default, no ORM / LangChain / agent framework
/ plugin system / retry middleware.

---

## Inference — the only GPU consumer

| Piece | Choice | Owner |
| :-- | :-- | :-- |
| Model | **Gemma 4 12B IT QAT `UD-Q4_K_XL`** (GGUF), swapped in 2026-08-30. sha256 `90fd44e2…c940c370`. Runs with `--parallel 1 -fa on --reasoning off` — all three load-bearing | **ADR-090**, ADR-089 |
| Model (rollback) | Qwen2.5-7B-Instruct **Q4_K_M** (GGUF) — kept in the same directory. NOTE: reverting reintroduces D19/D20/D21 | ADR-002, ADR-084 |
| Model candidate (NOT running) | Gemma 4 12B QAT `UD-Q4_K_XL`, 6405 MiB, on disk at `~/.cache/friday-model-eval/`. Ties on `just eval`, better chat, but 891 ms planner p50 vs 373 and only 214 MiB VRAM spare. Needs `--reasoning off`. | **ADR-084**, OQ-47 |
| Artifact | `unsloth/gemma-4-12B-it-qat-GGUF` (the QAT quant is load-bearing: bartowski's ordinary Q4_K_M of the same 12B is 7305 MiB and does not fit). Rollback: `bartowski/Qwen2.5-7B-Instruct-GGUF` | ADR-090, ADR-029 |
| Server | `llama.cpp` / `llama-server`, built for **sm_120** (Blackwell) | ADR-002, ADR-021 |
| Context | 8192 tokens, KV cache `q8_0` (k and v) | ADR-003 |
| Structured output | GBNF grammar **and** application-side validator, both always | ADR-006 |
| Grounding lock | `final.gbnf` action enum == `["none"]` | ADR-008 |

The security model depends on `llama.cpp`'s grammar support, so the build
commit is pinned and grammar behaviour is verified by test at G1/G3, never
assumed.

---

## Audio — all CPU, zero VRAM

| Piece | Choice | Owner |
| :-- | :-- | :-- |
| STT | `faster-whisper` **`small.en`**, `device=cpu`, `compute_type=int8`, `cpu_threads=8`, `beam_size=1`, hotwords-biased, VAD — **NO torch** (CTranslate2). p95 741 ms measured | ADR-004, **ADR-042** |
| TTS | **Kokoro-82M** via `kokoro-onnx` (ONNX Runtime, `CPUExecutionProvider`, fp32 model, 8 threads), one female en-US voice — **NO torch** | ADR-005, ADR-039 |
| Capture | `sounddevice` (PortAudio), preallocated 15 s ring buffer, mic gate. Both callbacks run behind one `CallbackGuard` — nothing may escape into PortAudio, which answers an exception by never calling back again | architecture §2, §5, M-A1 |
| Echo handling | **Phase 1: half-duplex boolean mic gate only.** Phase 2 (G10) added a real WebRTC APM echo canceller on top — the gate did not go away | ADR-014, **ADR-060** |
| Wake word | **openWakeWord** `hey_jarvis_v0.1.onnx` (CPU, streaming — it must be fed EVERY frame or it returns a stale score, OQ-29) | ADR-055, ADR-061 |
| VAD | **Silero** (`silero_vad_op18_ifless.onnx`, ONNX/CPU, SHA256-pinned, `just fetch-vad`) + a `SpeechGate` debounce state machine. Buffers the mic path's 20 ms frames to the graph's 512 samples and holds the last verdict, so no caller's frame size changed. `webrtcvad` is the fallback and logs the degradation. Arms end-of-speech only on FSM acceptance, never on wake detection | **ADR-095**, ADR-062, ADR-071 |
| Speaker verification | **3D-Speaker CAM++** via `sherpa-onnx` (CPU, 512-dim voiceprint, 10-utterance enrolment). OFF by default and it fails **OPEN** with no voiceprint enrolled | ADR-059, ADR-063 |
| torch wheel | **None — the venv is torch-free.** STT is CTranslate2, TTS is onnxruntime; neither needs torch (ADR-039 rejected the PyTorch Kokoro path) | ADR-018, ADR-039 |

### Pinned Python dependencies (the whole runtime set)

Every runtime dependency, its **distribution** name — which is not always the
import name — and the version installed on this machine. `pyproject.toml` is the
source of truth for the floors; this table is what is actually resolved.

| Distribution | Version | Imported as | For |
| :-- | :-- | :-- | :-- |
| `faster-whisper` | 1.2.1 | `faster_whisper` | STT (pulls `ctranslate2` 4.8.1, **not** torch) |
| `kokoro-onnx` | 0.6.1 | `kokoro_onnx` | TTS (pulls `onnxruntime` 1.29.0) |
| `openwakeword` | 0.4.0 | `openwakeword` | wake word |
| `webrtcvad-wheels` | 2.0.14 | **`webrtcvad`** | VAD — note the name mismatch: `uv add webrtcvad` gets you a source package that needs a compiler. **Measured 2026-08-30 as the cause of D3: it emits end-of-speech on only 15 of 20 real clips. Demoted to fallback 2026-08-31 (ADR-095); kept so a missing model file degrades loudly rather than to no VAD at all** |
| `pywebrtc-audio` | 0.1.0 | **`pywebrtc_audio`** | WebRTC APM echo canceller (underscores, not the hyphen-to-nothing you might guess) |
| `sherpa-onnx` | 1.13.6 | `sherpa_onnx` | speaker verification |
| `sounddevice` | 0.5.6 | `sounddevice` | PortAudio capture + playback |
| `soundfile` | ≥0.14.0 | `soundfile` | WAV I/O for enrolment and `just say` |
| `textual` | 8.2.8 | `textual` | the text-mode TUI |
| dev: `pytest` | ≥8 | — | the suite; the G2 eval harness itself is stdlib-only |

**No torch, no CUDA wheels, no LangChain, no agent framework.** The LLM is
reached over HTTP with `urllib` from the stdlib — there is no OpenAI client
either. Every addition to this table goes through CLAUDE.md rule 7 (enumerate,
`--dry-run` the footprint, benchmark on THIS laptop, pin, ADR).

Enforcement: only `llama-server` touches CUDA. The original FR-71 hazard
was a CUDA torch pulled in by the PyTorch Kokoro runtime; ADR-039's
`kokoro-onnx` removes torch from the venv entirely, so FR-71 holds by
construction (no CUDA code to misbehave). TTS voice preset locked at **G5**
(af_bella). STT locked at **G6** (ADR-042): the FR-10 `large-v3-turbo` pin
failed on CPU (2.7 s); `small.en` int8 beam1 hotwords hits p95 741 ms, so it
stays CPU — no GPU arm, ADR-018 remains closed.

---

## Storage

| Piece | Choice | Owner |
| :-- | :-- | :-- |
| Database | **SQLite**, WAL, single-writer async queue, `busy_timeout=5000` | ADR-010 |
| Migrations | forward-only versioned SQL (`001_init.sql`), applied at startup | ADR-010, architecture §9 |
| Location / perms | `~/.local/state/friday/memory.db`, `0600` file / `0700` dir | ADR-023, ADR-010 |
| At-rest crypto | **none** — disk is the boundary, single-machine (OQ-05 open) | ADR-031 |
| Transcripts | in-memory ring buffer (`Dialogue`), never on disk | ADR-028, ADR-048 |
| Habit mining | deterministic SQL patterns from `action_audit` into `<user_habits>` | ADR-049 |
| Long-term memory | distilled 1-2 sentence session summaries in `session_summaries` | ADR-050 |

---

## UI and input

| Piece | Choice | Owner |
| :-- | :-- | :-- |
| Interface | `textual` TUI + background voice daemon — no web UI | architecture §9 |
| Activation | **PTT** = Presentation key (`XF86Presentation`), toggle on/off (0.4 s debounce) via Hyprland `bind` -> `friday-ptt` -> unix socket. No evdev. | ADR-013, **ADR-044** |
| Wake word | **none in Phase 1** — Phase 2 (G10) added `hey_jarvis`; both triggers are live and PTT is still the interrupt, because voice barge-in is OFF by default (ADR-064) | ADR-012, **ADR-055** |

PTT path locked at **G6**: bind path (evdev not needed). Copilot key leaked Super
modifier; Presentation key (`XF86Presentation`) is clean and drives toggle (ADR-044).

---

## Egress — the only outbound path

| Piece | Choice | Owner |
| :-- | :-- | :-- |
| Search | self-hosted **SearXNG** on `127.0.0.1:8888` (`friday-searxng.service`) | ADR-015, ADR-045 |
| Modes | **local** (search refuses audibly) / **connected** (opt-in, visibly indicated) | ADR-015, ADR-046 |

Nothing binds beyond `127.0.0.1`. A turn that consumed search output cannot
dispatch an action (ADR-008).

---

## Observability & Service Layer

| Piece | Choice | Owner |
| :-- | :-- | :-- |
| Logging | Structured JSON lines to `friday.log`, `10 MB x 5` rotation, `/home/` redacted. `no_disk` records (transcripts, raw model output) are dropped from the log file **and from stderr when stderr is journald** — under systemd `FRIDAY_DEBUG` shows nothing, by design (H8) | ADR-051, FR-43, **FR-57b** |
| Systemd Units | `friday-llm.service`, `friday.service`, `friday-searxng.service` | ADR-051, architecture §8 |
| Self-Test | `just selftest` / `friday --selftest` (8 checks: LLM, search, GPU arch, **LLM actually on GPU**, DB perms/schema incl. WAL sidecars, audio, panic, binds) | ADR-051 |

---

## Application registry (`open_app` enum)

Closed enum. The model emits an opaque id; **code** builds argv. Extend by
editing code plus an eval fixture, never by config.

```
   app id      binary     role
   ---------   --------   -----------------------------------------
   browser     brave      the browser, default for "browser" / "the web"
   terminal    foot       the terminal, default for "terminal" / "shell"
   editor      code       the editor
   video       mpv        media, default for "play a video".  argv carries
                          --idle=yes --force-window=yes: bare `mpv` prints its
                          version and exits 0, so the launch "succeeded" with
                          no window (found live 2026-08-25)
   vlc         vlc        media, second player, named only
```

Five **curated** entries, and since 2026-09-02 they are the semantic core of a
set that is otherwise **generated from the machine's XDG desktop entries** —
101 applications here (ADR-097). The five above always win a collision: the
eval fixtures, the prompt and the habits miner speak them. The set is still a
CLOSED enum, exact-matched after NFKC; only its population moved from
hand-typed to machine-read. Entries whose `Exec` escalates privilege (`pkexec`
and friends, now in `ban.BANNED_BINARIES`) or invokes a shell are never
offered; a `Settings`-category entry is offered but confirm-gated.

Plus `youtube_search` — still **the single** audited exception
where a model-supplied string (the query) reaches an argv element, under the
five constraints in ADR-027.

The Hyprland tools' argv element is a **Lua expression** since Hyprland 0.56
(`hl.dsp.focus{workspace=2}`), but that is deliberately *not* a second
exception: no parameter is formatted into it — a closed-set param selects one of
sixteen constants built at import from code-owned literals, so there is nothing
to escape and nothing to inject into (ADR-074). Excluded: firefox, kitty (removed 2026-08-22),
file managers, Spotify, a general `open_url`.

Owner: **ADR-032** (supersedes ADR-026), ADR-027.

---

## Deliberately absent

No vector DB, no **text** embedding model, no ORM, no message queue, no Docker
for the app, no web UI, no plugin system, no retry middleware, no
LangChain/agent framework. Each absence is a decision (architecture §9);
adding any requires an ADR that names the problem it solves.

*"No embedding model" needs the qualifier since G13:* speaker verification runs
a 512-dim **voice** embedding (3D-Speaker CAM++ on CPU, ADR-059/063). What is
absent is semantic text embedding and the retrieval stack that comes with it —
memory is SQLite rows and a RAM dialogue buffer, not a vector index.

---

## Locked later, not here

| Thing | Gate | Status |
| :-- | :-- | :-- |
| Intel NPU inclusion (excluded Phase 1, present/verified) | G1 | **MEASURED and REJECTED 2026-08-30 — ADR-088.** ADR-019 filed it as a Phase-2 option and Phase 2 shipped without it; it was a fourth dead ADR. Throughput is now known: Whisper on NPU is 1.6x faster but cannot take `hotwords`; TTS core-dumps; the speaker model SIGSEGVs on utterances ≤1.9 s; wake already costs 0.78 ms/frame. `~/npu-test/model.onnx` is superseded by `scripts/accel_stage_bench.py` |
| STT CPU-vs-GPU final call | G6 | **RESOLVED — CPU, small.en (ADR-042)** |
| TTS voice preset | G5 | **RESOLVED — af_bella (ADR-005/040)** |
| PTT transport (Hyprland bind vs evdev) | G6 | **RESOLVED — bind toggle, XF86Presentation (ADR-044)** |
| Streaming TTS (only if measured TTFA demands it) | G6 | **RESOLVED — not needed (p95 2.73s < 4.4s fail cap, OQ-09)** |
| Service units & self-test | G9 | **RESOLVED — systemd user units + selftest CLI (ADR-051)** |

---

## Appendix — other local models on this machine (NOT used by Friday)

Inventory snapshot, 2026-08-22. Recorded for reference only. Friday does
**not** use any of these, and does **not** use Ollama as its server —
`llama-server` is the deliberate choice (ADR-002, for GBNF grammar). This
list is volatile; the user may add or remove models at any time.

| Model | Managed by | Size | Location |
| :-- | :-- | :-- | :-- |
| `qwen2.5-coder:7b` | Ollama | 4.4 G | `~/.ollama/models` (GGUF) |
| `llama3.1:8b` | Ollama | 4.6 G | `~/.ollama/models` (GGUF) |
| `deepseek-r1:7b` | Ollama | 4.4 G | `~/.ollama/models` (GGUF) |
| `gemma3:4b` | Ollama | 3.2 G | `~/.ollama/models` (GGUF) |
| `model.onnx` | none (loose file) | 14 M | `~/npu-test/` — an NPU experiment, relates to ADR-019 |

Ollama blob store totals ~17 G. If the pinned Qwen2.5-7B GGUF (ADR-029)
ever misbehaves, these are on-disk points of comparison — but a swap still
follows ADR-029 (re-run the eval baseline; never compare scores across
artifacts). Friday's own weights live only in
`~/.local/share/friday/models/` (ADR-023), separate from all of the above.



## Measured and NOT adopted (2026-08-30 drill — ADR-085…088)

Recorded so the next person does not re-derive them. All benched on this
laptop at `powerprofilesctl get` = `balanced`, against the real 20-clip DMIC
corpus where applicable. Harnesses in `scripts/`, full numbers in
`docs/hardware-placement.md`.

| candidate | for | measured | verdict |
| :-- | :-- | :-- | :-- |
| `silero-vad` (v4 / current / If-free) | VAD | end-of-speech **20/20** vs webrtcvad's 15/20, 0.048 ms per 32 ms frame | **ADOPTED 2026-08-31 (ADR-095)** — the `op18-ifless` export, by SHA256-pinned file. The pypi package itself is NOT a dependency: `onnxruntime` was already installed via kokoro-onnx/openwakeword |
| DTLN-aec 128/256/512 (TF-lite, read by OpenVINO) | AEC | 8–20 dB more suppression than WebRTC APM on every capture; preserves 152/243 of the user's frames vs 68 | **WINS — but fix D18 first, OQ-52** |
| `supertonic` 1.3.1 | TTS fallback | `F1` at `total_steps=2`: 308 ms short reply, RTF 0.070 | **ADOPTED as fallback, ADR-085 — NOT in `pyproject.toml`, OQ-55** |
| `useful-moonshine-onnx` | STT | 4x faster (p95 182 ms) at **10/20** misses vs Whisper's 4/20, after three tuning rounds | rejected, ADR-086 |
| `kittentts` 0.1.3 | TTS | slower than Kokoro on every axis | rejected and **removed**, ADR-085 |
| `openvino-genai` on NPU | STT | p95 456 ms but **cannot take `hotwords`** (static shapes) | rejected on quality, ADR-088 |
| `openvino-genai` on iGPU | STT | p95 1959 ms — 2.4x slower than CPU | rejected, ADR-088 |
| `faster-whisper` on CUDA | STT | p95 **107 ms**, 556 MiB, no LLM contention | **forbidden by invariant #6 — OQ-53** |
| OpenVINO on `GPU.1` (NVIDIA via OpenCL) | any | second `nvidia-smi` compute process **and** `CL_INVALID_VALUE` | closed twice over, ADR-088 |

**Scratch environments** (outside the repo, deletable): `~/.cache/friday-accel-eval/`
(OpenVINO + openvino-genai + supertonic + moonshine + DTLN-aec models + a
separate CUDA venv), `~/.cache/whisper-bench/` (**the 20 real DMIC clips, their
reference transcripts, and the ADR-042 harness — do not delete these**),
`~/.cache/kokoro-bench/`.

**Vendored into Friday's data dir 2026-08-30:**
`~/.local/share/friday/models/supertonic/` (383 MB, SHA256s in ADR-085).
