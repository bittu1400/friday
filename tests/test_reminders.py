import time
import pytest
from friday.store.db import Database
from friday.store.reminders import Reminder, ReminderStore


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
