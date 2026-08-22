# Diagram 07 — Context Window Budget (8192 tokens)

Every region has a hard cap enforced in code. Truncation happens per
region, with a visible marker, in a fixed priority order. Policy text is
never truncated — if the budget cannot fit policy, the turn fails closed.

```
   token 0                                                        8192
     |                                                              |
     +--------+---------+--------+----------------+-------+---------+
     | SYSTEM | MEMORY  | UNTRUS | CONVERSATION   | RSVD  | OUTPUT  |
     | POLICY | DIGEST  | -TED   | HISTORY        | slack | reserve |
     |        |         | DATA   |                |       |         |
     |  600   |   300   |  1500  |     4500       |  292  |   1000  |
     +--------+---------+--------+----------------+-------+---------+
      never    trim by   hard     evict oldest     -       hard stop
      trim     priority  cap      turn pairs               at 1000
      FAIL     then drop TRUNCATE                          new tokens
      CLOSED   lowest    + mark
```

## Region rules

```
   SYSTEM POLICY        600 tok   Static. Identity, action contract,
                                  refusal rules. Compiled at startup,
                                  asserted <= 600 by a unit test.
                                  If it grows past 600 the test fails
                                  and the build fails.

   MEMORY DIGEST        300 tok   From SQLite. Deterministic selection:
                                  ORDER BY (pinned DESC, updated_at DESC)
                                  LIMIT until 300 tokens.
                                  Rendered as DATA, never as instructions:

                                    <preferences>
                                    editor=code
                                    browser=brave
                                    name=Subham
                                    </preferences>

                                  NOT: "The user prefers you to always..."
                                  A stored preference must never be able
                                  to read like a system instruction.

   UNTRUSTED DATA      1500 tok   Present ONLY on grounding turns.
                                  Fenced, sanitized, capped.
                                  Its presence forces final.gbnf.

   CONVERSATION        4500 tok   Ring of (user, assistant) pairs.
                                  Evict oldest pair whole; never split
                                  a pair. Evicted content is gone —
                                  durable facts belong in SQLite.

   OUTPUT reserve      1000 tok   n_predict cap. Grammar makes overrun
                                  nearly impossible, but the cap stays.
```

## Truncation order when over budget

```
   1.  drop oldest conversation pairs   (until CONVERSATION fits)
   2.  drop lowest-priority preferences (until MEMORY fits)
   3.  truncate untrusted data + append "[truncated]"
   4.  still over?  ---->  FAIL CLOSED
                           action=none
                           speech="That's more than I can hold at once."
```

Never silently drop policy. Never silently drop the current user
utterance. A turn that cannot be represented honestly is refused, not
degraded.

## What changed from the original blueprint

```
   BEFORE                              AFTER
   ------                              -----
   ctx = 2048 (fear of KV overflow)    ctx = 8192, q8_0 KV, +224 MiB VRAM
   "inject a compact digest"           explicit 300-token region, capped
   no untrusted region at all          1500-token fenced region
   no truncation policy                priority order + fail-closed
   preferences as prose in prompt      preferences as key=value data
```

The 2048 cap was the load-bearing constraint behind most of the original
design's complexity. Pricing it (224 MiB) removed the constraint. See
ADR-003.
