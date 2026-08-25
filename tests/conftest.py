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
