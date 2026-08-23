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
    # ADR-052: the PLANNER (grammar != "") must also see the recent conversation
    # so follow-ups like "open that" resolve. Capture the planning call's system.
    d = Dialogue()
    d.add("open brave", "Opened Brave.")
    seen = {}

    class _Spy(_ChatClient):
        def complete(self, *, system, user, grammar="", untrusted=False, **kw):
            if grammar != "":                       # the planning call
                seen["system"] = system
            return super().complete(system=system, user=user, grammar=grammar,
                                     untrusted=untrusted, **kw)

    asyncio.run(turn_mod.run_turn(
        "open that", _Spy(), request_id="w2", history=d.render()))
    assert "<recent_conversation>" in seen["system"]
    assert "Opened Brave." in seen["system"]        # prior turn is in context
