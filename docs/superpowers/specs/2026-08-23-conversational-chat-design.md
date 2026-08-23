# Conversational chat & suggestions — design (gate G8)

**Status:** Design approved 2026-08-23. Not yet implemented. This is the
spec for a new conversational subsystem; it is gate **G8** in the build
plan. Build order decided 2026-08-23: **G7 (search) → G8 (conversation) →
G9 (service)** — conversation is the primary goal and comes before the
service/systemd layer, but after search so the "facts route to web_search"
path can land complete. Service was renumbered G8 → G9 to keep the gate
number equal to the execution order.

## Context & why

The user has stated that **chit-chat + suggestions is the primary goal**
of Friday — the action dispatcher (open apps, search) is the supporting
cast, not the point. The current architecture deliberately excludes
this: the planner is grammar-locked to a closed action set, the model
never emits free text, and `action=none` produces silence (a spoken
"hello, how are you" got no reply during the G6 spoken eval — that is
the motivating gap).

Building conversation well is a new capability, not a G6 patch. It adds
a model-generated-speech path, revisits ADR-009, and introduces a
dialogue memory. It is designed here for the full vision (conversation +
habit-driven + proactive suggestions + distilled long-term memory) but
**built in stages**, starting with in-reply, in-session chat.

## Decided requirements (from brainstorming, 2026-08-23)

- **Vision:** back-and-forth conversation + memory + proactive suggestions.
  Architect for all of it; build in stages.
- **Scope of talk:** casual conversation + Friday's own world (its apps,
  the user's preferences, the machine) + personality. Real-world FACT
  questions still route to `web_search` (G7) — the 7B does not answer
  facts from its own weights, to avoid confident hallucination.
- **Suggestions:** staged — in-reply first, then habit-driven (from the
  audit log), then truly proactive/unprompted (own later design).
- **Personality:** warm, witty, concise — "JARVIS/Friday" from Iron Man.
- **Reply length:** up to ~4 sentences for now; adaptive length later.
- **Non-functional:** fast and memory-efficient (user's explicit ask).

## Approach (chosen: A — two-stage)

Leave the proven grammar-locked planning turn unchanged. Add a second
stage that runs **only** when the planner selects a new `chat` action.
Rejected: (B) a unified grammar emitting action-or-speech — rewrites the
closed-action guarantee and is less reliable on a 7B; (C) an intent
router before every turn — adds a round-trip to the common action case
and duplicates what the planner already decides.

### Turn flow

```
utterance -> transcribe -> plan (grammar-locked, UNCHANGED) ->
   command       -> execute-first -> template speech      (UNCHANGED)
   web_search    -> (G7)                                  (UNCHANGED)
   chat          -> generate reply (stage 2) -> speak     (NEW)
   none          -> destructive/ambiguous: safe canned line or silence
```

The command-vs-chat decision stays inside the **grammar-locked** stage.
`none` is narrowed to genuine refusals/ambiguity; casual talk, greetings,
"who are you", and suggestion-seeking route to `chat`.

### The `chat` action

- Added to the closed action enum: `schema.py`, the plan grammar(s), the
  validator. Params: none (`{}`). Stage 2 uses the transcript the daemon
  already holds — the model does not pass the utterance through a field.
- Planner prompt (`SYSTEM_POLICY`) gains a short line describing when to
  choose `chat` vs `none` vs `web_search`.

## Stage 2 — the chat generator

New module **`friday/llm/chat.py`**, one purpose:
`generate_reply(client, utterance, *, prefs_digest, history) -> str`.

- **No grammar** — the new free-text path. Bounded by `max_tokens`
  (~4 sentences) plus a stop sequence. Not JSON, not gbnf.
- **Temperature > 0** (~0.7) for natural variety — distinct from the
  deterministic temp-0 planner. Exact value tuned in a listening test.
- **Reuses the same llama-server** — no second model in VRAM (memory-lean,
  and keeps invariant #6: only llama-server touches CUDA).
- **Output sanitized before TTS:** strip control chars / markdown / URLs,
  hard length cap. It is spoken aloud, so no code blocks or links.

### Context assembled per chat turn

1. **`CHAT_SYSTEM`** — new persona prompt, separate from `SYSTEM_POLICY`:
   warm/witty/concise JARVIS-ish; ≤4 sentences; you are spoken aloud so no
   markdown/URLs; use the user's preferences to personalize; when asked a
   real-world fact, say you would look it up rather than guessing; offer a
   relevant suggestion when natural; never claim to have done something you
   did not.
2. **Preferences digest** — the same inerted digest the planner already
   builds (reused; personalizes replies).
3. **Recent dialogue** — from the ring buffer below.
4. The current utterance.

## Dialogue memory — `Dialogue` ring buffer

- A bounded deque of recent exchanges: the user's words + what Friday said
  or did (including action outcomes, so "open my editor too" after "open
  Brave" has context).
- **In-memory only, never written to disk** (invariant #7). Lives in the
  daemon. Discarded on exit.
- Bounded by ~8–10 turns / a token cap — small context (fast), memory-lean,
  well inside ctx 8192.
- Appended every turn; oldest trims off.

## Safety — invariants preserved, plus a new ADR

- The command-vs-chat decision is made in the **grammar-locked** stage, not
  by free text.
- A `chat` turn **consumes no untrusted data** and **can never dispatch an
  action** — it only produces speech. Invariant #1 (untrusted → `final.gbnf`,
  no dispatch) holds by construction; #2/#4 (model never supplies argv;
  execute-first) do not apply (no action). A defense-in-depth assert forbids
  entering `chat` on any turn flagged as having consumed untrusted data.
- **New model-generated speech** is introduced, which ADR-009 currently
  forbids. ADR-009 governs *direct-action* speech (never say "Opened Brave"
  when the launch failed). Conversation is not direct-action speech — it
  drives no side effect. A **new ADR** will carve out "conversational speech"
  as an explicitly-allowed category, distinct from and not weakening the
  action-outcome template rule.

## Suggestions & long-term memory — staging

**Build 1 (this gate's first slice) — in-reply, in-session:**
`chat` action + generator + RAM dialogue ring buffer. Suggestions = the
persona prompt offering a relevant follow-up using current preferences. No
new storage.

**Stage 2 — habit-driven suggestions:** mine the **audit log** (already on
disk, args redacted) for patterns ("you open Code after Brave", "lo-fi
around this hour") and surface them inside a user-triggered turn. Reads
existing data; no raw transcripts.

**Stage 3 — distilled long-term memory (the answer to "why not log the
dialogue to disk"):** raw transcripts on disk are rejected — they are a
permanent plaintext record of private speech (privacy / the disk trust
boundary, ADR-031) and a **durable-injection** channel (re-feeding stored
raw text is exactly the T1 attack the grammar-lock design blocks; the one
persisted-and-re-fed channel, preferences, is deliberately rendered inert,
and raw transcripts cannot be). The RAM argument for persisting is moot —
the buffer is a few KB next to a 4.4 GB model. Instead, at end-of-session
the model distills the RAM dialogue into short **inerted** facts/summaries
→ `session_summaries` + preferences (the schema already has the table).
That delivers cross-session continuity and searchable context safely, and
feeds future chat context.

**Stage 4 — proactive/unprompted:** a trigger loop lets Friday speak
without a tap (time/context). Breaks the pure PTT model — its own design
(attention-getting, do-not-disturb).

## Error handling

- Chat gen timeout / failure / empty output → deterministic fallback line
  ("My words failed me for a second."), never a crash, never a leaked
  exception (an error-taxonomy code per spec §4).
- Per-stage timeout on the chat call.
- Sanitizer failure → fallback.

## Components (isolation)

- `friday/llm/chat.py` — the generator (assembly + client call + sanitize +
  fallback). New.
- `friday/llm/prompt.py` — add `CHAT_SYSTEM` + assembly helper.
- `friday/llm/schema.py` + grammars — add the `chat` action.
- `friday/turn.py` — route `plan == chat` to the generator; keep the action
  path untouched.
- `friday/dialogue.py` (or in the daemon) — the `Dialogue` ring buffer.
- `friday/daemon.py` — own the ring buffer, pass history in, append replies.
- Audio (STT/TTS) — unchanged, reused.

## Testing

- **Unit:** planner routes `chat`/command/`none`/`web_search`; `chat.py`
  (assembly, fallback on error/empty, sanitization); `Dialogue` bounds + a
  test asserting it never touches disk; `turn.py` routes `chat` → generator
  and never dispatches; daemon history append/trim; the untrusted-data
  defense-in-depth assert.
- **Eval:** add `chat` fixtures (greetings, "who are you", casual) → `chat`
  action; the existing 24 must still pass; adversarial: injection still →
  `none`/`web_search`, `chat` never dispatches.
- **Quality:** subjective → a user listening test, like G5.

## Acceptance (Build 1)

- Spoken casual input → a warm, ≤4-sentence spoken reply; commands and
  facts still route correctly (eval not regressed); `chat` can never
  dispatch an action (asserted); dialogue context works within a session
  and is never written to disk; fail-soft on generation error.

## Open items (decide during implementation)

- Exact temperature + `max_tokens` for the chat call (listening test).
- Ring buffer bound: turn count vs token budget, and the exact number.
- Whether action turns also append to the dialogue buffer (leaning yes, for
  cross-turn context like "and my editor too").
- The `none` case: brief canned line vs silence.
- ctx headroom: confirm dialogue + persona + prefs fit comfortably in 8192
  (redo the ADR-003 arithmetic); raise only if measured necessary.
