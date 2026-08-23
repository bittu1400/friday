from dataclasses import dataclass

from friday.llm import grounding, schema


@dataclass
class _StubClient:
    reply: str

    def complete(self, *, system, user, grammar, untrusted=False, **kw):
        # the grounding turn MUST pass the final grammar + untrusted=True
        assert untrusted is True
        assert grammar == schema.build_final_grammar()
        return self.reply


def test_ground_extracts_answer_from_params():
    reply = '{"action":{"name":"none","params":{"answer":"Paris is the capital."}}}'
    out = grounding.ground(_StubClient(reply), "capital of France?", ["France ... Paris"])
    assert out == "Paris is the capital."


def test_ground_strips_urls_from_the_spoken_answer():
    reply = '{"action":{"name":"none","params":{"answer":"See https://x.test now"}}}'
    out = grounding.ground(_StubClient(reply), "q", ["b"])
    assert "http" not in out and "x.test" not in out


def test_ground_falls_back_on_empty_answer():
    reply = '{"action":{"name":"none","params":{}}}'
    out = grounding.ground(_StubClient(reply), "q", ["b"])
    assert out == grounding.NO_ANSWER


def test_ground_falls_back_on_malformed_reply():
    out = grounding.ground(_StubClient("not json at all"), "q", ["b"])
    assert out == grounding.NO_ANSWER


def test_bodies_are_wrapped_as_untrusted():
    captured = {}

    class _Spy:
        def complete(self, *, system, user, grammar, untrusted=False, **kw):
            captured["user"] = user
            return '{"action":{"name":"none","params":{"answer":"ok"}}}'

    grounding.ground(_Spy(), "q", ["hostile body"])
    assert "<untrusted_data>" in captured["user"]
    assert "hostile body" in captured["user"]
