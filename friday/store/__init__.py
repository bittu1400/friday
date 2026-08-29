"""Persistence layer (G4): the single-writer SQLite store, preferences,
audit, and retention. Nothing here touches CUDA and nothing binds a socket
(T6/ADR-018); it is local disk state only.
"""


def prompt_digests(db) -> tuple[str, str]:  # noqa: ANN001 - store.db.Database
    """The `(habits, recent sessions)` digest pair the planning prompt carries.

    Both UIs need exactly this, and both were computing it inline on their event
    loop — two synchronous SQLite reads per turn, one of which scans 30 days of
    audit rows (audit H6). It lives here, in the store layer, so the daemon and
    the TUI can each hand it to `asyncio.to_thread` without the UI importing the
    daemon.
    """
    from .habits import mine_habits, render_habits_digest
    from .summarizer import get_recent_session_summaries, render_summaries_digest

    return (
        render_habits_digest(mine_habits(db)),
        render_summaries_digest(get_recent_session_summaries(db, limit=2)),
    )
