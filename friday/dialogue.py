"""In-session dialogue memory (G8, invariant #7).

A bounded ring of recent (user, friday) exchanges, held in RAM and discarded
on exit. It is NEVER written to disk: raw transcripts on disk are a permanent
plaintext record of private speech and a durable-injection channel (the T1
attack the grammar-lock design blocks). Cross-session continuity is a later
stage (distilled, inerted summaries -- design §"Stage 3"), not this buffer.

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
        # deque(maxlen=…) auto-trims the oldest on append -- the whole bound.
        self._turns = deque(self._turns, maxlen=self.max_turns)

    def add(self, user: str, friday: str) -> None:
        self._turns.append((user, friday))

    def render(self) -> str:
        """Recent exchanges as plain text, oldest first. Empty when no history."""
        return "\n".join(f"You: {u}\nFriday: {f}" for u, f in self._turns)

    def __len__(self) -> int:
        return len(self._turns)
