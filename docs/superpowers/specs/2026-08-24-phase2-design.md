# Friday — Phase 2 Design

**Status:** authoritative for Phase 2 planning
**Date:** 2026-08-24
**Builds on:** Phase 1 (G0–G9 + post-G9 hardening) — see `progress.md`
**Governs gates:** G10, G11, G12, G13

Phase 1 delivered a reactive, push-to-talk voice+text assistant that
launches a fixed app set, remembers preferences, searches the web behind
a loopback proxy, converses, and runs as hardened user services. Phase 2
makes Friday **hands-free, proactive, and capable of more real actions**,
without relaxing a single Phase 1 invariant.

This document is the design agreed in the 2026-08-24 brainstorming
session. Decisions here are recorded in `adr.md` (ADR-054…ADR-059; the
G10 spikes add ADR-060/061/062), `open-questions.md` (OQ-21…24), a Phase 2
pointer in `spec.md` §1.1, and `diagrams/06-build-gates.md`. Per-gate
acceptance tests live in each gate's plan (this doc's §-sections are the
requirements; FR IDs are assigned into `spec.md` if/when a gate is
finalized). The G10 implementation plan is
`docs/superpowers/plans/2026-08-24-g10-wake-word.md`.

---

## 0. Gate map, build order, and the one dependency

```
   G10 WAKE WORD + AEC    hands-free activation, PTT kept as fallback
   G11 PROACTIVE          timers/reminders, habit suggestions, briefings
   G12 ACTION SURFACE     system/Hyprland/notes/clipboard/file-open/dictation
   G13 SPEAKER VERIFY     only-your-voice gate + two-pass dangerous confirm
```

Order: `G10 → G11 → G12 → G13`. All independent **except one hard
dependency**: G12's *dangerous* confirm tier requires G13's voiceprint
core. Dangerous actions are therefore defined in G12 but ship
**gated-off** (fail closed, "requires speaker verification") until G13
lands, at which point the same verify call activates them. No other
cross-gate coupling.

**Deferred within Phase 2 (you will cue me):** custom "Friday" wake word
(replaces `hey_jarvis` once FA/FR training is worth it — OQ-12 update).

**Still out of Phase 2:** multilingual hi/es (OQ-13), screen vision
(OQ-14, Phase 3).

---

## 1. Invariants — none relaxed

All ten Phase 1 invariants hold unchanged. The two that Phase 2 tempts:

- **#10 (no irreversible tools).** NOT lifted. Instead, Phase 2 adds a
  **three-tier confirm policy** (§4.2). Genuinely destructive classes
  (shell exec, package removal, file deletion) are **permanently
  banned** — a hard denylist in the tool layer, not prompt guidance.
  What remains are reversible or soft-reversible actions, and even the
  soft ones require confirmation.
- **#5 (one turn in flight).** NOT weakened by proactivity. Proactive
  events enter the **same single turn queue** as voice turns and run
  only when the arbiter is idle (§3.1). There is exactly one
  serialization point, as before.

New security posture added by Phase 2 (strengthens the model):
**two-pass gate on dangerous actions** — spoken confirmation AND a
silent speaker-voiceprint match on the confirmation utterance (§4.3).

---

## 2. G10 — Wake word + acoustic echo cancellation

### 2.1 Decisions
- **Model:** openWakeWord pretrained `hey_jarvis`. CPU only (invariant
  #6). Non-commercial licence — acceptable for single-user personal use
  (record the licence in the ADR). Custom "Friday" word deferred.
- **PTT stays.** Wake word is additive. The existing toggle-PTT path
  (ADR-044) is unchanged and remains the reliable fallback when a room
  is noisy or the detector false-rejects.
- **Always-on mic accepted**, with **AEC mandatory** (ADR-014) so
  Friday's own TTS never self-triggers the wake word.
- **Rolling audio buffer in RAM only** — never disk (invariant #7).

### 2.2 Architecture
```
  mic ─▶ [AEC filter]─▶ cleaned ─┬▶ [wake detector] ─▶ on_wake  ─▶ begin capture
          ▲                      └▶ [VAD] ─▶ on_speech_end ─▶ end capture (no key)
          │ far-end reference               on_barge (while speaking) ─▶ cut + capture
       TTS render
```
- The wake path is a **background `WakeListener`, orthogonal to the turn
  FSM** — NOT a new FSM state. It runs whenever the daemon is up, on its
  own always-on stream, and reads the existing FSM via `is_idle` /
  `is_speaking` predicates. (Refinement over an earlier `LISTENING_WAKE`
  idea: a separate state complicated the proven IDLE↔CAPTURING
  transitions for no gain.) The existing capture/STT/PTT pipeline is
  unchanged; a wake hit simply drives the same `begin_capture`, and PTT
  still short-circuits straight to capture.
- AEC runs as a preprocessing stage. Far-end reference = the TTS playback
  signal (a `FarEndRef` the `Speaker` writes played PCM into). Wake
  detector and VAD both consume the **cleaned** stream.
- **VAD is required** (not optional): a wake-initiated capture has **no
  key release** to end it, so a voice-activity detector supplies
  end-of-utterance (`on_speech_end`). VAD also detects the user speaking
  during TTS, which is what drives **barge-in** (`on_barge`). Library
  chosen by a measured spike (OQ-24).
- **Barge-in becomes achievable** (not free): the cleaned near-end makes a
  real utterance during playback detectable (the precondition); the cut-
  playback logic + live check are done here and verified in §2.4 (closes
  the open G6 item).

### 2.3 Spikes (dependency drill, ADR-039/041) — gate G10
Three, each measured on THIS machine before wiring, `--dry-run` footprint
first (none may drag CUDA/torch — invariant #6):
1. **AEC library** (OQ-21): `webrtc-audio-processing` vs `speexdsp` echo
   canceller. Measure residual echo (does `hey_jarvis` self-trigger during
   TTS?), added latency, CPU. → ADR-060.
2. **openWakeWord footprint** (confirms ADR-055's model): ensure it pulls
   onnxruntime CPU, not torch; record `hey_jarvis` SHA256, licence,
   per-frame latency. → ADR-061.
3. **VAD library** (OQ-24): `webrtcvad` vs `silero-vad` (ONNX). Measure
   end-of-speech responsiveness, noise false-trigger, CPU. → ADR-062.

### 2.4 Acceptance
- 30-min always-on session: TTS playback never self-triggers wake (0
  false accepts from own voice).
- Wake FA/FR measured across ≥3 rooms / noise conditions; numbers
  recorded (not "feels fine").
- Barge-in: speaking during a long reply cuts playback, live-verified.
- PTT path regression-clean.

---

## 3. G11 — Proactive Friday

### 3.1 Turn arbitration (the FR-5-critical design)
A **scheduler thread** owns time and enqueues work; it never touches the
mic or TTS directly.
```
  scheduler ─(proactive turn)─▶  single turn queue  ◀─(voice turn)─ wake/PTT
                                        │
                                   turn arbiter  (runs one at a time)
                                        │  only if idle AND not in DND
                                   execute → speak (ADR-009)
```
- One queue, one arbiter, one turn in flight — FR-5 holds by
  construction. A proactive turn that arrives mid-voice-turn waits.
- A proactive turn that would fire during DND or quiet is dropped or
  deferred per its kind (reminders defer to the edge of DND; suggestions
  are dropped).

### 3.2 Timers & reminders
- Persisted table in the existing SQLite store (survives restart,
  invariant #7 respected — store the reminder text as user data, not a
  transcript blob). Fields: id, fire_at, kind, payload, state.
- Voice-set: "remind me in 10 minutes to …", "set a timer for pasta".
  This introduces the reminder *action type* reused conceptually in G12.
- On fire: enqueue a proactive turn → speak + `notify-send`.

### 3.3 Briefings
- **Startup briefing** (daemon comes up): pending reminders + one line
  from long-term memory (`store/summarizer.py`). Optional weather via the
  existing SearXNG proxy (still Zone-3 grounded — invariant #1).
- **Close summary** triggered by the **voice sign-off phrase**
  ("goodnight" / "bye"): speak the session summary while audio still
  works. Actual system shutdown stays silent (audio teardown is
  unreliable — do not attempt to speak into it).

### 3.4 Conversational DND (not a clock)
Default state is **quiet**. There is no nightly schedule.
- Startup briefing is allowed.
- Proactive **suggestions** surface primarily while a conversation is
  active (you are already talking to Friday).
- Hush phrases — "let's talk later", "do not disturb", "talk later",
  "be quiet" — set DND. Friday goes silent (notifications still queue)
  until you **ask a question or explicitly say resume**.
- Due **reminders** still fire (they are time-critical); DND only
  silences suggestions/briefings, not an alarm you set yourself. (Open
  nuance — confirm during G11 build.)

### 3.5 Delivery
Both channels: **speak when idle** AND a **`notify-send` desktop
notification** (Hyprland). Silent-but-visible fallback when speech is
suppressed.

### 3.6 Acceptance
- Reminder set by voice fires after restart of the daemon.
- Proactive turn never interrupts a live voice turn (FR-5 asserted in
  test).
- Hush phrase silences suggestions; a question re-enables them.
- Startup briefing and "goodnight" close-summary both fire and speak.

---

## 4. G12 — Action surface

### 4.1 New tools (each: closed enum → code builds argv; invariants #2, #3)
| Family | Actions (enum, illustrative) | Reversible? |
| :-- | :-- | :-- |
| System control | vol up/down/mute/set-N, brightness up/down/set, wifi on/off, media play-pause/next/prev | yes (wifi-off = consequential) |
| Hyprland | workspace switch(N), focus/move window(dir), fullscreen toggle | switch/focus yes; close = consequential |
| Notes | capture note(text→SQLite as data), read notes | yes (data only, never executed) |
| Clipboard | read, set(text) | set = consequential (overwrite) |
| File-open | open(alias) from closed alias→path registry | yes (launch only) |
| Dictation | start/stop; verbatim type into focused window | n/a (see §4.4) |

No tool ever receives a model-supplied path, URL, or shell string. The
file-open registry mirrors the app registry: the model emits an opaque
alias ID; code resolves it to a vetted path.

### 4.2 Confirm tiers
Every action carries a static tier in its tool definition:
- **harmless** — volume, brightness, media, workspace switch, focus
  window, read note/clipboard, file-open. Execute immediately, no
  confirm.
- **consequential** — close window, wifi off, clipboard overwrite, any
  dictation submit/Enter. Require a **spoken "yes"** (confirm turn).
- **dangerous** — **two-pass** (§4.3). Important: the genuinely
  destructive classes (shell, package, file-delete) are **banned
  outright** (§4.5), not placed in this tier — so the initial G12 toolset
  may have **no dangerous-tier members at all**. The tier and its
  two-pass machinery are still built now (gated on G13) so any action
  later judged dangerous is covered and cannot bypass it. Whether any
  specific initial action (e.g. wifi-off mid-transfer) is promoted from
  *consequential* to *dangerous* is decided per-tool during the G12
  build, not assumed here.

Any confirm that is not a clear affirmative fails closed to
`action=none` (invariant #5 discipline).

### 4.3 Two-pass dangerous gate (activates with G13)
For a dangerous action:
1. Friday speaks the confirm prompt; user says "yes".
2. **Silently**, the confirmation utterance's voiceprint is matched
   against the enrolled owner (G13 core). Match → execute. No match →
   refuse and log (never reveal the threshold).
Both passes required. Even an attacker who somehow reached a confirm
prompt cannot pass the voiceprint. Until G13 lands, dangerous actions are
**disabled** (fail closed), not merely unconfirmed.

### 4.4 Dictation
- **Explicit toggle:** "start dictation" → `DICTATION` mode; "stop
  dictation" → back to command mode. Unambiguous boundary so spoken words
  are typed, not parsed as commands.
- **Wake word paused** while dictating (so "hey jarvis" mid-sentence is
  typed, not fired). PTT can still force-stop.
- **Verbatim, never auto-Enter.** Friday types the transcript into the
  focused window and never presses Enter/submit on its own. Enter/submit
  is a **consequential** action requiring spoken confirm (§4.2).
- Punctuation/format by spoken command ("new line", "period").
- STT sink is switched, not the model: dictation text never enters the
  planner (it is Zone-1 user input typed as-is; it is not interpreted).

### 4.5 Hard ban (permanent non-goal)
No tool may expose: arbitrary shell/terminal execution, package
install/removal, file deletion, or any `rm`-like destructive class.
Enforced as a **denylist in the tool layer** (a tool whose resolved argv
matches a banned program/verb is rejected before spawn), not as prompt
text. Adding any such capability later requires its own ADR and does not
generalize from this one.

### 4.6 Spike (gates dictation) — Wayland typer
`wtype` vs `ydotool` (+uinput daemon/permissions) on this Hyprland
machine. Measure: does it type into the actually-focused window
reliably, latency, setup cost (ydotool needs a uinput-access daemon).
Record choice + rejected option in the ADR.

### 4.7 Acceptance
- Each tool family: enum-driven, argv built by code, adversarial fixture
  proves no free string reaches subprocess.
- Confirm-tier test: consequential action without "yes" → not executed.
- Dictation: a spoken sentence containing "open firefox" is TYPED, not
  executed (mode isolation test).
- Banned program in resolved argv → rejected before spawn (test).
- Injection suite extended: note/clipboard/dictation as new sinks, still
  0 dispatches from untrusted content.

---

## 5. G13 — Speaker verification

### 5.1 Decisions
- **Own gate** (after G12), with its own FA/FR eval.
- **Enroll once:** capture owner samples → store a voiceprint embedding
  (the embedding, not raw audio — invariant #7).
- **Gate wake activation:** after a `hey_jarvis` hit, compute the
  utterance embedding, cosine-match to the enrolled print; below
  threshold → ignore (TV, other people). PTT bypasses (physical presence
  = owner assumption).
- **Reused by G12:** the same verify call backs the dangerous-tier
  second pass (§4.3).

### 5.2 Spike (gates G13) — embedding model
SpeechBrain ECAPA-TDNN vs Resemblyzer vs alternatives, CPU only
(invariant #6). `--dry-run` footprint (no torch/CUDA drag). Measure:
embedding latency, RAM, and separation on real samples (owner vs
others). Pin the weights (SHA256). Record in ADR.

### 5.3 Acceptance
- FA/FR measured: owner accepted ≥ target, non-owner + TV-playback
  rejected. Numbers recorded.
- Threshold never spoken or logged.
- PTT bypass verified.
- Dangerous action confirmed by owner passes; same phrase from another
  speaker refused.

---

## 6. Testing & eval surface (new)

- **Wake FA/FR fixtures** (G10) and **speaker FA/FR fixtures** (G13) —
  measured, recorded, not felt.
- **Confirm-tier tests** (G12): each tier behaves; failures fail closed.
- **Dictation isolation test**: dictated command-like text is typed,
  never dispatched.
- **Ban test**: banned argv rejected pre-spawn.
- **Injection suite extended** to notes/clipboard/dictation sinks — must
  stay 0-dispatch (invariant #1).
- `just eval` must not regress at any gate (existing rule).

---

## 7. Open items folded in from Phase 1 live-review

- **Barge-in** — closed by G10 AEC, live-verified there.
- **TTFA long-reply spike** — revisit if G11 briefings feel slow; cap
  tokens as already noted. Not a gate blocker.
- **Reboot auto-start proof** — verify opportunistically during G10
  (the wake daemon must come up at login anyway).
- **"can you search the web?" meta-answer** — minor prompt nuance; fold
  into G12 chat-persona pass if convenient.

---

## 8. Spikes summary (each gates its gate; ADR before wiring)

| Spike | Gate | Question |
| :-- | :-- | :-- |
| AEC library (OQ-21) | G10 | webrtc-audio-processing vs speexdsp: residual echo, latency, CPU, footprint → ADR-060 |
| VAD library (OQ-24) | G10 | webrtcvad vs silero-vad: end-of-speech responsiveness, noise false-trigger, CPU → ADR-062 |
| openWakeWord footprint | G10 | onnxruntime-CPU not torch; hey_jarvis SHA256/licence/latency → ADR-061 |
| Wayland typer (OQ-22) | G12 | wtype vs ydotool: focus reliability, latency, setup cost |
| Speaker embedding (OQ-23) | G13 | ECAPA vs Resemblyzer: latency, RAM, separation, footprint |

None may drag torch/CUDA (invariant #6). All measured on this laptop,
pinned, recorded — no datasheet trust.
