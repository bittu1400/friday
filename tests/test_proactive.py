import asyncio
import time
import pytest
from friday.proactive.briefing import is_signoff_phrase, generate_startup_briefing
from friday.proactive.dnd import DndManager, is_hush_phrase, is_resume_phrase
from friday.proactive.scheduler import Scheduler
from friday.store.db import Database
from friday.store.reminders import ReminderStore


@pytest.fixture(autouse=True)
def _no_desktop_notifications(monkeypatch):
    """The Scheduler shells out to `notify-send` for real. Under test that pops
    actual desktop notifications on the developer's machine (a running suite
    once spammed real 'pasta is ready' toasts). Stub it everywhere the tests
    can reach it so pytest has no side effect on the desktop."""
    import friday.proactive.scheduler as sched_mod
    import friday.proactive.notifier as notifier_mod

    monkeypatch.setattr(sched_mod, "notify", lambda *a, **k: True)
    monkeypatch.setattr(notifier_mod, "notify", lambda *a, **k: True)


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "memory.db")


def test_dnd_phrase_detection():
    assert is_hush_phrase("let's talk later")
    assert is_hush_phrase("Friday, please do not disturb")
    assert is_hush_phrase("be quiet for now")
    assert not is_hush_phrase("what is the weather today")

    assert is_resume_phrase("resume")
    assert is_resume_phrase("disable quiet mode")
    assert is_resume_phrase("talk to me")


def test_dnd_manager_state():
    dnd = DndManager(initial_dnd=False)
    assert not dnd.is_dnd
    dnd.set_dnd()
    assert dnd.is_dnd
    dnd.clear_dnd()
    assert not dnd.is_dnd


def test_signoff_phrase_detection():
    assert is_signoff_phrase("goodnight Friday")
    assert is_signoff_phrase("bye for now")
    assert is_signoff_phrase("good night")
    assert not is_signoff_phrase("open my editor")


def test_startup_briefing(db):
    store = ReminderStore(db)
    store.create(seconds=60, message="check bread")
    briefing = generate_startup_briefing(db)
    assert "Good day" in briefing
    assert "active timer" in briefing


def test_scheduler_fires_due_reminders(db):
    store = ReminderStore(db)
    dnd = DndManager()
    r = store.create(seconds=0.1, message="pasta is ready")

    fired = []

    async def _on_proactive(title: str, msg: str):
        fired.append((title, msg))

    sched = Scheduler(
        store=store,
        dnd=dnd,
        is_idle=lambda: True,
        on_event=_on_proactive,
        poll_interval_s=0.05,
    )

    async def go():
        task = asyncio.create_task(sched.run())
        await asyncio.sleep(0.3)
        sched.stop()
        await task

    asyncio.run(go())
    assert len(fired) == 1
    assert fired[0][1] == "pasta is ready"
    assert len(store.get_due(now=time.time())) == 0
