"""Turn orchestration: fail-closed planning and execute-first dispatch.
Uses a stub client, so no llama-server is needed."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class StubClient:
    reply: str

    def complete(self, *, system: str, user: str, grammar: str) -> str:
        return self.reply

    def health(self) -> bool:
        return True


def _turn(reply: str, *, dry_run: bool = True):
    from friday.turn import run_turn

    return asyncio.run(
        run_turn(
            "whatever", StubClient(reply), request_id="t", dry_run=dry_run
        )
    )


def test_malformed_output_fails_closed_to_none() -> None:
    r = _turn("not json at all")
    assert r.plan_name == "none" and not r.dispatched
    assert r.spoken == "I didn't understand."


def test_valid_none_does_not_dispatch() -> None:
    r = _turn('{"action":{"name":"none","params":{}}}')
    assert r.plan_name == "none" and not r.dispatched


def test_none_speaks_out_of_scope_line() -> None:
    from friday.ui import templates
    r = _turn('{"action":{"name":"none","params":{}}}')
    assert r.plan_name == "none" and not r.dispatched
    assert r.spoken == templates.OUT_OF_SCOPE
    assert r.spoken != "(no action)"


# NOTE: NOT_YET_WIRED is empty as of G7 (web_search is now wired in the turn
# loop). The web_search path — which never dispatches — is covered by
# tests/test_web_search_turn.py; there is no "planned …" fallback left to test.


def test_open_app_dispatches_via_template() -> None:
    r = _turn('{"action":{"name":"open_app","params":{"app":"browser"}}}')
    assert r.plan_name == "open_app" and r.dispatched
    assert r.spoken.startswith("Opened Brave")
