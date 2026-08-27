# Friday — Open Questions

Every entry: what is unknown, who decides, what it blocks, and what
happens if nobody decides. An open question with no blocking gate is not
open — it is a note, and it belongs elsewhere.

**Status values:** `OPEN` / `ANSWERED` / `DEFERRED`
**Decider:** `USER` (needs your judgement) or `MEASURE` (a benchmark
answers it, no opinion required).

---

## Blocking Phase 1

_None — all Phase 1 questions are resolved and all gates G0 through G9 have passed._

---

## Kept Open (Long-Term / Optional)

### OQ-28 — Should a meta-question about capability route to chat, not web_search?
**Decider:** USER · **Blocks:** nothing · **Status:** OPEN (live-review 2026-08-23)

"can you search the web?" routes to a literal `web_search` (it searches for that
phrase) rather than a `chat` answer about its abilities. Harmless — it *can*
search — but slightly awkward. A planner-prompt nuance (distinguish "can you X"
meta-questions from "do X" commands). Low priority; note it if it recurs.

### OQ-05 — Does the disk count as the security boundary?
**Decider:** USER · **Blocks:** nothing today · **Status:** OPEN (answered
provisionally 2026-08-22 — deliberately kept open at the user's request)

**Current answer:** nothing leaves this machine, so `0600` on
`~/.local/state/friday/memory.db` is sufficient and no at-rest encryption
is built. See ADR-031.

**Kept open because this may change later, possibly much later.** Any one
of these reopens it:

```
   - cloud sync, offsite backup, or snapshot replication is enabled
   - the machine is shared, lent, or sold
   - transcripts are ever persisted (currently forbidden — ADR-028)
   - a second user account is added
```

If that happens the work is: exclude `~/.local/state/friday/` from the
sync, or encrypt `memory.db` at rest plus a key-management decision that
does not exist yet.

---

### OQ-11 — Does the desktop actually consume dGPU VRAM?
**Decider:** MEASURE · **Blocks:** nothing in Phase 1 · **Status:** OPEN

```bash
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
```

with Hyprland running and a browser open playing video. On hybrid
graphics, both should be on the Intel iGPU. If the output is empty,
roughly 1.9 GB of the projected VRAM peak does not exist and the working
ceiling can rise.

---

### OQ-09 — Is ~1.4 s TTFA actually a problem?
**Decider:** MEASURE then USER · **Blocks:** any streaming work · **Status:**
ANSWERED 2026-08-23 — TTFA measured at G6 spoken eval: p50 2156 ms, p95 2731 ms
(well within the 4.4 s hard fail cap). Streaming is not needed for Phase 1.

---

## Answered by measurement (no opinion needed)

### OQ-07 — Does whisper meet latency on CPU?
**Decider:** MEASURE · **Blocks:** G1 (deferred), now G6 · **Status:**
ANSWERED 2026-08-23 — YES, with the right model. `large-v3-turbo` (FR-10's
old pin) FAILED at p95 2.7 s, but `small.en` int8 beam=1 hotwords hits p95
**741 ms** (< 800 ms) on this CPU. CPU STT is viable; no GPU; ADR-018 stays
closed. Full 3-round table in ADR-042 + progress.md G6. int8 beat fp32 here
(no AVX-512 penalty for CTranslate2, unlike Kokoro).

CPU is the default (ADR-004): it removes an entire CUDA context and keeps
the Python environment CUDA-free, which is what makes FR-71 checkable.

Measure CPU only. 20 clips, 2-8 s, from the actual laptop mic. Pass if
p95 <= 800 ms. Only on failure does the CUDA arm get installed and
measured — that is stop condition #5, and it reopens ADR-018.

**Scope widened 2026-08-23 (ADR-041 standing rule).** Instead of accepting
the FR-10 pin (`faster-whisper large-v3-turbo`) unexamined, G6 benchmarks
it against at least one rival CPU backend (`whisper.cpp`, which keeps STT
out of the Python venv entirely and off onnxruntime). Winner chosen on
measured p50/p95 + footprint + robustness, recorded in an ADR; FR-10's pin
is provisional until then. Kokoro (ADR-039) is the worked precedent.

Record the table in `progress.md` G1/G6.

---

### OQ-08 — Does `thought` actually improve tool selection?
**Decider:** MEASURE · **Blocks:** nothing, informs ADR-011 · **Status:**
ANSWERED 2026-08-23 — delta 0

Ran the seed set twice, with and without `thought`, temperature 0:
**18/20 both ways, delta 0 fixtures.** Under the pre-committed threshold of
2, so the field earns nothing. Recommendation recorded in ADR-011: remove
`thought` from schema/grammar/prompt at the start of G3 (removal deferred
out of the G2 commit for a clean re-baseline; flagged for confirmation).
Re-measurable if the grown suite ever disagrees.

---

### OQ-09 — Is ~1.4 s TTFA actually a problem?
**Decider:** MEASURE then USER · **Blocks:** any streaming work · **Status:** OPEN

Measure p50/p95 TTFA at G6 with the blocking pipeline. Then use it for a
day. If it feels bad, build streaming (ADR-020). If it does not, that is
a week saved.

Cheap mitigations allowed regardless: an earcon or a "let me check"
filler on `web_search`, which does not touch the pipeline.

---

### OQ-10 — Is the Intel NPU actually usable?
**Decider:** MEASURE · **Blocks:** nothing in Phase 1 · **Status:** ANSWERED 2026-08-22 — device PRESENT

```bash
ls /dev/accel/ 2>/dev/null; lsmod | grep -i vpu
```

Result: `/dev/accel/accel0` exists and `intel_vpu` (389120) is loaded. The
blueprint's "NPU dead on Linux" claim is **false** on this kernel. Not
built on in Phase 1 (ADR-019 stands); filed as a Phase 2 option for
offloading whisper to free P-cores. Whether it is *usable* for STT (an
OpenVINO NPU path) is unmeasured — presence is confirmed, throughput is
not. See ADR-019.

---

### OQ-11 — Does the desktop actually consume dGPU VRAM?
**Decider:** MEASURE · **Blocks:** G1 sizing · **Status:** OPEN

```bash
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
```

with Hyprland running and a browser open playing video. On hybrid
graphics, both should be on the Intel iGPU. If the output is empty,
roughly 1.9 GB of the projected VRAM peak does not exist and the working
ceiling can rise.

---

## Phase 2 — active and deferred

Phase 2 = G10 wake word, G11 proactive, G12 action surface, G13 speaker
verification (ADR-054; design `docs/superpowers/specs/2026-08-24-phase2-design.md`).

### OQ-12 — Wake word: which one, and at what FA/FR?
**Status:** PARTIALLY ANSWERED 2026-08-24 (ADR-055).

`hey_jarvis` (openWakeWord pretrained, non-commercial licence, CPU)
adopted for G10, additive to PTT, with mandatory AEC (ADR-014) and a
RAM-only buffer. **Still open:** the custom "Friday" word — deferred
*within* Phase 2; the user will cue when it is worth the sample
synthesis + augmentation + per-room FA/FR training. FA/FR targets for
both `hey_jarvis` (G10) and the eventual custom word are measured, not
felt.

### OQ-22 — Wayland typing backend for dictation (gates G12 dictation)
**Status:** OPEN — spike. `wtype` vs `ydotool` (+uinput daemon) on this
Hyprland machine: focus reliability, latency, setup/permission cost.
Record in ADR-058's follow-up.

### OQ-23 — Speaker-embedding model (gates G13)
**Status:** OPEN — spike. SpeechBrain ECAPA-TDNN vs Resemblyzer vs
alternatives, CPU only: embedding latency, RAM, owner/non-owner
separation on real samples, footprint. Pin weights (SHA256). Record in
the G13 ADR (extends ADR-059).

### OQ-32 — Which echo canceller actually works on this laptop? (BLOCKS hands-free barge-in)
**Status:** OPEN — a full ADR-039/041 dependency drill. Raised 2026-08-25.

`pywebrtc_audio`'s EchoCanceller delivers **−52 dB** on a clean synthetic echo
and only **−5 to −10 dB** on this machine's real speaker→mic path, with the
reference correct and callback-synced (measured lag 58 ms, envelope correlation
0.53; `stream_delay_ms` at 0/30/60/90/120 ms changes nothing). The barge VAD
therefore called 238 of 349 playback frames speech, and Friday cut herself off
on every reply. Voice barge-in is off by default as a result (ADR-064).

Run the drill from CLAUDE.md rule 7: enumerate the real options (speexdsp,
WebRTC APM builds with the full AGC/NS chain rather than the bare
EchoCanceller, adaptive-filter implementations), check the footprint with
`uv pip install --dry-run` BEFORE installing (anything dragging in torch/CUDA
is disqualified by invariant #6), benchmark the survivors **on this laptop**
with the probe already written for it, and record the numbers plus the rejected
alternatives in an ADR before wiring anything in.

**What blocks it:** nothing but the work. The measurement harness exists.
**What it unblocks:** hands-free interruption. Until then PTT is the interrupt.

### OQ-33 — What should `WAKE_THRESHOLD` actually be? (needs logged score data)
**Status:** OPEN — needs one live session's logs. Raised 2026-08-25.

`WAKE_THRESHOLD` is 0.5 and has never been chosen from data. A 90 s bench in a
quiet room scored **0 false fires** (peak input 0.1250, max score 0.002), but a
live 3-minute session with the user present produced **three captures with no
speech in them at all** — false wakes. Ambient silence is clearly not the
trigger; something in the room (movement, keyboard, speech that is not the wake
word) crosses 0.5.

ADR-066 caps the *cost* of a false wake at ~3 s but does not reduce the rate.

**What blocks the answer:** score data at fire time, which did not exist until
ADR-066 added `wake fired score=… threshold=…`. Run one normal live session,
then:
```bash
journalctl --user -u friday | grep 'wake fired'
```
Compare the scores of genuine wakes against the false ones. If false fires
cluster just above 0.5 and real ones sit near 0.9, raise the threshold. If they
overlap, the threshold is the wrong lever and the answer is a second-stage
check (speaker verification, G13, already built but off by default).

### OQ-30 — Should "play a video" open mpv or search YouTube?
**Status:** OPEN — one-line prompt change either way. Raised 2026-08-25.

`"play a video"` routes to `youtube_search {'query': 'play a video'}`, not
`open_app {'app': 'video'}` (mpv). Both readings are defensible: the prompt
tells the planner that playback requests are `youtube_search`, and mpv with no
file argument opens an empty player. `"open mpv"` unambiguously reaches mpv.
Reproduced on a healthy GPU, so it is a genuine routing choice, not a
CPU-degraded artefact. Needs the user's intent, then a prompt tweak and an eval
fixture.

### OQ-31 — Wake-word feedback: is a busy toast the right channel?
**Status:** PROVISIONALLY ANSWERED 2026-08-25 — revisit after live use.

A trigger rejected under FR-5 (one turn in flight) now raises a low-urgency
desktop toast, because a silent rejection desyncs tap-toggle PTT and made the
user record an empty room. Toast was chosen over an earcon: no new asset, no
collision with TTS or the mic, and `notify-send` was already a G11 dependency.
**Open:** whether a toast per rejection becomes noise in real use, or whether a
short earcon reads better hands-free. Decide after the live-voice pass.

---

### OQ-13 — Multilingual re-enablement plan
**Status:** DEFERRED

Re-enabling Hindi/Spanish is not a config flag. It changes STT
(auto-detect reintroduces hallucination risk on noisy input), TTS
(voice routing), the prompt, and — critically — the **eval and injection
suites**, which are English-only today. Budget a full fixture set per
language. Phase 2 must not bypass Phase 1's policy layer.

---

### OQ-14 — Screen vision placement
**Status:** DEFERRED (Phase 3)

Moondream2 at int8 is ~1.2 GB of system RAM and roughly 600-900 ms on 24
cores, so CPU placement likely avoids the VRAM problem entirely — no
model swapping needed. Unbenchmarked.

Security note that must not be lost: **a screenshot is attacker-
controllable content.** Text rendered in any window becomes a new
injection sink, and it would arrive with far more authority than a search
snippet. If this is ever built, `look_at_screen` output is Zone 3 and its
grounding turn is grammar-locked exactly like search (ADR-008).

---

## Closed

_(Move entries here with the answer and the date. Do not delete them —
the reasoning behind a closed question is the thing you will want in six
months.)_

- **OQ-34 — Should `clipboard_read` ever speak clipboard contents aloud?**
  ANSWERED 2026-08-27: **no, not without an explicit confirm each time**
  (option d, ADR-068a). `clipboard_read` now returns a `PendingAction` and
  speaks the contents only after an affirmative answer — the same handshake
  that already guards `clipboard_set`. The user rejected the silent-safe
  fallback (c) because it removes the feature from voice mode, which is the
  mode Friday is used in, and rejected the secret-detection heuristic (b)
  because it fails both ways: a space-separated passphrase reads as prose and
  gets spoken, an ordinary long URL gets refused. A confirm asks honestly
  instead of guessing. This makes `clipboard_read` the first read-only tool
  behind a confirm — the gate is for disclosure, not reversibility.

- **OQ-35 — Retention policy for `notes` (and terminal-state reminders)?**
  ANSWERED 2026-08-27: **notes kept indefinitely, fired/cancelled reminders
  pruned at 90 days** (ADR-068b), matching FR-59's existing audit window rather
  than adding a second constant. Active reminders are never pruned regardless
  of age. Notes are user-authored content the user expects to still be there;
  terminal-state reminders are machine exhaust. Closes M-T9.

- **OQ-29 — What re-triggers the 15-second empty-capture loop?** ANSWERED
  2026-08-25. Not ambient noise and not a wake false fire: a 90 s
  `just wake-bench` scored **0 wake hits** (peak input 0.1250, max score 0.002 —
  the bench now prints both, because "0 hits" could not previously be told
  apart from a dead microphone). The cause is **detector starvation**.
  `WakeListener._on_frame` scored the detector only inside `if self.is_idle()`,
  so openWakeWord — a streaming model with rolling melspectrogram and embedding
  buffers — received nothing for the whole 15 s capture. One frame is 320
  samples and a prediction chunk is 1280, so the first frame after the capture
  could not run a new prediction and returned *the score that started the
  capture*: above threshold, refractory long expired, wake re-fires. One real
  "hey jarvis" seeds an endless loop; a daemon restart clears it, which is why
  it read as intermittent.

  **The first fix attempt was wrong and a live run disproved it.** Flushing the
  detector on resume looked right but was cosmetic: openWakeWord's
  `Model.reset()` only reassigns `prediction_buffer` (a deque of past scores)
  and leaves `preprocessor.melspectrogram_buffer` / `feature_buffer` intact, so
  the stale *features* survived and re-fired anyway. The correct fix is to stop
  starving it: score **every** frame and ignore the result unless idle
  (`friday/audio/wake.py`). Regression test
  `test_stale_score_cannot_refire_wake_after_capture`, proven to fail without
  it. The original wake tests could never have caught this — their
  `FakeDetector` returns a constant score, so the streaming contract it violates
  is invisible; the test now uses a `StreamingFakeDetector`.
  `WAKE_THRESHOLD` stays 0.5; no early-bail was added.

- **OQ-00 — Should context stay at 2048?** ANSWERED 2026-08-22. No.
  8192 with q8_0 KV costs 224 MiB. See ADR-003.
- **OQ-01 — Which apps in the registry?** ANSWERED 2026-08-22. Trimmed
  same day to five entries — browser=brave, terminal=foot, editor=code,
  media=mpv+vlc; no file manager, no Spotify; YouTube covers music and
  video. See ADR-032 (supersedes ADR-026), ADR-027.
- **OQ-02 — Does `run_script` ship in Phase 1?** ANSWERED 2026-08-22. No.
  The `ToolSpec` type supports it; no entry is registered. Add it the day
  a real script exists, with its own test.
- **OQ-04 — May Friday store raw transcripts?** ANSWERED 2026-08-22.
  In-memory ring buffer, last 20 turns, off by default, cleared on exit,
  never written to disk. See ADR-028.
- **OQ-15 — Where do runtime files live?** ANSWERED 2026-08-22. XDG dirs.
  See ADR-023.
- **OQ-16 — Task runner?** ANSWERED 2026-08-22. `just`. See ADR-025.
- **OQ-17 — Hardware identifiers in git?** ANSWERED 2026-08-22. Never;
  `laptop-specifications.md` is gitignored. See ADR-024.
- **OQ-18 — Preference key vocabulary?** ANSWERED 2026-08-23. Option (d):
  model supplies a free key, code slugifies it, a curated alias map folds
  common synonyms onto canonical keys, and every write is confirmed. Free
  enough to learn, deduped enough not to crash. See ADR-035.
- **OQ-19 — forget/reset: hard vs soft?** ANSWERED 2026-08-23. Split:
  `forget_preference` (voice-reachable) soft-expires; the `prefs` CLI
  hard-deletes only with `--hard` / `reset --yes`. See ADR-036.
- **OQ-20 — Confirm a spoken preference first?** ANSWERED 2026-08-23. Yes.
  A deterministic UI handshake (not a second model turn) writes only on an
  explicit yes; `source='user_confirmed'`. See ADR-037.
- **OQ-21 — Do preferences auto-expire by age?** ANSWERED 2026-08-23. No.
  Retention purges audit rows + session summaries only; preferences live
  until forgotten. `pinned` kept but inert. See ADR-038.
- **OQ-22 — Which Kokoro voice preset?** ANSWERED 2026-08-23. `af_bella`
  primary, `af_heart` fallback (heart/sky indistinct on audition). See
  ADR-005, ADR-040.
- **OQ-03 — PTT key + bind path?** REOPENED + RE-RESOLVED 2026-08-23 (ADR-044).
  The bind path (ADR-013, no evdev) stands; the KEY and press/release model
  changed after live testing. The Copilot key (`XF86Assistant`) was dropped —
  its firmware leaks Super into every press, mis-triggering the launcher (the
  reported "glitch") and never dispatching the chord reliably. The 3 s-hold
  "confirmation" recorded earlier was contaminated (the user was holding
  SUPER+SHIFT during the `wev` check). SHIPPED: **one bind on plain
  `XF86Presentation` → `friday-ptt toggle`** (tap on / tap off, 0.4 s
  debounce). The key is clean (modmask 0) but tap-only, so it drives toggle,
  not hold. Live-proven: tap→"open vlc"→tap launched VLC, capture 3.4 s.
  `press`/`release` remain for a future holdable key. See ADR-044.
- **OQ-07 — whisper CPU latency?** ANSWERED 2026-08-23. Yes with `small.en`
  (p95 741 ms); `large-v3-turbo` failed (2.7 s). CPU STT viable, no GPU.
  See ADR-042.
- **OQ-23 — mic device for capture?** ANSWERED 2026-08-23. Default
  PipeWire source (currently analog `Mic1`), config-overridable; not the
  `DMIC Raw` array (index can move). Recorded here to close the
  docs/"DMIC array" mismatch. (OQ-06 was the *voice* preset, closed by
  OQ-22 — do not confuse.)
- **OQ-25 — Habit pattern categories and threshold?** ANSWERED 2026-08-23.
  Mined deterministically from `action_audit` table; sequential transitions
  ($A \rightarrow B \le 30\text{ min}$) + granular time-of-day slots (sunrise/early
  morning 05-08, morning 08-12, afternoon 12-17, sunset/early evening 17-20, evening
  20-23, late night 23-05); threshold $\ge 2$. Rendered as `<user_habits>` DATA.
  See ADR-049.
- **OQ-26 — Distilled long-term memory trigger and context limit?** ANSWERED 2026-08-23.
  Distilled at session shutdown when $\ge 2$ in-RAM dialogue turns exist; 1-2 concise
  sentences saved in SQLite `session_summaries`; the 2 most recent summaries are
  injected as `<past_sessions>` DATA in future chat turns. See ADR-050.
- **OQ-27 — App launch vs focus behavior:** ANSWERED 2026-08-24. If the active
  window is that app, focus it; if not on that app/workspace, open a new window
  even if another instance exists, and announce via speech.
- **DND Timers/Reminders Policy (G11):** ANSWERED 2026-08-24. Explicitly scheduled
  timers and reminders fire anyway (speak + notify-send) during Conversational DND
  because they are time-critical and set by the user.
- **File-Open Registry Placeholders (G12):** ANSWERED 2026-08-24. Keep dictionary/list
  structure as placeholders in code; user will provide explicit alias-to-path mappings later.
- **Voiceprint Enrollment Samples (G13):** ANSWERED 2026-08-24. Collect 10 sample
  utterances during voice enrollment to capture vocal variation.
- **OQ-21 — AEC library choice (G10):** ANSWERED 2026-08-24. `pywebrtc-audio` (WebRTC APM
  EchoCanceller) adopted on CPU (73.3 µs/frame, RTF 0.0073). See ADR-060.
- **OQ-22 — Wayland typing backend (G12):** ANSWERED 2026-08-24. `ydotool` / `wtype` fail-soft
  in `friday/tools/typer.py` with standard punctuation formatting. See ADR-058.
- **OQ-23 — Speaker embedding model choice (G13):** ANSWERED 2026-08-24. `sherpa-onnx`
  3D-Speaker/CAM++ ONNX model (`3dspeaker_campplus.onnx`, 512-dim, 31.9 ms/2s audio on CPU, 0 torch/CUDA). See ADR-063.
- **OQ-24 — VAD library choice (G10):** ANSWERED 2026-08-24. `webrtcvad` mode 2 paired with
  pure `SpeechGate` debouncer (4.0 µs/frame, RTF 0.00020). See ADR-062.




