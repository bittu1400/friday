from friday.llm import chat


class _Stub:
    def __init__(self, reply): self._reply = reply
    def complete(self, *, system, user, grammar="", temperature=0.0,
                 max_tokens=128, stop=None, untrusted=False):
        self._system, self._user = system, user
        assert grammar == ""            # chat is the free-text path
        assert temperature > 0          # not the deterministic planner
        return self._reply


def test_returns_sanitized_reply():
    out = chat.generate_reply(_Stub("Sure thing!"), "hey")
    assert out == "Sure thing!"


def test_strips_markdown_urls_control():
    dirty = "Check **this** out https://x.test now\x07"
    out = chat.generate_reply(_Stub(dirty), "q")
    assert "**" not in out and "http" not in out and "x.test" not in out
    assert "\x07" not in out
    assert "this" in out and "out" in out


def test_empty_output_falls_back():
    assert chat.generate_reply(_Stub("   "), "q") == chat.CHAT_FALLBACK


def test_exception_falls_back():
    class _Boom:
        def complete(self, **kw): raise RuntimeError("server down")
    assert chat.generate_reply(_Boom(), "q") == chat.CHAT_FALLBACK


def test_history_and_utterance_reach_the_prompt():
    stub = _Stub("ok")
    chat.generate_reply(stub, "and my editor?", history="You: hi\nFriday: Hello!")
    assert "and my editor?" in stub._user
    assert "Hello!" in stub._user


def test_length_is_capped():
    assert chat._MAX_CHARS == 200
    huge = "word " * 500
    out = chat.generate_reply(_Stub(huge), "q")
    assert len(out) <= chat._MAX_CHARS
