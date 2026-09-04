"""The first-use allowlist (Phase 3, criterion 3.9; design §3.3).

Criterion 3.9's acceptance is one sentence: *a test changes the argv behind an
approved id and asserts Friday asks again*. That is
`test_an_approval_does_not_survive_a_changed_argv`, and it is not a
hypothetical — `desktop.app_key` resolves a collision with `setdefault`, first
wins, so an uninstall-then-install really can rebind an id to another binary.
"""

from __future__ import annotations

import time

import pytest

from friday.store.approvals import ApprovalStore, fingerprint
from friday.store.audit import sweep_retention
from friday.store.db import Database


@pytest.fixture()
def store(tmp_path) -> ApprovalStore:
    return ApprovalStore(Database(tmp_path / "friday.db"))


def test_nothing_is_approved_until_a_handshake_records_it(store) -> None:
    h = fingerprint(("brave",))
    assert store.is_approved("app", "browser", h) is False
    store.approve("app", "browser", h)
    assert store.is_approved("app", "browser", h) is True


def test_an_approval_does_not_survive_a_changed_argv(store) -> None:
    """Criterion 3.9. The id is the same; the binary behind it is not."""
    store.approve("app", "browser", fingerprint(("brave",)))
    assert store.is_approved("app", "browser", fingerprint(("brave",))) is True
    # Uninstall Brave, install something else that normalises to `browser`.
    assert store.is_approved("app", "browser", fingerprint(("firefox",))) is False
    # And re-approving replaces rather than accumulating.
    store.approve("app", "browser", fingerprint(("firefox",)))
    assert store.is_approved("app", "browser", fingerprint(("firefox",))) is True
    assert store.is_approved("app", "browser", fingerprint(("brave",))) is False
    assert len(store.list_approvals()) == 1


def test_the_fingerprint_cannot_confuse_one_argument_with_two(store) -> None:
    """`\\x00` cannot occur in an argv element; a space can. Joining on a space
    would make `("mpv --idle",)` and `("mpv", "--idle")` the same approval."""
    assert fingerprint(("mpv --idle",)) != fingerprint(("mpv", "--idle"))


def test_an_approval_is_scoped_to_its_kind(store) -> None:
    h = fingerprint(("x",))
    store.approve("app", "timeshift", h)
    assert store.is_approved("recipe", "timeshift", h) is False


def test_only_the_keyboard_revokes(store) -> None:
    store.approve("app", "browser", fingerprint(("brave",)))
    store.approve("app", "editor", fingerprint(("code",)))
    assert store.forget("app", "browser") == 1
    assert store.is_approved("app", "browser", fingerprint(("brave",))) is False
    assert len(store.list_approvals()) == 1
    assert store.reset() == 1
    assert store.list_approvals() == []


def test_retention_never_sweeps_an_approval(store) -> None:
    """An approval is user intent, like a preference — not machine exhaust.
    Aged a year past the 90-day cutoff and swept; it must still be there."""
    db = store._db
    db.write(
        "INSERT INTO approvals(kind, subject, argv_sha256, approved_at)"
        " VALUES (?, ?, ?, ?)",
        ("app", "browser", fingerprint(("brave",)), int(time.time()) - 365 * 86400),
    )
    sweep_retention(db, retention_days=90)
    assert store.is_approved("app", "browser", fingerprint(("brave",))) is True


def test_the_panic_switch_blocks_the_approval_write_not_just_the_launch(
    tmp_path, monkeypatch
) -> None:
    """Design §3.2, and it survived its first mutation.

    Recording the grant before the panic check leaves nothing red: the launch
    is still blocked by the executor and the spoken line is still "I'm switched
    off.". What changes is that the machine comes back on having quietly agreed
    to something while it was supposed to be doing nothing at all — the exact
    shape of F1, where a switch that stops SOME things is worse than none
    because it is trusted.
    """
    import asyncio

    from friday import config
    from friday.turn import PendingAction, resolve_pending

    monkeypatch.setattr(config, "is_disabled", lambda: True)
    approvals = ApprovalStore(Database(tmp_path / "a.db"))

    spoken = asyncio.run(resolve_pending(
        PendingAction("open_app", {"app": "browser"}, "open Brave"), "yes",
        prefs=None, audit=None, request_id="t", dry_run=True, approvals=approvals,
    ))
    assert spoken == "I'm switched off."
    assert approvals.list_approvals() == [], "a disabled machine recorded consent"
