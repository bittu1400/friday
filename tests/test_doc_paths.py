"""A path a document tells you to run must be the path the code uses (D36).

`docs/reality-check.md` §G1 and `progress.md`'s START HERE block both hand the
next session a `sqlite3` command to prove FIRST_USE fired. Both named
`~/.local/share/friday/memory.db`, which is where the MODELS live;
`config.MEMORY_DB` is under `XDG_STATE_HOME`. The failure is silent in the worst
possible direction — `sqlite3` CREATES an empty database at a missing path and
then answers `no such table: approvals`, which reads exactly like a FIRST_USE
that never fired. It cost a session on 2026-09-04 and left a stray zero-byte
file behind.

This is M-L4's shape (a DB check that created the database it then reported on)
having moved out of the code and into the instructions, where no test was
looking. ADR-042 wrote a coupling down in prose and prose prevented nothing;
`tests/test_stt_hotwords.py` exists for the same reason. So does this.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from friday import config

REPO = Path(__file__).resolve().parent.parent

#: Documents that RECORD rather than instruct. An ADR must be able to quote the
#: wrong path as the defect it describes — ADR-127 does exactly that, and this
#: test caught it, which is the right behaviour for the wrong file. `adr.md` is
#: excluded for the same reason `docs/archive/` is: nobody runs a command out of
#: a decision record, and forbidding the wrong value there would forbid writing
#: down what went wrong.
_RECORDS = {"adr.md"}

#: Every tracked document that carries runnable commands.
DOCS = sorted(
    p for p in [*REPO.glob("*.md"), *(REPO / "docs").glob("*.md")]
    if "archive" not in p.parts and p.name not in _RECORDS
)

#: The two documents that actually hand the next session a `sqlite3` command.
#: Named explicitly so this file cannot pass by the commands being DELETED —
#: a check that only forbids a wrong value goes green when the value goes away.
RUNBOOKS = ("docs/reality-check.md", "progress.md")

#: Any `~/...` or `$HOME/...` path ending in the database filename the code
#: actually opens. Deliberately keyed to `MEMORY_DB.name` and not to "any
#: friday .db": a document may legitimately name a DIFFERENT .db under a friday
#: directory — `progress.md` tells the owner to `rm` a stray
#: `~/.local/share/friday/friday.db` that this audit created, and that path is
#: correct precisely because it is not the database. The defect being pinned is
#: narrower and exact: wherever a runbook says `memory.db`, it must say the
#: right `memory.db`.
_DB_PATH = re.compile(
    r"(?:~|\$HOME)/[\w./$-]*" + re.escape(config.MEMORY_DB.name)
)


def _expected() -> str:
    """`config.MEMORY_DB` written the way a document writes it."""
    return "~/" + str(config.MEMORY_DB.relative_to(Path.home()))


def test_the_expected_path_is_the_one_the_code_actually_opens():
    """Guard the guard: if `MEMORY_DB` moves, this test must move with it
    rather than keep asserting a stale string."""
    assert _expected().endswith("/memory.db")
    assert config.MEMORY_DB.is_absolute()


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(REPO)))
def test_no_document_names_a_database_path_the_code_does_not_use(doc):
    want = _expected()
    for lineno, line in enumerate(doc.read_text().splitlines(), 1):
        for found in _DB_PATH.findall(line):
            assert found == want, (
                f"{doc.relative_to(REPO)}:{lineno} names {found!r}; "
                f"config.MEMORY_DB is {want!r}. sqlite3 CREATES an empty "
                f"database at a wrong path and then reports 'no such table' "
                f"— the failure is silent (D36)."
            )


@pytest.mark.parametrize("doc", RUNBOOKS)
def test_the_runbooks_still_carry_the_command_they_are_pinned_for(doc):
    """Guard against passing by deletion. Both documents hand the next session
    a `sqlite3 … approvals` command (§G1 step 5; START HERE step 1), and this
    file's whole value is that those commands name the right database."""
    text = (REPO / doc).read_text()
    assert _expected() in text, f"{doc} no longer names {_expected()}"
    assert "approvals" in text
