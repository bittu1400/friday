# Friday — Open Questions

Every entry: what is unknown, who decides, what it blocks, and what
happens if nobody decides. An open question with no blocking gate is not
open — it is a note, and it belongs elsewhere.

**Status values:** `OPEN` / `ANSWERED` / `DEFERRED`
**Decider:** `USER` (needs your judgement) or `MEASURE` (a benchmark
answers it, no opinion required).

---

## Blocking Phase 1

### OQ-03 — Is a Hyprland bind acceptable for PTT?
**Decider:** USER + MEASURE · **Blocks:** G6 · **Status:** OPEN

`bind = , KEY, exec, friday-ptt press` signalling the running daemon
avoids granting keyboard-observation privilege entirely (T5). It needs
one line in the Hyprland config and a key that is otherwise unused.

Which key? Right Ctrl and the Menu key are common choices. Does anything
already bind it?

**Default if undecided:** try the bind path at G6 and record whether it
works. Only fall back to `evdev` with written evidence.

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
**Decider:** USER · **Blocks:** G5 · **Status:** OPEN

Audition `af_heart`, `af_bella`, `af_sky` on the same five sentences,
through the laptop speakers (not headphones — that is the real listening
condition). Lock one, record it in ADR-005.

**Default if undecided:** `af_heart`.

---

## Answered by measurement (no opinion needed)

### OQ-07 — Does whisper meet latency on CPU?
**Decider:** MEASURE · **Blocks:** G1 · **Status:** OPEN

CPU is the default (ADR-004): it removes an entire CUDA context and keeps
the Python environment CUDA-free, which is what makes FR-71 checkable.

Measure CPU only. 20 clips, 2-8 s, from the actual laptop mic. Pass if
p95 <= 800 ms. Only on failure does the CUDA arm get installed and
measured — that is stop condition #5, and it reopens ADR-018.

Record the table in `progress.md` G1.

---

### OQ-08 — Does `thought` actually improve tool selection?
**Decider:** MEASURE · **Blocks:** nothing, informs ADR-011 · **Status:** OPEN

Run the 50 eval fixtures twice — grammar with `thought`, grammar without.
Compare pass rates. If the delta is under 2 fixtures, delete the field
and close the privacy question permanently.

Do this at G2, the moment the harness exists. It costs one command.

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
**Decider:** MEASURE · **Blocks:** nothing in Phase 1 · **Status:** OPEN

```bash
ls /dev/accel/ 2>/dev/null; lsmod | grep -i vpu
```

If the device exists, note it as a Phase 2 option for offloading whisper
and freeing P-cores. Do not build on it now. Thirty seconds to check;
ADR-019 exists because the blueprint asserted it was dead without looking.

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
- **OQ-01 — Which apps in the registry?** ANSWERED 2026-08-22. Seven
  entries; defaults firefox / foot / mpv; no file manager, no Spotify;
  YouTube covers music and video. See ADR-026, ADR-027.
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
