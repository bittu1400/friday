import io
import json

from friday.llm.client import LlamaClient


class _R(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): self.close()


def _capture(monkeypatch, reply="hi there"):
    seen = {}
    def _open(req, timeout=None):
        seen["payload"] = json.loads(req.data)
        return _R(json.dumps(
            {"choices": [{"message": {"content": reply}}]}).encode())
    monkeypatch.setattr("urllib.request.urlopen", _open)
    return seen


def test_empty_grammar_is_omitted_from_payload(monkeypatch):
    seen = _capture(monkeypatch)
    out = LlamaClient().complete(system="s", user="u", grammar="",
                                 temperature=0.7, stop=["\n\n"])
    assert out == "hi there"
    assert "grammar" not in seen["payload"]          # unconstrained
    assert seen["payload"]["temperature"] == 0.7
    assert seen["payload"]["stop"] == ["\n\n"]


def test_nonempty_grammar_still_sent(monkeypatch):
    seen = _capture(monkeypatch)
    LlamaClient().complete(system="s", user="u", grammar="root ::= \"x\"")
    assert seen["payload"]["grammar"] == 'root ::= "x"'
    assert "stop" not in seen["payload"]              # omitted when None
