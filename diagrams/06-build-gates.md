# Diagram 06 — Build Gates and Dependency Order

A gate is passed when its acceptance test runs green **and the evidence
is pasted into `progress.md`**. No gate is skipped, no gate is passed on
belief. Work on a later gate before an earlier one is how the original
plan would have burned a week on `evdev` before discovering the CUDA
wheel does not run on Blackwell.

```
   +------------------------------------------------------------------+
   |  G0  REPO                                                        |
   |      git init, docs committed, uv venv py3.12, lockfile          |
   |      accept: `uv run python -V` == 3.12.x                        |
   +--------------------------------+---------------------------------+
                                    |
                                    v
   +------------------------------------------------------------------+
   |  G1  TOOLCHAIN GATE            *** HIGHEST RISK. DO FIRST. ***   |
   |      sm_120 kernels present, llama-server answers curl           |
   |      accept: arch_list contains sm_120                           |
   |              curl /v1/chat/completions returns 200               |
   |              nvidia-smi peak recorded under desktop load         |
   +--------------------------------+---------------------------------+
                                    |
                                    v
   +------------------------------------------------------------------+
   |  G2  EVAL HARNESS                                                |
   |      50 fixtures, runner, baseline score                         |
   |      accept: `just eval` prints a pass count. any count.         |
   +--------------------------------+---------------------------------+
                                    |
                                    v
   +------------------------------------------------------------------+
   |  G3  TEXT MODE + REGISTRY                                        |
   |      stdin -> grammar -> validate -> registry -> execve -> print |
   |      only open_app.  no audio.  no network.  no db.              |
   |      accept: eval >= 45/50, adversarial suite 12/12              |
   +--------------------------------+---------------------------------+
                                    |
                    +---------------+---------------+
                    |                               |
                    v                               v
   +-------------------------------+  +-------------------------------+
   |  G4  PERSISTENCE              |  |  G5  VOICE OUT                |
   |      sqlite WAL, 0600,        |  |      kokoro, voice locked,    |
   |      migrations, audit,       |  |      outcome templates spoken |
   |      export/delete/reset      |  |      accept: 20 utterances    |
   |      accept: concurrency test |  |      spoken, no clipping      |
   +---------------+---------------+  +---------------+---------------+
                   |                                  |
                   +---------------+------------------+
                                   |
                                   v
   +------------------------------------------------------------------+
   |  G6  VOICE IN                                                    |
   |      whisper CPU, PTT, mic gate, barge-in                        |
   |      accept: 20 spoken utterances -> correct action              |
   |              TTFA p95 measured and recorded                      |
   +--------------------------------+---------------------------------+
                                    |
                                    v
   +------------------------------------------------------------------+
   |  G7  SEARCH  (the only egress + the only untrusted input.)       |
   |      searxng loopback, sanitizer, final.gbnf locked to none      |
   |      accept: injection suite 20/20 blocked                       |
   |              zero actions dispatched from any grounding turn     |
   +--------------------------------+---------------------------------+
                                    |
                                    v
   +------------------------------------------------------------------+
   |  G8  CONVERSATION  (the primary goal. reordered before service.) |
   |      `chat` action + free-text gen stage, RAM dialogue buffer    |
   |      see docs/superpowers/specs/2026-08-23-conversational-chat-  |
   |      design.md.  accept: casual -> warm <=4-sentence reply,      |
   |              eval not regressed, chat can never dispatch         |
   +--------------------------------+---------------------------------+
                                    |
                                    v
   +------------------------------------------------------------------+
   |  G9  SERVICE                                                     |
   |      systemd user units, restart, log rotation, panic switch     |
   |      accept: survives kill -9 of llama-server                    |
   |              survives suspend/resume                             |
   +------------------------------------------------------------------+
```

## Explicitly NOT gates in Phase 1

```
    custom "Friday" wake word    -> Phase 2.  ADR-012.
    Hindi / Spanish              -> Phase 2.
    screen vision / VLM          -> Phase 3.
    voice cloning                -> needs hardware that does not exist here
    streaming TTFA optimization  -> after G6 measures the real number
    acoustic echo cancellation   -> only needed once a wake word exists
```

## Risk ordering — why G1 is first

```
   risk = probability x cost-to-discover-late

   CUDA sm_120 mismatch      HIGH  x  kills every later gate   = do first
   eval harness absent       HIGH  x  every change is guesswork = do second
   prompt injection          MED   x  cheap if designed in      = design now, build G7
   VRAM OOM                  LOW   x  measurable in 10 minutes  = measure at G1
   evdev permissions         LOW   x  isolated, replaceable     = do last
   wake word FA/FR tuning    HIGH  x  zero Phase 1 value        = cut entirely
```
