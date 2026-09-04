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
    SHIPPED   both prompt regions                          (criterion 3.3)
    SHIPPED   the confirm decision and the panic gate      (criterion 3.5)
    next      eval fixtures, hotwords, describe_action     (3.6, 3.7)

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
    #: The planner-prompt entry for this action, VERBATIM. `prompt.py`
    #: renders `f"  {id:<21}{summary}"` per capability and the assembled
    #: SYSTEM_POLICY is byte-identical to the hand-written one it replaced
    #: -- `tests/test_prompt.py` pins that. Compressing this text is a
    #: separate, measurable commit (owner, 2026-09-04): today's `open_app`
    #: paragraph is the ADR-118 text that fixed D31 and E61-E64 test it,
    #: so rewriting it inside a behaviour-freeze refactor would make an
    #: intended change and a regression indistinguishable.
    summary: str
    #: ONE clause for the chat persona's toolset sentence, or None for a
    #: capability that never reaches the executor. `prompt.py` joins these
    #: in record order, so the persona cannot deny an ability the schema
    #: has -- F2 closed by construction rather than by a keyword test. It
    #: had to be closed twice by hand already: `system_wifi` was missing
    #: from G12 until D24, and the whole app enum after ADR-097 (F2), the
    #: second of which the NAME-coverage test could not see because an app
    #: id is a parameter VALUE. No default: a new capability that forgets
    #: its clause does not construct.
    persona: str | None
    #: The confirm question, spoken VERBATIM when a tier says to ask. It is a
    #: field and not a template because the five live questions are not one
    #: sentence shape: `clipboard_read` asks "Do you want me to ..." while the
    #: other three ask "Are you sure you want to ...", and ADR-120(b) freezes
    #: every existing gate bit-for-bit. FIRST_USE appends " I'll remember."
    ask: Callable[[Params], str] | None = None
    #: What the held `PendingAction` records, for the audit row and for the
    #: daemon's re-ask ("...you asked me to <describe>"). Shorter than `ask`
    #: and not derivable from it.
    describe: Callable[[Params], str] | None = None
    #: What a FIRST_USE approval is keyed to: (kind, subject, argv).
    #: `argv` is fingerprinted, because `desktop.app_key` resolves a collision
    #: with `setdefault` — first wins — so an uninstall-then-install can hand a
    #: stored approval to a DIFFERENT binary (design §3.3).
    subject: Callable[[Params], tuple[str, str, tuple[str, ...]]] | None = None

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


def _open_app_subject(params: Params) -> tuple[str, str, tuple[str, ...]]:
    """What an `open_app` approval is keyed to. The argv comes from the app
    table — never from the model — so the fingerprint is over code-owned
    strings."""
    key = params.get("app", "")
    app = APPS.get(key)
    return ("app", key, app.argv if app is not None else ())


def _open_app_describe(params: Params) -> str:
    app = APPS.get(params.get("app", ""))
    return f"open {app.display if app is not None else params.get('app', '')}"


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
    Capability(
        "none",
        _NO_PARAMS,
        Risk.NONE,
        summary=(
            "a truly ambiguous request, or ANY request to delete, destroy, or "
            "run shell commands, or anything outside your abilities. Refuse "
            "those by choosing none. params: {}"
        ),
        persona=None,
    ),
    Capability(
        "chat",
        _NO_PARAMS,
        Risk.NONE,
        summary=(
            "casual conversation, greetings (\"hi\", \"how are you\"), questions "
            "about YOU (who/what are you, what can you do), small talk, "
            "opinions, jokes, or a request for a suggestion. Talk about "
            "yourself, your apps, the user's saved preferences, or this "
            "machine. params: {}"
        ),
        persona=None,
    ),
    Capability(
        "open_app",
        _enum(app=APP_ENUM),
        _open_app_risk,
        summary=(
            "launch an installed application. params: {\"app\": one id}. Five ids "
            "are canonical: \"browser\" (Brave), \"terminal\" (foot), \"editor\" (VS "
            "Code / Code), \"video\" (mpv), \"vlc\" (VLC). Use one ONLY when the "
            "user says the generic word (\"a browser\", \"the editor\") or names "
            "that exact program (\"Brave\" -> browser, \"Code\" -> editor, \"foot\" "
            "-> terminal, \"mpv\" -> video). If the user NAMES A DIFFERENT "
            "PROGRAM, emit that program's own id, never the canonical one for "
            "its category: \"firefox\" -> \"firefox\" (NOT \"browser\"), \"kitty\" -> "
            "\"kitty\" (NOT \"terminal\"), \"neovim\" -> \"neovim\" (NOT \"editor\"). ANY "
            "installed application works: emit its COMMAND name in lowercase "
            "(\"discord\", \"spotify\", \"gufw\", \"blueman-manager\" -> "
            "\"blueman_manager\"), or, if you do not know the command, its "
            "displayed name lowercased with underscores for spaces "
            "(\"bluetooth_manager\", \"firewall_configuration\", \"zen browser\" -> "
            "\"zen_browser\"). Never shorten an id. If it is not installed the "
            "request fails closed and nothing runs, so emit the id rather than "
            "refusing."
        ),
        persona=(
            "open installed applications (Brave the browser, a terminal, VS Code, "
            "mpv, VLC, and other installed desktop apps)"
        ),
        ask=lambda p: f"Do you want me to {_open_app_describe(p)}?",
        describe=_open_app_describe,
        subject=_open_app_subject,
    ),
    # Egress. The ONLY tool that reaches the network, and a turn that consumes
    # its results is grammar-locked to action=none (invariant #1).
    Capability(
        "web_search",
        _text("query"),
        Risk.LOW,
        summary=(
            "look up any fact or current/real-world information: weather, news, "
            "sports results, prices, \"who/what/when/where/how\" questions about "
            "the world. params: {\"query\": text}"
        ),
        persona="search the web for real-world facts",
    ),
    Capability(
        "open_youtube",
        _NO_PARAMS,
        Risk.LOW,
        summary=(
            "open YouTube's front page. params: {}"
        ),
        persona="open YouTube",
    ),
    Capability(
        "youtube_search",
        _text("query"),
        Risk.LOW,
        summary=(
            "play or find something on YouTube — including \"put on\" or \"play "
            "some\" music, a song, artist, or genre (e.g. lo-fi, jazz). Music "
            "and video playback requests are youtube_search, not none. params: "
            "{\"query\": text}"
        ),
        persona="search or play things on YouTube",
    ),
    Capability(
        "remember_preference",
        _text("key", "value"),
        Risk.LOW,
        summary=(
            "the user states a lasting preference or how to be addressed. "
            "params: {\"key\": text, \"value\": text}"
        ),
        persona="remember a preference",
    ),
    Capability(
        "forget_preference",
        _text("key"),
        Risk.LOW,
        summary=(
            "the user asks to forget a preference. params: {\"key\": text}"
        ),
        persona="forget a preference",
    ),
    Capability(
        "set_reminder",
        _text("seconds", "message"),
        Risk.LOW,
        summary=(
            "the user asks to set a timer, alarm, or reminder (e.g. \"remind me "
            "in 10 minutes to ...\", \"set a timer for 5 minutes\"). Convert "
            "duration to integer seconds in \"seconds\" (e.g. 5 mins -> \"300\"). "
            "params: {\"seconds\": text, \"message\": text}"
        ),
        persona="set a timer or reminder",
    ),
    Capability(
        "list_reminders",
        _NO_PARAMS,
        Risk.NONE,
        summary=(
            "the user asks what reminders or timers are active. params: {}"
        ),
        persona="list active timers",
    ),
    # No params, deliberately. `id` used to be declared here as required text,
    # which made the tool unusable: reminder ids are `rem_<hex8>` and are never
    # spoken or shown, so the planner could not know one — while the validator
    # rejected an empty string, so turn.py's "cancel the latest" branch was
    # unreachable and every "cancel my timer" answered "No active timer to
    # cancel." A param the model can never fill is also what invariant #2
    # forbids: an opaque id from a CLOSED set, or nothing (ADR-070).
    Capability(
        "cancel_reminder",
        _NO_PARAMS,
        Risk.LOW,
        summary=(
            "the user asks to cancel or remove a timer or reminder. params: {}"
        ),
        persona="cancel a timer",
    ),
    Capability(
        "set_dnd",
        _NO_PARAMS,
        Risk.LOW,
        summary=(
            "the user asks for quiet, \"do not disturb\", \"let's talk later\", or "
            "\"be quiet\". params: {}"
        ),
        persona="enter quiet mode",
    ),
    Capability(
        "resume_dnd",
        _NO_PARAMS,
        Risk.LOW,
        summary=(
            "the user explicitly says \"resume\" or \"disable quiet mode\". params: "
            "{}"
        ),
        persona="leave quiet mode",
    ),
    Capability(
        "system_volume",
        _enum(direction=VOLUME_ENUM),
        Risk.LOW,
        summary=(
            "adjust or mute volume (\"volume up\", \"turn it down\", \"mute\", "
            "\"unmute\"). params: {\"direction\": \"up\" | \"down\" | \"mute\" | "
            "\"unmute\"}"
        ),
        persona="change the volume",
    ),
    Capability(
        "system_brightness",
        _enum(direction=BRIGHTNESS_ENUM),
        Risk.LOW,
        summary=(
            "adjust display brightness (\"brightness up\", \"dim screen\"). params: "
            "{\"direction\": \"up\" | \"down\"}"
        ),
        persona="change screen brightness",
    ),
    Capability(
        "system_media",
        _enum(action=MEDIA_ENUM),
        Risk.LOW,
        summary=(
            "control media playback (\"pause music\", \"next track\", \"previous "
            "track\", \"play\"). params: {\"action\": \"play_pause\" | \"next\" | "
            "\"previous\" | \"stop\"}"
        ),
        persona="control media playback",
    ),
    Capability(
        "system_wifi",
        _enum(state=WIFI_ENUM),
        _wifi_risk,
        summary=(
            "turn Wi-Fi on or off (\"turn off wifi\", \"enable wifi\"). params: "
            "{\"state\": \"on\" | \"off\"}"
        ),
        persona="turn Wi-Fi on or off",
        ask=lambda p: "Are you sure you want to turn off Wi-Fi?",
        describe=lambda p: "turn off Wi-Fi",
    ),
    Capability(
        "hypr_workspace",
        _enum(workspace=WORKSPACE_ENUM),
        Risk.LOW,
        summary=(
            "switch to a workspace (\"workspace 2\", \"go to workspace 3\"). "
            "params: {\"workspace\": \"1\"…\"10\"}"
        ),
        persona="switch workspaces",
    ),
    Capability(
        "hypr_window",
        _enum(action=WINDOW_ENUM),
        _window_risk,
        summary=(
            "manage window focus, fullscreen, or closing (\"focus left\", "
            "\"fullscreen\", \"close window\"). params: {\"action\": \"focus_left\" | "
            "\"focus_right\" | \"focus_up\" | \"focus_down\" | \"fullscreen\" | "
            "\"close\"}"
        ),
        persona="manage windows (focus, fullscreen, close)",
        ask=lambda p: "Are you sure you want to close the active window?",
        describe=lambda p: "close active window",
    ),
    Capability(
        "file_open",
        _text("alias"),
        Risk.LOW,
        summary=(
            "open a registered file (\"open my notes\", \"open my config\", \"open "
            "my todo\"). params: {\"alias\": text}"
        ),
        persona="open a registered file",
    ),
    Capability(
        "create_note",
        _text("content"),
        Risk.LOW,
        summary=(
            "capture a quick note (\"note that ...\", \"take a note ...\", \"save a "
            "note ...\"). params: {\"content\": text}"
        ),
        persona="take a note",
    ),
    Capability(
        "read_notes",
        _NO_PARAMS,
        Risk.NONE,
        summary=(
            "read saved notes (\"read my notes\", \"what are my notes\"). params: "
            "{}"
        ),
        persona="read your notes",
    ),
    # Reading the clipboard ALOUD puts its contents into whatever room Friday
    # is in — a copied password or 2FA code included. Speaking it because the
    # planner matched a phrase is not acceptable, so it is gated even though it
    # is read-only: opt-in is not a gate, and a mishear is exactly what a gate
    # is for (ADR-068a/ADR-104, OQ-34).
    Capability(
        "clipboard_read",
        _NO_PARAMS,
        Risk.ALWAYS,
        summary=(
            "read current clipboard (\"what is in my clipboard\", \"read "
            "clipboard\"). params: {}"
        ),
        persona="read the clipboard",
        ask=lambda p: "Do you want me to read your clipboard aloud?",
        describe=lambda p: "read the clipboard aloud",
    ),
    Capability(
        "clipboard_set",
        _text("text"),
        Risk.ALWAYS,
        summary=(
            "copy text to clipboard (\"copy ... to clipboard\"). params: {\"text\": "
            "text}"
        ),
        persona="copy text to the clipboard",
        ask=lambda p: "Are you sure you want to overwrite your clipboard?",
        describe=lambda p: "overwrite clipboard",
    ),
    Capability(
        "dictation_mode",
        _enum(action=DICTATION_ENUM),
        Risk.LOW,
        summary=(
            "start or stop dictation mode (\"start dictation\", \"stop "
            "dictation\"). params: {\"action\": \"start\" | \"stop\"}"
        ),
        persona="type dictation",
    ),
)

CAPABILITIES: Final[Mapping[str, Capability]] = MappingProxyType(
    {c.id: c for c in _ALL}
)
