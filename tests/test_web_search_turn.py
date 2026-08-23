import asyncio
from dataclasses import dataclass

import pytest

from friday.tools.search import SearchResult, SearchUnavailable
from friday.ui import templates
from friday import turn as turn_mod


class _PlanClient:
    """Returns a web_search plan first, then a grounding answer."""
    def __init__(self):
        self._n = 0

    def complete(self, *, system, user, grammar, untrusted=False, **kw):
        self._n += 1
        if untrusted:
            return '{"action":{"name":"none","params":{"answer":"Sunny, 25C."}}}'
        return '{"action":{"name":"web_search","params":{"query":"weather"}}}'


class _StubSearch:
    def __init__(self, results=None, boom=False):
        self._results = results or [SearchResult("T", "https://s.test", "weather data")]
        self._boom = boom

    def query(self, q):
        if self._boom:
            raise SearchUnavailable("down")
        return self._results


def _run(**kw):
    return asyncio.run(turn_mod.run_turn(
        "what's the weather", _PlanClient(), request_id="t1",
        search_client=kw.pop("search_client", _StubSearch()),
        connected=kw.pop("connected", True), **kw))


def test_web_search_connected_speaks_grounded_answer():
    r = _run()
    assert r.plan_name == "web_search"
    assert r.spoken == "Sunny, 25C."
    assert r.dispatched is False           # web_search never dispatches
    assert [s.url for s in r.sources] == ["https://s.test"]


def test_web_search_local_mode_refuses():
    r = _run(connected=False)
    assert r.dispatched is False
    assert "local mode" in r.spoken.lower()
    assert r.sources == () or list(r.sources) == []


def test_web_search_network_failure_speaks_fallback():
    # SearchUnavailable maps to E_NET_DOWN -> the spec-locked SEARCH_UNAVAILABLE
    # template ("I can't reach the web."); assert the template, not a substring.
    r = _run(search_client=_StubSearch(boom=True))
    assert r.dispatched is False
    assert r.spoken == templates.SEARCH_UNAVAILABLE
