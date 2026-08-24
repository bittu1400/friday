import pytest
from friday.store.db import Database
from friday.store.notes import Note, NoteStore


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "memory.db")


@pytest.fixture
def store(db):
    return NoteStore(db)


def test_create_and_list_notes(store):
    n1 = store.create("buy groceries: milk, eggs")
    n2 = store.create("call the dentist tomorrow")

    assert n1.content == "buy groceries: milk, eggs"
    assert n2.content == "call the dentist tomorrow"

    notes = store.list_notes()
    assert len(notes) == 2
    assert notes[0].id == n2.id  # most recent first
    assert notes[1].id == n1.id
