# Friday — Test-Suite Mutation Audit

**Date:** 2026-09-03
**Scope:** all 81 files in `tests/` (526 test functions, 581 collected tests,
9 196 LOC against 9 250 LOC of source) measured against `friday/`.
**Method:** 85 single-line defects injected into the source one at a time; the
full suite run against each; the tree reverted with `git checkout -- .` between
every one. **A mutation that leaves the suite green SURVIVED — that line is
unprotected. One that turns it red was KILLED.**
**Revision under test:** `ef6b8e4`. Baseline `581 passed, rc=0` in 6.7 s,
verified before and after every round. Working tree clean at exit; **no source
file was left modified and no test was added.**
**Question being audited:** *do these tests protect trust, or manufacture it?*

Companion: `audit-2026-09-02.md` audited the code. This file audits the thing
that is supposed to be watching the code. Where a finding here overlaps one
there, the F-number is named.

---

## A. Verdict

**Mutation score 66 % — 56 killed, 29 survived.** The suite is real, not
decoration: 526 test functions, effectively zero assertion-free tests
(3 flagged, all 3 false positives — two are "must not raise", one is a
fixture), and `test_injection.py`'s executor spy genuinely bites.

But it has one consistent shape, and it explains every hole:

> **The suite tests functions. It does not test wiring.**

Where a defect once bit and left a scar, the test drives the real path end to
end and nothing can be removed without turning it red. Everywhere else the test
calls a unit directly and never asks whether anything actually calls that unit.
That is how the ban list can be unhooked from the executor, how three confirm
gates can be deleted, and how `just eval` can stop gating — all with 581
passing.

**This is the tenth time in this project a green check has sat on a live
defect, and the first time the count was obtained by measurement instead of by
being bitten.**

## B. The pattern, which is the finding

Mutation score by module. It is not random — it tracks whether that module has
a defect number behind it.

| module | mutations | killed | score | has a live-defect history? |
| :-- | --: | --: | --: | :-- |
| `daemon.py` | 2 | 2 | **100 %** | H5, FR-5, D14 |
| `audio/vad.py` | 5 | 5 | **100 %** | **D3** |
| `tools/desktop.py` | 4 | 4 | **100 %** | ADR-114a |
| `store/db.py` | 4 | 4 | **100 %** | M-T2, M-T3 |
| `store/audit.py` | 3 | 3 | **100 %** | **D2**, D23 |
| `turn.py` · affirmation | 3 | 3 | **100 %** | **D1, D25** |
| `llm/client.py` | 2 | 2 | **100 %** | invariant #1 |
| `tools/typer.py` | 1 | 1 | **100 %** | **D22** |
| `logging_config.py` | 2 | 2 | **100 %** | **H8** |
| `llm/validate.py` | 8 | 6 | 75 % | AS-1…AS-12 |
| `audio/wake.py` | 7 | 5 | 71 % | OQ-29, ADR-113 |
| `tools/search.py` | 7 | 5 | 71 % | G7 injection suite |
| `tools/ban.py` | 5 | 3 | 60 % | ADR-097 (pkexec) |
| `tools/executor.py` | 6 | 3 | 50 % | M-T1, ADR-073 |
| `registry.py` · youtube | 4 | 2 | 50 % | ADR-027 |
| `selftest.py` | 2 | 1 | 50 % | F20 |
| `turn.py` · confirm gates | 5 | 2 | 40 % | — |
| `config.py` | 5 | 2 | 40 % | — |
| `llm/grounding.py` | 4 | 1 | 25 % | — |
| `eval_harness.py` | 4 | 0 | **0 %** | F23 |
| `audio/speaker.py` | 2 | 0 | **0 %** | — |
| **total** | **85** | **56** | **66 %** | |

Every module at 100 % has a D-number, an H-number or a microphone session
behind it. Every module below 60 % was tested once, at build time, by someone
who already knew how it worked.

**The suite is a fossil record of what has already hurt.** That is a good
property and it is why the regressions this project has paid for really are
pinned. It is also exactly why it cannot tell you what will hurt next.

## C. How to read the findings

- **M-numbers** are this audit's findings. **D-numbers** are the project defect
  ledger, **F-numbers** the 2026-09-02 code audit, **H/M-*** the 2026-08-26
  audit. No M-number is a code defect: every one is a *missing test*. The code
  under it is currently correct.
- **Severity is about what the missing test lets through silently**, not about
  today's behaviour. Nothing here is presently broken in `friday/`.
- Every survivor is reproducible: the mutation is quoted verbatim and can be
  applied with one `sed`.
- **A no-op control mutation (an identical string replacement) was included and
  correctly survived**, which is the evidence that the harness reported real
  results rather than noise.

---

## D. Findings

### Tier 1 — a hard invariant can be removed silently

#### M1 — Three of the five confirm gates have no arming test — INVARIANT #10

`system_wifi{off}`, `clipboard_set` and `hypr_window{close}` each have their
confirm branch in `turn.py` deleted with the suite green.

```
turn.py:  if plan.name == "system_wifi" and params.get("state") == "off":  ->  if False:
          if plan.name == "clipboard_set":                                 ->  if False:
          if plan.name == "hypr_window" and params.get("action") == "close": -> if False:
```

**Demonstrated, not inferred.** All three deleted at once, then real turns
driven through `run_turn` — the same way `tests/test_clipboard_confirm.py`
does it:

```
                             armed confirm?   dispatched?  spoken
BASELINE
turn off the wifi            True             False        'Are you sure you want to turn off Wi-Fi?'
copy hello to clipboard      True             False        'Are you sure you want to overwrite your clip'
close this window            True             False        'Are you sure you want to close the active wi'
what is in my clipboard      True             False        'Do you want me to read your clipboard aloud?'

GATES DELETED
turn off the wifi            False            True         'Wi-Fi off.'
copy hello to clipboard      False            False        "I can't do that yet."
close this window            False            True         'Window close.'
what is in my clipboard      True             False        'Do you want me to read your clipboard aloud?'

581 passed, 2 warnings in 6.27s
```

**Why `clipboard_read` survives the cull and the other three do not.**
`tests/test_clipboard_confirm.py` drives `run_turn` end to end with a stub
client and asserts `r.pending.tool_id == "clipboard_read"`, `not r.dispatched`,
and that the clipboard was **not even read**. The other three have tests only
for *resolving* a `PendingAction` that the test itself constructs by hand
(`tests/test_daemon.py:503`, `tests/test_audit_contract.py:110`). Nothing
anywhere asserts that the turn **arms** one.

`clipboard_set` degrades to *"I can't do that yet."* rather than dispatching
because it has no registry entry — less severe, same missing test.

**These are the exact rows the 2026-08-30 evening microphone session existed to
prove.** They were proven by voice and are pinned by nothing.

#### M2 — Nothing asserts the executor consults the ban list — INVARIANT #10

```
executor.py:  assert_not_banned(argv)  ->  pass
```

The whole permanent destructive-command denylist stops being consulted at
dispatch. Green — and specifically green across the suites that exist for this:

```
$ pytest -q tests/test_executor.py tests/test_action_surface.py \
           tests/test_open_app_scope.py tests/test_adversarial.py tests/test_injection.py
42 passed in 0.51s
```

`tests/test_action_surface.py` unit-tests `assert_not_banned` thoroughly.
`tests/test_executor.py` tests the executor thoroughly. **No test crosses
between them.** The one `Outcome.DENIED` assertion in `test_executor.py:90`
comes from the YouTube charset policy inside `build_argv`, not from the ban
list.

#### M3 — The `rm` denylist entry is the one entry its test cannot protect — INVARIANT #10

```
ban.py:  "rm", "rmdir",  ->  "rmdir",
```

Green. And `tests/test_action_surface.py:9-11` **does** feed `["rm","-rf","/"]`.
It passes anyway, because that argv is *also* caught by the `"rm -"` entry in
`BANNED_SUBSTRINGS` — two rules fire and the assertion cannot tell which.
Measured, per input in that loop:

```
  rm -rf /         binary=True  substring=['rm -']   BOTH -> the binary rule is redundant here
  pacman -rf /     binary=True  substring=[]         binary only
  yay/dd/mkfs/sh/bash/sudo/shutdown -rf /            binary only
```

Only `rm` is double-covered, and `rm` is the most dangerous entry in the set.
With it removed, an argv with no dash and no metacharacter passes the gate:

```
  rm /home/bittusah/notes.db       binary=True  substring=[]     <- rejected only by the binary rule
  dd of=/dev/nvme0n1               binary=True  substring=[]     <- same
```

**Rule this establishes:** a denylist entry needs a test argv that *only that
rule* rejects. A test that passes through two rules proves one of them at most.

#### M4 — The subprocess environment is never read by any test — INVARIANT #3

```
executor.py:  env=dict(spec.env)  ->  env=None
```

Every launched process inherits the daemon's full environment instead of the
minimal explicit one FR-32 promises. Green. This is the same surface as **F4**
(one explicit subprocess env), which is deferred to Phase 3 — so the Phase 3
work will land on a line with no test under it.

#### M5 — `SpeakerVerifier.verify()` is called by no test in the repository

```
speaker.py:  return score >= th, score  ->  return True, score      # accepts every impostor
             return score >= th, score  ->  return score < th, score # rejects the owner
```

Both survive. `grep -rn "\.verify(" tests/` returns **nothing**.

`tests/test_speaker.py::test_speaker_verifier_mock` constructs
`SpeakerVerifier(model_path=None, voiceprint=ref)` and then **never calls it** —
the local is assigned and unused. Its assertions run `cosine_similarity()`
directly against two synthetic vectors, which `test_cosine_similarity` twenty
lines above already covers. The test is named after the object it does not
exercise.

**Mitigating and worth stating:** speaker verification is **off by default**
(`FRIDAY_SPEAKER_VERIFY_ENABLE`) and fails **open** with no voiceprint
enrolled, so today's blast radius is small. The finding is that the G13
accept/reject decision has never been executed by a test, in either direction.

### Tier 2 — the gates that guard the gates

These matter out of proportion to their blast radius: they are what the project
trusts when it trusts everything else.

#### M6 — The eval gate is entirely untested — 0 of 4

```
eval_harness.py:
  if regressions or unbaselined_fails or (total > 0 and pass_pct < 90):  ->  if False:
  if prev.get(r.fid, False):                                             ->  if False:
  elif r.fid not in prev and not r.known_failing:                        ->  elif False:
  pass_pct < 90                                                          ->  pass_pct < 0
```

All four survive. `just eval` can be made to always exit 0; regressions against
the baseline can stop being detected; a failing newly-added fixture can stop
being counted; the ≥90 % floor can be removed. **Nothing in the suite touches
`eval_harness.main()`'s exit condition.**

The third of these is **F23's exact shape**. F23 was fixed in code — the
`unbaselined_fails` branch and the 90 % floor both exist and both work — but no
test was added, so the fix can silently regress. *A fix without a FAIL-path test
is a fix with a countdown on it.*

#### M7 — Selftest's FAIL path does not set the exit code, and nothing notices

```
selftest.py:  has_fail = True  ->  has_fail = False
```

Survives. A FAILing check no longer produces exit 1. This is **F20's own
defect, re-armed** — and the asymmetry is the interesting part:
`has_warn = True -> False` was **KILLED**. OQ-62's WARN→exit-2 fix got a test;
the FAIL→exit-1 path that has existed since G9 never did.

`just selftest` is the command every session is told to run first.

### Tier 3 — hardening layers removable without trace

Lower severity: in each case another layer still catches the attack. But
defence in depth stops being depth once a layer can be removed undetectably.

| M | mutation | what it removes |
| :-- | :-- | :-- |
| **M8** | `grounding.py`: `_CONTROL.sub(" ", answer)` / `_MD.sub(" ", answer)` / `unicodedata.normalize("NFKC", answer)` → `answer` | Three of the four cleaners on the spoken answer built from untrusted web text. Only URL stripping is tested. `grounding.py` scores **25 %**, the worst in the tree |
| **M9** | `search.py`: `text = _CONTROL.sub(" ", text)` / `text = _MD.sub(" ", text)` → `pass` | Two of the five cleaners on untrusted result bodies. NFKC, markup and zero-width **are** tested |
| **M10** | `registry.py`: `if parsed.scheme != "https" or parsed.netloc != "www.youtube.com":` → `if False:`; `unicodedata.normalize("NFKC", query)` → `query` | The netloc re-assertion and confusable folding on **the project's one audited exception to invariant #2** (ADR-027). The charset whitelist itself **is** tested |
| **M11** | `validate.py`: `unicodedata.normalize("NFKC", value)` → `value`; `if not isinstance(obj, dict)` → `if False and …` | AS-9 confusable folding, and failing closed on a non-object JSON top level. The closed enum still rejects, so this is depth not the wall |
| **M12** | `ban.py`: `if not argv:` → `if False:` | An empty argv passes the gate instead of raising |
| **M13** | `executor.py`: `shutil.which(target) is None` → `False` | The missing-binary preflight; failure moves to the spawn instead |

### Tier 4 — constants with no test, listed for completeness

| M | constant | judgement |
| :-- | :-- | :-- |
| **M14** | `MAX_CAPTURE_S: int = 15` → `600` | **Arguably a real gap.** FR-4 calls this a *hard cap*; a spec'd hard cap deserves a test that a tuning knob does not |
| **M15** | `VAD_END_SILENCE_S`, `RETENTION_DAYS`, `WakeListener(threshold=0.5)`, `refractory_s=1.5` | Probably correct to leave free. The **logic** consuming each is fully tested — every wake-gating, VAD and retention-sweep mutation was killed — so only the default values float, and pinning a tuning knob in a test is usually worse than leaving it |

### Tier 5 — structural findings, found by reading rather than by mutation

#### M16 — `tests/test_service_unit.py` reads the repo file, not the running system

All six checks parse `deploy/systemd/friday.service` from disk
(`tests/test_service_unit.py:24,29,92`). None asks `systemctl` anything.

The checks are not *wrong* — the file is what they claim to verify. But they
cannot catch the failure this project has already been bitten by: **the
installed unit is a symlink to the repo file**, so it always matches, while
`systemctl show` reported `Type=simple`, `WatchdogUSec=0`,
`NeedDaemonReload=yes`. `Type=notify` and `WatchdogSec=10s` were committed,
documented and **never once executed**. A file-reading test would have passed
throughout.

Of all 81 test files, **only `tests/test_egress.py` shells out to the live
system** (`tests/test_egress.py:158,165`). Everything else that touches
`subprocess` mocks it.

Whether to change this is a real decision, not a bug — see **OQ-66**.

#### M17 — Removing `start_new_session=True` kills the test runner, not the suite

The one mutation excluded from the 85. `start_new_session=True` → `False` in
`executor.py` caused the harness process itself to be SIGKILLed (exit 137)
rather than producing a test failure.

That is `_kill_group`'s `os.killpg(os.getpgid(proc.pid), SIGKILL)` reaching out
of the child and into the runner's own process group once detachment is
removed. Worth knowing before anyone tests that line, and a small argument that
`_kill_group` deserves a test which asserts *what* it kills.

### Tier 6 — documentation drift found while verifying the docs against the tree

#### M18 — `progress.md` understated `test_service_unit.py` by one check

The `>>> START HERE <<<` gate block said
`tests/test_service_unit.py # 5 passed -- the unit directives`. Measured: **6
passed**. `CLAUDE.md` said 6 and was right. Fixed 2026-09-03.

#### M19 — The app-enum size is pinned in prose, but the enum is generated from the machine

`CLAUDE.md` and `progress.md` state **162** app ids in two places. Measured
today: **165** (5 curated + 160 scanned). Nothing is broken — ADR-097 generates
the enum from the machine's XDG desktop entries, so the number moves whenever an
application is installed or removed.

**Pinning it in prose was the defect.** The docs now state the shape (curated +
scanned, generated at import) and give the count as an observation with its
date, not as a fact. Fixed 2026-09-03.

---

## E. What is genuinely strong

Reported because an audit that lists only failures is its own kind of dishonest.
These held against everything thrown at them.

| suite | evidence |
| :-- | :-- |
| `tests/test_injection.py` | Spies on `executor.execute` **via the module attribute**, and `turn.py` reaches it the same way (`from .tools import executor` … `executor.execute(...)`), so the monkeypatch really does bite — the classic hollow-spy failure was checked for and is absent. Asserts zero dispatches structurally with no model, and pins the fixture count at 20 |
| affirmation (D1 / D25) | 3 of 3 killed. Removing the negative-word veto, the head match, or the exact-match set each turns the suite red |
| daemon FSM + wake gating | 7 of 7 killed. FR-5 busy rejection, the dictation mute, idle gating, score gating and the ADR-113 abandon are pinned in **both** directions |
| `audio/vad.py` | 5 of 5, including both directions of the end-silence rule — the exact mechanism that was D3 |
| `store/db.py` | 4 of 4. Database mode, directory mode and WAL sidecar permissions each fail when loosened |
| `tools/desktop.py` | 4 of 4, including re-anchoring the field-code regex to `^%[a-zA-Z]$` — the ADR-114a bug — which is caught immediately |
| `llm/client.py` | 2 of 2. Invariant #1's `untrusted → final.gbnf` assertion cannot be removed |
| assertion hygiene | 526 test functions, 3 flagged as assertion-free, **all 3 false positives** |

---

## F. Findings index

| id | tier | one line | fix effort |
| :-- | :-- | :-- | :-- |
| **M1** | 1 | 3 of 5 confirm gates have no arming test — invariant #10 | 3 tests, ~40 lines |
| **M2** | 1 | Nothing asserts the executor calls the ban list | 1 test, ~15 lines |
| **M3** | 1 | The `rm` denylist entry is double-covered by its own test | 1 argv, ~2 lines |
| **M4** | 1 | The subprocess env is never read by a test — invariant #3 | 1 test, ~15 lines |
| **M5** | 1 | `SpeakerVerifier.verify()` is called by no test | 1 test, ~20 lines |
| **M6** | 2 | The eval gate is 0 % covered — it can stop gating | 1 test file, ~60 lines |
| **M7** | 2 | Selftest FAIL → exit 1 is untested (WARN → 2 is tested) | 1 test, ~15 lines |
| **M8** | 3 | 3 of 4 grounding-answer cleaners untested (25 %) | parametrise 1 test |
| **M9** | 3 | 2 of 5 search-body cleaners untested | parametrise 1 test |
| **M10** | 3 | YouTube netloc re-assertion + NFKC untested (ADR-027) | 2 asserts |
| **M11** | 3 | Validator NFKC + non-object top level untested | 2 asserts |
| **M12** | 3 | Empty argv passes the ban gate | 1 assert |
| **M13** | 3 | `which()` preflight untested | 1 assert |
| **M14** | 4 | `MAX_CAPTURE_S` — a spec'd hard cap (FR-4) with no test | 1 assert |
| **M15** | 4 | 4 tuning constants free — probably correct | none |
| **M16** | 5 | `test_service_unit.py` reads the file, not `systemctl` | decision — OQ-66 |
| **M17** | 5 | `start_new_session` mutation kills the runner, not the suite | note only |
| **M18** | 6 | `progress.md` said 5 unit checks; there are 6 | **FIXED** |
| **M19** | 6 | 162 app ids pinned in prose; generated enum is now 165 | **FIXED** |

## G. Decisions taken, and what was left to the owner

**Taken (method only, recorded as ADR-116):** mutation testing is how this
project measures its suite; mutations chosen by hand against the ten hard
invariants and the defect ledger rather than generated at random; full suite per
mutation; `git checkout -- .` between each; a no-op control included to prove
the harness.

**Left to the owner, because they are policy and not work — OQ-65, OQ-66,
OQ-67.** Ordering against Phase 3; whether the suite may ask the running system;
whether a mutation gate joins the definition of done.

**Not taken:** no test was written and no source line was changed. The tier-1
fixes are enumerated with their effort in §F and sequenced in `progress.md`'s
`>>> START HERE <<<` block. Writing them is the next session's first job if the
owner answers OQ-65 that way.

## H. What this audit did not do

- **Did not run a random mutation tool.** 85 hand-picked mutations weighted
  toward the invariants is a different measurement from `mutmut`'s exhaustive
  sweep, and **the 66 % is not comparable to a published mutation score.** An
  exhaustive run over `friday/` would find more survivors, most of them
  uninteresting.
- **Did not audit the eval fixtures for correctness** — only the harness that
  gates on them. E29's lesson (a fixture encoding a wrong belief) is unaddressed
  here.
- **Did not test the tests' own speed or flakiness.** The suite ran green 86
  times during this audit with no flake, which is itself a small result.
- **Did not touch `docs/superpowers/` or the archive.**
