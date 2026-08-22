> **ARCHIVED 2026-08-22.** Historical only. Superseded by `friday.md` (v5),
> `spec.md`, `adr.md`, `architecture.md`. Contains claims corrected in `adr.md`
> (see ADR-003, ADR-021, ADR-022). Do not cite as current.

# 🤖 Project "Friday" - Architecture & Blueprint (v4 — Final, Build-Ready)

**Date:** 2026-08-22
**Status:** Phase 1 Complete (Environment & Model Selection Verified) — Ready for implementation
**Target Environment:** Arch Linux, Hyprland (Wayland), PipeWire, `foot` terminal.

**Changelog from v3:** Swapped TTS engine from Piper to **Kokoro-82M** (§3C) — same zero-VRAM CPU footprint, meaningfully more natural/expressive delivery, with a specific female voice preset chosen for Friday's persona. Added a **Future Updates** section (§7) capturing screen-vision as a deferred, not-yet-scoped capability so it doesn't get lost, without pulling it into Phase 1 build scope.

**Changelog from v2:** Trilingual support (Hindi/Spanish) deferred to Phase 2. Phase 1 is English-only — no language detection, no language-override regex, single TTS voice. This shrinks the surface area for bugs so the core pipeline (Audio → LLM → Action → TTS) can be proven solid before multilingual complexity is added back in.

**Changelog from v1:** Fixed malformed action-JSON schema, added a real tool-call loop for search/recommendations, added a persistence layer for preferences, added wake-word training note, scoped `evdev` PTT to a single keycode, corrected VRAM headroom assumptions.

---

## 1. The Mandate (Strict Scope)
We are building a local, offline-first AI assistant named "Friday".

**In Scope (Phase 1):**
1. **English-only fluidity.** Auto-detects spoken/typed English. *Trilingual support (Hindi, Spanish) is explicitly deferred to Phase 2 — do not build language routing, multilingual TTS voices, or language-override regex interceptors in this phase. Hardcode English for STT and TTS.*
2. **Voice Priority:** Highest quality voice realistically achievable on local hardware.
3. **Direct Actions:** Open apps, run whitelisted scripts, remember preferences, perform live web searches, give recommendations.
4. **Conversational UI:** Fluid speech. No raw reasoning, chain-of-thought, or step-by-step logic shown to the user.
5. **Activation Modes:** Switchable between Always-Listening (Wake Word), Push-to-Talk (PTT), and Plain Text Chat.

**Out of Scope (For Now):** Hindi/Spanish support (Phase 2), smart home control, multi-device sync, autonomous background agents.

---

## 2. Hardware Reality: Paper vs. Runtime

| Component | Paper Spec | Verified Runtime Reality | Impact on Build |
| :--- | :--- | :--- | :--- |
| **GPU (VRAM)** | 8 GB GDDR7 (RTX 5070) | **7,653 MiB free** (at idle) | Usable budget, but idle ≠ real load — see §3D. |
| **System RAM** | 16 GB DDR5 | **9,131 MiB available** (at idle) | OS/Hyprland uses ~6GB. ~9GB left for CPU fallbacks. |
| **NPU** | Intel Core Ultra 200 NPU | **Effectively dead on Linux** | Ignored. Relying 100% on dGPU + CPU. |
| **CPU** | Core Ultra 9 275HX (24 cores) | Fully available | Runs Kokoro TTS and the orchestrator comfortably. |

---

## 3. The Stack: Models & Tradeoffs

### A. The Brain (LLM)
* **Selection:** `Qwen 2.5 7B Instruct` (Q4_K_M quantization).
* **Why:** Kept even though Phase 1 is English-only — its English instruction-following and structured JSON tool-calling are currently stronger out-of-the-box than comparable 7-8B alternatives (e.g. Llama 3.1 8B). No reason to swap the brain just because the mouth is monolingual for now; it also means no re-architecture is needed when Phase 2 re-enables Hindi/Spanish.
* **Memory Footprint:** ~4.8 GB VRAM.
* **Constraint:** Context window capped at 2048 tokens to prevent KV-cache overflow — see §4D for why this forces an external memory layer.

### B. The Ears (STT)
* **Selection:** `faster-whisper` (large-v3-turbo, int8 quantized).
* **Phase 1 config:** language auto-detection is **bypassed**. Pass `language="en"` directly to `faster-whisper` rather than letting it detect. This skips the detection pass entirely — roughly 15-20% faster transcription — and removes the risk of Whisper hallucinating a different language on a mumbled or noisy input. (Auto-detect gets re-enabled in Phase 2.)
* **Why this model regardless:** `int8` CTranslate2 backend is fast on CUDA, and it's the same model Phase 2 will lean on for Hindi/Spanish, so no swap needed later.
* **Memory Footprint:** ~1.5 GB VRAM during inference.

### C. The Voice (TTS)
* **Selection (Phase 1):** **Kokoro-82M**, single voice — a female American English preset (`af_heart`, `af_bella`, or `af_sky`; audition all three against the persona and lock one before Day 2). No other voice models are downloaded or wired up this phase. (Additional Kokoro presets for ES/HI, or a routing layer between them, are deferred to Phase 2 alongside the rest of multilingual support.)
* **Why Kokoro over Piper:** Piper was the original safe pick specifically because it's free, CPU-only, and zero VRAM — but its delivery is flat/robotic. Kokoro-82M (StyleTTS2-lineage, Apache 2.0) keeps the *exact same* CPU-only, 0MB-VRAM profile — critically, it does **not** change the VRAM budget in §2/§3D at all — while sounding meaningfully more natural and expressive. There's no tradeoff here; it's a strict upgrade over Piper for this hardware.
* **Why not XTTSv2 or Chatterbox:** Both sound better still (XTTSv2 supports voice cloning; Chatterbox has beaten ElevenLabs in blind listening tests), but both need real GPU VRAM (~4GB for XTTSv2; Chatterbox is a 0.5B model). 4.8 (LLM) + 1.5 (STT) + 4.0+ (either of these) blows past the 8GB card instantly — same OOM math as v1's Piper-vs-XTTSv2 comparison, just with a different competitor. If a future hardware upgrade or a lighter LLM ever frees up 4GB+ of headroom, either is worth revisiting for cloning a fully custom voice — Kokoro has no cloning, only its 54 fixed presets.
* **Known setup gotchas:** requires Python <3.13 and the `espeak-ng` system package. Get weights only from `huggingface.co/hexgrad/Kokoro-82M` — several lookalike domains (`kokorotts.ai`, `kokorotts.net`) are impersonation sites, not the real project.

### D. Real VRAM Headroom (Corrected)
The §2 numbers are *idle* readings. Two extra costs aren't in that budget:
* **Per-process CUDA context overhead:** if the LLM server and faster-whisper run as separate processes, each initializes its own CUDA context — typically **300–500MB apiece** on top of model weights, not included in the 4.8GB / 1.5GB figures above.
* **Desktop load:** a browser, Hyprland compositor effects, or a second GPU client running at the same time will eat into the same pool the idle reading didn't account for.

**Action item before Day 2:** load the LLM and STT models simultaneously under a normal desktop session (browser open, compositor running) and watch `nvtop` for the real peak, not just the idle baseline. Budget ~6.5GB as the realistic working ceiling, not 7.65GB.

---

## 4. The Pipeline & Execution Logic

### A. Input & Activation
* **Wake Word:** `openWakeWord` (CPU-based, low resource).
  * **Correction:** "Friday" is not one of openWakeWord's pretrained wake words (it ships things like `hey_jarvis`, `alexa`, `hey_mycroft`). Custom wake words require running openWakeWord's training pipeline — synthetic sample generation (via a TTS engine, plus noise/room augmentation) followed by a short training run. Budget an afternoon for this before it's usable; it isn't a config flag.
* **Push-to-Talk:** `evdev` raw input listener, **scoped to a single keycode**.
  * *Why evdev at all:* Wayland/Hyprland blocks global hotkey listeners for security, so a compositor-level keybind can't trigger PTT. `evdev` reads directly from `/dev/input/`, bypassing that restriction.
  * *Scoping requirement:* naively reading the raw event stream from a keyboard device sees *every* keystroke on that device, not just the PTT key. The listener must filter to one specific keycode (e.g. `KEY_RIGHTCTRL` or a dedicated key) at the read loop, rather than parsing and discarding the full stream — both for correctness and because a background process silently reading all keyboard input is worth keeping deliberately narrow.
  * *Permissions:* requires the running user to be in the `input` group, or a udev rule granting access to `/dev/input/eventX` — this does not work for a normal user out of the box.
* **Text:** `textual` (Python TUI). Renders natively in the terminal without a heavy Electron web UI.

### B. Language Logic — Deferred to Phase 2
* **Auto-Detect:** Bypassed for Phase 1 (see §3B) — `language="en"` is passed directly to `faster-whisper`, so there's no detected-language code to inject into the system prompt at all.
* **Manual Override:** Deferred to Phase 2. No regex interceptor is built this phase. When multilingual support returns, this section should be restored with override phrases for all supported languages (not just English), so a mid-conversation switch works regardless of which language the user is currently in.

### C. Action Execution — Corrected JSON Contract
The v1 schema had a stray, unparseable fragment sitting outside the JSON object. Fixed contract below — the model emits **only** this object, nothing else:

```json
{
  "thought": "Internal reasoning, hidden from the user",
  "action": {"name": "open_app", "params": {"app": "firefox"}},
  "speech": "Opening Firefox for you."
}
```

Logging and persistence are **orchestrator responsibilities**, not part of the model's output contract:
* Every `thought` + `action` pair is written to the active session's log file (for debugging/audit), never surfaced in the UI or spoken.
* At session end (or periodically), the orchestrator writes a **summary** of that session's actions to a local store on disk (see §4D) — this is a separate write, generated by the orchestrator, not something the model outputs per-turn.

**Execution flow:** orchestrator parses the JSON → sends `speech` to Kokoro TTS → concurrently dispatches `action` to the `ActionExecutor`.
**Safety:** `ActionExecutor` uses a strict whitelist. Apps launch via `hyprctl dispatch exec`. Scripts run **only** from `~/friday/scripts/`. No arbitrary shell commands.

### D. Tool-Call Loop — New (was missing in v1)
The single-shot schema in §4C works fine for actions where the ack doesn't depend on a result (`open_app`, `run_script`). It **cannot** work for `web_search` or "give a recommendation," because the model can't write accurate `speech` about results it hasn't seen yet. v1 had no second turn — this is the fix:

1. **Turn 1:** LLM receives the user request, emits an action-only JSON (`action.name = "web_search"`, no meaningful `speech` yet, or a placeholder like `"Let me check."`).
2. **Orchestrator executes** the tool (search, preference lookup, etc.) and captures the result.
3. **Turn 2:** orchestrator feeds the tool result back into context as a short system/tool message and re-prompts the LLM for a final `{thought, action: {"name": "none"}, speech}` object — this time `speech` is grounded in the actual result.
4. Only the **final** turn's `speech` is sent to TTS. Intermediate turns are logged but never spoken.

This adds one extra LLM round-trip for search/recommendation-class requests only; direct actions stay single-shot and low-latency.

### E. Preference Persistence — New (was missing in v1)
With context hard-capped at 2048 tokens, nothing said more than a few turns ago survives in-window — "remember preferences" cannot rely on conversation history alone.

* **Store:** a local SQLite file (`~/friday/memory.db`) — a `preferences` table (key/value + timestamp) and a `session_summaries` table (the per-session summaries from §4C).
* **Read path:** at the start of each turn, the orchestrator pulls the current preference set and injects a compact digest (not the raw table) into the LLM's system prompt, so it's aware of standing preferences without spending the whole context budget on them.
* **Write path:** when the LLM's `action.name` is `remember_preference` (a new whitelisted action type), the orchestrator writes it to SQLite immediately rather than trusting it to persist in-context.

---

## 5. Audit of AI Reasoning (Why I asked/decided what I did)

1. **Why did I refuse to rely on your spec sheet and demand runtime memory checks?**
   *Reasoning:* Paper specs lie. A high-res Wayland compositor can eat 1.5–2.5GB VRAM at idle before any model loads. `nvidia-smi` / `free -m` gave the actual ceiling (7.65GB VRAM / 9.1GB RAM) to build against — now further corrected downward in §3D for real per-process overhead.
2. **Why did I tell you to ignore the Intel NPU?**
   *Reasoning:* Arrow Lake-HX's Core Ultra 200 NPU lacks mature out-of-the-box Linux support without proprietary, messy drivers. Building around it would burn Week 1 for no payoff. Defaulted to the proven RTX 5070.
3. **Why did I force CUDA 12.4 PyTorch wheels when you have CUDA 13.3 drivers?**
   *Reasoning:* NVIDIA drivers are backward compatible; PyTorch stable hasn't shipped 13.3 wheels yet. Compiling against 13.3 or chasing nightlies risks dependency hell. 12.4 wheels run fine on the 610.57 driver.
4. **Why `foot` + `zellij` instead of just `foot`?**
   *Reasoning:* `foot` is fast and minimal but has no native split-pane support. Monitoring VRAM (`nvtop`), logs, and code simultaneously needs multiplexing. `zellij` (installable via existing Rust/Cargo) does that without five separate `foot` windows.
5. **Why did I enforce a strict JSON schema for the LLM?**
   *Reasoning:* You explicitly asked for no visible step-by-step reasoning — just natural speech and action. Separating `thought` from `speech` lets the orchestrator execute silently and speak only the `speech` string. **Correction in this revision:** the v1 schema had a syntax error (an orphaned parenthetical outside the JSON), and lacked any path for actions whose result the model needs before it can speak — both fixed in §4C/§4D above.

---

## 6. Current Status & Next Steps

**Completed:**
- [x] Hardware runtime verification (7.65GB VRAM confirmed, real headroom corrected in §3D).
- [x] Architecture and model selection finalized.
- [x] Environment setup commands provided.
- [x] Design audit: JSON schema fixed, tool-call loop added, preference persistence added, wake-word/PTT caveats documented.
- [x] Scope narrowed to English-only for Phase 1; trilingual (Hindi/Spanish) explicitly deferred to Phase 2.
- [x] TTS upgraded from Piper to Kokoro-82M for a more natural, expressive female voice — no VRAM cost change.

**Next Steps (Pending your review):**
- [ ] Review this revision to confirm the fixes, English-only scoping, and Kokoro swap match your intent.
- [ ] Run Phase 1/2/4 install scripts; verify the LLM loads without OOMing **under real desktop load**, not just idle.
- [ ] Stand up `memory.db` (SQLite) with `preferences` and `session_summaries` tables before wiring up STT.
- [ ] Install Kokoro-82M (`pip install "kokoro>=0.9.2" soundfile`, plus `espeak-ng`), confirm Python <3.13, and audition `af_heart` / `af_bella` / `af_sky` to lock Friday's voice.
- [ ] **Day 2:** hook `faster-whisper` to the PipeWire mic with `language="en"` hardcoded, build the scoped `evdev` PTT listener, and implement the two-turn tool-call loop for `web_search`.

**Phase 2 (Deferred):**
- [ ] Re-enable Whisper language auto-detection (`hi`, `es`, `en`).
- [ ] Add Kokoro presets or additional TTS routing for ES/HI.
- [ ] Rebuild the manual language-override regex interceptor, covering trigger phrases in all three languages.

---

## 7. Future Updates (Not Scoped — Do Not Build Yet)

Ideas that came up during design review but are deliberately **out of Phase 1 and Phase 2 build scope**. Listed here so they aren't forgotten, not so they get built early.

### A. Screen Vision ("What's on my screen?")
Friday would take a screenshot on request and answer questions about it, not just react to voice/text.
* **Capture:** `grim` (the standard Wayland/wlroots screenshot tool — works natively under Hyprland, unlike X11-era tools).
* **Understanding:** a small vision-language model (VLM) — e.g. Moondream2 (~1.9B params) — takes the screenshot + question and returns a text answer, which is then handed back to Qwen to speak naturally, using the same execute-then-re-prompt pattern as the §4D search loop.
* **The blocker:** VRAM, not capability. LLM (4.8GB) + STT (1.5GB) already consume the realistic 6.5GB ceiling from §3D — there's no room to keep a third model resident. This needs either (a) a model-swap pattern (unload Qwen, load the VLM, run the query, reload Qwen — a few seconds of added latency per screen query) or (b) running the VLM on CPU instead of GPU. Both are viable; neither has been benchmarked yet on this hardware.
* **New action type required:** `look_at_screen`, added to the `ActionExecutor` whitelist once this is actually built.

### B. Voice Cloning
If a future hardware upgrade or a lighter LLM choice ever frees ~4GB of VRAM headroom, XTTSv2 or Chatterbox become viable for a fully custom-trained voice rather than a fixed Kokoro preset — see §3C for the tradeoffs already evaluated.
