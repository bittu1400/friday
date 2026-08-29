"""The two shapes the LLM client got wrong (audit M-L1, M-L2).

Both live on the error path of one `try`, which no fixture drove: every test in
the suite either talks to a healthy llama-server or does not talk to one at all.
"""

import json
import urllib.error

import pytest

from friday.llm.client import (
    LlamaClient,
    LlamaServerError,
    LlamaTimeout,
    LlamaUnreachable,
)


class _Resp:
    def __init__(self, payload: bytes | Exception):
        self._payload = payload

    def read(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch(monkeypatch, side_effect):
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req)
        if callable(side_effect):
            return side_effect(len(calls))
        raise side_effect

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return calls


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "http://127.0.0.1:8080/v1/chat/completions", code, "Server Error", {}, None
    )


def test_a_bare_timeout_becomes_LlamaTimeout_not_a_crashed_turn(monkeypatch):
    """M-L1: a slow generation can raise bare `TimeoutError`, which matched no
    handler here and none in `_plan` either — it propagated out of the turn and
    left the TUI's input disabled forever."""
    _patch(monkeypatch, TimeoutError("timed out"))
    with pytest.raises(LlamaTimeout):
        LlamaClient().complete(system="s", user="u")


def test_a_timeout_during_the_read_is_also_a_timeout(monkeypatch):
    """The connect succeeded; the body never arrived. Same verdict."""
    _patch(monkeypatch, lambda n: _Resp(TimeoutError("timed out")))
    with pytest.raises(LlamaTimeout):
        LlamaClient().complete(system="s", user="u")


def test_a_server_error_is_not_retried(monkeypatch):
    """M-L2: HTTPError subclasses URLError, so a 500 fell into the connect-retry
    branch — three generations against a server that answered, contradicting
    the module's own "retry ONLY on connect"."""
    calls = _patch(monkeypatch, _http_error(500))
    with pytest.raises(LlamaServerError):
        LlamaClient(connect_retries=3, connect_backoff_s=0).complete(system="s", user="u")
    assert len(calls) == 1


def test_a_client_error_is_not_retried_either(monkeypatch):
    calls = _patch(monkeypatch, _http_error(400))
    with pytest.raises(LlamaServerError):
        LlamaClient(connect_retries=3, connect_backoff_s=0).complete(system="s", user="u")
    assert len(calls) == 1


def test_a_server_error_is_still_caught_by_callers_watching_for_unreachable():
    """`turn._plan` maps LlamaUnreachable to E_LLM_DOWN. A server that answers
    500 is down for our purposes, so the new class narrows rather than escapes."""
    assert issubclass(LlamaServerError, LlamaUnreachable)


def test_a_real_connect_failure_is_still_retried(monkeypatch):
    """The retry that SHOULD happen must survive the fix."""
    calls = _patch(monkeypatch, urllib.error.URLError(ConnectionRefusedError()))
    with pytest.raises(LlamaUnreachable):
        LlamaClient(connect_retries=3, connect_backoff_s=0).complete(system="s", user="u")
    assert len(calls) == 3


def test_a_recovered_connect_still_returns(monkeypatch):
    payload = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

    def side_effect(n):
        if n == 1:
            raise urllib.error.URLError(ConnectionRefusedError())
        return _Resp(payload)

    _patch(monkeypatch, side_effect)
    got = LlamaClient(connect_retries=3, connect_backoff_s=0).complete(system="s", user="u")
    assert got == "ok"


def test_health_is_false_not_an_exception_when_the_read_times_out(monkeypatch):
    """A health check that raises is worse than one that says False: selftest
    would report a crash rather than an unhealthy server."""
    _patch(monkeypatch, lambda n: _Resp(TimeoutError("timed out")))
    assert LlamaClient().health() is False
