"""Textual TUI for text mode: type an utterance, see the planned action,
see the outcome (architecture.md §2).

G3 scope: one input, a scrolling log, a mode indicator, and one turn in
flight at a time (the input is disabled while a turn runs — the minimal
form of FR-5; the full concurrency test lives at G6). No confirm prompt
yet: Phase 1 ships only reversible actions (FR-33), so nothing here needs a
guard. When an irreversible tool is ever added, its confirm prompt lands
with it.
"""

from __future__ import annotations

import uuid

from textual import work
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Input, RichLog

from ..llm.client import LlamaClient
from ..turn import run_turn


class FridayTUI(App):
    CSS = """
    #log { border: round $primary; padding: 0 1; }
    Input { dock: bottom; }
    """
    TITLE = "Friday — text mode"

    def __init__(self, client: LlamaClient, *, dry_run: bool) -> None:
        super().__init__()
        self._client = client
        self._dry_run = dry_run
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
        inp.disabled = True  # one turn in flight
        self.query_one("#log", RichLog).write(f"[bold cyan]you[/] {text}")
        self._do_turn(text)

    @work(exclusive=True)
    async def _do_turn(self, text: str) -> None:
        log = self.query_one("#log", RichLog)
        result = await run_turn(
            text, self._client, request_id=uuid.uuid4().hex, dry_run=self._dry_run
        )
        params = f" {result.params}" if result.params else ""
        log.write(f"[dim]→ action: {result.plan_name}{params}[/]")
        log.write(f"[bold green]friday[/] {result.spoken}")
        inp = self.query_one(Input)
        inp.disabled = False
        inp.focus()
