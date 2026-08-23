"""Textual TUI for text mode: type an utterance, see the planned action,
see the outcome (architecture.md §2).

G4 adds the confirm-first preference handshake (ADR-037). When a turn
returns a `pending` preference, the input switches to a yes/no prompt; the
next line is matched deterministically (no second model turn — FR-5 holds),
and only an explicit yes writes. Everything else cancels. This is the
"confirm prompt" architecture.md §3.1 anticipated; it is NOT the guard for
an irreversible tool (Phase 1 ships none — FR-33).

One turn in flight at a time: the input is disabled while a turn runs.
"""

from __future__ import annotations

import uuid

from textual import work
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Input, RichLog

from ..llm.client import LlamaClient
from ..store.audit import AuditLog
from ..store.prefs import PendingPreference, PrefStore
from ..turn import confirm_preference, is_affirmation, run_turn
from ..ui import templates


class FridayTUI(App):
    CSS = """
    #log { border: round $primary; padding: 0 1; }
    Input { dock: bottom; }
    """
    TITLE = "Friday — text mode"

    def __init__(
        self,
        client: LlamaClient,
        *,
        prefs: PrefStore | None = None,
        audit: AuditLog | None = None,
        dry_run: bool,
    ) -> None:
        super().__init__()
        self._client = client
        self._prefs = prefs
        self._audit = audit
        self._dry_run = dry_run
        self._pending: PendingPreference | None = None
        self.sub_title = "DRY-RUN (no launch)" if dry_run else "LIVE"

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="log", wrap=True, markup=True)
        yield Input(placeholder="Say something to Friday…")
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one("#log", RichLog)
        if not self._client.health():
            log.write("[red]llama-server unreachable — start it with `just serve`.[/]")
        else:
            log.write("[dim]Ready. Type an utterance and press Enter.[/]")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        inp = self.query_one(Input)
        inp.value = ""
        self.query_one("#log", RichLog).write(f"[bold cyan]you[/] {text}")

        if self._pending is not None:  # answering a confirm prompt
            inp.disabled = True
            self._resolve_pending(text)
            return

        inp.disabled = True  # one turn in flight
        self._do_turn(text)

    @work(exclusive=True)
    async def _do_turn(self, text: str) -> None:
        log = self.query_one("#log", RichLog)
        result = await run_turn(
            text,
            self._client,
            request_id=uuid.uuid4().hex,
            dry_run=self._dry_run,
            prefs=self._prefs,
            audit=self._audit,
        )
        params = f" {result.params}" if result.params else ""
        log.write(f"[dim]→ action: {result.plan_name}{params}[/]")
        log.write(f"[bold green]friday[/] {result.spoken}")
        if result.pending is not None:
            self._pending = result.pending  # await a yes/no next
        self._reenable()

    @work(exclusive=True)
    async def _resolve_pending(self, answer: str) -> None:
        log = self.query_one("#log", RichLog)
        pending = self._pending
        self._pending = None
        if pending is None:  # defensive
            self._reenable()
            return
        if is_affirmation(answer):
            spoken = await confirm_preference(
                pending, self._prefs, self._audit, request_id=uuid.uuid4().hex
            )
        else:
            spoken = templates.cancelled_preference()
        log.write(f"[bold green]friday[/] {spoken}")
        self._reenable()

    def _reenable(self) -> None:
        inp = self.query_one(Input)
        inp.disabled = False
        inp.focus()
