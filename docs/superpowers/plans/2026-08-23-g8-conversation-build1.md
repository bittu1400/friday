# G8 Conversation — Build 1 (in-reply, in-session chat) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a conversational reply path — a new `chat` action that routes to a free-text, model-generated spoken reply (warm/witty/concise JARVIS-ish, ≤4 sentences), with an in-RAM dialogue buffer for within-session context — so casual talk, greetings, "who are you", and suggestion-seeking get a real reply instead of silence, while commands and facts keep routing exactly as they do today.

**Architecture:** Two-stage, Approach A (design §"Approach"). The grammar-locked planning turn is UNCHANGED except that its closed action enum gains `chat` and its prompt narrows `none`. A new stage 2 (`friday/llm/chat.py`) runs ONLY when the planner selects `chat`: it calls the SAME llama-server with NO grammar (free text), temperature > 0, a stop sequence, and sanitizes the reply before TTS. A bounded in-memory `Dialogue` ring buffer (never on disk) gives within-session context. A `chat` turn consumes no untrusted data and can never dispatch an action.

**Tech Stack:** Python 3.12, `uv`, stdlib only (reuses the existing `LlamaClient` over HTTP), existing GBNF planner grammar, `pytest`. No new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-08-23-conversational-chat-design.md` (Build 1 slice). Also: `spec.md` §4 error taxonomy; `adr.md` ADR-009 (direct-action speech — carved out here by the new ADR-048), ADR-037 (confirm-first), ADR-008 (invariant #1); `CLAUDE.md` hard invariants #1/#4/#5/#6/#7/#9.

## Global Constraints

- **Invariant #1 (T1, ADR-008):** a turn that consumed untrusted web data uses `final.gbnf` and CANNOT dispatch. A `chat` turn consumes NO untrusted data; a defense-in-depth assert forbids entering `chat` on any turn flagged untrusted. `chat` never dispatches (no executor call, `dispatched=False` always).
- **Invariant #4 (ADR-009, FR-40):** direct-action speech comes from an outcome template, never the LLM. `chat` is NOT direct-action speech (it drives no side effect); ADR-048 carves out "conversational speech" as an explicitly-allowed, separate category. The action-outcome template rule is UNWEAKENED — command turns still speak from templates only.
- **Invariant #5 (ADR-006, FR-25):** grammar AND application-side validation; any failure fails closed to `action=none`. The planner stays grammar-locked; `chat` is added to BOTH the grammar and the validator.
- **Invariant #6 (ADR-018):** only llama-server touches CUDA. Chat reuses the SAME llama-server — no second model in VRAM.
- **Invariant #7 (FR-26/57):** raw transcripts / raw model output are NEVER written to disk. The `Dialogue` buffer is in-memory only, discarded on exit.
- **Invariant #9 (FR-5):** one turn in flight, enforced by the FSM — unchanged.
- **NFR (design):** fast and memory-lean — small context (persona + inert prefs digest + ~8 turns of dialogue), well inside ctx 8192; no extra dependency; reuse the running server.
- **Eval no-regression:** `just eval` currently 24/24. E15/E16 (greetings, currently `none`) MOVE to `chat` (this task's own change); E17/E18 (destructive) and E19 (ambiguous app) stay `none`. After the fixture update + re-baseline, all fixtures must pass.
- **`none` now SPEAKS (design open-item #4, decided 2026-08-23):** each terminal restriction gets a DISTINCT spoken line so the operator can tell live *why* there was no action. Deliberate in-scope `none` → an out-of-scope line; malformed/validation → "I didn't understand."; timeout → "That took too long."; unreachable → "My brain's offline."; panic/disabled → existing template.
- Style: Python 3.12, `frozen=True` dataclasses where immutable, type hints on every public function, one error code from the taxonomy (never speak/log a raw exception), comments explain *why*.

---

### Task 1: ADR-048 + the `chat` action in schema, grammar, validator

**Files:**
- Modify: `adr.md` (add ADR-048)
- Modify: `friday/llm/schema.py:35-47` (`PARAM_SCHEMA`)
- Regenerate: `friday/llm/grammars/plan.gbnf` (via `just grammar`)
- Test: `tests/test_schema.py` (already asserts committed grammars match — will pass after regen), `tests/test_validate.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `"chat"` is a valid action name with `PARAM_SCHEMA["chat"] == {}` (no params); `validate('{"action":{"name":"chat","params":{}}}')` returns `Plan(name="chat", params={})`; `build_grammar()` includes `chat` in the name alternatives.

- [ ] **Step 1: Write ADR-048** (the decision that authorizes model-generated conversational speech — do this first; it gates the gate)

In `adr.md`, append:
```markdown
## ADR-048 — Conversational speech is a distinct, allowed category (G8)

**Status:** Accepted 2026-08-24.

**Context:** ADR-009 forbids the LLM from producing *direct-action* speech —
Friday must never say "Opened Brave" from the model, because a model that
speaks the outcome can announce a success that did not happen. G8 introduces
conversation, which is model-generated speech.

**Decision:** Carve out "conversational speech" as an explicitly-allowed
category, distinct from direct-action speech. A `chat` reply is generated by
the model and spoken. This does NOT weaken ADR-009: command turns still speak
ONLY from outcome templates (execute-first, then template). The distinction is
side effects — a `chat` turn drives none. A `chat` turn consumes no untrusted
data and cannot dispatch an action (invariant #1 holds by construction; a
defense-in-depth assert forbids `chat` on any untrusted-flagged turn).

**Consequences:** A new free-text path exists (`friday/llm/chat.py`, no
grammar, temperature > 0). Its output is sanitized before TTS (no markup/URLs/
control chars, length-capped). The planner's command-vs-chat decision stays in
the grammar-locked stage; only after the planner has chosen `chat` does free
text get generated. See the G8 design doc.
```

- [ ] **Step 2: Write the failing validator test**

`tests/test_validate.py` — add:
```python
def test_chat_action_validates_with_empty_params():
    from friday.llm.validate import validate, Plan
    plan = validate('{"action":{"name":"chat","params":{}}}')
    assert plan == Plan(name="chat", params={})


def test_chat_rejects_unknown_params():
    from friday.llm.validate import validate, SchemaError
    import pytest
    with pytest.raises(SchemaError):
        validate('{"action":{"name":"chat","params":{"x":"y"}}}')
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/test_validate.py -k chat -v`
Expected: FAIL — `unknown action name: 'chat'` (chat not yet in `PARAM_SCHEMA`).

- [ ] **Step 4: Add `chat` to `PARAM_SCHEMA`**

In `friday/llm/schema.py`, inside `PARAM_SCHEMA`, add after the `"none"` entry:
```python
        # Conversational reply (G8, ADR-048). No params: stage 2 uses the
        # transcript the caller already holds — the model does not pass the
        # utterance through a field. Routed in turn.py to llm/chat.py, never
        # to the executor; can never dispatch.
        "chat": MappingProxyType({}),
```
(Order matters — the grammars are byte-reproducible. Put `chat` immediately after `none` and regenerate.)

- [ ] **Step 5: Regenerate the grammars**

Run: `just grammar`
Expected: prints "wrote …/plan.gbnf and final.gbnf". `plan.gbnf`'s `name ::=` line now includes `"\"chat\""`; `final.gbnf` is UNCHANGED (`FINAL_ACTIONS == ("none",)`).

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_validate.py tests/test_schema.py -v`
Expected: PASS. `test_schema.py` regenerates the grammars in-memory and asserts they match the committed files — green confirms no drift.

- [ ] **Step 7: Commit**

```bash
git add adr.md friday/llm/schema.py friday/llm/grammars/plan.gbnf tests/test_validate.py
git commit -m "feat(g8): chat action in schema+grammar+validator; ADR-048 conversational speech"
```

---

### Task 2: Planner prompt — route `chat` vs `none` vs `web_search`

**Files:**
- Modify: `friday/llm/prompt.py:17-52` (`SYSTEM_POLICY`)
- Test: `tests/test_prompt.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `SYSTEM_POLICY` describes when to choose `chat` (casual talk, greetings, "who/what are you", how-are-you, suggestion-seeking, talk about Friday's own apps/prefs/machine) vs `none` (genuine refusals: destructive/system-changing, or a truly ambiguous request) vs `web_search` (real-world facts). `assemble_system("")` still equals `SYSTEM_POLICY` byte-for-byte (test_prompt invariant holds trivially — it compares to the same constant).

- [ ] **Step 1: Write the failing test**

`tests/test_prompt.py` — add:
```python
def test_policy_mentions_chat_routing():
    from friday.llm.prompt import SYSTEM_POLICY
    low = SYSTEM_POLICY.lower()
    assert "chat" in low                       # the action is named
    assert "greeting" in low or "chit-chat" in low or "conversation" in low
    # none is narrowed to genuine refusals/ambiguity, not casual talk
    assert "destructive" in low or "refuse" in low
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_prompt.py -k chat_routing -v`
Expected: FAIL — `chat` not in the policy yet.

- [ ] **Step 3: Edit `SYSTEM_POLICY`**

In `friday/llm/prompt.py`, change the `none` line and add a `chat` line. Replace the current `none` entry:
```python
  none                 a truly ambiguous request, or ANY request to delete, \
destroy, or run shell commands, or anything outside your abilities. Refuse \
those by choosing none. params: {}
  chat                 casual conversation, greetings ("hi", "how are you"), \
questions about YOU (who/what are you, what can you do), small talk, opinions, \
jokes, or a request for a suggestion. Talk about yourself, your apps, the \
user's saved preferences, or this machine. params: {}
```
(Insert `chat` immediately after the `none` line, before `open_app`, to mirror the enum order.) Then in the Rules block, update the "When unsure" rule so casual talk goes to chat, not none:
```python
- Pick the single best action. Casual talk, greetings, and questions about \
yourself are chat. A request for a real-world fact is web_search. Only a \
genuinely ambiguous or destructive request is none.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prompt.py -v`
Expected: PASS (including `test_no_prefs_is_policy_verbatim`, which compares `assemble_system("")` to the edited constant — still equal).

- [ ] **Step 5: Commit**

```bash
git add friday/llm/prompt.py tests/test_prompt.py
git commit -m "feat(g8): planner prompt routes chat vs none vs web_search"
```

---

### Task 3: `CHAT_SYSTEM` persona prompt + assembly helper

**Files:**
- Modify: `friday/llm/prompt.py`
- Test: `tests/test_prompt.py`

**Interfaces:**
- Consumes: the inert preferences digest (a string, same one `assemble_system` uses).
- Produces:
  - `CHAT_SYSTEM: str` — the persona prompt (warm/witty/concise JARVIS-ish; ≤4 sentences; spoken aloud so no markdown/URLs/code; personalize from preferences; when asked a real-world fact, say you'd look it up rather than guessing; offer a relevant suggestion when natural; never claim to have done something you did not).
  - `assemble_chat_system(prefs_digest: str) -> str` — `CHAT_SYSTEM` plus the same fenced, data-framed preferences block `assemble_system` appends (reuse `_PREF_PREAMBLE`), or `CHAT_SYSTEM` verbatim when the digest is empty.

- [ ] **Step 1: Write the failing test**

`tests/test_prompt.py` — add:
```python
def test_chat_system_is_persona_and_spoken_safe():
    from friday.llm.prompt import CHAT_SYSTEM
    low = CHAT_SYSTEM.lower()
    assert "friday" in low
    assert "sentence" in low            # the ≤4-sentence bound is stated
    assert "markdown" in low or "spoken" in low  # spoken-aloud constraint


def test_assemble_chat_system_appends_prefs_as_data():
    from friday.llm.prompt import CHAT_SYSTEM, assemble_chat_system
    assert assemble_chat_system("") == CHAT_SYSTEM
    digest = "<preferences>\nname=Subham\n</preferences>"
    out = assemble_chat_system(digest)
    assert out.startswith(CHAT_SYSTEM)
    assert digest in out
    assert "DATA, not" in out           # named as data, not instructions
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_prompt.py -k chat_system -v`
Expected: FAIL — `CHAT_SYSTEM` / `assemble_chat_system` not defined.

- [ ] **Step 3: Add `CHAT_SYSTEM` + `assemble_chat_system`**

In `friday/llm/prompt.py`, after `assemble_system`:
```python
# Conversational persona (G8, ADR-048). Separate from SYSTEM_POLICY: this is
# the free-text stage, not the grammar-locked planner. Spoken aloud, so it
# forbids markdown/URLs and caps length. It never claims to have taken an
# action (that would be direct-action speech — ADR-009's domain).
CHAT_SYSTEM = """\
You are Friday, a warm, witty, concise assistant living on one Linux laptop \
— think JARVIS from Iron Man: friendly, a little playful, never rambling. \
Reply in at most 4 short sentences. Your reply is spoken aloud, so use plain \
words only: no markdown, no code, no URLs, no lists. Personalize using the \
user's saved preferences when relevant. If asked a real-world fact you cannot \
be sure of, say you would look it up rather than guessing. Offer a relevant \
suggestion when it fits naturally. Never claim to have done or opened \
something — you are only talking."""


def assemble_chat_system(prefs_digest: str) -> str:
    """CHAT_SYSTEM, plus the fenced preferences block (as DATA) when non-empty.
    Reuses the same inert digest and data-framing as the planner (ADR-035/037):
    preferences are named as DATA every turn they appear."""
    if not prefs_digest:
        return CHAT_SYSTEM
    return f"{CHAT_SYSTEM}\n\n{_PREF_PREAMBLE}\n{prefs_digest}\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prompt.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add friday/llm/prompt.py tests/test_prompt.py
git commit -m "feat(g8): CHAT_SYSTEM persona + assemble_chat_system (prefs as data)"
```

---

### Task 4: `Dialogue` ring buffer (in-memory only)

**Files:**
- Create: `friday/dialogue.py`
- Test: `tests/test_dialogue.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `@dataclass class Dialogue` with `max_turns: int = 8` and an internal `collections.deque(maxlen=max_turns)`.
  - `add(self, user: str, friday: str) -> None` — append one exchange; oldest trims automatically at the bound.
  - `render(self) -> str` — the recent exchanges as plain text for the chat prompt, oldest first, e.g. `"You: hi\nFriday: Hello!\n..."`; empty string when no history.
  - `__len__` reflects stored exchanges (for tests/observability).

- [ ] **Step 1: Write the failing tests**

`tests/test_dialogue.py`:
```python
import os
from pathlib import Path

from friday.dialogue import Dialogue


def test_add_and_render_round_trips():
    d = Dialogue()
    d.add("open brave", "Opening Brave.")
    d.add("thanks", "Anytime.")
    out = d.render()
    assert "open brave" in out and "Opening Brave." in out
    assert "thanks" in out and "Anytime." in out
    # oldest first
    assert out.index("open brave") < out.index("thanks")


def test_bound_trims_oldest():
    d = Dialogue(max_turns=3)
    for i in range(5):
        d.add(f"u{i}", f"f{i}")
    assert len(d) == 3
    out = d.render()
    assert "u0" not in out and "u1" not in out   # trimmed
    assert "u4" in out                            # newest kept


def test_empty_render_is_empty_string():
    assert Dialogue().render() == ""


def test_no_disk_writes(tmp_path, monkeypatch):
    # invariant #7: the buffer is RAM-only. Run a chdir into an empty tmp dir,
    # exercise the buffer heavily, and assert it created no files.
    monkeypatch.chdir(tmp_path)
    d = Dialogue()
    for i in range(50):
        d.add(f"user {i}", f"reply {i}")
    d.render()
    assert list(Path(tmp_path).iterdir()) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_dialogue.py -v`
Expected: FAIL — `friday.dialogue` does not exist.

- [ ] **Step 3: Write the module**

`friday/dialogue.py`:
```python
"""In-session dialogue memory (G8, invariant #7).

A bounded ring of recent (user, friday) exchanges, held in RAM and discarded
on exit. It is NEVER written to disk: raw transcripts on disk are a permanent
plaintext record of private speech and a durable-injection channel (the T1
attack the grammar-lock design blocks). Cross-session continuity is a later
stage (distilled, inerted summaries — design §"Stage 3"), not this buffer.

Bounded small (default 8 turns) so the chat context stays fast and memory-lean,
well inside ctx 8192.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class Dialogue:
    max_turns: int = 8
    _turns: deque[tuple[str, str]] = field(default_factory=deque, repr=False)

    def __post_init__(self) -> None:
        # deque(maxlen=…) auto-trims the oldest on append — the whole bound.
        self._turns = deque(self._turns, maxlen=self.max_turns)

    def add(self, user: str, friday: str) -> None:
        self._turns.append((user, friday))

    def render(self) -> str:
        """Recent exchanges as plain text, oldest first. Empty when no history."""
        return "\n".join(f"You: {u}\nFriday: {f}" for u, f in self._turns)

    def __len__(self) -> int:
        return len(self._turns)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_dialogue.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add friday/dialogue.py tests/test_dialogue.py
git commit -m "feat(g8): Dialogue ring buffer — bounded, RAM-only (invariant #7)"
```

---

### Task 5: Client — a no-grammar, temperature, stop path

**Files:**
- Modify: `friday/llm/client.py:39-73`
- Test: `tests/test_client_chat.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `LlamaClient.complete(..., grammar: str = "", stop: list[str] | None = None)` — `grammar` defaults to empty (unconstrained: the grammar key is OMITTED from the payload when empty); `stop`, when given, is passed to the server. All existing callers (which pass a non-empty `grammar`) are unaffected. The `untrusted` assert is unchanged and never fires for chat (`untrusted=False`).

- [ ] **Step 1: Write the failing tests** (monkeypatch `urlopen`, capture the payload)

`tests/test_client_chat.py`:
```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_client_chat.py -v`
Expected: FAIL — `stop` is not a parameter; empty grammar is still sent.

- [ ] **Step 3: Edit `complete`**

In `friday/llm/client.py`, change the signature and payload assembly:
```python
    def complete(
        self,
        *,
        system: str,
        user: str,
        grammar: str = "",
        max_tokens: int = 128,
        temperature: float = 0.0,
        untrusted: bool = False,
        stop: list[str] | None = None,
    ) -> str:
```
Keep the existing `untrusted` assert block unchanged. Replace the `payload = json.dumps({...})` block with a dict built conditionally:
```python
        body: dict[str, object] = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "cache_prompt": True,
        }
        if grammar:                 # empty grammar == unconstrained (chat, G8)
            body["grammar"] = grammar
        if stop:
            body["stop"] = stop
        payload = json.dumps(body).encode()
```
(The rest of the method — retry loop, error mapping — is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_client_chat.py tests/test_client_untrusted.py -v`
Expected: PASS. `test_client_untrusted` still green (the `untrusted=True` + plan-grammar assert is untouched).

- [ ] **Step 5: Commit**

```bash
git add friday/llm/client.py tests/test_client_chat.py
git commit -m "feat(g8): client no-grammar + stop path for free-text chat"
```

---

### Task 6: `chat.py` — the reply generator

**Files:**
- Create: `friday/llm/chat.py`
- Test: `tests/test_chat.py`

**Interfaces:**
- Consumes: `LlamaClient.complete(..., grammar="", temperature=…, stop=…)`, `assemble_chat_system`, `Dialogue.render()` (passed as a string).
- Produces: `generate_reply(client, utterance: str, *, prefs_digest: str = "", history: str = "") -> str` — assembles `assemble_chat_system(prefs_digest)` as system, `history` + the utterance as user, calls the client with no grammar (temperature `_CHAT_TEMPERATURE`, `max_tokens` `_CHAT_MAX_TOKENS`, stop `_CHAT_STOP`), sanitizes the reply for TTS (strip control/markdown/URLs, collapse whitespace, hard length cap), and returns it. Empty output or any exception → `CHAT_FALLBACK` (a fixed line, never the LLM).

- [ ] **Step 1: Write the failing tests** (stub client — no model needed)

`tests/test_chat.py`:
```python
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
    huge = "word " * 500
    out = chat.generate_reply(_Stub(huge), "q")
    assert len(out) <= chat._MAX_CHARS
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_chat.py -v`
Expected: FAIL — `friday.llm.chat` does not exist.

- [ ] **Step 3: Write the module**

`friday/llm/chat.py`:
```python
"""Stage 2 of a conversational turn (G8, ADR-048): generate a spoken reply.

Free text — NO grammar (temperature > 0, a stop sequence). Reuses the same
llama-server (invariant #6). The command-vs-chat decision was already made in
the grammar-locked planner; this runs only after `chat` was chosen, and it
NEVER dispatches. Output is sanitized before TTS: it is spoken aloud, so no
markup, URLs, or control chars, and a hard length cap. Any failure or empty
output returns a fixed fallback (never a raw exception — FR-26).
"""

from __future__ import annotations

import re
import unicodedata

from .prompt import assemble_chat_system

# Deterministic fallback (never the LLM): spoken when generation fails/empty.
CHAT_FALLBACK = "My words failed me for a second."

# Tuned provisionally; a listening test refines these (design open items).
_CHAT_TEMPERATURE = 0.7
_CHAT_MAX_TOKENS = 160          # ~4 short sentences
_CHAT_STOP = ["\nYou:", "\nUser:"]   # don't let it hallucinate the next turn
_MAX_CHARS = 600                # hard cap after sanitization

_URL = re.compile(r"https?://\S+")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_MD = re.compile(r"[*_`#>\[\]()]")


def _speakable(text: str) -> str:
    """Strip anything that should never be spoken; collapse whitespace; cap."""
    text = unicodedata.normalize("NFKC", text)
    text = _URL.sub("", text)
    text = _MD.sub(" ", text)
    text = _CONTROL.sub(" ", text)
    text = " ".join(text.split())
    return text[:_MAX_CHARS].strip()


def generate_reply(
    client,
    utterance: str,
    *,
    prefs_digest: str = "",
    history: str = "",
) -> str:
    system = assemble_chat_system(prefs_digest)
    user = f"{history}\nYou: {utterance}".strip() if history else utterance
    try:
        raw = client.complete(
            system=system,
            user=user,
            grammar="",                 # free text
            max_tokens=_CHAT_MAX_TOKENS,
            temperature=_CHAT_TEMPERATURE,
            stop=_CHAT_STOP,
        )
    except Exception:                   # never leak a raw exception (FR-26)
        return CHAT_FALLBACK
    return _speakable(raw) or CHAT_FALLBACK
```
(`client` is annotated structurally — any object with `complete(...)`; the daemon/turn pass a real `LlamaClient`, tests pass a stub. This mirrors `grounding.ground`'s duck-typed client.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_chat.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add friday/llm/chat.py tests/test_chat.py
git commit -m "feat(g8): chat.py reply generator — free text, sanitized, fail-soft"
```

---

### Task 7: Route `chat` in the turn loop + make `none` speak distinct lines

**Files:**
- Modify: `friday/turn.py`
- Modify: `friday/ui/templates.py`
- Test: `tests/test_chat_turn.py`, `tests/test_turn.py`

**Interfaces:**
- Consumes: `chat.generate_reply`, the prefs digest, a `history` string.
- Produces:
  - `run_turn(..., history: str = "")` and `_plan_and_act(..., history: str = "")` — the new kwarg threaded through, defaulting to `""` (existing callers unaffected).
  - When `plan.name == "chat"`: returns `TurnResult("chat", {}, <reply>, False)` — never dispatches. **Why `chat` is safe on invariant #1 without a runtime guard:** `chat` is only ever selected by the grammar-locked planner, which runs on `plan.gbnf` over *trusted* input; the *untrusted* path (grounding, G7) runs on `final.gbnf`, whose `name` is locked to exactly `"none"`, so an untrusted turn can NEVER emit `name == "chat"`. The safety is structural (the grammar), documented in a comment — not a no-op assert against a flag that does not exist on this path.
  - `none` now returns a SPOKEN line: `templates.OUT_OF_SCOPE` instead of the silent `"(no action)"`. The error paths keep their distinct existing lines. The `_UNSPOKEN` sentinel is removed; `run_turn` speaks any non-empty `spoken`.
  - `templates.OUT_OF_SCOPE: str` (fixed, non-LLM).

- [ ] **Step 1: Write the failing tests**

`tests/test_chat_turn.py`:
```python
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
```

Add to `tests/test_turn.py` (the `none`-speaks change):
```python
def test_none_speaks_out_of_scope_line() -> None:
    from friday.ui import templates
    r = _turn('{"action":{"name":"none","params":{}}}')
    assert r.plan_name == "none" and not r.dispatched
    assert r.spoken == templates.OUT_OF_SCOPE
    assert r.spoken != "(no action)"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_chat_turn.py tests/test_turn.py -k "chat or out_of_scope" -v`
Expected: FAIL — `history`/chat routing absent; `none` still returns `"(no action)"`; `OUT_OF_SCOPE` undefined.

- [ ] **Step 3: Add the `OUT_OF_SCOPE` template**

In `friday/ui/templates.py`, after the search templates:
```python
# The deliberate-none line (G8, design open-item #4). `none` now SPEAKS so the
# operator can tell live that the model chose no action (vs an error path,
# which has its own distinct line). Destructive/out-of-ability requests land
# here. Fixed string, never the LLM.
OUT_OF_SCOPE = "That isn't something I'm able to do."
```

- [ ] **Step 4: Wire `turn.py`**

In `friday/turn.py`:

Add the import:
```python
from .llm import chat, grounding, schema
```
(replace the existing `from .llm import grounding, schema`.)

Remove the `_UNSPOKEN` sentinel and its guard. Change the `run_turn` speak guard from:
```python
    if speaker is not None and result.spoken != _UNSPOKEN:
```
to:
```python
    if speaker is not None and result.spoken:
```
and delete the `_UNSPOKEN = "(no action)"` definition and its comment block.

Add `history: str = ""` to BOTH `run_turn` and `_plan_and_act` signatures (alongside the existing kwargs), and pass `history=history` from `run_turn` into the `_plan_and_act(...)` call.

Change the `none` branch:
```python
    if plan.name == "none":
        return TurnResult("none", params, templates.OUT_OF_SCOPE, False)
```

Add the `chat` branch immediately after the `none` branch (before `remember_preference`):
```python
    if plan.name == "chat":
        # invariant #1 (ADR-008/048) holds structurally: `chat` can only be
        # chosen by the grammar-locked planner (plan.gbnf, trusted input). The
        # untrusted path (grounding, G7) uses final.gbnf, whose name is locked
        # to "none", so an untrusted turn can never emit name=="chat". `chat`
        # NEVER dispatches — no executor call, dispatched=False.
        reply = await asyncio.to_thread(
            chat.generate_reply, client, utterance,
            prefs_digest=(prefs.digest() if prefs else ""), history=history,
        )
        return TurnResult("chat", {}, reply, False)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_chat_turn.py tests/test_turn.py tests/test_memory_turn.py tests/test_web_search_turn.py -v`
Expected: PASS. (The `web_search`/memory turn tests still green — new kwarg defaults to `""`; none-speaks change does not touch them.)

- [ ] **Step 6: Commit**

```bash
git add friday/turn.py friday/ui/templates.py tests/test_chat_turn.py tests/test_turn.py
git commit -m "feat(g8): route chat to the generator; none speaks a distinct out-of-scope line"
```

---

### Task 8: Daemon + TUI own the `Dialogue`, pass history, append replies

**Files:**
- Modify: `friday/daemon.py`
- Modify: `friday/ui/tui.py`
- Test: `tests/test_daemon.py` (extend), `tests/test_dialogue_wiring.py`

**Interfaces:**
- Consumes: `Dialogue`, `TurnResult`.
- Produces: the daemon and the TUI each own a `Dialogue`, pass `history=self._dialogue.render()` into `run_turn`, and append `(utterance, result.spoken)` after every turn that produced speech (both action and chat turns append, so "open my editor too" after "open Brave" has context — design open-item, decided yes). Nothing is written to disk.

- [ ] **Step 1: Write the failing test** (a small, framework-free wiring check)

`tests/test_dialogue_wiring.py`:
```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_dialogue_wiring.py -v`
Expected: PASS actually is possible here (it exercises only `run_turn` + `Dialogue`, both already built) — if it passes, that confirms the seam; the daemon/TUI wiring below has no pure-unit failing test, so verify it via the extended daemon test in Step 4. (If it fails, fix `run_turn`'s `history` threading from Task 7.)

- [ ] **Step 3: Wire the daemon**

In `friday/daemon.py`:
- Import: `from .dialogue import Dialogue`.
- In `__init__`, add `self._dialogue = Dialogue()`.
- In `_run_turn`, change the `run_turn(...)` call to pass `history=self._dialogue.render()`.
- After a turn produces speech, append the exchange. In the non-pending branch, the existing `will_speak` block (`daemon.py:197-199`) is:
```python
            will_speak = bool(result.spoken) and result.spoken != "(no action)"
            self.state.got_plan(will_speak=will_speak)
            if will_speak:
                await self._speak(result.spoken, measure=True)
```
Add the append inside that `if will_speak:` block, after the `_speak`:
```python
            if will_speak:
                await self._speak(result.spoken, measure=True)
                self._dialogue.add(text, result.spoken)
```
(Append regardless of action vs chat, so cross-turn context holds.)

**Leave the `!= "(no action)"` guard on line 197 as-is** — after Task 7 the real `none` path returns `OUT_OF_SCOPE`, never `"(no action)"`, so the sentinel is now dead in production, BUT the existing daemon tests (`test_daemon.py:97,259`) inject a fabricated `TurnResult("none", {}, "(no action)", False)` and rely on that guard to assert silence. Removing it would break them for no gain. It is a harmless belt-and-suspenders sentinel; keep it.

- [ ] **Step 4: Extend the daemon test**

In `tests/test_daemon.py`, add a test using the file's EXISTING harness (`_plan(monkeypatch, result)` monkeypatches `run_turn`; `_daemon(**kw)` builds the `Daemon`; `FakeTranscriber` returns actionable text by default):
```python
def test_chat_turn_appends_to_dialogue(monkeypatch):
    _plan(monkeypatch, TurnResult("chat", {}, "Hello there!", False))
    d = _daemon()
    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task
    asyncio.run(go())
    assert len(d._dialogue) == 1
    assert "Hello there!" in d._dialogue.render()
```
(Do NOT invent a new harness or a fake client — `_plan` replaces `run_turn` wholesale, so no client is exercised.)

- [ ] **Step 5: Wire the TUI**

In `friday/ui/tui.py`:
- Import: `from ..dialogue import Dialogue`.
- In `__init__`, add `self._dialogue = Dialogue()`.
- In `_do_turn`, pass `history=self._dialogue.render()` into `run_turn`, and after writing `result.spoken`, append: `self._dialogue.add(text, result.spoken)`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_dialogue_wiring.py tests/test_daemon.py -v`
Expected: PASS. Then `uv run pytest -q` — full suite green.

- [ ] **Step 7: Commit**

```bash
git add friday/daemon.py friday/ui/tui.py tests/test_dialogue_wiring.py tests/test_daemon.py
git commit -m "feat(g8): daemon+TUI own Dialogue, pass history, append each turn (RAM only)"
```

---

### Task 9: Eval fixtures — move greetings to `chat`, add chat fixtures, re-baseline

**Files:**
- Modify: `tests/fixtures/eval.jsonl` (E15/E16 → `chat`; add E25..E28)
- Modify: `tests/fixtures/adversarial.jsonl` (confirm injections still `none`/`web_search`)
- Regenerate: `tests/fixtures/baseline.json` (via `--update-baseline`)
- Test: `just eval` (needs `just serve` up)

**Interfaces:**
- Produces: an eval set where greetings/casual → `chat`, commands/facts unchanged, destructive/ambiguous → `none`. The baseline is re-recorded so `regressions == 0`.

- [ ] **Step 1: Update the greeting fixtures**

In `tests/fixtures/eval.jsonl`, change E15 and E16 to expect `chat`:
```json
{"id":"E15","utt":"hey","expect":{"name":"chat"}}
{"id":"E16","utt":"how are you doing today","expect":{"name":"chat"}}
```
Leave E17 (`delete everything…`), E18 (`run rm -rf /`), E19 (`open the thing`) as `none`.

- [ ] **Step 2: Add new chat fixtures**

Append to `tests/fixtures/eval.jsonl`:
```json
{"id":"E25","utt":"who are you","expect":{"name":"chat"}}
{"id":"E26","utt":"what can you do","expect":{"name":"chat"}}
{"id":"E27","utt":"tell me a joke","expect":{"name":"chat"}}
{"id":"E28","utt":"i'm bored, got any suggestions","expect":{"name":"chat"}}
```

- [ ] **Step 3: Run eval to see the pre-baseline result**

Run (with `just serve` up): `uv run python -m friday.eval_harness`
Expected: the fixtures resolve; E15/16/25-28 now plan `chat`. If any greeting still plans `none`, the Task 2 prompt needs a sharper `chat` line — tighten and re-run (this is the model-behavior check the design defers to eval). Destructive fixtures MUST stay `none`; if E17/E18 ever plan `chat`, STOP — the `none` narrowing went too far.

- [ ] **Step 4: Re-baseline**

Run: `uv run python -m friday.eval_harness --update-baseline`
Then: `just eval`
Expected: `passed 28/28` (24 existing + 4 new), `regressions vs baseline: 0`.

- [ ] **Step 5: Confirm adversarial still holds**

Run: `uv run pytest tests/test_adversarial.py tests/test_injection.py -q`
Expected: PASS — injections still route to `none`/`web_search`; `chat` never dispatches (Task 7 test already asserts the executor is untouched on a chat turn).

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/eval.jsonl tests/fixtures/adversarial.jsonl tests/fixtures/baseline.json
git commit -m "test(g8): greetings route to chat; add chat fixtures; re-baseline 28/28"
```

---

### Task 10: Docs + acceptance evidence

**Files:**
- Modify: `friday.md` (§10 G8 — mark Build 1 done, note ADR-048 / the two-stage flow)
- Modify: `spec.md` (add G8 FR entries or tick where met)
- Modify: `progress.md` (G8 Build 1 evidence + status + decision log)
- Modify: the design doc (mark Build 1 built; leave Stages 2-4 open)

**Interfaces:**
- Produces: the acceptance record for Build 1.

- [ ] **Step 1: Run the full acceptance battery**

Run (with `just serve` up):
```bash
uv run pytest -q                 # full suite green
just eval                        # 28/28, regressions 0
just test-injection              # 20/20 blocked, chat never dispatches
```
Expected: all green. Paste into `progress.md`.

- [ ] **Step 2: Live end-to-end (real model)**

With `just serve` up, run `just run` (text mode) and try: "hi", "who are you", "what can you do", "open my browser" (still launches), "what's the weather in Paris" (still `web_search`), "run rm -rf /" (speaks the out-of-scope line, no action). Confirm chat replies are warm/≤4 sentences and no URLs/markdown are spoken. Paste the transcript into `progress.md`. (A spoken listening test — like G5 — is the subjective quality gate; note it as the user's sign-off item.)

- [ ] **Step 3: Update the docs**

- `friday.md` §10 (G8): note the two-stage flow (planner unchanged + `chat` stage 2), ADR-048, the RAM `Dialogue` buffer, and that Build 1 = in-reply/in-session only (Stages 2-4 later).
- `spec.md`: add FR entries for the chat action / conversational speech / dialogue-never-on-disk, or tick where met.
- `progress.md`: fill the G8 Build 1 EVIDENCE block, flip the gate line, and update NEXT SESSION to point at G8 Stage 2 (habit-driven suggestions) or G9 (service) per the build order.
- The design doc: mark Build 1 as built; leave Stages 2-4 open.

- [ ] **Step 4: Commit**

```bash
git add friday.md spec.md progress.md docs/superpowers/specs/2026-08-23-conversational-chat-design.md
git commit -m "docs(g8): Build 1 done — acceptance evidence, ADR-048, dialogue-in-RAM"
```

---

## Self-Review

**Spec coverage (design doc → task):**
- The `chat` action (enum + grammar + validator) → Task 1. ✓
- Planner routes chat/none/web_search → Task 2. ✓
- `CHAT_SYSTEM` persona + assembly, prefs as data → Task 3. ✓
- `Dialogue` ring buffer, bounded, RAM-only (invariant #7) → Task 4. ✓
- Reuse the same server, no-grammar/temperature/stop path → Task 5. ✓
- `chat.py` generator: assembly, sanitize, fail-soft (design §"Stage 2"/§"Error handling") → Task 6. ✓
- Route `chat` in turn.py, never dispatch, defense assert; `none` speaks distinct lines (open-item #4) → Task 7. ✓
- Daemon owns buffer, passes history, appends (action turns append too — open-item decided yes) → Task 8. ✓
- Eval: chat fixtures, existing set still passes, adversarial → none/web_search, chat never dispatches → Task 9. ✓
- ADR-048 (conversational speech carve-out from ADR-009) → Task 1 Step 1. ✓
- Acceptance (Build 1) → Task 10. ✓

**Deferred by design (NOT in Build 1, correctly absent):** habit-driven suggestions from the audit log (Stage 2), distilled long-term memory / session_summaries (Stage 3), proactive/unprompted speech (Stage 4), adaptive reply length, final temperature/max_tokens/buffer-size tuning (listening test), ctx-headroom re-measurement (do during Task 10 if a spoken turn feels tight).

**Placeholder scan:** every code step contains runnable code; test bodies are complete. The one soft spot — Task 8 Step 4's daemon test — points at the existing `tests/test_daemon.py` harness rather than duplicating it, because that file's `Daemon` construction and stubs must be matched exactly; the assertion (`len(daemon._dialogue) == 1`) is concrete.

**Type consistency:** `Dialogue.add(user, friday)` / `.render() -> str` / `.__len__` used identically in Tasks 4/8. `generate_reply(client, utterance, *, prefs_digest="", history="") -> str` defined Task 6, called Task 7. `complete(..., grammar="", stop=None)` defined Task 5, used Task 6. `TurnResult("chat", {}, reply, False)` matches the existing `TurnResult(plan_name, params, spoken, dispatched, ...)` shape. `templates.OUT_OF_SCOPE: str` defined Task 7, used in Tasks 7/10. `assemble_chat_system(str) -> str` defined Task 3, used Task 6.

**Invariant audit:** #1 — chat consumes no untrusted data and never dispatches; safety is STRUCTURAL, not a runtime assert: `chat` is only selectable by the grammar-locked planner (plan.gbnf, trusted), while the untrusted path uses final.gbnf locked to `name=="none"`, so an untrusted turn can never emit `chat` (final.gbnf path untouched). #4 — ADR-048 carves conversational speech out of ADR-009; command turns still template-only. #5 — chat added to grammar AND validator; other paths fail closed unchanged. #6 — same server, no new VRAM. #7 — Dialogue RAM-only, tested. #9 — one turn in flight (FSM) untouched. `web_search`/final.gbnf grounding path (G7) is not touched by any task.
