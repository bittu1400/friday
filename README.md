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

The desk suite is green:

```
uv run pytest             450 passed
just eval                 28/28, regressions 0
just test-injection       20/20 blocked
just selftest             8/8
```

**A green suite here has repeatedly not meant a working feature.** Five review
passes and a live-voice pass found defects that every test missed, because the
tests never exercised the real path. Currently **15 known open defects
(D1–D15)**, documented with root causes in `progress.md` and indexed in
`docs/reality-check.md` §F. The most important:

- **D1 (critical)** — `is_affirmation` matches bare tokens, and Whisper writes
  `Yes.` with a full stop. Every *spoken* confirmation has been recorded as a
  decline, so no confirm-gated capability has ever worked by voice. Typed
  confirms work. This is fixed nowhere yet.
- **D3** — hands-free wake captures never end; push-to-talk is the only usable
  trigger today.
- **D13** — the STT model load contacts Hugging Face at every daemon start
  (~9 KB of metadata; no audio or text leaves the machine).

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
- `llama.cpp` built **with sm_120 kernels** — a stock CUDA 12.4 build fails at
  runtime with `no kernel image is available for execution on the device`
  (see ADR-021)
- `just`, `docker` (for SearXNG)

---

## Setup

```bash
uv sync
just fetch-voice          # Kokoro TTS voice weights
```

Build `llama.cpp` per ADR-021 (the sm_120 flags matter), place the GGUF in
`~/.local/share/friday/models/`, then deploy the three user units described in
`docs/systemd-setup.md` and `docs/searxng-setup.md`:

```bash
systemctl --user enable --now friday-llm friday-searxng friday
just selftest             # must be 8/8 before anything else
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
