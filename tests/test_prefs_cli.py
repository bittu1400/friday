"""The `prefs` CLI (FR-56): list, export, forget (soft/--hard), reset --yes."""

from __future__ import annotations

import json

from friday.prefs_cli import main
from friday.store.db import Database
from friday.store.prefs import PrefStore, resolve


def _seed(tmp_path):
    db = tmp_path / "memory.db"
    s = PrefStore(Database(db))
    s.put(resolve("name", "Subham"))
    s.put(resolve("editor", "code"))
    return db


def test_list(tmp_path, capsys) -> None:
    db = _seed(tmp_path)
    assert main(["--db", str(db), "list"]) == 0
    out = capsys.readouterr().out
    assert "name=Subham" in out and "editor=code" in out


def test_export_json(tmp_path, capsys) -> None:
    db = _seed(tmp_path)
    assert main(["--db", str(db), "export"]) == 0
    assert json.loads(capsys.readouterr().out) == {"editor": "code", "name": "Subham"}


def test_forget_soft(tmp_path, capsys) -> None:
    db = _seed(tmp_path)
    assert main(["--db", str(db), "forget", "name"]) == 0
    # soft: gone from active, row survives
    assert PrefStore(Database(db)).active() == {"editor": "code"}
    assert Database(db).query("SELECT COUNT(*) AS n FROM preferences")[0]["n"] == 2


def test_forget_hard(tmp_path) -> None:
    db = _seed(tmp_path)
    assert main(["--db", str(db), "forget", "name", "--hard"]) == 0
    assert Database(db).query("SELECT COUNT(*) AS n FROM preferences")[0]["n"] == 1


def test_forget_unknown_returns_1(tmp_path) -> None:
    db = _seed(tmp_path)
    assert main(["--db", str(db), "forget", "nope"]) == 1


def test_reset_requires_yes(tmp_path) -> None:
    db = _seed(tmp_path)
    assert main(["--db", str(db), "reset"]) == 2  # refused
    assert PrefStore(Database(db)).active() != {}


def test_reset_yes(tmp_path) -> None:
    db = _seed(tmp_path)
    assert main(["--db", str(db), "reset", "--yes"]) == 0
    assert PrefStore(Database(db)).active() == {}
