import asyncio

from friday.dialogue import Dialogue
from friday import turn as turn_mod


class _ChatClient:
    def complete(self, *, system, user, grammar="", untrusted=False, **kw):
        if grammar == "":
            return "Hi Subham!"
        return '{"action":{"name":"chat","params":{}}}'


def test_turn_reads_history_and_caller_appends():
    # Simulates what the daemon/TUI do: render history in, append the result.
    d = Dialogue()
    d.add("earlier", "context line")
    seen = {}

    class _Spy(_ChatClient):
        def complete(self, *, system, user, grammar="", untrusted=False, **kw):
            if grammar == "":
                seen["user"] = user
            return super().complete(system=system, user=user, grammar=grammar,
                                     untrusted=untrusted, **kw)

    r = asyncio.run(turn_mod.run_turn(
        "hello", _Spy(), request_id="w1", history=d.render()))
    assert "context line" in seen["user"]          # history flowed in
    d.add("hello", r.spoken)                        # caller appends
    assert len(d) == 2 and "Hi Subham!" in d.render()


def test_history_reaches_the_planner_system(monkeypatch):
    # ADR-052 + ADR-065: the PLANNER must be able to see the recent
    # conversation so follow-ups like "open that" resolve — but only on the
    # SECOND pass. The first pass is asked without history, and history is
    # brought in exactly when the user's own words planned to `none`.
    d = Dialogue()
    d.add("open brave", "Opened Brave.")
    plans = []

    class _Spy(_ChatClient):
        def complete(self, *, system, user, grammar="", untrusted=False, **kw):
            if grammar != "":                       # a planning call
                plans.append(system)
                # first pass (no history) cannot resolve "open that"
                if "<recent_conversation>" not in system:
                    return '{"action":{"name":"none","params":{}}}'
                return '{"action":{"name":"open_app","params":{"app":"browser"}}}'
            return super().complete(system=system, user=user, grammar=grammar,
                                     untrusted=untrusted, **kw)

    r = asyncio.run(turn_mod.run_turn(
        "open that", _Spy(), request_id="w2", history=d.render()))

    assert len(plans) == 2, "planner must be asked without history first"
    assert "<recent_conversation>" not in plans[0]
    assert "<recent_conversation>" in plans[1]
    assert "Opened Brave." in plans[1]              # prior turn is in context
    # ADR-065: history resolved it, so it is CONFIRMED, never dispatched.
    assert r.dispatched is False
    assert r.pending is not None and r.pending.tool_id == "open_app"


def test_action_in_the_users_own_words_is_not_confirmed():
    """ADR-065 must not add a confirm to a plain command. Only an action that
    appears solely because history was in the prompt is held back."""
    class _Direct(_ChatClient):
        def complete(self, *, system, user, grammar="", untrusted=False, **kw):
            if grammar != "":
                return '{"action":{"name":"open_app","params":{"app":"browser"}}}'
            return super().complete(system=system, user=user, grammar=grammar,
                                     untrusted=untrusted, **kw)

    d = Dialogue()
    d.add("earlier", "context line")
    r = asyncio.run(turn_mod.run_turn(
        "open my browser", _Direct(), request_id="w3", dry_run=True,
        history=d.render()))
    assert r.pending is None
    assert r.plan_name == "open_app"


def test_bare_greeting_never_dispatches_from_history():
    """The measured bug: after Friday proposed VS Code and asked 'Ready to
    start coding?', a bare 'hey jarvis' dispatched open_app{editor} 4/4. The
    first pass sees only the user's words, which are a greeting -> chat."""
    calls = []

    class _Greeting(_ChatClient):
        def complete(self, *, system, user, grammar="", untrusted=False, **kw):
            if grammar != "":
                calls.append(system)
                # Without history it is plainly a greeting; WITH history the
                # model would answer Friday's own question and open the editor.
                if "<recent_conversation>" not in system:
                    return '{"action":{"name":"chat","params":{}}}'
                return '{"action":{"name":"open_app","params":{"app":"editor"}}}'
            return "Hello!"

    d = Dialogue()
    d.add("hey jarvis", "Let's open VS Code. Ready to start coding?")
    r = asyncio.run(turn_mod.run_turn(
        "hey jarvis", _Greeting(), request_id="w4", history=d.render()))

    assert len(calls) == 1, "a chat plan must not be re-planned with history"
    assert r.plan_name == "chat"
    assert r.dispatched is False and r.pending is None
