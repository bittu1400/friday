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
| Model | Qwen2.5-7B-Instruct **Q4_K_M** (GGUF) | ADR-002 |
| Artifact | `bartowski/Qwen2.5-7B-Instruct-GGUF`; `Qwen/…` first-party = fallback | ADR-029 |
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
| Capture | `sounddevice` (PortAudio), preallocated 15 s ring buffer, mic gate | architecture §2, §5 |
| Echo handling | half-duplex boolean mic gate — **no** acoustic echo cancellation | ADR-014 |
| torch wheel | **None — the venv is torch-free.** STT is CTranslate2, TTS is onnxruntime; neither needs torch (ADR-039 rejected the PyTorch Kokoro path) | ADR-018, ADR-039 |

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
| Migrations | forward-only versioned SQL, applied at startup (no ORM) | ADR-010, architecture §9 |
| Location / perms | `~/.local/state/friday/memory.db`, `0600` file / `0700` dir | ADR-023, ADR-010 |
| At-rest crypto | **none** — disk is the boundary, provisionally (OQ-05 open) | ADR-031 |
| Transcripts | in-memory ring buffer (last 20 turns), off by default, never on disk | ADR-028 |

---

## UI and input

| Piece | Choice | Owner |
| :-- | :-- | :-- |
| Interface | `textual` TUI — no web UI | architecture §9 |
| Activation | **PTT** = Copilot key (chord `SUPER SHIFT, XF86Assistant`), hold-to-talk via Hyprland `bind`/`bindrelease` -> `friday-ptt` -> unix socket. No evdev. | ADR-013, OQ-03 |
| Wake word | **none** in Phase 1 | ADR-012 |

PTT path locked at **G6**: bind path (evdev not needed). Copilot key tracks
physical hold (verified via `wev`), so hold-to-talk works (OQ-03).

---

## Egress — the only outbound path

| Piece | Choice | Owner |
| :-- | :-- | :-- |
| Search | self-hosted **SearXNG** on `127.0.0.1:8888` | ADR-015 |
| Modes | **local** (search refuses audibly) / **connected** (opt-in, visibly indicated) | ADR-015 |

Nothing binds beyond `127.0.0.1`. A turn that consumed search output cannot
dispatch an action (ADR-008).

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
   video       mpv        media, default for "play a video"
   vlc         vlc        media, second player, named only
```

Five entries. Plus `youtube_search` — the single audited exception where a
model-supplied string (the query) reaches an argv element, under the five
constraints in ADR-027. Excluded: firefox, kitty (removed 2026-08-22),
file managers, Spotify, a general `open_url`.

Owner: **ADR-032** (supersedes ADR-026), ADR-027.

---

## Deliberately absent

No vector DB, no embedding model, no ORM, no message queue, no Docker for
the app, no web UI, no plugin system, no retry middleware, no
LangChain/agent framework. Each absence is a decision (architecture §9);
adding any requires an ADR that names the problem it solves.

---

## Locked later, not here

| Thing | Gate | Status |
| :-- | :-- | :-- |
| Intel NPU inclusion (excluded Phase 1, present/verified) | G1 | resolved — ADR-019, Phase 2 option |
| STT CPU-vs-GPU final call | ~~G1~~ G6 | **RESOLVED — CPU, small.en (ADR-042)** |
| TTS voice preset | G5 | **RESOLVED — af_bella (ADR-005/040)** |
| PTT transport (Hyprland bind vs evdev) | G6 | **RESOLVED — bind, Copilot key (ADR-013/OQ-03)** |
| Streaming TTS (only if measured TTFA demands it) | G6 | OPEN — pending live TTFA (OQ-09) |

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

