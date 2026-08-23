"""Minimal synchronous llama-server client for the G2 eval harness.

Scope: this is deliberately small and synchronous. The orchestrator's real
client (async, prompt-region assembly, the final.gbnf invariant of
architecture.md §4) arrives with the turn loop at a later gate. What is
true here and must stay true: retry ONLY on connect, NEVER on generate
(a generation is a side-effect-free but expensive call, and the eval
harness wants deterministic single-shot results).

Uses the stdlib only — no runtime dependency is added at G2.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import schema


class LlamaUnreachable(Exception):
    """llama-server could not be reached (maps to E_LLM_DOWN)."""


class LlamaTimeout(Exception):
    """Generation exceeded the budget (maps to E_LLM_TIMEOUT)."""


@dataclass(frozen=True)
class LlamaClient:
    base_url: str = "http://127.0.0.1:8080"
    timeout_s: float = 30.0
    connect_retries: int = 3
    connect_backoff_s: float = 0.5

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
        """Return the assistant message content for one constrained turn.

        `grammar` is a GBNF string enforced server-side. `temperature=0.0`
        keeps eval runs reproducible.
        """
        # Invariant #1 (T1, ADR-008): a request that consumed untrusted web data
        # MUST be grammar-locked to final.gbnf (action name == "none"), so the
        # model cannot dispatch no matter what the injected text says. Enforced
        # HERE — the one place every request passes through — not at the call site.
        if untrusted and grammar != schema.build_final_grammar():
            # NOT an assert: a `python -O` run strips asserts, and this is a T1
            # control (ADR-008), not a debug check. Fail closed, always.
            raise ValueError("untrusted turn must use final.gbnf")
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

        last_exc: Exception | None = None
        for attempt in range(self.connect_retries):
            req = urllib.request.Request(
                f"{self.base_url}/v1/chat/completions",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    body = json.loads(resp.read())
                return body["choices"][0]["message"]["content"]
            except urllib.error.URLError as exc:
                # A timeout surfaces as URLError(reason=socket.timeout). That
                # is a generate failure, not a connect failure — do not retry.
                reason = getattr(exc, "reason", None)
                if isinstance(reason, TimeoutError) or "timed out" in str(reason):
                    raise LlamaTimeout(str(reason)) from exc
                last_exc = exc
                if attempt < self.connect_retries - 1:
                    time.sleep(self.connect_backoff_s * (attempt + 1))
            except (KeyError, IndexError, json.JSONDecodeError) as exc:
                raise LlamaUnreachable(f"malformed server response: {exc}") from exc

        raise LlamaUnreachable(f"{self.base_url} unreachable: {last_exc}")

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(
                f"{self.base_url}/health", timeout=5.0
            ) as resp:
                return json.loads(resp.read()).get("status") == "ok"
        except (urllib.error.URLError, json.JSONDecodeError):
            return False
