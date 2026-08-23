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


def test_not_yet_wired_action_is_not_dispatched() -> None:
    r = _turn('{"action":{"name":"web_search","params":{"query":"weather"}}}')
    assert r.plan_name == "web_search" and not r.dispatched
    assert "planned" in r.spoken


def test_open_app_dispatches_via_template() -> None:
    r = _turn('{"action":{"name":"open_app","params":{"app":"browser"}}}')
    assert r.plan_name == "open_app" and r.dispatched
    assert r.spoken.startswith("Opened Brave")
