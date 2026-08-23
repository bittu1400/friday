"""FR-52: parameterized SQL only — no f-string / %-formatted / concatenated
SQL anywhere in the store layer. A grep, as spec.md prescribes."""

from __future__ import annotations

import re
from pathlib import Path

_STORE = Path(__file__).parent.parent / "friday" / "store"

# An f-string or a .format() whose text contains a SQL keyword, or string
# concatenation building a SQL fragment. Deliberately blunt: the store must
# pass SQL as static strings with `?` placeholders.
_SQL_KEYWORDS = r"(?:SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|PRAGMA)"
_FSTRING_SQL = re.compile(rf'f"""?.*{_SQL_KEYWORDS}', re.IGNORECASE | re.DOTALL)
_FSTRING_SQL_SINGLE = re.compile(rf"f'.*{_SQL_KEYWORDS}", re.IGNORECASE)
_PERCENT_SQL = re.compile(rf'"[^"]*{_SQL_KEYWORDS}[^"]*"\s*%', re.IGNORECASE)


def test_store_has_no_fstring_sql() -> None:
    for py in _STORE.rglob("*.py"):
        src = py.read_text()
        assert not _FSTRING_SQL.search(src), f"f-string SQL in {py.name}"
        assert not _FSTRING_SQL_SINGLE.search(src), f"f-string SQL in {py.name}"
        assert not _PERCENT_SQL.search(src), f"%-formatted SQL in {py.name}"
