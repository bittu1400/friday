"""One record per capability. Everything else is derived (Phase 3, design §1).

A capability lives in **ten** places today — the param schema, both grammars,
the planner prompt, the chat persona, the confirm branches, the panic gate, an
eval fixture, `STT_HOTWORDS`, `habits.describe_action`, and the audit row shape
— and every recent defect is a place someone forgot one:

  D26  `STT_HOTWORDS` had no G12 vocabulary, so "wifi" came back as
       wife / weapon / way / life on four consecutive turns.
  D31  ADR-097 widened the app enum 5 -> 165 and left the prompt and the
       hotwords at Phase 1, so for a month no scanned app was ever dispatched.
  D33  the id derived from a `.desktop` Name was not a name anyone says, while
       four of those names sat in the hotword list.
  F2   the chat persona denied an ability the schema had, twice, months apart.
  F1   the panic switch guarded one of eleven side-effecting paths.

The fix is fewer places. This module is the first of them, and it is being
filled one derivation at a time so each step keeps the contract visible:

    SHIPPED   `PARAM_SCHEMA` and therefore both grammars   (criterion 3.2)
    SHIPPED   the risk tier for all 25 actions             (criterion 3.8)
    next      the prompt regions                           (criterion 3.3)
    next      the confirm decision and the panic gate      (criterion 3.5)
    later     eval fixtures, hotwords, describe_action     (3.6, 3.7)

**The contract for the whole phase**: if `just grammar` stops reproducing the
committed `.gbnf` byte-for-byte, or `just eval` moves off 64/64 with zero
regressions, the refactor changed behaviour and is wrong. `tests/test_eval_gate.py`
is what makes the second half of that a contract rather than a claim (M6).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Callable, Final, Mapping

from .tools.apps import APPS

Params = Mapping[str, str]


class Risk(Enum):
    """What a capability costs if it fires when it should not.

    The tier decides the confirm behaviour and the panic gate, in ONE place,
    for every capability — replacing five hand-coded confirm branches in
    `turn.py` and the twelve `config.is_disabled()` checks Phase 1 scattered
    across four modules (design §1, §3.1).
    """

    NONE = "none"           # read-only. never confirms.
    LOW = "low"             # reversible, undramatic. never confirms.
    FIRST_USE = "first_use"  # confirms once per subject, then remembered
    ALWAYS = "always"       # confirms every time
    NAMED = "named"         # confirms every time AND speaks the consequence


# A tier, or a code-owned function of the params when the tier depends on one.
#
# Three of the five live confirm gates are conditional on a PARAM VALUE rather
# than on the action: `system_wifi` gates only on "off", `hypr_window` only on
# "close", and `open_app` only for a Settings panel. Design §1 declared
# `risk: Risk`, a flat field, which cannot express any of them — found while
# building this module, decided by the owner 2026-09-04. The callable form
# matches the record's existing shape (`subject` and `describe` are already
# `Callable | None`) and keeps risk in CODE, never a model judgement.
RiskSpec = Risk | Callable[[Params], Risk]


@dataclass(frozen=True)
class Capability:
    """One action Friday can take.

    Fields are added as each derivation lands, so that every field in this
    record has a consumer and a test. `risk` has NO DEFAULT: criterion 3.8 is
    that no capability can ship without an explicit tier, and a default is how
    that stops being true.
    """

    id: str
    params: Mapping[str, Mapping[str, object]]
    risk: RiskSpec

    def risk_for(self, params: Params) -> Risk:
        """The tier for this invocation. Code, never a model judgement."""
        return self.risk(params) if callable(self.risk) else self.risk


def _enum(**kw: tuple[str, ...]) -> Mapping[str, Mapping[str, object]]:
    return MappingProxyType(
        {k: MappingProxyType({"kind": "enum", "values": v}) for k, v in kw.items()}
    )


def _text(*names: str) -> Mapping[str, Mapping[str, object]]:
    return MappingProxyType({n: MappingProxyType({"kind": "text"}) for n in names})


_NO_PARAMS: Final[Mapping[str, Mapping[str, object]]] = MappingProxyType({})

# --- the closed param vocabularies -----------------------------------------
# Each is exactly the set its registry builder knows how to turn into argv — a
# superset of what the prompt advertises, so no phrasing the planner already
# emits regresses, and anything outside fails closed to action=none.
#
# These are enums and not text because a prompt is not a control (ADR-008):
# declared as "text" the validator only checked non-emptiness, so an
# off-vocabulary value reached the registry and silently became the WRONG
# action — volume "lower" went UP, brightness anything-but-"up" went DOWN,
# and the spoken line still named what the user asked for (2026-08-25).
APP_ENUM: Final[tuple[str, ...]] = tuple(APPS)
VOLUME_ENUM: Final[tuple[str, ...]] = ("up", "down", "mute", "unmute", "toggle_mute")
BRIGHTNESS_ENUM: Final[tuple[str, ...]] = ("up", "down")
MEDIA_ENUM: Final[tuple[str, ...]] = (
    "play_pause", "play", "pause", "next", "previous", "stop",
)
WIFI_ENUM: Final[tuple[str, ...]] = ("on", "off")
WINDOW_ENUM: Final[tuple[str, ...]] = (
    "focus_left", "focus_right", "focus_up", "focus_down", "fullscreen", "close",
)
DICTATION_ENUM: Final[tuple[str, ...]] = ("start", "stop")
# Ten workspaces as strings, because that is what the planner emits. This was
# `{"kind": "text"}` with the range checked only inside build_argv — the same
# shape that let brightness "brighten" reach a builder that guessed. It matters
# more now: the workspace selects a Lua dispatch constant (ADR-074).
WORKSPACE_ENUM: Final[tuple[str, ...]] = tuple(str(i) for i in range(1, 11))


# --- the three conditional tiers -------------------------------------------
# Each reproduces a hand-coded branch in `turn.py` EXACTLY. ADR-120(b): the
# refactor changes no gate, so `tests/test_confirm_arming.py` — which drives
# `run_turn` for system_wifi{off}, clipboard_set and hypr_window{close} and
# asserts each ARMS without dispatching — must keep passing untouched.

def _wifi_risk(params: Params) -> Risk:
    """Turning Wi-Fi OFF drops the network; turning it on is undramatic."""
    return Risk.ALWAYS if params.get("state") == "off" else Risk.LOW


def _window_risk(params: Params) -> Risk:
    """Closing the focused window can lose unsaved work. Focus and fullscreen
    are free."""
    return Risk.ALWAYS if params.get("action") == "close" else Risk.LOW


def _open_app_risk(params: Params) -> Risk:
    """A Settings panel is launchable but never off a bare phrase match — the
    owner's call 2026-09-02, because refusing them outright would mean
    Bluetooth settings could never be opened by voice at all (ADR-097).

    Everything else is FIRST_USE: ask once per application, remember the answer
    with the argv's fingerprint, never ask again. The owner chose this over the
    safer plumb-only option (ADR-120) because `desktop.app_key`'s `setdefault`
    collision can hand a stored approval to a DIFFERENT binary, and
    `argv_sha256` is the only thing that notices. **FIRST_USE is declared here
    and is not yet live** — it turns on with the approvals table (criterion
    3.9) and the derived gate (3.5), in that order, so the tier never exists
    without the store that makes it mean anything.
    """
    app = APPS.get(params.get("app", ""))
    return Risk.ALWAYS if app is not None and app.confirm else Risk.FIRST_USE


# --- the 25 -----------------------------------------------------------------
# ORDER IS LOAD-BEARING. `ACTIONS` is `tuple(PARAM_SCHEMA)` and the committed
# grammars enumerate the names in exactly this sequence, so a reordering here
# changes `plan.gbnf` and fails criterion 3.2 — which is the point of that test.
_ALL: Final[tuple[Capability, ...]] = (
    # `none` and `chat` never reach the executor. `chat` is routed to
    # llm/chat.py and `none` to a template, so neither can dispatch and both
    # are NONE — but they are still capabilities, because the grammar's name
    # alternation is generated from this tuple.
    Capability("none", _NO_PARAMS, Risk.NONE),
    Capability("chat", _NO_PARAMS, Risk.NONE),
    Capability("open_app", _enum(app=APP_ENUM), _open_app_risk),
    # Egress. The ONLY tool that reaches the network, and a turn that consumes
    # its results is grammar-locked to action=none (invariant #1).
    Capability("web_search", _text("query"), Risk.LOW),
    Capability("open_youtube", _NO_PARAMS, Risk.LOW),
    Capability("youtube_search", _text("query"), Risk.LOW),
    Capability("remember_preference", _text("key", "value"), Risk.LOW),
    Capability("forget_preference", _text("key"), Risk.LOW),
    Capability("set_reminder", _text("seconds", "message"), Risk.LOW),
    Capability("list_reminders", _NO_PARAMS, Risk.NONE),
    # No params, deliberately. `id` used to be declared here as required text,
    # which made the tool unusable: reminder ids are `rem_<hex8>` and are never
    # spoken or shown, so the planner could not know one — while the validator
    # rejected an empty string, so turn.py's "cancel the latest" branch was
    # unreachable and every "cancel my timer" answered "No active timer to
    # cancel." A param the model can never fill is also what invariant #2
    # forbids: an opaque id from a CLOSED set, or nothing (ADR-070).
    Capability("cancel_reminder", _NO_PARAMS, Risk.LOW),
    Capability("set_dnd", _NO_PARAMS, Risk.LOW),
    Capability("resume_dnd", _NO_PARAMS, Risk.LOW),
    Capability("system_volume", _enum(direction=VOLUME_ENUM), Risk.LOW),
    Capability("system_brightness", _enum(direction=BRIGHTNESS_ENUM), Risk.LOW),
    Capability("system_media", _enum(action=MEDIA_ENUM), Risk.LOW),
    Capability("system_wifi", _enum(state=WIFI_ENUM), _wifi_risk),
    Capability("hypr_workspace", _enum(workspace=WORKSPACE_ENUM), Risk.LOW),
    Capability("hypr_window", _enum(action=WINDOW_ENUM), _window_risk),
    Capability("file_open", _text("alias"), Risk.LOW),
    Capability("create_note", _text("content"), Risk.LOW),
    Capability("read_notes", _NO_PARAMS, Risk.NONE),
    # Reading the clipboard ALOUD puts its contents into whatever room Friday
    # is in — a copied password or 2FA code included. Speaking it because the
    # planner matched a phrase is not acceptable, so it is gated even though it
    # is read-only: opt-in is not a gate, and a mishear is exactly what a gate
    # is for (ADR-068a/ADR-104, OQ-34).
    Capability("clipboard_read", _NO_PARAMS, Risk.ALWAYS),
    Capability("clipboard_set", _text("text"), Risk.ALWAYS),
    Capability("dictation_mode", _enum(action=DICTATION_ENUM), Risk.LOW),
)

CAPABILITIES: Final[Mapping[str, Capability]] = MappingProxyType(
    {c.id: c for c in _ALL}
)
