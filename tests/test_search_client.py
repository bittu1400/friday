import io
import json
import urllib.error

import pytest

from friday.tools.search import SearchClient, SearchResult, SearchUnavailable


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _fake_json(payload):
    def _open(req, timeout=None):
        return _Resp(json.dumps(payload).encode())
    return _open


def test_query_parses_results(monkeypatch):
    payload = {"results": [
        {"title": "A", "url": "https://a.test", "content": "alpha"},
        {"title": "B", "url": "https://b.test", "content": "beta"},
    ]}
    monkeypatch.setattr("urllib.request.urlopen", _fake_json(payload))
    client = SearchClient(base_url="http://127.0.0.1:8888", timeout_s=8.0)
    out = client.query("hello")
    assert out == [
        SearchResult("A", "https://a.test", "alpha"),
        SearchResult("B", "https://b.test", "beta"),
    ]


def test_query_wraps_network_error(monkeypatch):
    def _boom(req, timeout=None):
        raise urllib.error.URLError("no route")
    monkeypatch.setattr("urllib.request.urlopen", _boom)
    client = SearchClient(base_url="http://127.0.0.1:8888", timeout_s=8.0)
    with pytest.raises(SearchUnavailable):
        client.query("hello")


def test_query_wraps_malformed_body(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _Resp(b"not json"))
    client = SearchClient(base_url="http://127.0.0.1:8888", timeout_s=8.0)
    with pytest.raises(SearchUnavailable):
        client.query("hello")
