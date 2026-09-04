# Diagram 07 — Context Window Budget (8192 tokens)

Every region has a hard cap enforced in code. Truncation happens per
region, with a visible marker, in a fixed priority order. Policy text is
never truncated — if the budget cannot fit policy, the turn fails closed.

> **The `600` in the bar below is the DESIGN allocation and the live value is
> `1401`** (measured 2026-09-04). The overage is real and it is affordable:
> 1401 + 300 + 1500 + 4500 + 1000 = 8701 against an 8192 window, but the
> untrusted region is present ONLY on grounding turns and the conversation ring
> is a cap rather than a floor, so no single turn assembles all five at maximum.
> The prefix is also already cached (`cache_n 1222` of 1235, `gemma-brief.md`
> §5), so the policy region costs prompt-processing time once, not per turn.
> **Do not "fix" this by compressing the prompt inside another change** — see
> the SYSTEM POLICY note below for why that is its own commit.

```
   token 0                                                        8192
     |                                                              |
     +--------+---------+--------+----------------+-------+---------+
     | SYSTEM | MEMORY  | UNTRUS | CONVERSATION   | RSVD  | OUTPUT  |
     | POLICY | DIGEST  | -TED   | HISTORY        | slack | reserve |
     |        |         | DATA   |                |       |         |
     | 1401*  |   300   |  1500  |     4500       |  292  |   1000  |
     |  *live |         |        |                |       |         |
     +--------+---------+--------+----------------+-------+---------+
      never    trim by   hard     evict oldest     -       hard stop
      trim     priority  cap      turn pairs               at 1000
      FAIL     then drop TRUNCATE                          new tokens
      CLOSED   lowest    + mark
```

## Region rules

```
   SYSTEM POLICY       1401 tok   Static. Identity, action contract,
                                  refusal rules. MEASURED 2026-09-04 via
                                  llama-server /tokenize -- the "600, and
                                  a unit test fails past it" written here
                                  was aspirational and no such test ever
                                  existed. What DOES exist since Phase 3
                                  criterion 3.3 is stronger and different:
                                  the block is DERIVED, one `summary` per
                                  capability, and the whole 5381-character
                                  string is pinned byte-for-byte against
                                  tests/fixtures/system_policy.txt.

                                  It grew because it had to: ADR-118's
                                  twelve-line open_app paragraph is the D31
                                  fix, and E61-E64 test it. Compressing it
                                  is deliberately its own commit (ADR-125)
                                  -- inside a behaviour-freeze refactor an
                                  intended change and a regression look
                                  identical. Design §1.2's real ceiling is
                                  ~40 capabilities, after which the fix is
                                  to GROUP them (system.*, window.*, ...)
                                  and let the planner choose a family then
                                  a member. Because `summary` is a field,
                                  that is a rendering change, not a rewrite.

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
