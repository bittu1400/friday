# Friday — Open Questions

Every entry: what is unknown, who decides, what it blocks, and what
happens if nobody decides. An open question with no blocking gate is not
open — it is a note, and it belongs elsewhere.

**Status values:** `OPEN` / `ANSWERED` / `DEFERRED`
**Decider:** `USER` (needs your judgement) or `MEASURE` (a benchmark
answers it, no opinion required).

---

## Blocking Phase 1

### OQ-22 — Which Kokoro voice preset? (audition)
**Decider:** USER · **Blocks:** G5 · **Status:** CLOSED 2026-08-23 —
`af_bella` primary, `af_heart` fallback. User found heart/sky indistinct,
preferred bella. See ADR-005 / ADR-040.

The runtime, model, and thread count are settled by benchmark (ADR-039);
the VOICE is subjective and yours to pick — it cannot be measured. Audition
`af_heart` / `af_bella` / `af_sky` **through the laptop speakers** (not
headphones — that is the real listening condition).

fp32 WAVs are already generated at `~/.cache/kokoro-bench/samples/`
(`fp32_af_heart.wav`, `fp32_af_bella.wav`, `fp32_af_sky.wav`); a quality
A/B of the same line under q8 and q4f16 is there too, if you want to hear
why fp32 was chosen. All are the same fixed sentence.

**Default if undecided:** `af_heart` — the most common community default;
change on a listen.

**On answer:** write the preset into ADR-005's TBD line and `config.toml`,
close this OQ, tick the G5 voice-lock box.

---

### OQ-03 — Is a Hyprland bind acceptable for PTT?
**Decider:** USER + MEASURE · **Blocks:** G6 · **Status:** ANSWERED +
RESOLVED 2026-08-23 (key = Copilot key; hold-to-talk confirmed viable via
Hyprland bind — see below)

`bind = , KEY, exec, friday-ptt press` signalling the running daemon
avoids granting keyboard-observation privilege entirely (T5). It needs
one line in the Hyprland config and a key that is otherwise unused.

Which key? Right Ctrl and the Menu key are common choices. Does anything
already bind it?

**Default if undecided:** try the bind path at G6 and record whether it
works. Only fall back to `evdev` with written evidence.

**Answer (2026-08-23):** PTT key = the **Copilot key** (right of the arrow
cluster). This laptop has **no Right Ctrl**. Menu was the other candidate;
user picked Copilot.

**Keysym captured + hold verified (2026-08-23, `wev`).** The Copilot key
emits a chord: `Super_L` + `Shift_L` + `XF86Assistant` on press. It was
feared to be a firmware one-shot (a short tap released in ~0.6 s), but a
deliberate ~3 s hold showed the trigger key stays down for the whole hold
(press→release gap = hold duration, ~6.5 s measured; no auto-repeat during
the hold). **Hold-to-talk is therefore viable** — FR-2 (hold, capture,
release to submit) is unchanged; no toggle, no Menu fallback, no evdev.

Bind (the bind path of ADR-013, no keyboard-observation privilege):
```
bind        = SUPER SHIFT, XF86Assistant, exec, friday-ptt press
bindrelease = SUPER SHIFT, XF86Assistant, exec, friday-ptt release
```
`XF86Assistant` releases before the modifiers, so `bindrelease` fires
cleanly on trigger key-up. Verify the bind end-to-end when the daemon
socket exists (progress.md G6). Evdev fallback remains the ADR-013 escape
hatch only if the live bind misbehaves.

---

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

### OQ-06 — Voice preset
**Decider:** USER · **Blocks:** G5 · **Status:** CLOSED by OQ-22 2026-08-23
(af_bella primary / af_heart fallback — ADR-005/040)

Audition `af_heart`, `af_bella`, `af_sky` on the same five sentences,
through the laptop speakers (not headphones — that is the real listening
condition). Lock one, record it in ADR-005.

**Default if undecided:** `af_heart`.

---

### OQ-18 — Preference key vocabulary
**Decider:** USER · **Blocks:** G4 · **Status:** CLOSED 2026-08-23 —
option (d): free slugified key + curated alias anchors + confirm-on-save.
See ADR-035.

`schema.py` currently lets the model supply `remember_preference.key` as
free text. That decides how predictable the digest is and whether
`forget_preference` can reliably find the key the user means.

```
   (a) Closed enum      fixed keys (name, editor, browser, terminal,
                        media_player, ...). Model maps to a known key or
                        the write fails closed. Predictable digest, forget
                        always matches. New pref kind = code change.
   (b) Free, normalized any key, slugified (lowercase, spaces->_, strip).
                        Flexible; risk of near-dupes (my_name vs name).
   (c) Free, raw        store verbatim. Most flexible, least findable.
```

**Default if undecided:** (a) closed enum — smallest T2 surface, matches
the "model supplies an opaque ID from a closed set" invariant in spirit,
digest is deterministic for the FR-55 snapshot test.

**On answer:** update `schema.py` PARAM_SCHEMA, `validate.py`, the digest
renderer, and `forget_preference` matching; write ADR-035.

---

### OQ-19 — `forget_preference` / `prefs reset`: hard-delete vs soft-expire
**Decider:** USER · **Blocks:** G4 · **Status:** CLOSED 2026-08-23 —
(c) split: voice soft-expires, keyboard `--hard`/`--yes` hard-deletes.
See ADR-036.

Hard-deleting user data is a prohibited-by-default action in the safety
rules. This is the user's own local prefs, user-initiated, so it is
allowed — but the *mechanism* is a real choice.

```
   (a) Soft-expire     set expires_at=now; row stops being injected at
                       once, survives until retention sweep. Recoverable,
                       audit-friendly.
   (b) Hard delete     DELETE the row. Literal 'forget', nothing lingers.
                       Not recoverable.
   (c) Split           voice forget_preference soft-expires (safe on a
                       mishear); CLI `prefs forget --hard` / `reset --yes`
                       hard-deletes when explicit at the keyboard.
```

**Default if undecided:** (c) split — protects against a misheard voice
command while giving the keyboard an explicit hard path.

**On answer:** write ADR-036; wire into the tool + the `prefs` CLI.

---

### OQ-20 — Confirm a spoken preference before storing?
**Decider:** USER · **Blocks:** G4 · **Status:** CLOSED 2026-08-23 —
(b) confirm first, deterministic UI handshake (no 2nd model turn).
source='user_confirmed'. See ADR-037.

Decides what the `source` column means (`user_confirmed` vs `user_typed`,
per the schema CHECK) and whether the turn loop grows a handshake.

```
   (a) Store directly  remember_preference writes, then speaks the
                       confirmation template (execute-first, ADR-009).
                       source='user_typed'. No new turn machinery.
   (b) Confirm first   'Remember that your browser is brave?' -> writes
                       only on yes. source='user_confirmed'. Adds a
                       two-turn handshake + pending state this gate.
```

**Default if undecided:** (a) store directly — a misheard pref is cheap to
forget, and (b) is real new turn-loop machinery not otherwise needed at G4.

**On answer:** if (b), the turn loop + a pending-preference state are G4
work; note in ADR-034/architecture §3.1. Record in ADR-037.

---

### OQ-21 — Retention scope: do preferences auto-expire by age?
**Decider:** USER · **Blocks:** G4 · **Status:** CLOSED 2026-08-23 —
(a) logs only; preferences never age out. See ADR-038.

The retention job caps at 90 days / 50 MB (config.toml `[memory]`). Audit
rows and session summaries are logs; preferences are user data with a
lifecycle.

```
   (a) Logs only       purge action_audit + session_summaries only.
                       Preferences never expire by age — they live until
                       forgotten or their own expires_at fires.
   (b) Everything      preferences also age out at 90 days unless
                       pinned=1. Smallest DB; a set-and-forgotten pref
                       vanishes.
```

**Default if undecided:** (a) logs only — a preference the user stated
should not silently disappear; the `pinned` column then only matters if
(b) is ever chosen.

**On answer:** scope the retention job accordingly; record in ADR-038.

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

## Deferred to Phase 2

### OQ-12 — Wake word: which one, and at what FA/FR?
**Status:** DEFERRED (ADR-012)

If always-on listening is ever wanted: start with pretrained
`hey_jarvis`. A custom "Friday" needs sample synthesis, augmentation,
training, and a measured false-accept/false-reject target across rooms
and noise conditions — not a threshold picked by feel. Note the
non-commercial licence on openWakeWord's pretrained models.

A wake word also makes acoustic echo cancellation mandatory (ADR-014).

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
- **OQ-03 — PTT key + bind path?** ANSWERED + RESOLVED 2026-08-23. Key =
  the Copilot key (no Right Ctrl; Menu was the alternative). Emits chord
  `SUPER SHIFT, XF86Assistant`; a 3 s hold confirmed it tracks physical
  hold, so hold-to-talk (FR-2) works via `bind`/`bindrelease` on the bind
  path (ADR-013) — no toggle, no Menu, no evdev. See OQ-03 body for the
  exact bind lines + evidence.
- **OQ-07 — whisper CPU latency?** ANSWERED 2026-08-23. Yes with `small.en`
  (p95 741 ms); `large-v3-turbo` failed (2.7 s). CPU STT viable, no GPU.
  See ADR-042.
- **OQ-23 — mic device for capture?** ANSWERED 2026-08-23. Default
  PipeWire source (currently analog `Mic1`), config-overridable; not the
  `DMIC Raw` array (index can move). Recorded here to close the
  docs/"DMIC array" mismatch. (OQ-06 was the *voice* preset, closed by
  OQ-22 — do not confuse.)
