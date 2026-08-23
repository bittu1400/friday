import pytest

from friday.llm import schema
from friday.llm.client import LlamaClient


def test_untrusted_request_rejects_non_final_grammar():
    """Invariant #1: a turn carrying untrusted data MUST use final.gbnf. The
    check lives in the client so every request passes through it. It raises
    (not asserts) so `python -O` cannot strip this T1 control."""
    client = LlamaClient()
    plan_grammar = schema.build_grammar()  # the full action enum — forbidden here
    with pytest.raises(ValueError):
        client.complete(system="s", user="u", grammar=plan_grammar, untrusted=True)


def test_trusted_request_allows_plan_grammar(monkeypatch):
    # a normal planning turn (untrusted=False) is unaffected; stub the network
    def _fake(req, timeout=None):
        import io, json
        class _R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): self.close()
        return _R(json.dumps(
            {"choices": [{"message": {"content": "{}"}}]}).encode())
    monkeypatch.setattr("urllib.request.urlopen", _fake)
    client = LlamaClient()
    out = client.complete(system="s", user="u", grammar=schema.build_grammar())
    assert out == "{}"
