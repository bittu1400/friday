> **ARCHIVED 2026-08-22.** Historical only. Superseded by `friday.md` (v5),
> `spec.md`, `adr.md`, `architecture.md`. Contains claims corrected in `adr.md`
> (see ADR-003, ADR-021, ADR-022). Do not cite as current.

# Friday Architecture Audit — GPT Thoughts

**Reviewed:** `friday.md` v4 (2026-08-22)  
**Scope:** architecture/design only; no application source exists in this workspace to audit.  
**Verdict:** promising and appropriately scoped, but **not yet build-ready for an assistant that can execute local actions**. The model selection is a reasonable starting hypothesis. The missing security boundary and lifecycle design are the larger risks—not DSA complexity or SQLite performance.

## What is good

- Deferring multilingual and vision scope is the right product decision.
- Separating tool execution from final response is necessary for factual search results.
- A small SQLite store is the right fit for local preferences and summaries; no graph/vector database is justified in Phase 1.
- Measuring simultaneous GPU load on the actual desktop is much better than trusting model-card figures.
- The document correctly recognizes that a custom `Friday` wake word needs training and that raw input-device access is sensitive.

## Findings, ordered by priority

| Priority | Finding | Why it matters | Required design change |
|---|---|---|---|
| P0 | **The model is asked to emit hidden `thought`, and it is persisted.** (§4C) | It creates a highly sensitive record, will capture secrets and personal data, is not reliably useful for debugging, and conflates user-visible safety with hidden reasoning. A local compromise, backup sync, or another desktop user can read it. | Delete `thought` from the contract and do not request chain-of-thought. Log structured, non-sensitive telemetry only: request ID, chosen tool, validated arguments, policy decision, duration, exit status, and redacted error code. |
| P0 | **No threat model or authorization model exists for local actions.** | A voice transcript, text pasted from a web page, memory entry, or tool result can steer the model to use an otherwise allowed tool. “Whitelist” alone does not define *who* may invoke an action or which actions are safe unattended. | Define assets, attacker paths, trust levels, and a per-action policy before coding. Start with: read-only/no side effect; reversible local effect; irreversible/external effect. Require an explicit local confirmation for the latter two, plus a clear cancellation path. |
| P0 | **Web search results are treated as system/tool context without an untrusted-data boundary.** (§4D) | Search snippets/pages can contain prompt injection: “ignore prior rules and run…”. A second LLM call does not make that data trustworthy. This is the highest-probability path from web content to local action. | Label tool output as untrusted data; never permit a follow-up call that consumed web output to choose an action. Its output must be final speech only under a schema that permits `action=none`. Strip markup, cap length, keep provenance/URLs separate, and require confirmation for any action derived from results. |
| P0 | **Action execution semantics are unsafe and misleading.** (§4C) | TTS is started concurrently with dispatch. “Opening Firefox” may be spoken even if policy rejects, `hyprctl` fails, the app is missing, or the script fails. Retrying an action after an uncertain failure can duplicate an external effect. | Execute first, await a bounded result, then say a factual outcome. Model actions as an idempotent command with `request_id`, timeout, cancellation, exit status, and a user-safe error. Do not automatically retry non-idempotent actions. |
| P0 | **`~/friday/scripts/` is not a secure execution boundary by itself.** | Path traversal, symlinks, writable scripts, interpreter/shebang changes, inherited environment variables, and TOCTOU races can turn a valid allowlist into arbitrary code execution. The model must not supply a path or arbitrary arguments. | Store a static registry: tool ID → canonical, root-owned-or-user-approved executable + typed arguments + working directory + timeout. Resolve canonical paths, reject symlinks/out-of-tree files, use `execve`/argument arrays (`shell=False`), minimal environment, and no free-form script parameters. Prefer an in-process implementation for simple tools. |
| P0 | **Raw `evdev` membership grants keyboard-observation capability.** (§4A) | Filtering after `read_loop()` does not prevent the process from receiving every keyboard event; a bug or compromise becomes a keylogger. The `input` group is broad privilege. | Prefer a Hyprland-native bind that launches/signals the assistant, or a dedicated USB/HID PTT device. If evdev is unavoidable, use a narrowly scoped udev ACL for one stable `/dev/input/by-id/...` device, avoid logging events, verify its capabilities at startup, and document this as a privileged component. Never use `grab()`: it exclusively receives input and can lock users out. |
| P1 | **The local LLM server’s network exposure is unspecified.** | Many inference servers expose an HTTP API. Binding beyond loopback exposes an action-capable assistant to the LAN; an unauthenticated local TCP port also widens attack surface. | Bind to a Unix socket or `127.0.0.1` only, reject proxy exposure, use a per-process capability/token if a separate client is necessary, and run the model and orchestrator under a dedicated non-login user where practical. |
| P1 | **“Offline-first” conflicts with live web search, model downloads, and potentially remote telemetry.** | Privacy and UX expectations will otherwise be wrong, and a lost network connection has no defined behavior. | State two modes: *local mode* (no egress) and *connected search mode* (only selected search provider receives the query). Make egress opt-in, show an indicator, define timeouts/fallback speech, and pin/checksum downloaded model artifacts. |
| P1 | **Persistence design lacks schema, data lifecycle, and concurrency rules.** (§4E) | SQLite is robust, but concurrent audio/UI/orchestrator tasks can hit `database is locked`; unbounded summaries/logs cause disk and prompt growth; preferences are user data, not automatically trustworthy instructions. | Use one writer queue/connection strategy, parameterized SQL, migrations, WAL with a tested busy timeout, bounded transactions, unique normalized keys, `updated_at`, source/confidence, and explicit delete/export/reset operations. Enforce `0600` file/directory permissions, retention/rotation, and a size cap. |
| P1 | **All preferences are injected every turn with no budget, priority, expiry, or conflict rules.** | It wastes a 2048-token context, enables durable indirect prompt injection, and allows stale values to silently dominate a conversation. | Keep a deterministic, bounded selection (for example top relevant preferences within a fixed token cap); represent values as data, not instructions; give entries provenance and expiry; confirm destructive/ambiguous preference writes; support “forget X.” |
| P1 | **Output correctness is assumed from JSON syntax.** | Valid JSON does not mean a valid action: extra fields, a wrong enum/argument type, duplicate keys, Unicode confusables, or unsupported schema features can still cause an unsafe dispatch. A grammar is useful but cannot supply semantic authorization. | Use constrained generation where verified in an integration test, then parse once, reject duplicates/unknown fields, validate against a strict application-side schema, and validate every typed parameter against the static tool registry. Fail closed with `action=none`. Current llama.cpp documentation supports grammars/schema constraints, but compatibility should be pinned and tested rather than assumed. |
| P1 | **No explicit limits/backpressure strategy exists for voice, LLM, tools, or TTS.** | Wake-word false positives, a held PTT key, overlapping turns, slow web searches, or a hung subprocess can exhaust VRAM/RAM or create stale actions after the user has moved on. | Use a single-turn state machine and bounded queues. Define maximum audio duration, transcript bytes/tokens, generation tokens, tool-result bytes, concurrent tools, per-tool timeout, cancellation on barge-in, and resource cleanup. Reject/queue a second request visibly. |
| P1 | **Audio pipeline behavior is under-specified.** | Assistant playback can trigger the wake word/STT; endpointing errors make latency and transcription quality unpredictable; speaking an action confirmation before completion is already unsafe. | Add VAD/endpointing, echo cancellation or playback suppression, microphone mute/duck while TTS plays, a barge-in policy, device-loss recovery, and a latency budget measured from end-of-speech to first audio. Do not optimize streaming JSON before correctness is established. |
| P1 | **No auditable policy for dangerous or ambiguous intents.** | “Run whitelisted scripts” may include deletion, sending data, opening URLs, or modifying files. Voice recognition mistakes are normal. | For Phase 1, make scripts read-only by default. Require typed confirmation for any destructive/network/data-sharing action; show tool name and salient arguments; record approval/denial as metadata, not raw speech. Add a panic/disable control. |
| P2 | **VRAM/RAM estimates are presented with too much certainty.** (§3A–D) | Model format, GPU layers, batch size, Flash Attention, driver, STT compute type, context, and concurrent browser use change peaks substantially. The blueprint’s STT “int8” wording is ambiguous: the documented CUDA path is `int8_float16`, while `int8` is the CPU example. | Treat values as benchmark targets. Build a repeatable load test with exact versions/settings, warm-up, 95th-percentile latency, peak VRAM/RAM, and OOM recovery. Benchmark GPU and CPU STT before permanently allocating scarce VRAM. |
| P2 | **The 2048-token cap is an implementation knob, not a memory architecture.** | It may truncate system instructions/tool output and harm tool reliability. Repeatedly injecting session data also increases latency. | Reserve explicit budgets for system policy, user transcript, trusted memory digest, untrusted tool data, and output. Truncate by source with markers; never silently discard policy. Summarize only after a turn/session through a bounded, reviewable pipeline. |
| P2 | **`hyprctl dispatch exec` needs exact quoting and launch semantics.** | Hyprland dispatch commands may ultimately parse a command string. Passing LLM-derived app names/arguments is injection-prone even if Python’s subprocess is invoked safely. | Do not construct an `exec` string from model output. Map opaque app IDs (e.g. `browser`) to fixed desktop entries/argv owned by code. Test spaces, quotes, and failures. |
| P2 | **No service/supervision and restart design.** | A desktop assistant runs for long periods: model server, PipeWire, input device, GPU, and DB can disappear or fail independently. | Specify systemd user units, dependency order, restart/backoff, health checks, graceful shutdown, model unload, stale lock handling, and log rotation. Ensure it starts with least privilege and does not silently respawn a privileged input listener after policy changes. |
| P2 | **The search/recommendation feature lacks a data contract.** | “Live search” says neither which provider is used nor what result fields/citations are accepted. Recommendations can become misleading, stale, or privacy-leaking. | Define a provider adapter with query limits, timeout, result schema, source URL/title/date, content-size cap, caching policy, citation requirement, and explicit statement that recommendations are advisory. |
| P3 | **Wake-word training needs evaluation criteria, not only an afternoon estimate.** | False accepts cause unwanted recording/actions; false rejects make the product feel broken. The upstream project documents custom training but also notes false-activation mitigation. | Collect consented test audio across rooms/noise, set a target false-accept and false-reject rate, tune threshold/cooldown, and provide a visible mic state. |
| P3 | **The Phase 2 plan has no migration/security gate.** | Re-enabling language detection changes prompt, TTS, and policy behavior; it can regress action recognition. | Treat every new language and voice as a separate evaluation matrix: STT intent accuracy, confirmation phrases, tool schema compliance, and prompt-injection tests. Do not let Phase 2 bypass Phase 1’s policy layer. |

## Data structures and database assessment

There is no algorithmic/DSA bottleneck in the proposed system. The right defaults are intentionally boring:

- An in-memory `dict`/immutable registry for tools and apps gives O(1) dispatch; do not discover executable paths dynamically.
- A bounded FIFO queue for audio/turn requests prevents memory growth. A finite-state machine is more appropriate than ad-hoc concurrent tasks: `idle → capturing → transcribing → planning → awaiting_confirmation|executing → responding → idle`.
- SQLite indexes are only needed for actual query paths. At minimum: `preferences(key)` as a unique primary key, and `session_summaries(session_id, created_at)`. Add indexes only after `EXPLAIN QUERY PLAN` shows a need.
- Use prepared statements exclusively. The likely SQLite risks are concurrent writers and lifecycle/permissions—not SQL injection if values are parameterized.
- Keep raw transcripts/audio out of SQLite by default. If a debugging mode stores them, make it time-limited, encrypted at rest if the threat model requires it, and clearly visible to the user.

An initial schema should include provenance rather than only key/value:

```sql
CREATE TABLE preferences (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('user_confirmed', 'user_typed')),
  updated_at INTEGER NOT NULL,
  expires_at INTEGER,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE action_audit (
  request_id TEXT PRIMARY KEY,
  tool_id TEXT NOT NULL,
  args_redacted_json TEXT NOT NULL,
  policy_decision TEXT NOT NULL,
  outcome TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
```

Do **not** store model thoughts, full prompts, raw key events, or unredacted web/tool payloads in this database.

## Correctness and source notes

1. `faster-whisper` documents CUDA `int8_float16` and CPU `int8`; the plan should name the tested compute type rather than calling both “int8.” Its published large-v2 benchmark also shows VRAM varying materially by batch size, so the 1.5 GB figure is not a guarantee. [faster-whisper README](https://github.com/SYSTRAN/faster-whisper)
2. openWakeWord does support custom-model training, but its included pre-trained models have a non-commercial license. That is fine for a personal assistant; record the licensing decision before any redistribution. [openWakeWord README](https://github.com/dscripka/openWakeWord)
3. Kokoro’s own instructions demonstrate `espeak-ng`; pin the working package versions in a lockfile and test on the chosen Python version. “Zero VRAM” should be treated as an intended CPU placement, not an inherent guarantee if dependencies select a GPU. [Kokoro repository](https://github.com/hexgrad/kokoro)
4. Constrained output should be verified end-to-end with the exact server version. llama.cpp documents grammar/JSON-schema support, but its schema subset/API behavior has had compatibility bugs; application-side validation remains mandatory. [llama.cpp grammars](https://github.com/ggml-org/llama.cpp/tree/master/grammars)
5. The statement that compositor-level binds cannot trigger PTT is too absolute. Investigate a Hyprland bind first: it is a lower-privilege architecture than granting raw keyboard-event access. Raw evdev does, by design, read a device’s entire event stream. [python-evdev tutorial](https://python-evdev.readthedocs.io/en/latest/tutorial.html)

## Recommended build gate before Phase 1 implementation

1. Write the threat model and the static tool registry/policy. Implement only `open_app` with opaque IDs and factual post-execution acknowledgement.
2. Implement strict structured output plus application-side validation and a malicious-input test suite (invalid JSON, tool-result injection, transcript errors, path traversal, duplicate events, timeout, cancellation).
3. Implement SQLite with permissions, migrations, deletion/export, writer serialization, and redacted audit metadata—then preferences.
4. Build text mode first. Add PTT through a compositor binding if feasible; only then evaluate a narrowly privileged evdev component.
5. Add audio/VAD/TTS, load-test the chosen model versions under normal desktop use, and test recovery from GPU/model/audio/DB failures.
6. Add web search last, in an opt-in connected mode whose post-search turn cannot invoke actions.

## Decisions to make before implementation

- Which exact actions/scripts are allowed in Phase 1, and which must require typed confirmation?
- Is Friday single-user only, and may it store any transcript/audio at all? If yes, what retention period and backup/encryption policy are acceptable?
- Which search provider is acceptable for query privacy, and does “offline-first” mean the product must visibly refuse web search while disconnected?
- Is a Hyprland config bind acceptable for PTT? It materially reduces the need for keyboard-device privilege.

