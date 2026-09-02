# Friday

A local-first voice and text assistant for one Arch Linux + Hyprland machine.

Everything that thinks runs on this laptop. No model API, no cloud STT, no
telemetry. The language model is a GGUF file on local disk served by
`llama-server` bound to `127.0.0.1`; speech-to-text, text-to-speech, wake word,
echo cancellation and speaker verification are all CPU-side and local. The only
intentional outbound path is a self-hosted SearXNG instance on loopback, used
for web search.

Friday launches a small fixed set of applications, remembers preferences,
controls the system and the compositor, takes notes, sets reminders, dictates,
searches the web, and holds a conversation — by voice or by text.

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

Post-audit Phase 1 ("Stop Lying") and Phase 2 ("Make it Measurable") are both
COMPLETE. Phase 2's last item — one proven hands-free capture — landed
2026-09-02: five wake captures, all ended by Silero at 2.3-3.7 s, none reaching
the 15 s cap. D3 is fixed live and OQ-39 is closed.

```text
uv run pytest             568 passed, rc=0 (76 test files)
just eval                 60/60, regressions 0 (100%)
just test-injection       20/20 blocked
just test-egress          8 passed (a real egress check since ADR-110)
just selftest             9/9 PASS, rc=0 (including power profile verification)
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
just selftest             # must be 9/9 PASS before anything else
```

`selftest` checks reachability, GPU architecture, that the LLM is *actually*
resident on the GPU (not silently fallen back to CPU), database permissions,
audio devices, the panic switch, and that nothing binds off loopback.

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
| `just selftest` | 8 health checks; must pass before trusting a measurement |
| `just eval` | 28 planner fixtures → pass count and regressions |
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
adr.md                 83 decisions (ADR-001…ADR-083), each with its cost and
                       rejected alternatives
threat-model.md        threats, controls, and which file enforces each
open-questions.md      what is undecided and what it blocks
tech-stack.md          pinned versions and what each piece is for
friday.md              the gate-by-gate build plan (all gates complete — a
                       record of sequencing, not a to-do list)
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
the change contradicts is fixed in the same commit, and a new decision has an
ADR.

A diagram that disagrees with the code is a bug in the diagram.
