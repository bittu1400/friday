# Friday

A local-first voice and text assistant for one Arch Linux + Hyprland machine.

Everything that thinks runs on this laptop. No model API, no cloud STT, no
telemetry. The language model is a GGUF file on local disk served by
`llama-server` bound to `127.0.0.1`; speech-to-text, text-to-speech, wake word,
echo cancellation and speaker verification are all CPU-side and local. The only
intentional outbound path is a self-hosted SearXNG instance on loopback, used
for web search.

Friday launches applications, remembers preferences, controls the system and
the compositor, takes notes, sets reminders, dictates, searches the web, and
holds a conversation — by voice or by text. Since ADR-097 the app list is
**every installed application**, generated at import from the machine's XDG
desktop entries and merged over five curated ids — so its size moves whenever
you install something. Settings panels are confirm-gated; privilege-escalating
and shell `Exec` entries are never offered. The enum stays CLOSED: it is
generated, not fuzzy-matched.

---

## Why this repo is unusual

Most of the interesting work here is not the features. It is the constraints
they are built inside, and the fact that they are enforced in code rather than
promised in a prompt.

**The model never supplies anything executable.** It picks an opaque ID from a
closed enum; code builds the argv. There is no `open_url`, no shell string, no
path from the model. One audited exception exists (a YouTube search query) and
it is charset-whitelisted, length-capped, percent-encoded into a fixed
template, with the resulting netloc re-asserted.

**A turn that has read the web cannot act.** Search results are untrusted data.
Once a turn consumes them it is locked to a grammar whose action enum is
literally `["none"]`, so no amount of injected text in a web page can cause a
dispatch. This is a grammar-level control, not a prompt asking nicely.

**Structured output is enforced twice** — GBNF grammar server-side *and* an
application-side validator. Any failure fails closed to `action=none`.

**Execute first, then speak.** Direct-action speech comes from an outcome
template after the action returns, never from the model. This exists because
the alternative says "Opening Firefox" when the launch failed.

**Destructive command classes are permanently banned**, not gated. Reversible
consequential actions go through a three-tier confirm.

The full list is in `CLAUDE.md` under *Hard invariants*. Each one has an ADR
explaining what it cost.

---

## Status — read this before trusting anything

All gates are built: G0–G9 (scaffolding, toolchain, eval harness, registry,
persistence, voice out, voice in, search, conversation, service) and G10–G13
(wake word + AEC + VAD + barge-in, proactive scheduler, action surface,
speaker verification).

Post-audit Phase 1 ("Stop Lying"), Phase 2 ("Make it Measurable") and **Phase 3
("Make it Extensible") are all COMPLETE.** Phase 2's last item — one proven
hands-free capture — landed 2026-09-02: five wake captures, all ended by Silero
at 2.3-3.7 s, none reaching the 15 s cap. D3 is fixed live and OQ-39 is closed.

**Phase 3 closed 2026-09-04.** One record — `friday/capabilities.py` — now
drives the param schema, both grammars, the planner prompt's action block, the
chat persona's toolset sentence, the confirm decision, the panic gate, the eval
fixture obligation and `STT_HOTWORDS`. **Adding a capability is one
`Capability(...)`, one handler row, and ≥2 eval fixtures**; four separate tests
fail if you forget a piece. The safety net is that `SYSTEM_POLICY` assembles
**byte-identical** and both grammars still regenerate byte-for-byte.

```text
.venv/bin/python -m pytest   687 passed, rc=0 (87 test files in tests/)
just eval                 81/81, regressions 0 (100%)
just test-injection       20/20 blocked
just test-egress          8 passed (a real egress check since ADR-110)
just selftest             10/10 PASS, rc=0 (incl. power profile and unit-deploy drift)
just bootstrap --check    11/11 verified PASS (all 6 models SHA256 pinned)
just stats                empirical latency distributions by action class
just grammar              regenerates the committed GBNF byte-identical
```

Note on that first line: until ADR-111 the full-suite run **crashed** with
SIGSEGV/SIGILL at session finish (a leaked PortAudio stream), so every test
count published before 2026-09-02 evening was only reachable by running the
files one at a time.

**A green suite here has repeatedly not meant a working feature.** Five review
passes and a live-voice pass found defects that unit tests missed when they bypassed the real path.

- **Phase 1 (Stop Lying, ADR-108):** Unified panic gate over all 10 side-effecting paths (F1), persona truth (F2, F3), `local_files_only=True` for offline STT (F8, D13), dictation mutes wake (F7, D14), selftest WARN exits code 2 `[DEGRADED]` (F20), eval harness rate gating (F23).
- **Phase 2 (Make it Measurable, ADR-109):** Real duration tracking (`duration_ms`) and unconditional stage timings (F10, FR-128), `just stats` CLI aggregator, systemd watchdog heartbeat + `Type=notify` (F11), power profile sanity check in selftest (F28), and deterministic `just bootstrap` (§10, F24). **The seventh item landed 2026-09-02 at the microphone:** five hands-free captures ended by Silero at 2.3-3.7 s, none reaching the 15 s cap, confirming the ADR-095 VAD swap through the real AEC path. D3 fixed live, OQ-39 closed.
- **Launch fixes (ADR-113/114/115), 2026-09-02 night:** the post-wake pause budget went 3.0 → 5.0 s and an abandoned capture now skips STT and the turn entirely (ADR-113, OQ-64); launched apps stopped dying with the daemon (`KillMode=process`, ADR-114, D29); and **`PrivateTmp=yes` was removed** (ADR-115, D30) — it gave the daemon an empty `/tmp`, so a Brave it launched could not reach the Chromium singleton socket in the real `/tmp` and exited 0 in ~50 ms with no window while the launch was announced as successful. **D30/ADR-115 was confirmed by the owner on 2026-09-03** — the browser opens, and the audit row agrees (401 ms, the healthy signature, against 49-119 ms for the life of the project). **ADR-113 was proven live the same morning**: a marginal wake (score 0.543) opened a speechless capture and the journal reads `capture abandoned: no speech within 5.0s` at +4.985 s, with no STT line and no TTFA after it — the turn was skipped, not merely shortened. **ADR-114 was proven live 2026-09-04** — and it took five sessions because of ordering and subject choice: the launch must come BEFORE the restart, and the app must actually be inside the service cgroup (`kitty` is; Discord moves itself into `app-discord-<pid>.scope` and proves nothing). kitty survived a restart at the same PID, and `systemctl show` reports `KillMode=process` live rather than merely committed. **This project now owes a microphone nothing.**
- **Mutation audit of the test suite (ADR-116) and its fixes (ADR-117), 2026-09-03:** 85 defects were injected into the source one at a time and the full suite run against each — **56 killed, 29 survived, score 66 %**. The suite turned out to test *functions, not wiring*: three of the five confirm gates could have their branch deleted from `turn.py` with all 581 tests passing, `assert_not_banned(argv)` could be removed from the executor with the adversarial and injection suites green, and `SpeakerVerifier.verify()` was called by no test in the repository. **All five tier-1 gaps are now closed (ADR-117)**, each proven by applying its mutation and watching the suite turn red. That practice is now line six of the definition of done. **Tier 2 followed the same day (M6, M7):** the eval gate could be made to always exit 0 and the self-test's FAIL path could stop producing exit 1 — the two gates every session is told to trust — and both are now pinned (`tests/test_eval_gate.py` is new). What is left is tier 3, M8–M11, which is depth behind walls that still stand. Report: `test-audit-2026-09-03.md`.
- **The app enum was reachable in principle and not in practice (D31–D34, ADR-118/121/122), 2026-09-03 → 2026-09-04.** A month after the enum was widened from 5 ids to every installed application, `action_audit` still held `open_app` rows for **only those five** — the requests never reached the executor. ADR-097 had widened one list and left two at Phase 1: the planner prompt (so "firefox" resolved to `browser` and Brave opened) and `STT_HOTWORDS`. Both fixed and **proven live by voice**. Three more defects fell out of testing it properly: **D32** was raised from n=2 and **refuted at n=8** the next day (two-word names are fine; "Zen Browser" and "LibreWolf" both landed); **D34**, the planner writing `easy-effects` where the generator makes `easy_effects`, fixed by folding a miss through `app_key` itself — a whitelist, so the adversarial fixtures still reject; and **D33**, an id of `android_studio_panda_4_2025_3_4_patch_1` taken straight from a `.desktop` `Name`, fixed by taking the known name from the vendor path and **proven live at 410 ms**.
- **Phase 3 opened (ADR-119/120/123), 2026-09-04.** Its two security items shipped first and standalone: **F4**, invariant #3's "minimal explicit env, no exceptions" had *five* exceptions inheriting the daemon's whole environment including `NOTIFY_SOCKET`; and **F5**, the binary denylist inspected `argv[0]` only, so `distrobox-enter -- bash`, `env nohup rm -rf ~` and `foot -e bash` all walked through it. Then the capability record itself: `friday/capabilities.py` holds `Risk` and a frozen `Capability` for all 25 actions, `PARAM_SCHEMA` is now a view over it, and **the proof the move changed nothing is that `just grammar` still reproduces both committed `.gbnf` byte-for-byte** — reordering two capabilities fails that test. Criteria 3.1, 3.2 and 3.8 landed there.

- **Phase 3 closed (ADR-124/125), 2026-09-04.** Both prompt regions are derived
  and `SYSTEM_POLICY` comes out byte-identical (5381 chars, 1401 tokens, pinned
  against a committed fixture); the confirm decision and the panic gate are read
  off `Capability.risk`, deleting five hand-coded branches and eight
  `config.is_disabled()` blocks — **`tests/test_confirm_arming.py` passes
  untouched**, which is how "nothing moved" is known rather than believed;
  `turn.py` is **941 → 246 lines** around a handler table; every capability owes
  ≥2 eval fixtures (**64 → 81, still 100 %**); and `STT_HOTWORDS` is derived as a
  superset of the list it replaces. **`open_app` is now FIRST_USE and live** — an
  application you have never opened asks once, and the grant is keyed to a
  SHA-256 of its argv, because the id generator resolves collisions first-wins.
  Fifteen mutations turned the suite red; **one survived** — recording an
  approval while the panic switch was engaged left everything green, and now has
  a test named after it. **Whether asking once per app is tolerable is OQ-69, and
  no test can answer it.**
- **Cold audit (ADR-127), 2026-09-04.** A read-only architecture and security
  pass run against the code rather than the docs found **three defects under a
  completely green gate** — `pytest` 653, `eval` 81/81, `selftest` 10/10,
  grammars byte-identical. **D35:** a handler caught `SchemaError` without
  importing it, so a malformed preference raised `NameError` instead of failing
  closed; 653 tests could not see it because `daemon.py` catches `Exception` and
  speaks one line for every failure. **D36:** the `sqlite3` command that proves
  FIRST_USE fired named a database that does not exist — and `sqlite3` *creates*
  an empty one at a missing path, then reports `no such table: approvals`, which
  is indistinguishable from the thing it was written to disprove. **D37:**
  `chat`, the slowest turn class in the system, wrote **no audit row at all**, so
  `just stats` could not see it and 0 of 192 live rows were chat; it now writes
  one carrying `params={}`, because the utterance and the reply are both what
  invariant #7 forbids on disk. Reading the *consumer* found two more: `just
  stats` would have raised `KeyError` on the first chat row, and `file_open` had
  had no latency class since G12. Six mutations turned the suite red. **The same
  audit closed OQ-69's mechanism half from the audit tables** — FIRST_USE asked,
  was declined with no approval written, asked again, was approved, then
  dispatched with no question; a second application asked on its own.
- **Closed enum parameter constraints (ADR-128), 2026-09-04.** `plan.gbnf` previously constrained the action name only while params were generic `{string: string}` — the root cause of D19, D20 and D34. The seven machine-independent closed enum actions are now server-side constrained in GBNF: `system_volume.direction`, `system_brightness.direction`, `system_media.action`, `system_wifi.state`, `hypr_workspace.workspace`, `hypr_window.action`, `dictation_mode.action`. `open_app.app` is kept free in `action-generic` to preserve host machine-independence and allow failing closed with an informative log rather than forced hallucinations. `pytest` **685 → 687**, `eval` **81/81 (100%)**, 0 regressions.
- **Verification pass (ADR-110/111/112):** the phases above were then checked against the machine rather than against their own write-ups, and three claims did not survive. `just test-egress` still could not observe a connection, so it was rewritten as a real guard over `socket.getaddrinfo`/`socket.socket.connect` with a demonstrated FAIL path (ADR-110). `pytest -q` had been crashing at session finish on a leaked PortAudio stream (ADR-111). And the new egress check immediately found that **`import onnxruntime` transmits to Microsoft telemetry on import** — on Linux, with no inference, on every daemon start for the life of the project; fixed with `ORT_DISABLE_TELEMETRY=1` (ADR-112).

**On "local-first":** it is true, and it was not fully true before 2026-09-02.
Inference is local — `llama-server` holds the model in VRAM and binds loopback
only. But two dependencies transmitted off the machine for months without any
test noticing (D13, D27), because until ADR-110 this project had no check
capable of observing an outbound connection. Both are closed and guarded now.

If you want to know whether something actually works, `docs/reality-check.md`
is the manifest of what Friday must do and must refuse, with each row marked
verified or not. Nothing in this project is reported as working on the basis of
a passing test alone.

---

## Requirements

This is a single-machine project, not a distributable. It targets one laptop
and makes no attempt to be portable.

- Arch Linux, Hyprland, PipeWire
- NVIDIA Blackwell GPU (sm_120) with 8 GB VRAM
- Python 3.12 via `uv` (never the system interpreter)
- `llama.cpp` built **with sm_120 kernels** at `/opt/llama.cpp/build/bin/llama-server`
- `just`, `docker` (for SearXNG)

---

## Setup

```bash
uv sync
just bootstrap            # verifies/fetches all 6 SHA256-pinned models, container, and units
just bootstrap --check    # preflight verification (must be 11/11 PASS)
```

Deploy the three user units described in `docs/systemd-setup.md` and `docs/searxng-setup.md`:

```bash
systemctl --user enable --now friday-llm friday-searxng friday
just selftest             # must be 10/10 PASS before anything else
```

`selftest` checks reachability, GPU architecture, that the LLM is *actually*
resident on the GPU (not silently fallen back to CPU), database permissions,
audio devices, the panic switch, that nothing binds off loopback, the power
profile, and that **the unit systemd is running matches the one committed** —
asked of `systemctl show`, because the installed unit is a symlink to the repo
file and a file comparison can never disagree with itself (ADR-117).

---

## Running

```bash
just run                  # text mode (Textual TUI)
just voice                # voice daemon: push-to-talk + wake word
just ptt press            # send a PTT command to a running daemon
```

`friday.service` is `Restart=always`, so `kill <pid>` will not stop it — use
`systemctl --user stop friday`. **Never run `just voice` while the service is
up**; two daemons fight over the microphone and the PTT socket.

To see transcripts in the log you must clear `JOURNAL_STREAM`, or the
disk-disclosure guard suppresses them:

```bash
systemctl --user stop friday
env -u JOURNAL_STREAM FRIDAY_DEBUG=1 just voice
```

---

## Commands

| | |
| :-- | :-- |
| `just selftest` | 10 health checks; must pass before trusting a measurement |
| `just eval` | 60 planner fixtures → pass count and regressions |
| `just test` | full unit + adversarial + injection suite |
| `just test-injection` | 20 hostile web results, all must fail closed |
| `just test-no-fstring-sql` | asserts `store/` SQL is strictly parameterized |
| `just wake-bench` | live wake-word / VAD benchmark with input-level readout |
| `just enroll-voice` | 10-utterance speaker enrollment |
| `just prefs list \| forget` | manage stored preferences |

Recipe names are authoritative — check the `justfile` before citing one.

---

## Documentation

Read in this order. `progress.md` is the only file that says what is true now;
everything else describes intent.

```
progress.md            what is ACTUALLY done, with pasted command output.
                       Its >>> START HERE <<< block is written for the next
                       session. Start here, always.
docs/reality-check.md  the manifest of what Friday must do and must refuse,
                       on the real machine. §F is live status.
spec.md                requirements with IDs and acceptance tests
architecture.md        modules, interfaces, concurrency, deployment
adr.md                 117 decisions (ADR-001…ADR-117), each with its cost and
                       rejected alternatives. Verify the count with
                       `grep -c '^## ADR-' adr.md` — it has been wrong in
                       prose three times
threat-model.md        threats, controls, and which file enforces each
open-questions.md      what is undecided and what it blocks
tech-stack.md          pinned versions and what each piece is for
friday.md              the gate-by-gate build plan (all gates complete — a
                       record of sequencing, not a to-do list)
audit-2026-09-02.md    the current CODE audit. 29 findings F1–F29, each either
                       measured on this machine with output pasted, or read
                       with a how-to-prove line.
design-2026-09-02.md   the plan that came out of it: 8 owner decisions, 12
                       phases. §11.1 is Phase 3's acceptance contract.
test-audit-2026-09-03.md
                       the TEST-SUITE audit. Findings M1–M19 from 85
                       mutations. Every M-number is a MISSING TEST, not a code
                       defect. Its STATUS block says which are now closed.
gemma-brief.md         the model question, verified: identity + SHA256 pins,
                       the hardware envelope, measured headroom, and where a
                       turn's milliseconds actually go.
diagrams/              ASCII. 02-tool-call-loop.md and 04-trust-boundaries.md
                       are the ones that matter.
```

`Alpha-ox-analysis.md` is a 2026-08-26 audit snapshot: read its fix-status
table at the bottom, not its line numbers, which now point into deleted code in
places. `docs/archive/` (`friday-v4.md`, `review-gemini.md`, `review-gpt.md`)
holds historical inputs containing claims later proven wrong — do not cite them
as current.

---

## Working agreement

Contributions — including from AI agents, which is most of this repo's history
— follow the agreement in `CLAUDE.md`. The short version:

1. **Never assume; ask.** A decision that is the user's gets asked, not
   defaulted.
2. **Batch a phase's questions up front.** Five interruptions that were all
   knowable at the start is the failure this prevents.
3. **Record the decision the moment it is made**, in the same turn — ADR,
   spec, open-questions, progress log.
4. **Evidence, not belief.** Nothing is reported done without the command
   output pasted into `progress.md`. "It should work" is not a status.
5. **Research every dependency on this machine.** Measured beats "should be
   faster" — an int8 build of the TTS model turned out 4× *slower* here.

The definition of done for any change: the acceptance test named in `spec.md`
passes, `just eval` did not regress, evidence is in `progress.md`, any diagram
the change contradicts is fixed in the same commit, a new decision has an ADR,
and — since 2026-09-03 (ADR-117) — **a change touching a hard invariant ships
with a mutation of that line demonstrated to turn the suite red.**

A diagram that disagrees with the code is a bug in the diagram.
