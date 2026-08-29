# Diagram 01 — Turn Lifecycle (Finite State Machine)

One turn at a time. Ever. A second request while not `IDLE` is rejected
with an audible "one moment" and dropped — it is never queued behind a
turn the user has already stopped caring about.

```
                              +----------+
                +------------>|   IDLE   |<-------------------+
                |             +-----+----+                    |
                |                   |                         |
                |         PTT press / text submit             |
                |                   |                         |
                |                   v                         |
                |            +------+-------+                 |
                |            |  CAPTURING   |                 |
                |            |  max 15 s    |                 |
                |            |  mic OPEN    |                 |
                |            +------+-------+                 |
                |                   |                         |
                |         PTT release / VAD silence           |
                |                   |                         |
                |                   v                         |
                |            +------+-------+                 |
                |            | TRANSCRIBING |                 |
                |            | whisper CPU  |                 |
                |            | target 250ms |                 |
                |            +------+-------+                 |
                |                   |                         |
                |         empty or  |  text                   |
                |         garbage   |                         |
                |     +-------------+                         |
                |     |             v                         |
                |     |      +------+-------+                 |
                |     |      |   PLANNING   |                 |
                |     |      | llama-server |                 |
                |     |      | plan.gbnf    |                 |
                |     |      | target 900ms |                 |
                |     |      +------+-------+                 |
                |     |             |                         |
                |     |             v                         |
                |     |      +------+-------+                 |
                |     |      |  VALIDATING  |   reject        |
                |     |      | strict schema+---------+       |
                |     |      | + registry   |         |       |
                |     |      +------+-------+         |       |
                |     |             |                 |       |
                |     |     +-------+-------+         |       |
                |     |     |               |         |       |
                |     | needs confirm    safe         |       |
                |     |     |               |         |       |
                |     |     v               |         |       |
                |     | +---+---------+     |         |       |
                |     | | CONFIRMING  |     |         |       |
                |     | | typed y/n   |     |         |       |
                |     | | 30 s t/o    |     |         |       |
                |     | +---+-----+---+     |         |       |
                |     |     |     |         |         |       |
                |     |    yes    no        |         |       |
                |     |     |     |         |         |       |
                |     |     v     |         v         |       |
                |     | +---+-----+---------+---+     |       |
                |     | |      EXECUTING        |     |       |
                |     | |  execve, bounded      |     |       |
                |     | |  timeout per tool     |     |       |
                |     | +-----------+-----------+     |       |
                |     |             |                 |       |
                |     |    +--------+--------+        |       |
                |     |    |                 |        |       |
                |     | tool needs      terminal      |       |
                |     | 2nd turn        outcome       |       |
                |     |    |                 |        |       |
                |     |    v                 |        |       |
                |     | +--+-----------+     |        |       |
                |     | |  GROUNDING   |     |        |       |
                |     | | final.gbnf   |     |        |       |
                |     | | ACTION LOCKED|     |        |       |
                |     | | TO "none"    |     |        |       |
                |     | +--+-----------+     |        |       |
                |     |    |                 |        |       |
                |     |    +--------+--------+        |       |
                |     |             |                 |       |
                |     |             v                 v       |
                |     |      +------+-----------------+--+    |
                |     +----->|        SPEAKING           |    |
                |            |  mic MUTED (half duplex)  |    |
                |            |  kokoro CPU, chunked      |    |
                |            +-------------+-------------+    |
                |                          |                  |
                |                          +------------------+
                |
                |            +---------------------------+
                +------------+          ERROR            |
                             |  say user-safe message    |
                             |  log code, never raw exc  |
                             +---------------------------+
                                          ^
                                          |
                    any state on timeout / exception / cancel
```

## Timeouts (all enforced, all configurable, none infinite)

```
   CAPTURING     15 s hard stop
   TRANSCRIBING   5 s   -> ERROR "I didn't catch that"
   PLANNING      20 s   -> ERROR "I'm having trouble thinking".  `daemon.py`
                 `_PLANNING_TIMEOUT`.  It was 10 s in this diagram and 12 s in
                 the code; a web_search turn adds SearXNG (<=8 s, FR-64) plus
                 grounding on top of planning, and the search stage has its own
                 cap, so the turn cannot actually hang for 20 s
   CONFIRMING    30 s   -> drop the pending, say nothing. The FSM is NOT
                 reset: if the user is mid-answer the capture owns the machine
                 and finishes normally, and with no pending held that utterance
                 is simply a fresh command. Resetting here used to slam the mic
                 gate shut mid-answer (ADR-069 / audit M-P1)
   EXECUTING     per-tool `ToolSpec.timeout_s`, and it is REAL since ADR-073
                 (it was dead config until 2026-08-29).  A COMMAND is awaited
                 and its process GROUP killed on expiry; a LAUNCH keeps
                 ADR-043's 0.4 s fire-and-forget grace and is never killed,
                 because it must outlive the turn.  web_search 8 s (FR-64)
   GROUNDING     10 s   -> speak degraded answer from raw tool result
   SPEAKING      interruptible by PTT press (barge-in = cancel playback,
                 drop the turn, go to CAPTURING — the user is already holding
                 the key to speak; FR-7, diagram 05, G6 daemon).
                 An interrupted line counts as NOT DELIVERED: it does not enter
                 dialogue history, and if it was a confirm question no pending
                 is armed — the barged utterance is a command, never a yes/no
                 (ADR-069 / audit H3)
```

## The two rules this diagram exists to enforce

```
   1.  EXECUTING happens BEFORE SPEAKING.  Always.
       Never say "Opening Firefox" before Firefox actually opened.

   2.  GROUNDING can never reach EXECUTING.
       There is no arrow from GROUNDING back to EXECUTING and there
       never will be.  See diagram 02.
```
