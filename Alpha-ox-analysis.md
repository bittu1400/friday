# Alpha-ox Analysis — Full Codebase Audit

**Date:** 2026-08-26 · **Scope:** all Python under `friday/` (6,928 src lines,
57 modules) + `scripts/`, cross-checked against `tests/` (57 files, 308 tests),
`justfile`, `deploy/systemd/`.
**Method:** static analysis (ruff, vulture), four independent line-by-line subsystem audits,
then manual verification of every CRITICAL/HIGH finding against source before inclusion.
**No code was changed.** Line numbers refer to the tree as of this date.
Every file:line citation below was re-verified mechanically against the tree
later the same day (61-point check); corrections found by that pass are applied
inline and listed at the bottom of this file.

Findings that were **[verified]** were re-read and confirmed by hand, not just reported.

---

## Executive summary

The core security spine is genuinely strong (single schema → grammar + validator,
forced `final.gbnf` on untrusted turns, parameterized SQL, closed enums at both layers).
What keeps producing new defects is exactly what previous sessions documented:
**the unhappy paths and cross-module seams are where state leaks**, and no test
composes degraded paths or races two trigger sources.

| Severity | Count | Themes |
|---|---|---|
| CRITICAL | 1 | Text-mode confirm of actions crashes / does nothing |
| HIGH | 8 | unaudited dispatches, orphaned pending-confirm state, FSM double-transition, trigger race, event-loop blocking, wrong-item cancel, debug transcripts to disk |
| MEDIUM | 21 | silent callback death, timer leaks, DB perms/migration races, HTTP client edge shapes, cannot-fail selftest checks |
| LOW | ~25 | listed below |
| Dead code | 15 items | caller-verified |

---

## CRITICAL

### C1. TUI confirmation of every G12 action is broken — answering "yes" raises AttributeError [verified]
`friday/ui/tui.py:166-181` stores whatever `result.pending` holds, then always calls
`confirm_preference(pending, ...)` (`friday/turn.py:323-343`), which executes
`prefs.put(pending)` and reads `pending.key` / `pending.value`. But `run_turn`
also stores **`PendingAction`** there (`turn.py:171,226,232,238` — `clipboard_set`,
`system_wifi{off}`, `hypr_window{close}`, and any ADR-065 history-resolved action),
and `PendingAction` has `tool_id`/`params`, not `key`/`value`.

Result: in text mode, confirming "Are you sure you want to overwrite your clipboard?"
does nothing and errors. The voice path handles both types correctly
(`daemon.py:441-482` branches on `isinstance`) — the TUI was never migrated when
Phase 2 introduced `PendingAction`. This is the exact "spoke success while doing
nothing" defect family from 2026-08-24, alive in the other UI.
**Fix:** mirror the daemon's isinstance branch in `_resolve_pending`; fix the
`self._pending: PendingPreference | None` annotation at `tui.py:68`.

---

## HIGH

### H1. Confirmed-action dispatches and ALL web searches write no audit row [verified]
- `daemon.py:455-476`: when a user *confirms* `system_wifi off`, `hypr_window close`,
  `clipboard_set`, the executor runs but no `audit.arecord` follows. Same for
  `cancel_reminder` (`turn.py:472-489`, dispatched). DND and dictation
  (`turn.py:208-212,241-244`) also write no audit row, but note they return
  `dispatched=False` — the daemon applies their side effect later
  (daemon.py:359-370), so under FR-58-as-amended they need a row at the point
  the side effect lands, not a dispatch row.
- `turn.py:276-309` (`_do_web_search`): no audit row on any path — which also makes
  `habits.describe_action`'s `web_search` branch (`habits.py:77-81`) unreachable dead logic.

FR-58 ("audit records everything") is enforced nowhere by test: only 5 sites write rows.
The dangerous confirmed dispatches — precisely what the audit exists for — are invisible.
**Fix:** one row per confirmed dispatch in `_resolve_confirm`; audit search attempts;
add a cross-cutting contract test "every dispatched action produces an audit row."

### H2. Orphaned `_pending` when the confirm-question TTS fails → next utterance confirms an action the user never heard [verified]
`daemon.py:375-380`: `self._pending = result.pending` is assigned **before**
`await self._speak(result.spoken)` (the question). If `speaker.say` raises
(audio device gone), the generic handler at :397-401 runs `_fail_speak` and returns —
`_pending` stays set, **no confirm timer armed**, FSM back to IDLE. The next utterance,
possibly minutes later ("yeah" opening a chat turn), hits `daemon.py:285` and is consumed
as the yes/no answer. For a held `system_wifi{off}` pending that means dispatching Wi-Fi
off on a "yes" that answered nothing. Asymmetric with the cancel path, where
`_open_confirm_window()` still runs.
**Fix:** clear `_pending` in the exception/timeout handlers, or set it only after speak succeeds.

### H3. Barge-in during the confirm question leaves pending + 30 s timer shadowing the new conversation [verified]
`daemon.py:495-502`: `_speak` swallows `CancelledError` and **returns normally**, so
`_run_turn` continues to `_open_confirm_window()`. The user's barge command is then read
as the yes/no answer (non-affirmation cancels it — fail-safe but the real command is eaten
and answered with "Okay, cancelled."). Related, same root cause: **interrupted replies are
recorded in dialogue history as if fully delivered** (`daemon.py:390-394` adds
`result.spoken` even when the speak was cut off), feeding the exact ADR-065 attack surface
(history-resolution reasoning over content the user never received), and leaving the old
turn task running concurrently with the new capture's task.
**Fix:** have `_speak` report completion-vs-cancelled; drop pending + disarm window on barge;
only `dialogue.add` after uncanceled speech.

### H4. Double FSM transition → `IllegalTransition` on every capture in no-STT mode [verified]
`daemon.py:403-406` (`_transcribe`, transcriber=None): calls `state.got_transcript(nonempty=False)`
(TRANSCRIBING→IDLE), then `_run_turn:269` calls `got_transcript` **again** → `_require(TRANSCRIBING)`
raises. Every voice press in the supported degraded mode speaks "Something went wrong."
for what FR-12 mandates be a silent return to IDLE. Invisible to tests because no fixture
drives `transcriber=None` end-to-end.
**Fix:** remove the transition from `_transcribe`'s None-backend path; let the caller own it.

### H5. Trigger-source TOCTOU: wake arms VAD end-of-speech on the audio thread before the FSM accepts [verified]
`wake.py:297-308` sets `_awaiting_end = True` and resets gates *before* scheduling
`on_wake`; `daemon.py:156-161` may reject (`begin_capture()` false). On rejection the
listener **stays armed**: VAD end-of-speech now terminates what is by definition a
PTT-controlled capture (contradicting ADR-044), or a spurious "busy" toast fires and
tap-toggle desyncs — the partially-fixed 2026-08-25 defect class.
**Fix:** pass accept/reject back to disarm the listener, or arm only after acceptance.

### H6. CPU/blocking work on the asyncio event loop
- `daemon.py:277-279` — speaker verification (ONNX embedding inference) runs inline;
  hundreds of ms of deafness per turn when G13 is enabled. Contrast: STT/TTS correctly
  use `asyncio.to_thread`.
- `daemon.py:328-333` — `generate_signoff_summary` performs a full synchronous LLM
  round-trip on the loop (the sibling call in `Daemon.close()` IS wrapped in `to_thread`).
- `proactive/notifier.py:26-32` via `daemon.py:150` / `scheduler.py:73` — synchronous
  `subprocess.run(notify-send, timeout=2)` on the loop, in the reject path that can burst.
- `daemon.py:339-345` — sync SQLite reads (`mine_habits`, summaries) inline each turn.
**Fix:** `asyncio.to_thread` / `create_subprocess_exec` for each.

### H7. "Cancel latest reminder/timer" cancels the one firing farthest in the future [verified]
`turn.py:484-486` takes `active[-1]`, but `alist_active` orders by `fire_at ASC`
(`reminders.py:81`). With a pasta timer and a meeting reminder outstanding,
"cancel my reminder" kills the meeting. The comment says "latest"; nothing orders by
creation time.
**Fix:** pick by `created_at DESC` (and say *which* reminder was cancelled).

### H8. `FRIDAY_DEBUG=1` writes raw transcripts to persistent disk via journald
`logging_config.py:121-138`: `NoDiskFilter` guards only the file handler; `no_disk`
records go to stderr freely. Under systemd (default journald persists to
`/var/log/journal`), the documented debug workflow silently violates invariant #7.
Nothing enforces foreground execution.
**Fix:** suppress `no_disk` records on stderr when running under journald, or set
`StandardError=null` in the unit and log a warning.

---

## MEDIUM

### Audio pipeline
- **M-A1. Unhandled exception in a PortAudio callback permanently kills the stream, silently.**
  `wake.py:310-314` calls into ONNX scoring + WebRTC VAD unguarded;
  `vad.is_speech` raises `ValueError` for non-10/20/30 ms frames. (The
  capture.py callback (:90-92) only gate-checks and copies — it does not touch
  ONNX/VAD — but it is equally unguarded, and a raise there kills the stream
  the same way.) python-sounddevice
  prints to stderr and stops calling back — wake/VAD/barge die while the service looks
  healthy. The next "green suite, broken feature." Wrap both callbacks, count failures, degrade loudly.
- **M-A2. Capture-cap timer leak on re-arm.** `daemon.py:248-252` overwrites `_cap_timer`
  without cancelling the old handle (the confirm timer got exactly this discipline with a
  comment explaining the hazard; the cap timer didn't). Fires mid-next-capture.
- **M-A3. `vad=None` silently resurrects pre-ADR-066 behavior.** `wake.py:266-290`:
  without a VAD, an armed capture has neither end-of-speech nor the 3 s bail-out — every
  hands-free capture runs the full 15 s cap. Refuse to arm; log once.
- **M-A4. Hot-path allocations in the audio threads.** `wake.py:101,105` concatenate+slice
  per frame; `wake.py:36-39` `FarEndRef.write` copies the whole ≤80k buffer per output
  callback; `vad.py:36-38` ~4 temporaries/frame ×2; `aec.py:68` `empty_like`/frame.
  Against the modules' own "callback allocates nothing" contracts. Ring buffers for FarEndRef.
- **M-A5. Playback-truncation reports success.** `tts.py:175-180`: if the finished-callback
  never fires, `say()` still returns True ("played to the end").
- **M-A6. `wait_for_llm` treats `"loading model"` as ready.** `voice_main.py:51-54` —
  defeats the entire purpose of the cold-start wait; first turns hit a non-serving server.
- **M-A7. Recorder ring cursor shared across threads with no ordering guarantee**
  (`capture.py:44-64`) — worst case ±1 stale frame today, but undocumented.
- **M-A8. Startup mic-open failure ignored.** `daemon.py:572` discards `recorder.open()`
  result; a mic-less machine starts "successfully" and every press silently no-ops.

### Confirm/proactive lifecycle
- **M-P1. `_expire_confirm` force-resets a live capture mid-answer.** `daemon.py:434-439`:
  timer fires while user is CAPTURING the yes/no → mic gate slams shut, release finds
  state ≠ CAPTURING, answer lost with zero feedback.
- **M-P2. Proactive speech bypasses the FSM entirely.** `daemon.py:540-553`: multiple due
  reminders each wait for idle, then all proceed → concurrent unsynchronized `speaker.say`
  (interleaved audio), and during playback the FSM is IDLE so Friday can transcript her own voice.
- **M-P3. Scheduler serial delivery stalls its poll loop.** `scheduler.py:54-78`:
  `_on_event` busy-waits ≤30 s for idle inside the poll loop (burst → late timers);
  poll errors logged at DEBUG (silent in production); `mark_fired` precedes delivery so a
  failed delivery loses the reminder permanently.
- **M-P4. `mark_fired` overwrites a concurrent cancellation.** `reminders.py:72-76`:
  `UPDATE ... SET state='fired' WHERE id=?` lacks `AND state='active'` — user hears
  "Cancelled.", scheduler notifies anyway within one poll interval.

### Tools/store
- **M-T1. `ToolSpec.timeout_s` is dead config; the documented timeout guarantee doesn't exist.**
  Set ten times, never read; `executor.py:111-114` waits only `_LAUNCH_GRACE_S=0.4`,
  kills nothing on timeout, yet the docstring claims process-group kill. Invariant #3's
  "bounded timeout" is enforced by accident of a constant, not by the spec.
- **M-T2. SQLite `-wal`/`-shm` can exist before the 0600 chmod.** `db.py:51-58`:
  `PRAGMA journal_mode=WAL` (creates sidecars) precedes `path.chmod(0o600)`. Under a
  permissive umask the WAL (prefs, notes, reminder text in flight) can be world-readable.
  Selftest checks only the main DB. Fix: chmod immediately after connect.
- **M-T3. Partial migration failure → permanent crash-loop.** `db.py:78-84`:
  `executescript` implicitly commits, version insert is separate; crash between them
  re-runs CREATE TABLE (migrations lack IF NOT EXISTS) → OperationalError forever under
  `Restart=always`. Wrap migration + version bump in one transaction.
- **M-T4. `typer.py` argv parsing + swallowed failure.** `typer.py:24-30`: dictated text
  starting with `-` is parsed by wtype as an option (needs `--`); `dictation` return value
  discarded at `daemon.py:307` (typed-nothing-but-said-success family); inherits full env
  (also `clipboard.py`, `notifier.py` — deviates from invariant #3's minimal env).
- **M-T5. Habits digest lacks the fence neutralization every other prompt-bound renderer has.**
  `habits.py:149-158` strips control chars and caps at 150 chars, but performs no
  `<`/`>` neutralization, so habit text containing `</user_habits>` could break out of
  the prompt frame — unlike `prefs.render_value`, built exactly for this (FR-55
  durable-injection vector). Currently hard-to-reach payloads — but "currently
  unreachable" is not a control (ADR-008 lesson).
- **M-T6. `search.py` AttributeError on malformed SearXNG payload.** `search.py:103-109`
  assumes dict elements; `{"results": ["str"]}` escapes the except net with the wrong
  error contract (generic "Something went wrong" instead of E_NET_DOWN).
- **M-T7. `PolicyRejected` human messages stored as error codes.** `errors.py:39-41`,
  `ban.py:49,54` — raw param values ride in `.code`; harmless until someone logs it.
- **M-T8. Import-time env snapshot.** `registry.py:105` freezes PATH/session vars at
  module import — the boot-race family from 2026-08-25 makes launches silently broken
  until restart. Build lazily per dispatch.
- **M-T9. Retention never prunes `reminders`/`notes`** (`audit.py:76-84` sweeps only two
  tables). Unbounded growth on long-lived installs.

### LLM/UI/selftest
- **M-L1. Read-phase HTTP timeout escapes uncaught.** `client.py:86-100`: a slow
  generation raising bare `TimeoutError` during `resp.read()` matches no except →
  propagates through `_plan`'s narrow handlers → turn crash; TUI input disabled forever.
- **M-L2. Server 500s retried and misclassified.** `HTTPError` subclasses `URLError`;
  its reason string isn't a timeout, so a generate-time 500 is retried 3× (docstring says
  retry ONLY on connect) then reported as `LlamaUnreachable` though the server answered.
- **M-L3. `gpu_arch` returns PASS on unparsable nvidia-smi output** (`selftest.py:158-159`)
  — the cannot-fail pattern, again. FAIL/WARN on garbage instead.
- **M-L4. Socket-bind audit misses LAN-IP binds and IPv6 wildcards** (`selftest.py:287-327`):
  only `0.0.0.0/*/[::]` flagged; `/proc/net/tcp6` never read in the fallback.
  Invariant #8's check has holes in exactly the states it exists for.
- **M-L5. Full tracebacks persisted to the log file** (`logging_config.py:70-73`) —
  contradicts "log the code, never log a raw exception"; redaction strips paths only.
- **M-L6. Grounded answers re-enter planner history labeled first-party.** `tui.py:164-165`
  (+ voice equivalent) puts spoken web-derived answers into `Dialogue`, injected into the
  planner prompt despite `turn.py:139-140`'s "first-party only" comment. Grammar+validator
  bound the damage, but the stated guarantee is false as written.
- **M-L7. Text mode speaks success for DND/dictation changes it never applies**
  (`turn.py:208-212,241-244` return enabled-lines with `dispatched=False`; actual change is
  daemon-side post-processing the TUI never runs).
- **M-L8. Free-text params: no central length cap or control-char rejection**
  (`validate.py:126-128` checks non-empty only); ad hoc truncation downstream.
- **M-L9. Selftest `audio_devices` cannot fail** (every failure mode → WARN, exit 0) and
  `check_database` creates the DB it claims to verify existing. (`llm_on_gpu` does
  have one real FAIL path — running-without-VRAM at :373-381 — but every *surprise*
  outcome still downgrades to WARN; Step 10 closes the downgrade, not that FAIL.)
- **M-L10. Silent blanket-excepts in grounding/chat** (`grounding.py:69`, `chat.py:66`)
  log nothing — systematic bugs invisible, violating the taxonomy's "log the code".

---

## LOW

**Audio/daemon:** L1 `ptt.py:60` never awaits `writer.wait_closed()`. L2 `urllib.error`
relied on as import side effect (`voice_main.py:55`). L3 `LlamaTimeout` path fine but
`_say_now`/`_fail_speak` have no timeout — hung audio wedges FSM in ERROR (`daemon.py:516-520`).
L4 `dispatched=True` counts TIMEOUT/ERROR tool outcomes (`turn.py:263`). L5 dev placeholder
string would be TTS'd if NOT_YET_WIRED ever routed (`turn.py:251-254`). L6 `db.close()` not
exception-safe in `__main__.py:72-77`. L7 reminder text logged raw (`daemon.py:550`). L8 cap-timer
callback spawns unreferenced task (`daemon.py:250-252`); sched task cancelled but never awaited (:593-594).
L9 repeated function-local imports per turn (`daemon.py:289,340,445,461,562`).
**Config/LLM/UI:** L10 `FRIDAY_DEBUG=0` enables debug (presence-check vs truthiness, `config.py:78`).
L11 `RUNTIME_DIR` falls back to STATE_DIR → PTT socket on real disk (`config.py:93-95`).
L12 malformed env ints crash at import before logging exists (`config.py:30,44-48,...`).
L13 prompt↔schema vocabulary drift: `toggle_mute`, media `play`/`pause` absent from prompt
lines (`prompt.py:52-54` vs schema). L14 `confirm_from_history` always says "open {what}"
even for wifi-off/reminder (`templates.py:69-72`). L15 typed newlines can forge `\nYou:` chat
lines (`chat.py:56`). L16 eval harness KeyError on unknown fixture param aborts whole run
(`eval_harness.py:63`); exit 0 possible on 0/28-with-matching-baseline (:174). L17 enroll
accepts 3-of-10 printout without warning; `--samples` silently capped (`speaker_enroll.py:99-112`).
L18 `setup_logging` leaks handler fds across repeated calls (`logging_config.py:94-96`).
L19 non-str LLM content coerces badly (`client.py:89` → TypeError not LlamaUnreachable).
L20 `llm_on_gpu` downgrades surprises to WARN (`selftest.py:351-384`); `pgrep -x` breaks on
wrapped binary. L21 `file_open` substring alias match can open the wrong registered file
(`registry.py:200`) — token-boundary matching needed. L22 `_humanize_duration` rounds 90 min
to "2 hours" (`turn.py:390-398`). L23 reminder listing mixes kinds, truncates to 3 silently
(`turn.py:467-468`, briefing repeats). L24 `clipboard_read` speaks up to 100 chars aloud —
copied passwords get vocalized (`turn.py:549`). L25 selftest docstring lists 7 checks, 8 run.

---

## Dead code inventory (all caller-verified)

| Item | Location | Note |
|---|---|---|
| `PendingAction` name in annotation | `daemon.py:124` | never imported; survives only via `from __future__ import annotations` — NameError under introspection |
| `RiskTier` enum + `import os` | `ban.py:17-22,10` | zero references anywhere |
| `ToolSpec.timeout_s` | `registry.py:45` + 10 setters | never read (see M-T1) |
| `NOT_YET_WIRED` + dispatch branch | `registry.py:311`, `turn.py:251-254` | mapping is `{}`; kept alive only by one test |
| `describe_action` web_search branch | `habits.py:77-81` | unreachable — no web_search audit rows exist (H1) |
| `ToolResult.code` | `executor.py:41,66` | constructed, never consumed |
| `E_SCHEMA`, `E_TOOL_TIMEOUT`, `E_TOOL_FAILED` | `errors.py:23-32` | defined, never referenced; `E_BUSY` used as string literal instead (`daemon.py:147`); `E_LLM_TIMEOUT` cited in comments, defined nowhere |
| `PolicyRejected` | `errors.py:39-40` | raised, but `.code` never consumed |
| scheduler `dnd` param | `scheduler.py:29` | stored, never used |
| `PendingAction.description` | `turn.py:57` | constructed everywhere, never read |
| `create_detector(threshold=…)` param | `wake.py:119` | accepted, ignored |
| `awrite`/`aquery` | `store/db.py:104-108` | no callers in src (one test uses awrite) |
| registry docstring "web_search not-yet-wired" | `registry.py:10-11` | stale — it is wired in turn.py |
| preferences.source `'user_typed'` | migration 001 | no writer passes it |
| vestigial `sd.stop()` in `Speaker.stop()` | `tts.py:200-205` | targets unused `sd.play()` API |
| `_Probe.reset()` → nonexistent detector method | `scripts/wake_bench.py:42-43` | latent AttributeError, currently never called |

Static analysis (ruff): 127 findings total — 9 unused imports, 13 unsorted imports,
43 blind excepts (mostly deliberate fail-soft; see note), 13 try-except-pass,
plus one F821 (the `PendingAction` annotation above), one F841 (`selftest.py:412 color`),
one comparison-with-itself-class flag on the intentional sanitizer regexes in
`search.py:27` (linter false positive — the ZWSP/bidi regex is intentional; suggest
rewriting with explicit escapes like the neighboring `_CONTROL` to silence it).

---

## Verified solid (checked, not assumed)

- **Invariant #1 mechanically sound:** search bodies enter prompts at exactly one point
  (`grounding.py:47-50`); `untrusted=True` forces `final.gbnf` inside the client
  (`client.py:55-62`); grammar pins `name ::= "none"` (committed-file drift tested);
  `_do_web_search` hardcodes `dispatched=False`; injection suite spies on the executor.
- **SQL:** 100% parameterized across store/ (both by grep-test and manual read); indexes
  cover hot queries; single serialized connection + lock is coherent.
- **Subprocess:** argv lists everywhere, shell=False, timeouts set; youtube_search remains
  the single audited exception with its five hardening layers intact.
- **Enum discipline:** schema-side enums match builder vocabularies; builders raise rather
  than guess — the brightness regression is structurally closed and tested at both layers.
- **One-turn-in-flight (FSM level):** enforced by begin_capture/barge_in returning bools
  from IDLE/SPEAKING only; residual holes are task-level (H3/M-P2), not turn-level.
- **Datetime:** epoch floats for reminders (DST-immune); no naive/aware mixing found.
- **RAM:** Dialogue bounded (deque maxlen=8); task refs released; no unbounded growth found.
- **Voiceprint perms:** save enforces 0600/0700 as claimed.

---

## Recommended fix order (each small, none touches an invariant)

1. **C1** (TUI confirm) + **H4** (double transition) — user-visible breakage in supported modes.
2. **Confirm-lifecycle commit:** H2 + H3 + M-P1 together (one coherent handshake fix).
3. **H1** audit coverage + contract test; **H7** cancel-pick ordering.
4. **H6** move blocking calls off the loop (mechanical, four sites).
5. **H5 + M-A2 + M-A3** trigger-arm discipline in wake/daemon.
6. **M-T2 + M-T3** DB perms/migration atomicity (small, high blast radius).
7. **M-A1** callback guard (cheap insurance against the next silent death).
8. **M-T1** decide timeout_s: honor or delete + fix docstring.
9. **M-L1/L2** HTTP client edge shapes; **M-L3/L4/M-L9** make selftest checks able to fail.
10. Everything else at leisure; delete the dead-code table in one sweep.

**Meta-lesson (same one, fifth time):** every CRITICAL/HIGH above lives on a
path no
fixture drives — degraded modes (no-STT, no-VAD, TTS-failure), two racing triggers,
or the other UI. Before Phase 3 work, add the missing *composition* tests:
degraded-capability matrix, dual-trigger race test, "every dispatch audits a row",
and a TUI-parity test mirroring the daemon's confirm semantics.

---

## Citation re-verification pass (2026-08-26, same day)

A 61-point mechanical check of every file:line citation against the tree found
the original report materially wrong in three places; all are corrected inline
above and summarized here so no reader trusts the earlier wording:

1. **H1 overcounted unaudited dispatched paths.** DND and dictation return
   `dispatched=False` — the daemon applies their side effect post-turn, so they
   were never "dispatched without audit"; only confirmed dispatches
   (`clipboard_set`, wifi-off, window-close, history-resolved) and
   `cancel_reminder` dispatch unaudited. The fix plan is unaffected.
2. **M-A1 wrongly implicated capture.py in ONNX/VAD work.** The capture
   callback only gate-checks and copies; it never touches the detector or VAD.
   It remains unguarded (same stream-death consequence), so the fix wraps both
   callbacks.
3. **M-T5 overstated the habits gap.** The digest already strips control chars
   and caps length; what is missing is only `<`/`>` fence neutralization.

Minor line drift corrected: clipboard_read slice :540→:549; second
PolicyRejected raise ban.py:53→:54; awrite/aquery span :104-108. Also noted:
`llm_on_gpu` has one genuine FAIL path (running-without-VRAM); Step 10 targets
its surprise-downgrade-to-WARN behavior, not that FAIL. No severity changed;
no fix step reordered.

---

## Fix status — updated 2026-08-29 (Steps 1–9 executed)

This report is a snapshot of 2026-08-26 and is **not** rewritten as fixes land.
Use this table for what is done; use `progress.md`'s START HERE block for what
is next. Test names are the proof, and every one of them was verified failing
before its fix.

| Finding | Status | Where |
| :-- | :-- | :-- |
| C1 TUI confirm crashes | FIXED — one shared `turn.resolve_pending` for both UIs | `tests/test_tui_confirm.py`, ADR-069 |
| H1 unaudited dispatches + searches | FIXED — schema-walking contract test | `tests/test_audit_contract.py` |
| H2 orphaned `_pending` on TTS failure | FIXED — arming requires delivery | `tests/test_confirm_lifecycle.py`, ADR-069 |
| H3 barge-in eats the command; interrupted speech in history | FIXED — `_speak` reports delivered-or-not | `tests/test_confirm_lifecycle.py`, ADR-069 |
| H4 double FSM transition in no-STT mode | FIXED — caller owns the transition | `test_no_stt_mode_returns_to_idle_silently` |
| H5 trigger-arm TOCTOU | FIXED — acceptance arms, detection does not | `tests/test_trigger_arming.py`, ADR-071 |
| H6 blocking work on the event loop | FIXED — four sites threaded (five, with the TUI's copy) | `tests/test_event_loop_blocking.py` |
| H7 cancel picks the wrong reminder | FIXED — **and the branch turned out to be unreachable**; see ADR-070 | `tests/test_audit_contract.py` |
| H8 journald debug leak | FIXED — `NoDiskFilter` on the console handler too when `JOURNAL_STREAM` is set; verified through real journald (`systemd-run --user`) pre- and post-fix, not only in pytest | `tests/test_log_no_disk.py`, spec FR-57b |
| M-P1 expiry resets a live capture | FIXED — expiry never touches the FSM | `test_confirm_expiry_does_not_reset_a_live_capture` |
| M-A2 cap-timer leak on re-arm | FIXED | `test_rearming_the_cap_cancels_the_previous_handle` |
| M-A3 `vad=None` resurrects the 15 s cap | FIXED (conservative half-step) — refuse + warn once; OQ-36 raised | `test_arming_without_a_vad_is_refused_and_logged_once` |
| M-T2 WAL sidecar perms | FIXED — **stated mechanism did not reproduce**; see below | `tests/test_db_integrity.py` |
| M-T3 partial-migration crash loop | FIXED — one transaction + idempotent DDL | `tests/test_db_integrity.py` |
| M-T9 reminders never pruned | FIXED (ADR-068b) | `test_retention_sweeps_terminal_reminders_only` |
| M-L9 (part) `check_database` cannot fail on perms | FIXED — perms read BEFORE the DB is opened | `test_selftest_checks_the_sidecar_perms` |
| L25 selftest docstring lists 7 checks, 8 run | FIXED 2026-08-29 while verifying docs against the tree | `friday/selftest.py` module docstring |
| *(not a finding)* declined confirms unaudited | CHANGED by decision, not defect — ADR-072 answers OQ-37: a decline now writes a `declined` row | `tests/test_audit_contract.py` |
| M-A1 unguarded PortAudio callbacks | FIXED — one shared `CallbackGuard`; consecutive-failure count, `E_AUDIO_DEAD` at ERROR, wake detector disabled, capture degraded-but-alive | `tests/test_callback_guard.py`, spec FR-6a |
| M-T1 `timeout_s` dead config + false process-group-kill docstring | FIXED — `ToolSpec.detach` splits launch from command; commands are bounded + group-killed + exit-code judged, launches keep ADR-043 and stop saying "Opened" | `tests/test_executor_timeout.py`, ADR-073 |
| M-L1..L4, M-L5..L10, M-P2..P4, M-A4..A8, all LOWs | **OPEN** — Steps 10–12 and the triage tail | progress.md |

**Status line, 2026-08-29 (Step 9):** the CRITICAL and **all eight HIGHs** are
closed. Everything still open is MEDIUM or LOW, and none of it is a disclosure
defect — the remaining work is robustness (Steps 10–12 and the triage tail). Note that Step
9's real-path run found a defect **this audit missed entirely**: both Hyprland
tools have never worked on this machine (OQ-38). The audit read the executor
and the registry and never ran them against the compositor.

### Corrections this execution pass found in the report itself

1. **M-T2's mechanism is wrong for this machine.** The report says
   `PRAGMA journal_mode=WAL` creates the sidecars before the `chmod`. Measured
   2026-08-29 under `umask 000`: it does not — SQLite creates `-wal`/`-shm` at
   the first *write transaction*, which is `_migrate`, already after the chmod.
   Both sidecars come out `0600` with and without the reordering. The reachable
   exposure is a WAL left by an **unclean** shutdown (routine here, given
   `Restart=always`): pre-fix, a `-wal` chmod-ed to `0644` after `kill -9`
   stayed `0644` across every subsequent restart. The fix is right; the stated
   cause was not.

2. **H7 understated the damage.** The wrong-reminder pick was real, but the
   branch containing it was **unreachable**: `PARAM_SCHEMA["cancel_reminder"]`
   required a non-empty `id`, and reminder ids (`rem_<hex8>`) are never spoken,
   shown, or put in the prompt — so the planner could not supply one. Every
   route ended in "No active timer to cancel." or "I didn't understand."
   `cancel_reminder` had never worked at all. Deleting the param is ADR-070.
   Worth noting for future audits: the report checked the *ordering* bug inside
   the function without checking whether the function could be reached.

3. **A `_say_now` hazard the report did not list.** With a raising speaker
   (H2's premise), `_fail_speak` called `_say_now`, which raised again *inside*
   the exception handler — killing the turn task mid-unwind and stranding the
   FSM in ERROR, so every later trigger was rejected. Fixed with H2 in Step 2.

4. **The dead-code table shrank by two.** `PendingAction` is now genuinely
   imported in `daemon.py` (retiring the F821 annotation item), and
   `habits.describe_action`'s `web_search` branch is reachable now that search
   writes audit rows — it is kept and tested, as ADR-067b directed.
