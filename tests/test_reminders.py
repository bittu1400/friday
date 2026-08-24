import asyncio
import time
import pytest
from friday.store.db import Database
from friday.store.prefs import PrefStore
from friday.store.reminders import Reminder, ReminderStore
from friday.turn import _do_set_reminder, _humanize_duration, _parse_reminder_seconds


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "memory.db")


@pytest.fixture
def store(db):
    return ReminderStore(db)


def test_create_and_get_due_reminders(store):
    now = time.time()
    r1 = store.create(seconds=10, message="check the oven", kind="timer")
    r2 = store.create(seconds=60, message="call mom", kind="reminder")

    assert r1.state == "active"
    assert r1.message == "check the oven"
    assert r1.kind == "timer"

    # Immediately, none are due
    due = store.get_due(now=now)
    assert len(due) == 0

    # At now + 15s, r1 is due but not r2
    due_15 = store.get_due(now=now + 15)
    assert len(due_15) == 1
    assert due_15[0].id == r1.id

    # Mark fired
    store.mark_fired(r1.id)
    assert len(store.get_due(now=now + 15)) == 0


def test_list_active_and_cancel(store):
    r1 = store.create(seconds=30, message="drink water")
    r2 = store.create(seconds=40, message="stretch")

    active = store.list_active()
    assert len(active) == 2

    cancelled = store.cancel(r1.id)
    assert cancelled is True

    active_after = store.list_active()
    assert len(active_after) == 1
    assert active_after[0].id == r2.id

    # Cancelling again returns False
    assert store.cancel(r1.id) is False


def test_parse_reminder_seconds():
    assert _parse_reminder_seconds("300") == 300.0
    assert _parse_reminder_seconds("90.5") == 90.5
    # garbled / missing / non-positive -> None (means "ask", never guess)
    assert _parse_reminder_seconds("") is None
    assert _parse_reminder_seconds("soon") is None
    assert _parse_reminder_seconds("0") is None
    # Non-digits are stripped (so "300 seconds" works), and a zero-length or
    # non-positive result asks rather than guesses.
    assert _parse_reminder_seconds("300 seconds") == 300.0


def test_humanize_duration():
    assert _humanize_duration(1) == "1 second"
    assert _humanize_duration(30) == "30 seconds"
    assert _humanize_duration(60) == "1 minute"
    assert _humanize_duration(300) == "5 minutes"
    assert _humanize_duration(3600) == "1 hour"


def test_set_reminder_unparseable_asks_and_creates_nothing(store, db):
    prefs = PrefStore(db)
    res = asyncio.run(_do_set_reminder({"seconds": "umm", "message": "check pasta"}, prefs, None, "r1"))
    assert res.dispatched is False
    assert "didn't catch how long" in res.spoken.lower()
    assert store.list_active() == []  # nothing was set on a mishear


def test_set_reminder_natural_confirmation_with_task(store, db):
    prefs = PrefStore(db)
    res = asyncio.run(_do_set_reminder({"seconds": "300", "message": "check the pasta"}, prefs, None, "r2"))
    assert res.dispatched is True
    assert res.spoken == "Okay, I'll remind you to check the pasta in 5 minutes."
    assert len(store.list_active()) == 1


def test_set_reminder_bare_timer_no_task(store, db):
    prefs = PrefStore(db)
    res = asyncio.run(_do_set_reminder({"seconds": "60", "message": ""}, prefs, None, "r3"))
    assert res.dispatched is True
    assert res.spoken == "Timer set for 1 minute."
