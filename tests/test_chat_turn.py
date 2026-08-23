import asyncio

from friday import turn as turn_mod
from friday.tools import executor as executor_mod


class _ChatClient:
    def complete(self, *, system, user, grammar="", untrusted=False, **kw):
        if grammar == "":                       # stage 2 (chat)
            return "Hello! How can I help?"
        return '{"action":{"name":"chat","params":{}}}'   # planner


def _run(**kw):
    return asyncio.run(turn_mod.run_turn(
        "hi there", _ChatClient(), request_id="c1", **kw))


def test_chat_plan_routes_to_generator_and_speaks():
    r = _run()
    assert r.plan_name == "chat"
    assert r.spoken == "Hello! How can I help?"
    assert r.dispatched is False


def test_chat_never_calls_executor(monkeypatch):
    called = []
    async def _spy(*a, **k): called.append(1)
    monkeypatch.setattr(executor_mod, "execute", _spy)
    _run()
    assert called == []


def test_history_is_passed_through():
    class _Spy:
        def complete(self, *, system, user, grammar="", untrusted=False, **kw):
            if grammar == "":
                self.seen_user = user
                return "ok"
            return '{"action":{"name":"chat","params":{}}}'
    spy = _Spy()
    asyncio.run(turn_mod.run_turn("and my editor?", spy, request_id="c2",
                                  history="You: hi\nFriday: Hello!"))
    assert "Hello!" in spy.seen_user
