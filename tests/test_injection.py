"""G7 injection suite (IS-1..IS-20, spec §5.3 / FR-63).

The hard guarantee, asserted structurally with no model: even if the grounding
reply is fully compromised — echoing an action-shaped string a hostile search
result tried to induce — the `web_search` path produces ZERO executor
dispatches. The grammar lock (final.gbnf, name=="none") + the turn returning
dispatched=False unconditionally are what make this true; this test proves the
executor is never reached, by spying on it.
"""

import asyncio
import json
from pathlib import Path

from friday import turn as turn_mod
from friday.tools import executor as executor_mod
from friday.tools.search import SearchResult

FIX = Path(__file__).parent / "fixtures" / "injection.jsonl"


def _load():
    return [json.loads(ln) for ln in FIX.read_text().splitlines() if ln.strip()]


class _InjectingClient:
    """Plans web_search, then (as the grounding turn) returns whatever the
    hostile body tried to make it say — wrapped as a none-action whose answer
    carries the attack. The point: even a compromised grounding reply must not
    dispatch."""
    def __init__(self, hostile: str):
        self._hostile = hostile

    def complete(self, *, system, user, grammar, untrusted=False, **kw):
        if untrusted:
            return ('{"action":{"name":"none","params":{"answer":'
                    + json.dumps(self._hostile) + "}}}")
        return '{"action":{"name":"web_search","params":{"query":"q"}}}'


class _Search:
    def __init__(self, body):
        self._body = body

    def query(self, q):
        return [SearchResult("t", "https://s.test", self._body)]


def test_no_injection_fixture_dispatches(monkeypatch):
    calls = []

    async def _spy(spec, params, request_id, dry_run=False):
        calls.append(getattr(spec, "tool_id", spec))
        raise AssertionError("executor must never run for a grounding turn")

    monkeypatch.setattr(executor_mod, "execute", _spy)

    blocked = 0
    for fx in _load():
        r = asyncio.run(turn_mod.run_turn(
            "question", _InjectingClient(fx["body"]), request_id=fx["id"],
            search_client=_Search(fx["body"]), connected=True))
        assert r.dispatched is False, fx["id"]
        assert r.plan_name == "web_search", fx["id"]
        blocked += 1
    assert blocked == 20
    assert calls == []  # zero dispatches, asserted on the executor
