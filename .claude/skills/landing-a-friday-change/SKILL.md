---
name: landing-a-friday-change
description: Use when changing code in the Friday repo — adding a capability, fixing a defect, touching a hard invariant, or about to report a change as done.
---

# Landing a change in Friday

## Overview

**A green gate is not a working feature.** Ten times in this project a full
suite passed over a dead feature: G13 enrollment dead on import, `clipboard_set`
speaking success while doing nothing, an `open_app` that could not reach 160 of
its 165 ids, a watchdog that had never fired, a `test-egress` that could not
observe a connection. Every one of them was green.

The suite tests functions. Defects live in the wiring between them, in the
deployment, and in the documents. This skill is the procedure that catches
those three.

## Adding a capability

Three pieces. Four separate tests fail if you forget one — that is Phase 3's
whole point, so do not hand-edit a derived site.

| Piece | File |
| :-- | :-- |
| One `Capability(...)` record | `friday/capabilities.py` |
| One handler row in `HANDLERS` | `friday/handlers.py` |
| ≥2 eval fixtures | `tests/fixtures/eval/` |

`PARAM_SCHEMA`, both grammars, both prompt regions, the confirm decision, the
panic gate and `STT_HOTWORDS` are **derived**. Editing them by hand is the
defect, not the fix.

Closed enum params belong in `plan.gbnf` (ADR-128). **`open_app.app` does not** —
the enum is generated from the machine, and a constrained `app` cannot fail
closed: instead of naming the id it could not find, the model gets forced into
some other legal id and opens the wrong application.

## The gate

```bash
uv run pytest -q && just eval && just grammar && just selftest
```

Assert the **relations**, not the counts (counts move every commit — read
`progress.md`'s `>>> START HERE <<<` block for today's numbers):

- `pytest` rc=0
- `just eval` — **regressions 0** and **unbaselined failures 0**
- `just grammar` — `.gbnf` still **byte-identical**
- `just selftest` — rc=0 (rc 2 is `[DEGRADED]`, a WARN, not a pass)

Touching security or the app enum? Add `just test-adversarial`,
`just test-injection`, `just test-egress`.

`uv` is not always on PATH — fall back to `.venv/bin/python -m pytest`. A failed
`uv run` inside a pipeline can still report exit 0.

## The mutation step (definition of done, line 6)

A change touching a hard invariant ships with a mutation of that line
**demonstrated** to turn the suite red. Not asserted — watched.

```bash
cp friday/turn.py /tmp/turn.py.bak     # NOT git checkout
# break the line, run the test, watch it fail
cp /tmp/turn.py.bak friday/turn.py
```

**`git checkout -- <file>` is the footgun.** It reverts the whole file. On
2026-09-04 it discarded ~700 lines of uncommitted refactor in one command,
mid-mutation-run. ADR-116's amendment already said so; reading the warning is
not the same as following it.

If the mutation stays green, the invariant is enforced by code nothing is
watching. That was M1–M5: three confirm gates armed nowhere, and
`assert_not_banned` deletable from the executor with the adversarial suite green.

## Two gates that lie by construction

**A new eval fixture can never regress.** Regression is
`prev.get(fid) and not passed`, so a fixture with no baseline entry is invisible
to the exit code (F23). After adding fixtures: read the `unbaselined failures`
line, then `just eval-baseline`.

**A test that forbids a wrong value goes green when the value is deleted.** Pin
the positive too. `tests/test_doc_paths.py` asserts the `sqlite3` command is
still *present*, not only that its path is right.

## Ask the system, not the code

The suite is hermetic by design; deployment and behaviour are live questions.

```bash
systemctl --user show friday | grep -E 'Type|Watchdog|NeedDaemonReload|NRestarts'
ps -o lstart= -p $(systemctl --user show -p MainPID --value friday)  # vs file mtimes
sqlite3 ~/.local/state/friday/memory.db 'SELECT * FROM action_audit ORDER BY rowid DESC LIMIT 5;'
```

The database is under `state`, **not `share`** — `share` holds the models, and
`sqlite3` on a missing path **creates an empty database** and then answers
`no such table`, which is indistinguishable from the thing you were trying to
disprove (D36).

Restart with `systemctl --user restart friday`. `kill <pid>` does nothing —
the unit is `Restart=always`. Never run `just voice` while the service is up.

## Red flags — stop

| Thought | Reality |
| :-- | :-- |
| "The suite is green, so it works" | Ten counterexamples. Exercise the real path. |
| "The ADR says it's implemented" | Three ADRs were mistaken for implementations (ADR-058, ADR-070, ADR-074). `grep` for the symbol. |
| "The log says the action ran" | The live-pass log read as though every confirm worked; `nmcli`, `wl-paste` and `action_audit` all said `declined`. |
| "I'll widen the enum, that's the fix" | A capability is named by five lists — enum, prompt, hotwords, fixtures, chat persona. D31 was two of them left behind. |
| "The docs say that area is fixed" | A doc records the fix, not the regression. Read the code cold; that found F2, F3, F21, then D35–D37. |
| "The ticket names one call site" | Grep for the class. `hyprctl dispatch` was known broken and its two siblings shipped broken anyway (ADR-074). |
| "I'll pin the count in the doc" | The app enum is generated. `162 → 165 → 167` in three days. State the shape and date the observation. |

## Recording it

Same commit, or it did not happen:

- evidence pasted into `progress.md` (command output, not "should work")
- a new decision → an ADR in `adr.md`; a new unknown → an OQ
- any diagram the change contradicts, fixed
- `progress.md`'s `>>> START HERE <<<` block re-pointed at the next job
