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

## Blocking the post-live-pass fix list (raised 2026-08-29 by the LIVE-VOICE PASS)

_All seven are knowable now. Working agreement §2: ask them in ONE batch before
a line of the fix list is written. Evidence for every one of them is in
`progress.md`, "SESSION 2026-08-29 (night, later)"._

### OQ-39 — What is `webrtcvad` actually reporting on this microphone?
**Decider:** MEASURE · **Blocks:** D3 (hands-free is unusable) · **Status:** OPEN

All three wake captures ran the full 15 s cap. One contained zero speech by
Silero's reckoning yet ADR-066's 3 s bail-out never fired, which can only
happen if `_heard_speech` went true — i.e. `webrtcvad` called the room voiced.
The same code ended captures at 2.0/3.4/1.7/1.9 s on 2026-08-25.

**What answers it:** a probe that prints the voiced-fraction of live mic frames
at `VAD_AGGRESSIVENESS` 0-3, through the same AEC path as
`friday/audio/wake.py:_on_frame`, in this room. Nothing is decided until that
number exists — the 2026-08-25 barge-in cutoff was blamed on two wrong causes
before measurement found the real one.

**If nobody decides:** hands-free stays unusable and PTT is the only trigger.

### OQ-40 — What counts as a spoken "yes", and what should a non-answer do?
**Decider:** USER · **Blocks:** D1 (CRITICAL) · **Status:** **ANSWERED 2026-08-29 → ADR-075**

**Answer:** normalise punctuation **and widen** the phrase set ("go ahead", "do
it", "please do", "confirm"); a non-answer cancels the pending **and is then run
as a fresh command**. The user was shown that both halves loosen the same gate
and chose them anyway — that risk is recorded in ADR-075, not overlooked.

Two questions. The first is narrow: `is_affirmation` (`friday/turn.py:47-53`)
matches bare tokens, so Whisper's `"Yes."` is not an affirmation and every
spoken confirm has declined. Stripping trailing punctuation is the obvious
minimum — but is the accepted set also too narrow for speech ("go ahead",
"yeah do it", "please do", "confirm")? Widening it trades a missed yes for a
wrongly-accepted one on a destructive action.

The second is the interesting half: **today ANY non-affirmation cancels**
(ADR-069's fail-safe). During the live pass the user issued `Open a terminal`
while a preference confirm was live; it was swallowed as a decline and the
terminal never opened. Should a clearly-new command RUN instead of cancelling
— and if so, how is "clearly a new command" decided without a second model turn
(which ADR-037 rules out)?

**If nobody decides:** default to the narrow fix — normalise punctuation only,
keep the fail-safe cancel — and leave the second half open. That is the smaller
change and it does not weaken invariant #10.

### OQ-41 — What should `request_id` be, and should the audit write be `INSERT OR REPLACE`?
**Decider:** USER (architectural) · **Blocks:** D2 · **Status:** **ANSWERED 2026-08-29 → ADR-076**

**Answer:** UUID plus a plain `INSERT`. The readable `v{n}` stays in the debug
log for correlation; it stops being the database key.

`friday/store/audit.py:56` writes `INSERT OR REPLACE INTO action_audit` keyed
on `request_id`, and `friday/daemon.py:136,288` generate that id as `v{seq}`
with `seq` resetting to 0 on every daemon start. So every restart silently
overwrites the previous run's low-numbered rows. Proven live: run 2's `v3`
replaced run 1's `v3` web_search row.

Options: a per-run prefix (`{boot_id}-v{n}`), a UUID, a monotonic rowid, or
keeping the id and making the write a plain `INSERT` that fails loudly on
collision. The choice decides whether the audit log is trustworthy across
restarts, which is why it is an ADR and not a patch.

**If nobody decides:** the audit table keeps eating itself, and it is the
primary evidence channel for verifying every other fix.

### OQ-42 — Should Friday have a local-time action?
**Decider:** USER · **Blocks:** D7 · **Status:** **ANSWERED 2026-08-29 → ADR-078**

**Answer:** yes, add `get_time`. Code reads the clock, a template speaks it, the
model never supplies the string.

"What time is it?" routes to `web_search` and answers from a scraped page —
live evidence: *"05:00:05 P.M. UTC-7 as of 08/28/2026"* when the real local
time was 20:29. No invariant broke (a search turn cannot act), but Friday
states a wrong fact confidently with the machine's own clock available.

A `get_time` action would be a new entry in the closed enum plus an outcome
template; per invariant #2 and ADR-009 the model must never supply the time
string — code reads the clock, the template speaks it.

**If nobody decides:** it keeps answering wrongly from the web.

### OQ-43 — What happens when no duration is stated?
**Decider:** USER · **Blocks:** D5 · **Status:** **ANSWERED 2026-08-29 → ADR-077**

**Answer:** ask again and set nothing. This needs a new **clarify turn**
mechanism — the only question Friday can pose today is a yes/no confirm.

`set_reminder`'s `seconds` is `{"kind": "text"}` (`friday/llm/schema.py:72`) —
free text the model fills in. Live: `'suited timer for uhh... umm...'` became a
60-second timer and `'remind me to call my mom later'` became a 3600-second
one, both dispatched, both spoken as if the user had said so. The manifest
promises it asks; **no ask path exists anywhere in the codebase.**

This is the 2026-08-25 brightness defect's shape (a free-text param a builder
guesses at) in the one place a closed enum cannot help, because a duration is a
number and not a vocabulary. What is the rule — a bounded numeric with a
"was a duration actually spoken?" test, a clarify turn, or something else?

**If nobody decides:** garbled speech keeps becoming real timers.

### OQ-44 — Should spoken model output have a sanity floor?
**Decider:** USER · **Blocks:** D6 · **Status:** **ANSWERED 2026-08-29 → ADR-079**

**Answer:** floor plus the existing fixed fallback. LLM summaries are kept —
they are good; the failure was a degenerate output, not the feature.

Friday spoke the literal string `String.Empty` (her own stored session summary
records it). It came from the model via
`friday/proactive/briefing.py:57-62`, which speaks `distill_dialogue`'s raw
output. Startup briefings and sign-off summaries are the two places raw model
text reaches the speaker by design (they are not direct-action templates, so
ADR-009 does not cover them). Should there be a floor — reject output that is
empty, a bare identifier, or non-prose — and fall back to the fixed line?

**If nobody decides:** Friday occasionally says something that is obviously a
programming artefact.

### OQ-45 — Is the 1400 ms TTFA target still the target?
**Decider:** USER · **Blocks:** nothing today · **Status:** **ANSWERED
2026-08-29 → ADR-080**

**Answer:** re-baseline to the measurement — p50 2200 ms, p95 hard fail
3600 ms — and exclude `web_search` turns from the hard fail.

Measured live with `llm_on_gpu` PASS, n=77:

```
min=1689  p50=2172  p90=3613  p95=4900  max=8674  mean=2483  (ms)
over the 4400 ms hard fail: 4    at or under the 1400 ms target: 0
```

**Zero of 77 turns met the p50 target and the observed floor is 1689 ms.**
Three of the four hard-fail breaches are `web_search` (network + grounding,
arguably exempt); the fourth is not. Either the target moves to something the
system can actually hit, or optimisation gets scheduled. Note the clock
includes STT, since `_capture_end` starts it.

**If nobody decides:** the manifest keeps carrying a target nothing has ever
met, which is worse than no target.

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

### OQ-36 — Should a wake trigger be refused outright when there is no VAD?
**Status:** OPEN — needs data, raised 2026-08-29 while fixing M-A3.

Without a VAD there is no end-of-speech and no ADR-066 no-speech bail-out, so
every hands-free capture runs the full 15 s cap with Friday deaf throughout.
ADR-071 takes the conservative half-step: `arm_end_of_speech` refuses and warns
once, naming the consequence and the workaround (use PTT). It does **not**
refuse the wake trigger itself, because that would silently remove hands-free
operation on a degraded install, and nothing measures how often `webrtcvad`
actually fails to load on this machine — the answer so far is "never observed".

**What decides it:** the warning firing in a real session. If it does, refusing
the trigger (wake logs "no VAD, PTT only" and does not open a capture) is
strictly better than 15 s of deafness. If it never fires, this stays as is.
**Blocks:** nothing. **Default if undecided:** keep ADR-071's behaviour.

**ASKED AND DEFERRED 2026-08-29.** Put to the user the same day it was raised,
with the option of refusing the wake trigger outright or failing at startup.
Answer: **wait for the warning to actually fire.** `webrtcvad` failing to load
has never been observed on this machine, so refusing wake would be designing
for a state with no evidence behind it — and it has its own failure mode
(silently removing hands-free operation on a degraded install). This is a
deliberate hold, not an unanswered question: it stays open **until the log line
appears**, and the next session should not re-litigate it without that
evidence.

---

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
**Decider:** USER · **Status:** **ANSWERED 2026-08-29 (live pass)**

**Answer:** YouTube stays the default. When it cannot work — e.g. the network
is down — fall back to VLC or mpv, and Friday **may ask** which at that point.

**This is why mpv never opened during the live pass:** `'Play a video'` →
`youtube_search{"query": "play a video"}` (audit v28), never `open_app{video}`.
`open VLC` did reach `open_app`, so a bare app name still works.

**Two constraints on implementing it, both from ADR-043 and the live pass:**
the launch is fire-and-forget, so Friday **cannot** detect that YouTube failed
to load — the only honest pre-dispatch signal is network state (`nmcli`). And
the "may ask" half needs the clarify turn of **ADR-077**, so it lands with that
work or not at all.

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

- **OQ-38 — How should the Hyprland tools talk to Hyprland 0.56's Lua
  dispatcher?** ANSWERED 2026-08-29, the same day it was raised (**ADR-074**),
  and implemented the same day. Both `hypr_workspace` and `hypr_window` had
  **never worked on this machine** while Friday announced success every time —
  two causes: `HYPRLAND_INSTANCE_SIGNATURE` was missing from the executor's
  minimal env (`hyprctl` cannot find the compositor, rc=1), and Hyprland 0.56
  routes `dispatch` through Lua so the old positional form no longer parses
  (rc=7). Found only because ADR-073 made a command's exit code a verdict.
  Two questions were put to the user: **fix now, before Step 10** (rather than
  after Step 12), and **treat the Lua as its own audited exception with its own
  ADR** (rather than an ordinary `build_argv` change). The answer went stricter
  than ADR-027: no parameter is formatted into the Lua at all — a closed-set
  param SELECTS one of sixteen import-time constants — and `workspace` became a
  closed enum in `PARAM_SCHEMA` instead of free text. Verified against the live
  compositor (workspace 3 -> 1 -> 2, read back with `hyprctl activeworkspace`).
  `hypr_window` is implemented but deliberately NOT live-probed: `close` and
  `fullscreen` act on the focused window, so it stays a hand-tick row in
  `docs/reality-check.md` §A10. The original write-up follows.

  **The evidence, as first written:**

  `hypr_workspace` and `hypr_window` have **never worked on this machine**, and
  Friday announced success every time. Found the moment ADR-073 made a command's
  exit code a verdict. Two independent causes, both measured through the real
  executor (evidence in `docs/reality-check.md` §A10 and the Step 9 session block
  in `progress.md`):

  1. `HYPRLAND_INSTANCE_SIGNATURE` is missing from `registry._APP_ENV`, so
     `hyprctl` cannot find the compositor at all (rc=1). One line to fix; the
     systemd unit already passes the variable through.
  2. `hyprctl dispatch workspace 2` no longer parses — Hyprland 0.56 routes
     `dispatch` through Lua (rc=7). `registry.py`'s own comment records this for
     `dispatch exec` (it is why apps are spawned directly); nobody checked the
     sibling call sites. The working form here, verified by switching workspaces
     and reading `hyprctl activeworkspace` back, is
     `hyprctl dispatch 'hl.dsp.focus{workspace=N}'`, with window dispatchers
     under `hl.dsp.window.*` (`close`, `fullscreen`, `float`, …).

  **What decides it:** the user, on two points. (a) Fix now or after Steps 10–12
  — ADR-067 explicitly rejected opportunistic fixes during other work, which is
  why this was recorded instead of folded into Step 9. (b) Whether building a
  **Lua expression** in `build_argv` needs its own ADR. It is not an invariant-#2
  breach as long as the parameter stays a closed set (workspace is a validated
  1–10, the window action a closed enum) — code owns the template, the model owns
  only an enum member — but it is the same *shape* as ADR-027's audited youtube
  exception, and that precedent says a second string-building tool gets its own
  ADR rather than inheriting one.
  **Blocks:** two of the twelve G12 rows of `docs/reality-check.md`.
  **Default if undecided:** fix both causes with the measured syntax, under a new
  ADR, immediately after Step 12.

  ---

- **OQ-37 — Should a DECLINED confirm write an audit row?** ANSWERED
  2026-08-29: **yes** (ADR-072), and it is implemented the same day. The four
  confirm-gated tools are exactly the dangerous ones, and "Friday *proposed*
  turning off Wi-Fi and I said no" is the more interesting half of that
  exchange — it is also the half that says something about the planner, since a
  proposal the user keeps refusing is a mis-planning signal that was previously
  invisible. FR-58 changes from "one row per dispatch" to "one row per resolved
  action, dispatched or declined". Two constraints came with the answer: a
  declined row must never feed `mine_habits` (it filters `outcome='ok'`, and a
  test now proves five consecutive declines mine to zero habits — Friday
  learning "you often turn off Wi-Fi" from five refusals is the worst possible
  reading of this data), and the redaction rule lives in exactly one function,
  `turn.audit_params`, called by both the executed and declined paths. Rejected:
  the narrower "only for confirm-gated tools" option, which describes the same
  set today and would need re-deciding the moment a fifth confirm-gated tool
  appears; and reusing `outcome='denied'`, which already means "policy refused
  it" and would conflate a user changing their mind with the ban list firing.

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
  **IMPLEMENTED 2026-08-29** (fix-phase Step 2), and slightly stronger than the
  decision: the clipboard is not *read at all* until the user says yes, so a
  declined confirm never fetches the selection, let alone speaks it.
  `tests/test_clipboard_confirm.py`.

- **OQ-35 — Retention policy for `notes` (and terminal-state reminders)?**
  ANSWERED 2026-08-27: **notes kept indefinitely, fired/cancelled reminders
  pruned at 90 days** (ADR-068b), matching FR-59's existing audit window rather
  than adding a second constant. Active reminders are never pruned regardless
  of age. Notes are user-authored content the user expects to still be there;
  terminal-state reminders are machine exhaust. Closes M-T9.
  **IMPLEMENTED 2026-08-29** (fix-phase Step 6), `audit.sweep_retention`;
  `tests/test_db_integrity.py` proves notes and active reminders survive at
  100 days while fired/cancelled ones do not.

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




