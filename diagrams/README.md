# Diagrams

ASCII only. Renders in any terminal, diffs cleanly in git, never rots
into a stale PNG nobody can edit.

```
   00-system-overview.md    processes, hardware, who owns what resource
   01-turn-lifecycle.md     the FSM.  one turn at a time, ever.
   02-tool-call-loop.md     the trust boundary.  read this one twice.
   03-memory-budget.md      VRAM and RAM arithmetic with real numbers
   04-trust-boundaries.md   zones 0-3 and the privilege ladder
   05-audio-pipeline.md     signal path + half-duplex mic gate
   06-build-gates.md        G0..G8 dependency order and risk ranking
   07-context-budget.md     8192 tokens, region by region
```

## Rule

A diagram that disagrees with the code is a bug in the diagram. Fix it in
the same commit as the code change. These are not documentation-of-record
for a past state; they are the current map.
