"""Suite-wide guards.

`notify()` shells out to a real `notify-send`. A test that reaches it pops a
real desktop toast on the developer's screen — which is exactly how the
phantom "pasta is ready" notifications appeared during a `pytest` run (the
reminders table was empty; the string lived only in a fixture). Stub it once,
autouse, so no test present or future can spam the desktop.

A test that wants to ASSERT on notifications monkeypatches its own recorder
over this one.
"""

import pytest

from friday.proactive import notifier


@pytest.fixture(autouse=True)
def _no_real_desktop_toasts(monkeypatch):
    monkeypatch.setattr(notifier, "notify", lambda *a, **k: True)


@pytest.fixture
def approved_apps(tmp_path):
    """An `ApprovalStore` in which every installed app is already approved.

    `open_app` is `Risk.FIRST_USE` for every id (ADR-120), so from Phase 3
    criterion 3.5 onward a turn that opens an app it has never opened before
    ARMS a confirm instead of dispatching. That is the intended behaviour and
    `tests/test_open_app_scope.py` is where it is asserted; a test that is
    about something ELSE — an audit row, the spoken template, recovering from
    a dead llama-server — passes this fixture so it reaches the dispatch it
    actually came to check.

    Tests ABOUT the gate build their own empty store, so approving everything
    here cannot hide a missing confirm.
    """
    from friday.store.approvals import ApprovalStore, fingerprint
    from friday.store.db import Database
    from friday.tools.apps import APPS

    store = ApprovalStore(Database(tmp_path / "approvals.db"))
    for key, app in APPS.items():
        store.approve("app", key, fingerprint(app.argv))
    return store
