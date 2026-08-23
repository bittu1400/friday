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
   PLANNING      10 s   -> ERROR "I'm having trouble thinking"
   CONFIRMING    30 s   -> cancel, back to IDLE, say nothing
   EXECUTING     per-tool, from registry (open_app 5 s, web_search 8 s)
   GROUNDING     10 s   -> speak degraded answer from raw tool result
   SPEAKING      interruptible by PTT press (barge-in = cancel playback,
                 drop the turn, go to CAPTURING — the user is already holding
                 the key to speak; FR-7, diagram 05, G6 daemon)
```

## The two rules this diagram exists to enforce

```
   1.  EXECUTING happens BEFORE SPEAKING.  Always.
       Never say "Opening Firefox" before Firefox actually opened.

   2.  GROUNDING can never reach EXECUTING.
       There is no arrow from GROUNDING back to EXECUTING and there
       never will be.  See diagram 02.
```
