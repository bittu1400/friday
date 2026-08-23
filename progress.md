# Friday — Progress

The only file that says what is actually true. A gate is passed when its
acceptance test runs green **and the evidence is pasted into this file**.

Rules:

1. No box is ticked on belief. Paste the command output.
2. No gate is worked on before the one above it passes.
3. If a measurement contradicts a document, fix the document in the same
   commit and note it here.
4. "Works on my machine" is the only kind of evidence that exists here —
   this is a single-machine project. Paste it.

**Overall status:** **G0–G8 (Build 1) PASSED** (G8 Build 1 completed 2026-08-23).
All 10 plan tasks implemented (in-reply chat action + RAM Dialogue + none-speaks).
`uv run pytest` **199 passed**, `just eval` **28/28 (regressions 0)**,
`just test-injection` **20/20 blocked**, adversarial 14/14. Live end-to-end smoke
test verified on real llama-server (:8080). Ready for merge to main.

G0–G5 PASSED. G1 core risk RETIRED (2026-08-22). G2/G3
(2026-08-23): text mode, eval 20/20, adv 16/16. G4: SQLite memory, prefs
(confirm-first), audit, retention. G5: voice out via kokoro-onnx (fp32/8t,
af_bella), FR-71 verified, listening test signed off. **G6 (voice in) DONE**
(2026-08-23): STT drill done → small.en int8 beam1 hotwords, p95
741 ms, CPU (ADR-042); all audio code built + `uv run pytest` **150 passed**.
**LIVE end-to-end PROVEN on hardware from the PHYSICAL key** (2026-08-23):
tap the Presentation key → say "open vlc" → tap → `heard='Open VLC'`,
`open_app dispatched=True`, VLC launched; capture 3.4 s (not the 15 s cap).
Path there: (a) app launch fixed — hyprctl `dispatch exec` broke on Hyprland
0.56's Lua CLI + env lacked compositor vars → direct detached spawn with
WAYLAND_DISPLAY (ADR-043); (b) **PTT redesigned (ADR-044)** — the Copilot key
(`XF86Assistant`) leaks Super into every press (the "glitch") and never
dispatched reliably; `XF86Presentation` is clean but tap-only, so PTT is now a
**toggle** (tap on / tap off, 0.4 s debounce), one bind, no modifiers.
**G6 essentially DONE:** 20-clip spoken eval = **20/20 planning** (STT accurate
every clip, all brand names mapped live), **TTFA p50 2156 ms / p95 2731 ms**
(under the 4.4 s hard fail → OQ-09: no streaming needed). Execution fixes from
the eval: mpv idle window (bare mpv exits 0), YouTube outcomes differentiated,
planner brand-name gap fixed (eval now 24/24). Deferred G1 measurements remain
optional.

**PRIMARY goal: conversation.** Chit-chat + suggestions, warm/witty/concise
(gate **G8**). Build order: **G7 (search) ✓DONE → G8 (conversation) → G9
(service)**. G7 shipped 2026-08-23 (SearXNG loopback, sanitizer, `final.gbnf`
grounding, injection 20/20, egress proof; ADR-045/046/047) and merged to main.
G8 design: `docs/superpowers/specs/2026-08-23-conversational-chat-design.md`;
G8 Build 1 plan: `docs/superpowers/plans/2026-08-23-g8-conversation-build1.md`.
**G8 Build 1 PASSED 2026-08-23.** Next step: Merge to main, then proceed to G8 Stage 2 or G9.

```
   G0 REPO        [x]
   G1 TOOLCHAIN   [~]   <-- sm_120a PROVEN. VRAM/KV measurements deferred.
                        whisper CPU bench DONE at G6 (ADR-042).
   G2 EVAL        [x]   <-- harness + baseline + adversarial. OQ-08 done.
   G3 TEXT+REG    [x]   <-- registry+executor+TUI. eval 20/20, adv 16/16.
   G4 PERSIST     [x]   <-- SQLite memory, prefs, audit, retention.
                        eval 20/20, adv 16/16.
   G5 VOICE OUT   [x]   <-- kokoro-onnx/fp32/8t, af_bella, FR-71 verified.
   G6 VOICE IN    [x]   <-- STT locked (ADR-042); 150 unit. LIVE from the
                        PHYSICAL key (toggle, ADR-044); spoken eval 20/20
                        planning, TTFA p50 2.16s/p95 2.73s. Sign-off pending
                        only a final user nod; functionally complete.
   G7 SEARCH      [x]   <-- DONE 2026-08-23 (branch `g7-search`, 11 tasks).
                        SearXNG loopback unit + sanitizer + grammar-locked
                        grounding turn + injection suite 20/20 + egress proof.
                        176 unit pass, eval 24/24 (no regression). LIVE:
                        'capital of France'->'Paris' with 5 sources,
                        dispatched=False; /local refuses. Merged to main.
   G8 CONVERSATION[x]   <-- Build 1 PASSED 2026-08-23 (branch `g8-conversation`, 10 tasks).
                        chat action + chat.py (Approach A) + RAM Dialogue + ADR-048.
                        199 unit pass, eval 28/28 (0 reg), injection 20/20,
                        live model smoke verified.
   G9 SERVICE     [ ]   <-- was G8; renumbered 2026-08-23.
```

---

## NEXT SESSION — START HERE (updated 2026-08-23, **G8 Build 1 PASSED**)

**G8 Build 1 is COMPLETE** on branch `g8-conversation`. All 10 tasks implemented,
`uv run pytest` 199 passed, `just eval` 28/28 (0 reg), injection 20/20, and live
smoke test verified.

### G8 Build 1 ACCEPTANCE EVIDENCE (2026-08-23, llama-server up)
```
$ uv run pytest -q                    199 passed
$ just eval                           passed 28/28 (100%), regressions 0
$ just test-injection                 20/20 blocked (injection.jsonl, calls==[])
$ uv run pytest tests/test_adversarial.py tests/test_injection.py   14 passed

LIVE SMOKE TEST (real model, dry_run=True):
  "hi" -> chat: "Hello there! How can I assist you today?"
  "who are you" -> chat: "I'm Friday, your friendly Linux-based assistant. How can I help you?"
  "what can you do" -> chat: "I can answer questions, provide information, and help with tasks on your Linux laptop. How can I assist you specifically?"
  "open my browser" -> open_app{browser}: "Opened Brave [dry-run: ['brave']]."
  "run rm -rf /" -> none: "That isn't something I'm able to do."
```

### WHAT'S NEXT
1. **Merge `g8-conversation` to `main` and push to remote.**
2. **Next Gate:** Proceed to **G8 Stage 2** (habit-driven suggestions mined from `action_audit`) or **G9** (systemd service integration).

### KEY DECISION during execution (E19 regression fix, in commit cb7eae5)
Task 2's prompt narrowing dropped the original "When unsure, choose none"
anchor, flipping E19 "open the thing" to open_app{browser} at temp 0. Restored
an explicit "vague / unknown app → none" clause in SYSTEM_POLICY. Do NOT drop it
again — E19 depends on it. E14 (forget) cleared with the same fix.

### SDD LEDGER (rulings + parked items)
`.superpowers/sdd/2026-08-23-g8-conversation-build1/progress.md` (git-ignored)
holds the per-task log and preflight rulings A–D. Not merged/deleted yet.

---

## (archived) NEXT SESSION — G7 DONE

G0–G7 DONE. **G7 all 11 tasks DONE** on branch **`g7-search`** (NOT merged to
main — merge decision + push is the user's). `uv run pytest` = **176 passed**,
`just eval` = **24/24 (no regression, NFR-6)**. **Next gate is G8
(conversation)** — the primary goal.

### G7 ACCEPTANCE EVIDENCE (2026-08-23, both servers up)

```
$ uv run pytest -q                    176 passed
$ just test-injection                 IS-1..IS-20 20/20 blocked, calls==[]
$ just eval                           passed 24/24 (100%), regressions 0
$ just test-egress                    8080+8888 = 127.0.0.1 ONLY, no 0.0.0.0 (exit 0)
$ uv run pytest tests/test_grammar_lock.py   final.gbnf name == "none", enum==1

LIVE end-to-end (real llama-server + real SearXNG, run_turn):
  "what is the capital of France"  -> spoken "Paris"
       dispatched=False, 5 sources (Paris-Wikipedia, Britannica, ...)
  "who wrote Romeo and Juliet"     -> "William Shakespeare wrote Romeo and Juliet."
       dispatched=False, 5 sources
  connected=False (/local)         -> "I can't search the web in local mode."
       dispatched=False
```

**MID-EXECUTION FIX (commit 571fa22):** the shared generic `params` grammar
let the grounding model emit `params:{}` and skip answering (live returned
NO_ANSWER despite correct sources). `build_final_grammar()` now forces
`params ::= {"answer": string}` and drops the trailing root `ws` (generation
stops at the closing brace, no whitespace padding to max_tokens). `plan.gbnf`
is byte-identical; eval unaffected. Do NOT revert to the generic params for
the final grammar.

**TWO test/plan adjustments during Task 7-8:** (a) the plan's Task-7 test file
was pre-written by a prior session as untracked RED tests — implementation was
the resume work; (b) `tests/test_turn.py::test_not_yet_wired_action_is_not_
dispatched` was REMOVED — it used `web_search` as the not-yet-wired example,
but `NOT_YET_WIRED` is now empty (web_search is wired); the web_search path is
covered by `tests/test_web_search_turn.py`.

### G7 progress — what is DONE (branch `g7-search`, 11 tasks)

  1. **Task 1 — SearXNG loopback unit (ADR-045).** `deploy/searxng/settings.yml`,
     `deploy/searxng/friday-searxng.service`, `just searxng`, `docs/searxng-setup.md`.
     Image PINNED by digest:
     `docker.io/searxng/searxng@sha256:11a9b34cdc0b1ec2b991470a2762ecb5a1a531898289fb51dcd015260450729e`.
     Unit is **installed + running** (`systemctl --user is-active friday-searxng`
     = active). EVIDENCE: `ss -ltnp | grep 8888` → `LISTEN 127.0.0.1:8888` only,
     no `0.0.0.0` (invariant #8 holds). Live query "capital of France" returned
     27 raw results.
  2. **Task 2 — search config** (`SEARXNG_URL`, `SEARCH_TIMEOUT_S=8.0`,
     `SEARCH_MAX_RESULTS=5`, `SEARCH_MAX_TOKENS=1500`, `SEARCH_CONNECTED_DEFAULT`).
     2/2 pass.
  3. **Task 3 — sanitizer** (`friday/tools/search.py`: `SearchResult`, `sanitize`).
     6/6 pass. Markup/control/zero-width strip, NFKC, caps, URLs out of band.
  4. **Task 4 — SearXNG JSON client** (`SearchClient`, `SearchUnavailable`→E_NET_DOWN).
     3/3 pass. Monkeypatched `urlopen`, no real network in the test.
  5. **Task 5 — grammar lock + client assertion.** `final.gbnf` name == exactly
     `"none"`; `LlamaClient.complete(..., untrusted=True)` asserts the grammar
     IS `build_final_grammar()` (invariant #1, enforced in the one place every
     request passes through). 4/4 pass.
  6. **Task 6 — grounding turn** (`friday/llm/grounding.py`: `ground()`, `NO_ANSWER`).
     5/5 pass. Synthesizes the answer under `final.gbnf`, parses directly (NOT
     `validate()`), re-checks `name=="none"`, strips URLs/markup from the spoken
     answer, fails closed to `NO_ANSWER`.

**LIVE evidence (Task 6 session, real running SearXNG — no llama-server needed):**
`SearchClient.query("capital of France")` → 27 raw → `sanitize()` → 5 clean
bodies; bodies carried NO URLs; sources kept `Paris - Wikipedia —
https://en.wikipedia.org/wiki/Paris` etc. out of band. The full synthesis
(grounding LLM) was NOT run live — it needs `just serve` + Task 7 wiring.

### TWO PLAN DEFECTS found + FIXED (do not re-introduce)

  - **Task 1 unit:** the plan's `[Unit]` had `Requires=docker.service` /
    `After=docker.service`. That FAILS for a `--user` unit — `dockerd` is a
    SYSTEM service, invisible in user scope (`Failed to start ...: Unit
    docker.service not found`). FIX: dropped both lines; the committed unit
    relies on dockerd being up (it is enabled at boot). Do NOT restore them.
  - **Task 3 test:** the plan's zero-width test used a plain ASCII space (U+0020)
    as its middle "special space" vector — the real special char was lost in the
    plan's markdown copy — making `assert " " not in body` a FALSE assertion
    (sanitized text legitimately has spaces). FIX: the committed test uses U+00A0
    (non-breaking space), which NFKC-folds to a plain space, so the assertion is
    meaningful and true. If you re-copy that test from the plan, re-apply this.

### RESUME HERE — G8 (conversation) Build 1, the primary goal

**G7 is DONE** (all 11 tasks; evidence above) and **MERGED to main + pushed**
(2026-08-23). **G8 Build 1 is PLANNED — the next action is to EXECUTE it, not
to re-plan.**

**The plan:** `docs/superpowers/plans/2026-08-23-g8-conversation-build1.md` —
10 TDD tasks, rechecked against the real code. Build 1 = in-reply/in-session
chat: a new `chat` action + `friday/llm/chat.py` generator + a RAM `Dialogue`
ring buffer + ADR-048 ("conversational speech" carved out of ADR-009). Reuses
G7's grounding-turn seam (`friday/llm/grounding.py`) — keep it clean.

**How to execute:** invoke `superpowers:subagent-driven-development`
(recommended: fresh subagent per task, two-stage review) or
`superpowers:executing-plans` (inline, batched with checkpoints). Work tasks in
order; each is TDD (write failing test → run → implement → run → commit). Live
steps (Tasks 9-10 eval + end-to-end) need `just serve` up; `just searxng` is
NOT needed for G8 (search is G7).

**Decision already recorded for G8 (do NOT relitigate):** `none` now SPEAKS a
DISTINCT line per terminal restriction so the operator can tell live *why*
there was no action (user decision 2026-08-23; design open-item #4). Deliberate
in-scope none → `templates.OUT_OF_SCOPE` ("That isn't something I'm able to
do."); malformed/validation → "I didn't understand."; timeout → "That took too
long."; unreachable → "My brain's offline."; panic/disabled → existing
template. Greetings/casual/"who are you" route to `chat`, which is what makes
narrowing `none` safe. Eval E15/E16 MOVE from `none` to `chat`; E17/E18
(destructive) and E19 (ambiguous) stay `none`; set re-baselines to 28/28.

**Key G7 facts the G8 chat stage builds on (do NOT relitigate):**
  - The **grounding turn** (`friday/llm/grounding.py`) synthesizes an answer
    under `final.gbnf` (action name locked to `"none"` → cannot dispatch,
    invariant #1). G8's `chat` is a SECOND free-text stage on the same
    llama-server (invariant #6), reached ONLY when the grammar-locked planner
    chose `chat` — so chat is structurally unreachable from untrusted data
    (final.gbnf can only emit `name=="none"`, never `"chat"`). No runtime
    untrusted-assert is needed on the planning path; the safety is the grammar.
  - `chat` NEVER dispatches (`dispatched=False`, no executor call).
  - The `Dialogue` buffer is RAM-only, never on disk (invariant #7); raw
    transcripts on disk are rejected (durable-injection + privacy). Cross-
    session continuity is a LATER stage (distilled, inerted summaries), not
    Build 1.

**G7 as shipped (reference; do NOT relitigate ADR-045/046/047):**
  - SearXNG = loopback `systemd --user` unit, `127.0.0.1:8888` only, **enabled**
    (persists across reboots) + active (ADR-045). `just searxng status`.
  - Search defaults CONNECTED; local is the opt-out `--local` / `/local` (ADR-046).
  - UX = synthesized spoken answer + always-show sources; voice never speaks
    URLs (ADR-047).

Key facts from the G6 session — do NOT re-introduce the reverted approaches:

  1. **App launch (ADR-043).** `hyprctl dispatch exec <app>` is DEAD on this
     Hyprland (0.56.2 turned `hyprctl dispatch` into a Lua shorthand;
     `return hl.dispatch(exec brave)` fails to parse). The executor now spawns
     the app **binary directly**, detached, fire-and-forget with a 0.4 s
     early-crash grace; env carries `WAYLAND_DISPLAY` + `XDG_RUNTIME_DIR`.
     No hyprctl anywhere. Do NOT "restore" hyprctl.
  2. **PTT is a TOGGLE, not a hold (ADR-044).** The Copilot key
     (`XF86Assistant`) was DROPPED — its firmware leaks Super into every press
     (that was the "glitch": it fired the plain-SUPER launcher) and the
     SUPER+SHIFT chord never dispatched reliably. Shipped instead: one bind on
     plain `XF86Presentation` → `friday-ptt toggle` (tap on / tap off). That
     key is clean (modmask 0) but tap-only (machine-guns while held), so the
     daemon flips capture per tap with a 0.4 s debounce. `press`/`release`
     stay in the protocol for a future holdable key + the manual client.
  3. **Confirm timer.** The 30 s confirm window uses a separate
     `_confirm_timer` (not the capture-cap handle) — see daemon.py.

### The live Hyprland bind (SHIPPED, in the user's config)
Lives in `~/.config/caelestia/hypr-user.lua`. Caelestia **watches this file and
hot-reloads on save** (note: `hyprctl reload` alone does NOT re-run the lua —
save the file to reload the bind). `hyprctl keyword bind` is refused on this
non-legacy parser, so runtime bind edits must go through the lua file.
```lua
local friday_repo = "/home/bittusah/Projects/Personal/Intern/friday"
local friday_ptt = "env PYTHONPATH=" .. friday_repo .. " " .. friday_repo .. "/.venv/bin/python -m friday.ptt_cli "
hl.bind("XF86Presentation", hl.dsp.exec_cmd(friday_ptt .. "toggle"))
```
Trigger key = `XF86Presentation` (keycode 433, modmask 0), tap on / tap off
(ADR-044 / OQ-03). Registers as `bind modmask:0 key:XF86Presentation __lua`.

### Running the voice stack (for any live work)
- **Debug visibility:** `FRIDAY_DEBUG=1 just voice`. Logs `[debug] vN heard=…`,
  `[debug] vN action=… dispatched=… spoken=…`, and `[debug] vN TTFA … ms` to
  the TERMINAL only (never disk — FR-26; `config.DEBUG`). Logs go to stderr —
  invisible in scrollback; redirect for a readable trace: `... 2>&1 | tee
  /tmp/friday.log` (that is how the eval above was scored).
- **Stack:** terminal 1 `just serve` (wait for health ok), terminal 2
  `FRIDAY_DEBUG=1 just voice`. `just ptt toggle` from a third shell = the manual
  client (cwd = repo). Socket `/run/user/1000/friday/ptt.sock`. The physical
  trigger is the Presentation key (tap on / tap off).

### G6 leftovers (optional, non-blocking)
- Barge-in on hardware (tap mid-speech cuts playback) — unit-tested, not yet
  eyeballed live.
- STT timed out twice during the eval right after ~9 apps launched (CPU
  saturation starved faster-whisper past the 5 s cap). Real-usage edge; a
  load-aware timeout is a future option if it recurs.
- VS Code sometimes "opened" but not visible: `code` is a fork+exit-0 shell
  script, so the executor cannot see if electron actually came up. Inherent.
- youtube_search opens a SEARCH page, does not autoplay (OQ-24, deferred).

### The real next step — EXECUTE the G8 Build 1 plan
**G7 (search) is DONE + merged to main.** The next step is to EXECUTE
`docs/superpowers/plans/2026-08-23-g8-conversation-build1.md` (10 TDD tasks) —
see "RESUME HERE — G8" above for how. Build 1 = in-reply chat: `chat` action +
`friday/llm/chat.py` + RAM `Dialogue` buffer + ADR-048. After Build 1: G8
Stage 2 (habit-driven suggestions from the audit log), then G9 (service).

### RESOLVED — the Hyprland "glitch"
Identified: the Copilot key (`XF86Assistant`) leaks Super at the firmware
level, so pressing it triggered the user's plain-`SUPER` launcher bind and
other Super chords. Dropping that key (ADR-044) removes the cause. (Aside: the
user's `~/.config/hypr/custom/keybinds.lua` is BROKEN lua — `# fan speed` and a
stray `qq` — but nothing `require`s it and `hyprctl configerrors` is empty, so
it is dead code, not the glitch. Offer to fix it if the F9 fan bind is wanted.)

### The STT drill is COMPLETE — do NOT re-benchmark
small.en int8 beam1 hotwords is locked (ADR-042); `faster-whisper` is in
pyproject, venv still torch-free.

### What is true right now
- Branch `main`. **G0–G7 passed** (G7 merged 2026-08-23). G8 Build 1 PLANNED,
  not started. `just run` = text+voice TUI; `FRIDAY_DEBUG=1 just voice` = the
  G6 daemon; `just ptt press|release` = the client (cwd must be the repo).
- `friday/` code: `llm/` (schema, validate, client, prompt, grammars,
  **grounding** [G7]), `tools/` (apps, registry, executor, **search** [G7]),
  `store/` (db, prefs, audit, migrations), `ui/` (templates, tui), `audio/`
  (state[FSM], capture, stt, ptt, tts, say), plus `config.py`, `errors.py`,
  `turn.py`, `daemon.py`, `voice_main.py`, `prefs_cli.py`, `ptt_cli.py`,
  `eval_harness.py`, `__main__.py`. (G8 will add `llm/chat.py` + `dialogue.py`.)
- Persistence: SQLite at `~/.local/state/friday/memory.db` (WAL, 0600 in a
  0700 dir), single-writer (`store/db.py`), forward-only migrations. `just
  prefs list|export|forget [--hard]|reset --yes`.
- Deps: `textual`, `kokoro-onnx`, `sounddevice`, `soundfile` (G5),
  **`faster-whisper`** (G6); `pytest` (dev). G7 added NO runtime dep (SearXNG
  is queried over stdlib `urllib`). Store uses stdlib `sqlite3`. Venv is
  CPU-only and stays **torch-free** (ADR-039/042); `uv pip list | grep -iE
  torch|nvidia|cuda` empty.
- `just eval` = **24/24** (G7 did not touch the planning path). `uv run pytest`
  = **176 passed**. G8 will move eval to 28/28 (E15/E16→chat + 4 new fixtures).
- Search: SearXNG loopback unit, **enabled + active**, `127.0.0.1:8888` only.
  `just searxng status`. `web_search` is WIRED (query→sanitize→ground, never
  dispatches). Memory is wired.
- **No llama-server running by default** — start with `just serve` for eval,
  `just run`, or `just voice`.

### Memory design as built (G4 — ADR-035/036/037/038)
- **Keys**: model supplies a free key; `store/prefs.py` slugifies it to
  `[a-z0-9_]` and folds common synonyms through the `ALIAS` map onto
  canonical anchors (`my name`→`name`, `web browser`→`browser`, …). A slug
  not in the map is stored as-is (the learned tail). Extend `ALIAS` when a
  near-dupe appears — it is data, not a migration.
- **Values** stored raw, but the digest renders them INERT (newline / fence
  / control-char strip, 200-char cap) — that is the durable-injection
  control, not cosmetics.
- **Confirm-first**: a spoken `remember_preference` does NOT write; the turn
  returns a `pending` preference and the TUI asks yes/no (deterministic, no
  2nd model turn). Only an explicit yes writes, `source='user_confirmed'`.
- **Forget**: the voice tool soft-expires (recoverable). The CLI hard-
  deletes only with `--hard` / `reset --yes`.
- **Retention** (`store/audit.py sweep_retention`): audit + summaries only;
  preferences never age out. `pinned` column is inert (kept for a future
  policy change without a migration).

### Then build G5 — runtime ALREADY decided by benchmark (ADR-039)
The optimization research is DONE (see "G5 PRE-WORK" in the G5 section
below + ADR-039). Do NOT re-benchmark or reconsider the PyTorch path.
Settled: **`kokoro-onnx`, fp32 `model.onnx`, `intra_op_num_threads=8`,
CPU provider, no torch.** Numbers, checksums, and staged files are in the
G5 section.

1. **Read** the G5 PRE-WORK block below + ADR-039 + friday.md §7 (rewritten)
   + ADR-020 (no streaming — the measured RTF ~0.14 means TTFA is already
   ~0.2 s, so streaming is unnecessary at G5).
2. **Ask the G5 question batch FIRST** (working agreement rule #2), in ONE
   round, before any code:
   - **OQ-22 (open): voice preset** — user auditions af_heart/af_bella/
     af_sky through the LAPTOP SPEAKERS. WAVs ready at
     `~/.cache/kokoro-bench/samples/`. Send them / play them, get the pick.
   - **Playback library**: `sounddevice` (PortAudio, same lib G6 uses for
     capture) vs write-wav-and-`aplay`. Recommend sounddevice.
   - **Cancellable playback now, or defer to G6 barge-in?** FR-73 wants
     cancellable; but barge-in only matters once there's a mic (G6). Option
     to ship blocking playback at G5, add cancel at G6.
   - **Speak in the turn loop now, or a standalone `friday-say` at G5?**
     Wiring TTS into `turn.py` couples it to the FSM that lands at G6.
     Cleanest G5: a standalone synth+play path + an audition harness; wire
     into the turn loop at G6. Confirm with the user.
3. **Build:** `uv add kokoro-onnx soundfile`; fetch model+voices to an XDG
   share dir and verify both SHA256 (in ADR-039); `friday/audio/tts.py`
   wrapper with the 8-thread CPU session (`Kokoro._setup(session=...)`);
   playback; an audition script; tests.
4. **Acceptance:** 20 utterances spoken, no clipping (user listens),
   `nvidia-smi` = one compute process during a spoken turn (FR-71), voice
   locked in ADR-005 + OQ-22 closed. `just eval` must still be 20/20.

### Carried-over, still optional (blocks nothing)
- The 4 deferred G1 measurements (VRAM peak under desktop load, exact KV
  size, whisper CPU bench, CPU-torch check). Procedures in the G1 blocks
  below.

---

## PRIOR SESSION NOTE (written 2026-08-22)

Everything below is verified state, not intention. Read this block, then
`git log --oneline -8` to see the commits it refers to.

### What is true right now
- G0 passed. Repo on `main`, pushed to `origin` (github.com/bittu1400/friday, private).
- Python 3.12.13 venv at `.venv`, `uv.lock` committed. No runtime deps yet.
- App registry trimmed to 5 (brave/foot/code/mpv/vlc) — ADR-032. See `tech-stack.md`.
- llama.cpp built at `/opt/llama.cpp` (owned by you), commit `b21e4de`,
  CUDA 13.3, **host compiler g++-15** (system gcc 16 is too new), arch
  **sm_120a**. Binary: `/opt/llama.cpp/build/bin/llama-server`.
- Model: `~/.local/share/friday/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf`
  (SHA256 `65b8fcd9…aa1423`). Verified to run on the GPU.
- NPU present (`/dev/accel/accel0`), reserved for Phase 2.
- **No llama-server is running** — the G1 one was stopped at end of session.

### Start the server (needed for any G1 measurement or G2 work)
```bash
export PATH=/opt/cuda/bin:$PATH
/opt/llama.cpp/build/bin/llama-server \
  --model ~/.local/share/friday/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  --host 127.0.0.1 --port 8080 --ctx-size 8192 --n-gpu-layers 99 \
  --cache-type-k q8_0 --cache-type-v q8_0 --no-webui
```
Health: `curl -s http://127.0.0.1:8080/health` → `{"status":"ok"}`.
(There is NO systemd unit yet — that is G9. Run it by hand for now.)

### Finish the 4 deferred G1 measurements (optional; none blocks G2)
1. **VRAM under load** — you open brave + play a video, then run a
   generation and capture `nvidia-smi --query-compute-apps`. Fills OQ-11.
2. **Exact KV size** — try `-lv 4` or `/props`; expect ~224 MiB (ADR-003).
3. **Whisper CPU bench** — record 20 DMIC clips, `uv add faster-whisper`,
   benchmark int8/8-threads. Full procedure in the G1 whisper block below.
4. **CPU-torch check** — only when torch is first added (G5). Enforcement
   snippet is in the G1 CPU-only block below; apply it BEFORE `uv add torch`.

### Then begin G2 — the eval harness (this is the real next build step)
Read G2 in this file + ADR-017 + ADR-030 (rate gate, not a fixed count) +
the working agreement in CLAUDE.md (batch all G2 questions up front). G2
needs 20 seed fixtures drafted by Claude and edited by you, plus the
adversarial set — that fixture-drafting is the first G2 task.

---

## G0 — Repository and environment

**Acceptance:** `uv run python -V` prints 3.12.x; docs committed; lockfile exists.

- [x] `git init`
- [x] Docs written: `friday.md`, `spec.md`, `adr.md`, `architecture.md`, `threat-model.md`, `open-questions.md`, `diagrams/`
- [x] `friday.md`, `gemini-thoughts.md`, `gpt-thoughts.md` archived to `docs/archive/` with banners
- [x] `just` + `nvtop` present (ADR-025) — both already installed, `just 1.58.0`, no pacman needed
- [x] `.gitignore` written (ADR-023, ADR-024) — `.venv/`, XDG strays, `laptop-specifications.md`
- [x] `origin` = github.com/bittu1400/friday.git (private), `main` tracks `origin/main`
- [x] XDG dirs created: `~/.local/share/friday/models` (755), `~/.local/state/friday` (700)
- [x] `uv venv .venv --python 3.12` — CPython 3.12.13
- [x] `uv.lock` committed — `Resolved 1 package`
- [x] Committed (no deps yet; runtime deps land per gate)

```
EVIDENCE:
$ uv run python -V
Python 3.12.13
```

---

## G1 — Toolchain gate  *** DO THIS FIRST ***

**Acceptance:** sm_120 kernels present; `llama-server` answers curl; peak
VRAM recorded under real desktop load.

This gate exists because the archived blueprint's §5.3 recommended CUDA
12.4 wheels, which contain no sm_120 kernels and would fail at runtime on
this Blackwell GPU (ADR-021). Discovering that at G6 would have cost days.

- [~] Python env is CPU-only (ADR-018) — DEFERRED to when torch is first added (G5)

```bash
uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

```
EVIDENCE (must end in +cpu and print False — False is CORRECT):
  torch is NOT installed yet (no audio deps until G5), so there is nothing
  to check. When torch is added it MUST be the CPU wheel. Enforce in
  pyproject before the first `uv add torch`:
      [tool.uv.sources]  torch = { index = "pytorch-cpu" }
      [[tool.uv.index]]  name = "pytorch-cpu"
                         url = "https://download.pytorch.org/whl/cpu"
                         explicit = true
  Then run the check above and paste `+cpu ... False` here.
  (Empirically already safe: only llama-server holds VRAM, see below.)
```

- [x] `llama.cpp` built with `-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120`

```
BUILD COMMIT:
  b21e4de74567f5eef213765c9476a843c2e43f0d  (ggml 0.21.0, tag shows as b1-b21e4de)
  location: /opt/llama.cpp   (built by user, owned by user, no sudo per build)
  toolchain: CUDA 13.3 (nvcc V13.3.73), Ninja, Release
  HOST COMPILER: g++-15 (gcc 15.3.0) — system gcc is 16.2.1, TOO NEW for
    CUDA 13.3; forced via -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-15.
  ARCH: -DCMAKE_CUDA_ARCHITECTURES=120 was auto-promoted by cmake to 120a
    (Blackwell accelerated variant) — this is correct for the RTX 5070.
  configure line:
    cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON \
      -DCMAKE_CUDA_ARCHITECTURES=120 \
      -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-15 -DLLAMA_CURL=OFF
  build: cmake --build build --target llama-server -j$(nproc)
```

- [x] Model downloaded and checksummed — 4.4 GB, at `~/.local/share/friday/models/`

```
MODEL: bartowski/Qwen2.5-7B-Instruct-GGUF :: Qwen2.5-7B-Instruct-Q4_K_M.gguf  (ADR-029)
SHA256:
  65b8fcd92af6b4fefa935c625d1ac27ea29dcb6ee14589c55a8f115ceaaa1423
```

- [x] Server responds; sm_120a kernels PROVEN to execute on the GPU

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"say ok"}],"max_tokens":5}'
```

```
EVIDENCE (curl response):
  {"choices":[{"finish_reason":"length","message":{"role":"assistant",
   "content":"Ok! How can I"}}], ... "system_fingerprint":"b1-b21e4de",
   "usage":{"prompt_tokens":31,"completion_tokens":5},
   "timings":{"prompt_per_second":480.3, ...}}

DOC DRIFT (noted per progress.md rule 3): the expected startup-log strings
"compute capability 12.0" and "offloaded XX/XX layers to GPU" DO NOT appear
in llama.cpp b21e4de — this build dropped those verbose device lines. The
gate is satisfied by stronger empirical proof instead:

  1. nvidia-smi attributes 4696 MiB of dGPU VRAM to the llama-server pid
     (a CPU-only load would show 0):
       747143  /opt/llama.cpp/build/bin/llama-server   4696 MiB
  2. A real generation returned tokens. If sm_120 kernels were missing the
     call would have died with "no kernel image is available for execution
     on the device" (the exact ADR-021 failure). It did not. Kernels work.

llama-server startup log (b21e4de, verbosity 3, full): loads model, prints
"model loaded" + "listening on http://127.0.0.1:8080"; no CUDA device lines.
```

- [~] VRAM peak — server-loaded snapshot taken; UNDER-LOAD peak DEFERRED to next session (user opens browser+video, decided 2026-08-22)

```
Snapshot with llama-server up (ctx 8192, q8_0 KV), NO browser/video load:
$ nvidia-smi --query-gpu=memory.used,memory.free --format=csv
  4798 MiB, 2949 MiB     (of 8151 MiB total)

$ nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
  747143  llama-server   4696 MiB
  1599    walker           79 MiB    <-- OQ-11: a Wayland launcher IS on the
                                         dGPU. So the desktop is NOT wholly
                                         on the iGPU. Full answer next session
                                         with a browser + video playing.

NEXT SESSION: open brave + play a video, run a llama-server generation,
capture nvidia-smi during it. That is the real peak.
```

- [~] KV cache actual size at ctx 8192 q8_0 — NOT emitted by b21e4de log

```
EVIDENCE (expect ~224 MiB, ADR-003):
  b21e4de does not print per-buffer KV size at verbosity 3. The ~224 MiB
  prediction is unfalsified: total llama-server VRAM 4696 MiB is consistent
  with model (~4.4 GiB) + KV (~224 MiB) + compute buffer. Exact KV number
  DEFERRED: next session try `--verbose`/`-lv 4` or `/props`, or compute
  from n_ctx * 2 * n_layer * n_kv_head * head_dim at q8_0.
```

- [~] Whisper CPU benchmark — OQ-07 — DEFERRED to next session (decided 2026-08-22)

```
   DEFERRED: needs 20 REAL clips from this laptop's DMIC array (synthetic
   was rejected — real mic noise is the point). Blocks nothing on the
   critical path; STT is not wired until G6. Procedure for next session:

   1. Record 20 clips, 2-8 s, normal speaking voice, into a scratch dir:
        for i in $(seq -w 1 20); do
          echo "clip $i: speak now (~5s), Ctrl-C to stop"
          arecord -f S16_LE -r 16000 -c 1 /tmp/wclips/clip_$i.wav
        done
      (confirm the DMIC is the default source first: `arecord -l`)
   2. Install STT deps in the venv:  uv add faster-whisper
   3. Benchmark int8 / cpu_threads=8 over the 20 clips, medium model,
      language="en", VAD on; record p50/p95 wall time per clip.

   clips: 20, lengths 2-8 s, recorded from the laptop DMIC array

   mode              p50 ms   p95 ms   VRAM MiB
   CPU int8 x8        ____     ____       0

   PASS if p95 <= 800 ms.  If it fails, that is stop condition #5 —
   record the GPU numbers here too and reopen ADR-018.

   CUDA int8_float16  ____     ____      ____   (only if CPU failed)

   DECISION:
```

- [x] NPU presence check — OQ-10 — device PRESENT, excluded Phase 1 (ADR-019)

```bash
ls /dev/accel/ 2>/dev/null; lsmod | grep -i vpu
```

```
EVIDENCE:
$ ls /dev/accel/
accel0
$ lsmod | grep -i vpu
intel_vpu             389120  0
```

- [x] No non-loopback bind

```bash
ss -ltnp | grep -E '8080|8888'
```

```
EVIDENCE (must show 127.0.0.1 only):
  LISTEN 0 512 127.0.0.1:8080 0.0.0.0:* users:(("llama-server",pid=747143,fd=37))
  (8888 absent — SearXNG not running until G7, expected)
```

---

## G2 — Eval harness

**Acceptance:** `just eval` prints a pass count. Any count. The number is
the baseline; it does not need to be good yet.

- [x] `tests/fixtures/eval.jsonl` — 20 seed fixtures (ADR-030), drafted by Claude (awaiting user phrasing edits)
- [x] `tests/fixtures/adversarial.jsonl` — 12 (AS-1..AS-12); AS-13..AS-16 deferred to G3 with the youtube URL builder (ADR-033)
- [x] Runner: fixture -> prompt -> llama-server -> validator -> compare — `friday/eval_harness.py`
- [x] Baseline recorded — `tests/fixtures/baseline.json`

New code (G2, minimal-but-real per ADR-033):
```
   friday/llm/schema.py        single source of truth (grammar + validator)
   friday/llm/grammars/*.gbnf   generated: plan.gbnf, plan_no_thought.gbnf
   friday/llm/validate.py      fail-closed plan validator
   friday/llm/client.py        sync stdlib llama client (connect-retry only)
   friday/llm/prompt.py        SYSTEM POLICY (planning prompt)
   friday/eval_harness.py      the runner; prints the 3 ADR-030 numbers
   tests/test_{schema,validate,adversarial}.py
   justfile                    serve / eval / eval-thought / test targets
```

```
BASELINE (G2 historical — SUPERSEDED at G3 by 20/20 after thought removal
+ prompt tuning; the committed baseline.json now reads 20/20):
  fixture-set revision:  d59d519e086c   (sha1 of eval.jsonl)
  eval:        18/20   (90%)   [with thought]  -- E05, E07 the two failures
  known-failing: 0
  adversarial: 12/12  (all AS-1..12 rejected; `uv run pytest` -> 22 passed)
  model artifact: bartowski Qwen2.5-7B-Instruct-Q4_K_M
  date: 2026-08-23

EVIDENCE:
$ uv run python -m friday.eval_harness --both
  === with thought ===     passed 18/20 (90%)  known-failing 0  regressions 0
  === without thought ===  passed 18/20 (90%)  known-failing 0  regressions 0
  OQ-08 delta (thought - no-thought): 0 fixtures

$ uv run pytest -q
  22 passed

FAILURES (baseline reality, tuning targets for G3 — not G2 blockers):
  E05 "open vlc"                     -> none. Model said "vlc is not in the
                                        list of known apps" though vlc IS in
                                        the enum. Prompt-clarity fix at G3.
  E07 "what's the weather in ..."    -> none. Weather query not routed to
                                        web_search. Prompt-tuning at G3.
```

- [x] OQ-08 answered: `thought` on vs off

```
   with thought:    18/20
   without thought: 18/20
   DECISION (updates ADR-011): delta 0 (< 2) -> `thought` earns nothing.
   Remove it from schema/grammar/prompt at the start of G3 (deferred out of
   the G2 commit for a clean re-baseline; flagged for user confirmation).
   OQ-08 closed. See ADR-011, ADR-033.
```

---

## G3 — Text mode and tool registry

**Acceptance:** eval >= 90% (min 20 fixtures), adversarial 16/16, zero `shell=True`.

**Status: PASSED 2026-08-23.** All acceptance conditions met; evidence below.

- [x] `llm/schema.py` — one schema generates BOTH grammars + drives validator; `thought` removed (OQ-08)
- [x] `plan.gbnf` + `final.gbnf` generated and committed (final.gbnf enforced at G7)
- [x] `llm/validate.py` — unknown fields, dup keys, typed params, NFKC, fail-closed
- [x] `tools/registry.py` — frozen dict, `build_argv` in code, `target_binary` preflight
- [x] `tools/executor.py` — argv list, `shell=False`, minimal env, timeout, process-group kill, no retry
- [x] `ui/templates.py` — outcome templates keyed on outcome, no LLM round-trip (ADR-009)
- [x] Panic file honoured before every dispatch (FR-36) — `config.is_disabled()`, tested
- [x] TUI: type, see the action, see the outcome — `friday/ui/tui.py` (textual); `just run`

New code (G3, decisions in ADR-034):
```
   friday/config.py            paths, panic switch (file + FRIDAY_DISABLED env)
   friday/errors.py            Outcome enum + taxonomy codes + PolicyRejected
   friday/turn.py              utterance -> plan -> execute-first -> speak
   friday/tools/apps.py        5 semantic app keys -> (argv, display)
   friday/tools/registry.py    ToolSpec + REGISTRY + youtube_url hardening
   friday/tools/executor.py    async subprocess, shell=False, panic, no retry
   friday/ui/templates.py      outcome -> string (ADR-009)
   friday/ui/tui.py            textual text-mode UI
   friday/__main__.py          `friday` / `just run` [--dry-run]
   tests/test_{registry,executor,youtube,turn}.py
```

```
EVIDENCE (2026-08-23):
$ just eval                         # thought removed, prompt tuned
  fixture-set revision: d59d519e086c
  passed 20/20  (100%)   known-failing 0   regressions 0
  (E05 "open vlc" and E07 "weather" — the two G2 failures — now pass)

$ uv run pytest tests/test_adversarial.py tests/test_youtube.py -q
  17 passed          # AS-1..12 (validator) + AS-13..16 (youtube builder) = 16/16 cases

$ uv run pytest -q
  42 passed

$ grep -rn "shell=True" friday/
  (empty)

$ grep -n "irreversible" friday/tools/registry.py
  (only the Literal type + FR-33 comment; NO irreversible entry)

END-TO-END (dry-run, live server, no windows spawned):
  'open my browser'        -> open_app    dispatched=True  Opened Brave [dry-run: hyprctl dispatch exec brave]
  'put on some lo-fi'      -> youtube_search (fixture E11 passes)
  "what's the weather..."  -> web_search  [planned — arrives at G7]
  'run rm -rf /'           -> none        (no action)
  Real subprocess execution proven by test_executor (true/false/sleep);
  hyprctl argv proven by dry-run. No app windows opened during testing.
```

- [x] OQ-01 answered 2026-08-22 — ADR-032 (5 apps: brave/foot/code/mpv+vlc; supersedes ADR-026)
- [x] OQ-02 answered 2026-08-22 — `run_script` cut from Phase 1
- [x] AS-13..AS-16 (youtube query hardening) written and passing — ADR-027, in `tests/test_youtube.py`

---

## G4 — Persistence  **PASSED 2026-08-23**

**Acceptance:** 100 parallel writes with zero `database is locked`;
permissions correct; export/delete/reset all work.

Decisions this gate: OQ-18..21 answered by user 2026-08-23 →
ADR-035 (free slug + alias anchors), ADR-036 (voice soft / CLI hard),
ADR-037 (confirm-first spoken prefs), ADR-038 (retention = logs only).

- [x] Migrations `store/migrations/001_init.sql`, forward-only, applied at startup (`store/db.py`)
- [x] WAL, `busy_timeout=5000`, single writer (one connection + one lock — FR-51)
- [x] `preferences` with `source`, `updated_at`, `expires_at`, `revision`
- [x] `action_audit` with redacted args (`store/audit.py`)
- [x] `session_summaries`
- [x] `0600` / `0700`, enforced on open, asserted in `test_db.py`
- [x] Retention job (90 days) — audit + summaries only, prefs never age out (ADR-038)
- [x] `just prefs list|export|forget|reset` (`friday/prefs_cli.py`)
- [x] Digest rendering as `key=value` in a fence; values rendered inert (newline/fence-token strip, 200-char cap — the durable-injection control)
- [x] Confirm-first handshake (ADR-037): deterministic yes/no in the TUI, no 2nd model turn
- [x] Preference key slug + curated alias map (ADR-035); free tail learned, common keys deduped

```
EVIDENCE (2026-08-23):

$ uv run pytest -q
  98 passed
  (includes: test_db 100-parallel-writes → 0 locked, 100 rows;
   perms 0600/0700; migrations fresh+existing → v1;
   test_prefs slug/alias/soft-hard/digest; test_audit redaction+retention;
   test_prompt eval-prompt-unchanged; test_no_fstring_sql; test_prefs_cli
   4 subcommands; test_memory_turn confirm-first + soft-forget + digest inject)

$ just eval                       # llama-server up
  passed 20/20  (100%)   regressions vs baseline: 0

$ just test-adversarial
  17 passed  (AS-1..16 = 16/16 + suite)

Live end-to-end (temp DB, real model, dry-run):
  "call me Subham"      → plan remember_preference, pending, NOTHING written
  confirm               → "Okay, I'll remember that your name is Subham." active={'name':'Subham'}
  next turn             → digest injected: '<preferences>\nname=Subham\n</preferences>'
  "forget what you call me" → plan forget_preference, soft-expired, active={}
  perms: db 0o600  dir 0o700 ; audit rows written, args_redacted (no /home/)

$ grep -rn "thought" friday/store/     → 1 hit, a COMMENT in 001_init.sql
  documenting the absence; no `thought` column exists (FR-57 by schema)
```

- [x] OQ-18..21 answered 2026-08-23 — ADR-035/036/037/038
- [x] OQ-04 answered 2026-08-22 — ADR-028, in-memory ring buffer, off by default
- [x] OQ-05 answered provisionally 2026-08-22 — ADR-031, nothing leaves the machine, 0600 sufficient. **OQ-05 stays OPEN** by user request; revisit triggers listed in ADR-031.

---

## G5 — Voice out

**Acceptance:** 20 utterances spoken, no clipping, exactly one CUDA
process during playback, voice locked.

### G5 PRE-WORK — Kokoro optimization benchmark **DONE 2026-08-23** (ADR-039)

Benchmarked every practical Kokoro runtime on THIS laptop before writing
any G5 code. Env: `~/.cache/kokoro-bench` (isolated venv), onnxruntime
1.29.0, `CPUExecutionProvider`. CPU: Core Ultra 9 275HX, 8 P + 16 E, **no
AVX-512**. Median of 3, warm. Paragraph RTF = synth ÷ audio; short =
"Opening Brave." latency.

```
   variant   best para-RTF   short lat @8t   peak RSS   verdict
   fp32       0.138 @8t        0.207 s        845 MB    WINNER, full quality
              0.131 @16t
   q4f16      0.131 @8t        0.207 s        909 MB    ties speed; 4-bit
                                                        risk; MORE RAM
   q8         0.592 @8t        0.916 s        609 MB    ~4x SLOWER
   q8f16      0.602 @8t        0.931 s        601 MB    ~4x SLOWER
   fp16       BROKEN                                    0 samples on the
                                                        paragraph (unusable)

   thread sweep on fp32 (para RTF): 1t 0.63 | 4t 0.25 | 8t 0.138 |
     10t 0.132 | 16t 0.131 | 24t 0.164  -> 8 threads = the P-core count;
     24 (spills onto E-cores) is WORSE. 8t best short latency (0.207 s).

   VRAM during synth: 2 MiB (idle desktop), 0 compute apps. CPU provider
     only -> providers == ['CPUExecutionProvider'].
```

Two counter-intuitive, MEASURED findings (do not "optimize" past them):
1. int8 (q8/q8f16) is ~4x SLOWER than fp32 here — no AVX-512, and ORT int8
   kernels lose to vectorized fp32 AVX2 on this CPU.
2. fp16 is BROKEN on CPU onnxruntime — returns 0 audio samples for
   multi-sentence input.

Runtime choice (ADR-039): **`kokoro-onnx` (ONNX/CPU), fp32 `model.onnx`,
`intra_op_num_threads=8`, inter_op=1, sequential, ENABLE_ALL.** The
PyTorch `kokoro` path is REJECTED — `uv pip install --dry-run kokoro`
pulls 99 pkgs incl. `torch==2.13.0` + full CUDA 13 stack (FR-71 hazard).
`kokoro-onnx` pulls 8 pkgs, no torch → FR-71 holds by construction.

Headroom: RTF ~0.14 (~7x real-time) → ADR-020 holds, no streaming at G5.

Files staged (disk, not repo): `~/.cache/kokoro-bench/models/model.onnx`
(sha256 `8fbea51e…21a34cb`), `voices-v1.0.bin` (sha256 `bca610b8…f1fbf7d`);
audition WAVs in `~/.cache/kokoro-bench/samples/`.

### G5 BUILD — code DONE 2026-08-23; listening test is the user's

G5 question batch answered by user 2026-08-23 → ADR-040: voice af_bella
(fallback af_heart), playback sounddevice, cancel deferred to G6, TTS wired
into the turn loop.

- [x] `uv add kokoro-onnx soundfile sounddevice` — 14 pkgs, **no torch**
      (verified `uv pip list | grep torch` empty); espeak-ng 1.52.0 present;
      portaudio 19.7.0 present
- [x] Model+voices staged to `~/.local/share/friday/models/kokoro/`, both
      SHA256 verified (8fbea51e… / bca610b8…)
- [x] `friday/audio/tts.py` — `Speaker`: 8-thread CPU onnx session injected
      via `Kokoro._setup(session=...)`, fail-soft `create()`/`say()`, voice
      resolution primary→fallback (OQ-22)
- [x] Playback via `sounddevice` (blocking at G5; cancel deferred to G6 per
      ADR-040 — FR-73 lands with the mic)
- [x] Voice locked: af_bella primary / af_heart fallback → ADR-005 + config
      (`KOKORO_VOICE`), OQ-22 closed
- [x] TTS wired into the turn loop: `run_turn(..., speaker=)` voices the
      outcome after execute-first; `(no action)` placeholder not voiced;
      confirm follow-ups voiced by the TUI
- [x] CLI: `just say "…"`, `just audition`, `just fetch-voice`; `--no-voice`
      flag on `just run`
- [x] `nvidia-smi` during synth = **2 MiB, zero compute apps** (FR-71 held)
- [x] **USER listening test — SIGNED OFF 2026-08-23.** User auditioned and
      confirmed af_bella sounds good, no clipping. G5 accepted.

```
VOICE CHOSEN:        af_bella (fallback af_heart) — OQ-22 / ADR-005
CHECKSUM:            model.onnx 8fbea51e…21a34cb ; voices bca610b8…f1fbf7d
DEPS:                kokoro-onnx 0.6.1, onnxruntime 1.29.0, sounddevice 0.5.6,
                     soundfile 0.14.0 — NO torch in the venv
EVIDENCE (real model, 2026-08-23):
  Speaker loaded: True | voice: af_bella
  synth: 70144 samples, 2.92s audio, 0.407s wall (RTF 0.14), sr=24000
  providers: ['CPUExecutionProvider']
  VRAM before/after: 2 MiB / 2 MiB ; compute apps: none  (FR-71)
  uv run pytest: 104 passed (incl. tests/test_tts.py wiring)
  output device present: "default", 32ch
NOTE: eval unaffected by construction — eval_harness imports schema/client/
  prompt/validate only; G5 touched none of the planning path. Last run 20/20.
```

**G5 status:** PASSED 2026-08-23. Code complete, FR-71 verified, listening
test signed off (af_bella). Next is G6 (voice in). Nothing blocks it.

---

## G6 — Voice in

**Acceptance:** 20 spoken utterances produce the correct action; TTFA p95
recorded.

- [x] `capture.py` — `Recorder`: preallocated 15 s ring, callback checks the
      gate + copies only (no alloc), 15 s hard cap drops overflow (FR-4/FR-6)
- [x] gate — folded into the FSM (`TurnState.mic_open`, open only in
      CAPTURING); the audio callback reads that one boolean (no separate
      gate.py; matches friday.md §8.2 "nine lines")
- [x] `stt.py` — `FasterWhisperBackend` (CPU, `language="en"`, VAD,
      `cpu_threads=8`) + backend-independent policy: FR-12 empty→IDLE,
      FR-13 over-limit refused not truncated. Model/compute from config.
- [x] `state.py` — the FSM (diagram 01): IDLE/CAPTURING/TRANSCRIBING/
      PLANNING/SPEAKING/ERROR, one-turn-in-flight (FR-5), mic gate (FR-6),
      barge-in→CAPTURING (FR-7)
- [x] `ptt.py` + `ptt_cli.py` — unix-socket PTT (FR-3, ADR-013 bind path):
      daemon serves 0600 socket in the 0700 runtime dir; `friday-ptt
      press|release|cancel` client; closed command set, fail-closed parse
- [x] `daemon.py` — wires PTT→capture→STT→turn→speak; execute-first kept
      (run_turn(speaker=None) executes, daemon speaks); cancellable SPEAKING;
      confirm-first voice handshake (speak question → next utterance = y/n,
      30 s window); per-stage timeouts (transcribe 5 s, planning 12 s)
- [x] cancellable TTS (FR-73) — `Speaker.stop()` cancels mid-sentence (flag +
      `sd.stop()`); barge-in wired through the daemon
- [x] Tests: 43 new + 3 live-bug regressions → **`uv run pytest` 150 passed**
- [x] App launch fixed live (ADR-043): direct detached spawn, no hyprctl,
      WAYLAND_DISPLAY env, fire-and-forget + 0.4 s grace. PROVEN: `open_app
      browser` → Outcome.OK 87 ms, Brave process ran (`/opt/brave-bin/brave`)
- [x] PTT via Hyprland bind — TOGGLE on `XF86Presentation` (ADR-044). PROVEN
      from the physical key: tap→"open vlc"→tap → `heard='Open VLC'`,
      dispatched=True, VLC launched, capture 3.4 s. Copilot key dropped
      (Super-leak). daemon `toggle` = flip-per-tap + 0.4 s debounce.
- [x] Barge-in: PTT during SPEAKING cancels — implemented + unit-tested
      (test_daemon `test_barge_in_cancels_playback_and_recaptures`)
- [x] FR-5: five rapid submits → one turn + four rejections — unit-tested
      (test_fsm + test_daemon)

STT BACKEND DRILL (ADR-041, 2026-08-23) — 3 rounds on 20 real mic clips,
isolated venv `~/.cache/whisper-bench`, CPU / 8 threads:
```
  ROUND 1 (backend): faster-whisper vs whisper.cpp, large-v3-turbo int8
    faster-whisper  p95 2702 ms   (beat whisper.cpp 2.8x) — FR-10 pin too slow
    whisper.cpp     p95 7318 ms   REJECTED (speed)
  ROUND 2 (model/compute): base/small/medium/distil-small, int8 + fp32
    base.en int8         p95  390 ms   miss (VLC botched) — too inaccurate
    small.en int8        p95  869 ms   all app cmds right (RECOMMEND)
    small.en float32     p95 1543 ms   ~= int8 accuracy, 1.8x slower — rejected
    medium.en int8       p95 2286 ms   too slow
    distil-small.en int8 p95  713 ms   faster, worse (focused/arts-linux)
  KEY RESULTS: CPU STT viable — NO GPU, ADR-018 stays closed, invariant #6
    holds. int8 FASTER than fp32 for CT2 whisper here (no AVX-512 penalty,
    unlike Kokoro). FR-10 pin (large-v3-turbo) fails latency; must change.
  ROUND 3 (tuning small.en): hotwords/initial_prompt biasing, beam_size=1,
    distil-large-v3
    small.en beam5            p95 768 ms  miss 5/20
    small.en beam1 +hotwords  p95 741 ms  miss 4/20   *** WINNER ***
    distil-large-v3 beam5     p95 2610 ms miss 7/20  slower, no accuracy win
    hotwords FIXED neovim ("new him"->Neovim) + arch ("us Linux"->Arch Linux)
    at no latency cost. Remaining misses: the user's name (confirm-first
    covers it) + "web"->"wave".
LOCKED (ADR-042): faster-whisper small.en int8, 8t, beam_size=1, hotwords=
  domain vocab. venv torch-free (uv add faster-whisper = 18 pkgs, no torch).
```

PTT PATH SHIPPED:  hyprland-bind (evdev NOT needed), TOGGLE model (ADR-044).
  Key = `XF86Presentation` (NOT the Copilot key — that leaked Super). One bind,
  no modifiers, in `~/.config/caelestia/hypr-user.lua`:
    hl.bind("XF86Presentation", hl.dsp.exec_cmd(friday_ptt .. "toggle"))
  Tap = start capture, tap = stop+transcribe; daemon debounces 0.4 s (the key
  is tap-only and machine-guns while held). The bind MUST set `PYTHONPATH=<repo>`
  (`package = false`). Caelestia hot-reloads the lua on file save. `just ptt
  toggle` is the manual client.

LIVE PIPELINE (2026-08-23, FRIDAY_DEBUG=1, physical key + llama-server up):
  tap → "open vlc" → tap:
    capture 00:03.414 (VAD dropped 0.816 s)
    v1 heard='Open VLC'
    v1 action=open_app dispatched=True spoken='Opened VLC.'   → VLC running
  ~2 s from second tap to dispatch. Earlier "open my browser" also launched
  Brave (Outcome.OK 87 ms) once ADR-043 landed. STT accurate every attempt;
  TTS spoke every outcome. Only numbers still missing: the eval score + TTFA.
  NOTE: planner brand-name gap — `heard='Open Brave'` returned action=none
  (STT fine; the literal brand didn't map to the `browser` key). Fix before eval.

SPOKEN EVAL: 20/20 planning (2026-08-23, physical key, FRIDAY_DEBUG).
  Every clip: STT accurate + correct action chosen. Brand names all mapped
  live (Brave->browser, foot->terminal, code->editor, mpv->video, VLC->vlc);
  lo-fi/jazz/piano->youtube_search; weather/football/bitcoin->web_search;
  open youtube->open_youtube; hello/rm-rf/fridge->none. VLC needed one retry.
  EXECUTION issues found (planning was clean):
   - mpv exited immediately (bare `mpv` prints version + exits 0) -> FIXED:
     --idle=yes --force-window=yes keeps a window (apps.py, verified).
   - all YouTube outcomes said "Opened YouTube." -> FIXED: youtube_search now
     "Opened YouTube for <query>." (registry display), open_youtube unchanged.
   - 2 STT timeouts (v10/v11) right after launching ~9 apps: CPU saturation
     starved faster-whisper past the 5 s cap. Real-usage edge; both retried
     OK. Watch if it recurs; a load-aware timeout is a future option.
   - VS Code "opened" but not always visible: `code` is a fork+exit-0 shell
     script, so the executor can't see if electron actually came up. Inherent
     to fork-launchers; no clean fix at the executor.

TTFA (end of speech -> first audio), 19 samples, physical key:
  p50 2156 ms     p95 2731 ms   (min 1815, max 2731, mean 2150)
  target 1400 / hard fail 4400  -> PASSES the hard gate, MISSES soft target.

OQ-09 DECISION (streaming needed?): NOT required — p95 2.7 s is well under the
  4.4 s hard fail. Breakdown: transcribe ~1 s + plan ~0.5 s + synth ~0.4 s.
  Streaming TTS (ADR-020) would shave ~0.4 s only; the bigger cost is STT.
  Deferred; revisit if the primary chit-chat path (below) needs faster turns.

---

---

## G7 — Search  *** the only egress ***  **PASSED 2026-08-23**

**Acceptance:** IS-1..IS-20 all blocked, asserted on the executor.

- [x] SearXNG running on `127.0.0.1:8888` (systemd --user unit, ADR-045)
- [x] `tools/search.py` client + sanitizer (markup, control chars, zero-width, 5 results, 1500 tokens, URLs out of band)
- [x] `final.gbnf` — action enum length asserted == 1 by a unit test
- [x] `llm/client.py` asserts: untrusted region non-empty implies `final.gbnf`
- [x] `tests/fixtures/injection.jsonl` — 20 hostile results
- [x] Connected mode opt-in, visibly indicated in the TUI (default connected, ADR-046)
- [x] Local mode refuses search audibly

```
EVIDENCE:
$ just test-injection
  IS-1..IS-20 20/20 blocked, dispatches from grounding turns: 0

$ just test-grammar-lock
  final.gbnf action enum size: 1 (name == "none")

$ just test-egress
  8080+8888 = 127.0.0.1 ONLY, no 0.0.0.0 (exit 0)
```

---

## G8 — Conversation (Build 1: in-reply, in-session)  **PASSED 2026-08-23**

**Acceptance:** spoken casual input → a warm ≤4-sentence reply; commands + facts still
route right (eval not regressed); `chat` can never dispatch (`test_chat_turn` asserts
executor untouched); dialogue never written to disk (`test_dialogue` asserts RAM-only);
fail-soft on generation error; ADR-048.

- [x] ADR-048: Conversational speech carved out of ADR-009 for non-side-effect turns
- [x] `chat` action in `PARAM_SCHEMA`, `plan.gbnf`, `validate.py` (empty params `{}`)
- [x] Planner prompt `SYSTEM_POLICY` routes casual/greetings/persona to `chat`
- [x] `CHAT_SYSTEM` persona (warm, witty, concise JARVIS-ish, ≤4 sentences, spoken-safe)
- [x] `friday/dialogue.py` bounded RAM `Dialogue` ring buffer (invariant #7, no disk writes)
- [x] `friday/llm/chat.py` reply generator (free text, temp 0.7, stop sequences, sanitized for TTS)
- [x] `run_turn` / `turn.py` routes `chat` → `generate_reply` (`dispatched=False`, zero executor calls)
- [x] `none` speaks distinct terminal line `OUT_OF_SCOPE` ("That isn't something I'm able to do.")
- [x] Daemon + TUI own `Dialogue`, pass history into turns, append spoken replies
- [x] Eval fixtures updated (E15/E16→chat, added E25..E28) and re-baselined 28/28 (0 regressions)
- [x] Live end-to-end smoke test verified against running model

```
EVIDENCE (2026-08-23, llama-server up on :8080):
$ uv run pytest -q
  199 passed in 1.23s

$ just eval
  fixture-set revision: a661efe50529
  passed 28/28 (100%), known-failing: 0, regressions vs baseline: 0

$ just test-injection
  20/20 blocked, calls==[]

$ uv run pytest tests/test_adversarial.py tests/test_injection.py
  14 passed

LIVE END-TO-END SMOKE TEST (real Qwen2.5-7B model, dry_run=True):
  UTTERANCE: "hi"
    -> PLAN: name=chat params={} dispatched=False
    -> SPOKEN: "Hello there! How can I assist you today?"
  UTTERANCE: "who are you"
    -> PLAN: name=chat params={} dispatched=False
    -> SPOKEN: "I'm Friday, your friendly Linux-based assistant. How can I help you?"
  UTTERANCE: "what can you do"
    -> PLAN: name=chat params={} dispatched=False
    -> SPOKEN: "I can answer questions, provide information, and help with tasks on your Linux laptop. How can I assist you specifically?"
  UTTERANCE: "open my browser"
    -> PLAN: name=open_app params={'app': 'browser'} dispatched=True
    -> SPOKEN: "Opened Brave [dry-run: ['brave']]."
  UTTERANCE: "what's the weather in Paris"
    -> PLAN: name=web_search params={'query': 'weather in Paris'} dispatched=False
    -> SPOKEN: "I didn't find anything on that."  (fail-soft SearXNG timeout)
  UTTERANCE: "run rm -rf /"
    -> PLAN: name=none params={} dispatched=False
    -> SPOKEN: "That isn't something I'm able to do."
```

---

## G9 — Service

**Acceptance:** survives `kill -9` of llama-server; survives suspend/resume.

- [ ] `friday-llm.service`, `friday.service`, ordering, restart backoff
- [ ] `friday --selftest`: server reachable, GPU arch, DB schema + perms, audio devices, panic file, no wildcard bind
- [ ] Log rotation (10 MB x 5)
- [ ] Graceful shutdown, model unload
- [ ] Panic switch documented and tested

```
EVIDENCE:
$ systemctl --user status friday
  (paste)

$ kill -9 $(pgrep llama-server); sleep 10; just selftest
  (paste — must recover)

suspend/resume audio recovery:
  (paste)
```

---

## Decision log

Append a line whenever a measurement changes a document.

```
   DATE        WHAT CHANGED                                    WHERE
   2026-08-22  ctx 2048 -> 8192 q8_0 after pricing KV cache    ADR-003
   2026-08-22  CUDA 12.4 guidance retracted (needs sm_120)     ADR-021
   2026-08-22  wake word cut from Phase 1                      ADR-012
   2026-08-22  STT moved to CPU, one CUDA context              ADR-004/018
   2026-08-22  friday.md v4 archived, no longer authoritative  ADR-022
   2026-08-22  runtime files moved to XDG dirs                  ADR-023
   2026-08-22  laptop-specifications.md gitignored (MACs)       ADR-024
   2026-08-22  task runner = just (installed, not make)         ADR-025
   2026-08-22  app registry fixed: 7 entries, no files/spotify  ADR-026
   2026-08-22  registry trimmed 7->5 (drop firefox, kitty)     ADR-032
   2026-08-22  youtube_search allowed as audited exception      ADR-027
   2026-08-22  run_script cut from Phase 1                      OQ-02
   2026-08-22  transcripts: in-memory ring buffer only          ADR-028
   2026-08-22  model artifact pinned to bartowski GGUF          ADR-029
   2026-08-22  eval gate is a RATE on a growing set, not 45/50  ADR-030
   2026-08-22  disk is the boundary, provisionally (OQ-05 open) ADR-031
   2026-08-22  NPU present (/dev/accel/accel0), Phase 2 option  ADR-019/OQ-10
   2026-08-22  llama.cpp sm_120a build runs on GPU; risk gone   G1/ADR-021
   2026-08-22  CUDA 13.3 needs g++-15 host (gcc16 too new)      G1 build note
   2026-08-22  b21e4de log dropped "compute capability" strings G1 doc-drift
   2026-08-23  G2 harness built; baseline 18/20, adversarial 12/12  G2/ADR-033
   2026-08-23  youtube = 2 top-level actions (fixes §5.1 drift)     ADR-033
   2026-08-23  eval scoring: enum exact, free-text lenient          ADR-033
   2026-08-23  G2 adversarial = AS-1..12; AS-13..16 to G3           ADR-033
   2026-08-23  OQ-08 delta 0: drop `thought` (removal at G3)        ADR-011
   2026-08-23  G3 PASSED: eval 20/20, adversarial 16/16            G3/ADR-034
   2026-08-23  `thought` removed from schema/grammar/prompt        ADR-011
   2026-08-23  full textual TUI + --dry-run flag                    ADR-034
   2026-08-23  not_found via which() preflight (hyprctl exits 0)    ADR-034
   2026-08-23  youtube opens in brave, not firefox                  ADR-034
   2026-08-23  panic: DISABLED file or FRIDAY_DISABLED env         ADR-034/FR-36
   2026-08-23  pref keys: free slug + alias anchors (opt d)        OQ-18/ADR-035
   2026-08-23  forget: voice soft-expire, CLI --hard/--yes         OQ-19/ADR-036
   2026-08-23  spoken pref confirmed first (UI handshake)          OQ-20/ADR-037
   2026-08-23  retention = logs only; prefs never age out          OQ-21/ADR-038
   2026-08-23  G4 PASSED: 98 unit, eval 20/20, adv 16/16           G4
   2026-08-23  Kokoro runtime = kokoro-onnx (ONNX/CPU), not torch  ADR-039
   2026-08-23  Kokoro model = fp32; int8 4x slower, fp16 broken    ADR-039
   2026-08-23  ONNX intra_op=8 (P-cores); 24 threads worse         ADR-039
   2026-08-23  venv now torch-free (STT=CT2, TTS=ORT)              ADR-039
   2026-08-23  OQ-22 opened: voice audition (user)                 OQ-22
   2026-08-23  voice = af_bella primary / af_heart fallback        OQ-22/ADR-005
   2026-08-23  G5 playback = sounddevice; cancel deferred to G6    ADR-040
   2026-08-23  TTS wired into turn loop (run_turn speaks)          ADR-040
   2026-08-23  G5 PASSED: af_bella signed off, 104 unit, FR-71 ok  G5
   2026-08-23  standing rule: research+bench every new dependency  ADR-041/CLAUDE§7
   2026-08-23  G6 re-verify: diagram 05 Kokoro 4t->8t (G5 drift)   diagram 05
   2026-08-23  G6 STT = full ADR-041 drill (fw vs whisper.cpp)     OQ-07/ADR-041
   2026-08-23  G6 PTT = Copilot key, chord SUPER SHIFT XF86Assistant,
               hold verified (bind/bindrelease); hold-to-talk viable   OQ-03
   2026-08-23  G6 mic = default PipeWire source (Mic1), not DMIC   OQ-23
   2026-08-23  G6 arch = daemon+FSM+unix socket built now          G6
   2026-08-23  STT drill: whisper.cpp rejected (2.8x slower fw)    ADR-042
   2026-08-23  STT = small.en int8 beam1 hotwords (p95 741 ms)     ADR-042
   2026-08-23  large-v3-turbo pin dropped (2.7s CPU); FR-10 edited ADR-042
   2026-08-23  CPU STT viable, no GPU; ADR-018 stays closed        ADR-042
   2026-08-23  int8 > fp32 for CT2 whisper (no AVX-512 penalty)    ADR-042
   2026-08-23  barge-in target: IDLE -> CAPTURING (diagram 01 fix) FR-7
   2026-08-23  G6 audio code + 40 tests (144 total); live pending  G6
   2026-08-23  G6 live: STT+plan+TTS proven; heard='open my browser' G6
   2026-08-23  BUG: hyprctl dispatch broke (Hyprland 0.56 lua CLI)  ADR-043
   2026-08-23  launch = direct spawn, no hyprctl; WAYLAND_DISPLAY   ADR-043
   2026-08-23  launch fire-and-forget, 0.4s grace; _kill_group gone ADR-043
   2026-08-23  BUG: PTT bind needs PYTHONPATH (package=false, cwd~) G6/bind
   2026-08-23  BUG: confirm timer shared cap handle -> separated    G6/daemon
   2026-08-23  FRIDAY_DEBUG env: log heard/action to terminal only  G6/config
   2026-08-23  open_app browser -> OK 87ms, Brave ran; 147 unit     G6/ADR-043
   2026-08-23  OQ-03 REOPENED: Copilot key leaks Super (glitch)    OQ-03/ADR-044
   2026-08-23  PTT = toggle on XF86Presentation (tap on/off)       ADR-044
   2026-08-23  toggle debounce 0.4s (tap-only key machine-guns)    ADR-044
   2026-08-23  glitch RESOLVED: Copilot Super-leak, key dropped    ADR-044
   2026-08-23  G6 physical key PROVEN: tap->"open vlc"->VLC; 150 unit G6/ADR-044
   2026-08-23  planner brand-name gap fixed (Brave/Code/foot/mpv->id) G6/prompt
   2026-08-23  youtube_search strengthened (music/"put on") re E11    G6/prompt
   2026-08-23  eval set 20->24 (+brand fixtures E21-24); 24/24         G6/eval
   2026-08-23  SPOKEN EVAL 20/20 planning; TTFA p50 2.16s/p95 2.73s   G6
   2026-08-23  OQ-09: no streaming (p95 2.7s < 4.4s hard fail)        OQ-09
   2026-08-23  mpv --idle --force-window (bare mpv exits 0)           G6/apps
   2026-08-23  youtube_search outcome echoes query (differentiated)   G6/registry
   2026-08-23  TTFA debug instrument (say on_play callback)           G6/daemon
   2026-08-23  DIRECTION: chit-chat + suggestions = PRIMARY goal      NEEDS DESIGN
   2026-08-23  youtube autoplay deferred (search-only for now)        OQ-24
   2026-08-23  G7 chosen before G8 (search unblocks chat facts)       progress
   2026-08-23  SearXNG = systemd --user unit (docker), loopback only  ADR-045
   2026-08-23  search default = CONNECTED; local is opt-out           ADR-046
   2026-08-23  search UX = synth spoken answer + always-show sources  ADR-047
   2026-08-23  G7 T1-6 built on branch g7-search; 170 unit pass       G7
   2026-08-23  SearXNG image pinned sha256:11a9b34c...; unit running  G7/T1
   2026-08-23  plan fix: --user unit can't Requires=docker.service    G7/T1
   2026-08-23  plan fix: zero-width test space vector U+0020->U+00A0  G7/T3
   2026-08-23  client complete(untrusted=True) asserts final.gbnf     G7/T5/inv#1
   2026-08-23  grounding turn parses direct (not validate); name=none G7/T6
```

## Time log

Optional, but the honest version of "how long will this take".

```
   GATE   ESTIMATE   ACTUAL   NOTES
   G0     1 h        ____
   G1     3 h        ____     highest variance — CUDA build
   G2     4 h        ____     writing 50 fixtures is the slow part
   G3     8 h        ____
   G4     4 h        ____
   G5     3 h        ____
   G6     6 h        ____     PTT path unknown
   G7     5 h        ____
   G8     ? h        ____     conversation (primary goal)
   G9     3 h        ____     service
```
