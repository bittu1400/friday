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


def test_habits_digest_is_passed_to_chat_generator():
    class _Spy:
        def complete(self, *, system, user, grammar="", untrusted=False, **kw):
            if grammar == "":
                self.seen_system = system
                return "Sure!"
            return '{"action":{"name":"chat","params":{}}}'
    spy = _Spy()
    habits = "<user_habits>\n- After opening Brave, you often open VS Code.\n</user_habits>"
    asyncio.run(turn_mod.run_turn("any suggestions?", spy, request_id="c3",
                                  habits_digest=habits))
    assert "After opening Brave, you often open VS Code" in spy.seen_system
    assert "observed user habits" in spy.seen_system


def test_summaries_digest_is_passed_to_chat_generator():
    class _Spy:
        def complete(self, *, system, user, grammar="", untrusted=False, **kw):
            if grammar == "":
                self.seen_system = system
                return "Sure!"
            return '{"action":{"name":"chat","params":{}}}'
    spy = _Spy()
    summaries = "<past_sessions>\n- User worked on Python in VS Code.\n</past_sessions>"
    asyncio.run(turn_mod.run_turn("what were we doing?", spy, request_id="c4",
                                  summaries_digest=summaries))
    assert "User worked on Python in VS Code" in spy.seen_system
    assert "distilled summaries of past sessions" in spy.seen_system


