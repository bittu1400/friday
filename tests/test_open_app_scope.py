"""`open_app` reaches every installed application, not five (ADR-097).

Two things are locked here, and they are the two the user decided:

  - a Settings panel is launchable but CONFIRMED, never dispatched straight
    off a phrase match — so a misheard command cannot silently open the
    firewall;
  - an ordinary application still dispatches with no ceremony.

The third lock is the one that must not regress: the enum is still CLOSED.
`tests/fixtures/adversarial.jsonl` AS-7/AS-8/AS-9 already assert that a path,
a command injection and a Cyrillic confusable are rejected in the `app` slot;
widening the set must not turn any of them into a launch.
"""

import asyncio
from dataclasses import dataclass

import pytest

from friday.llm import schema, validate
from friday.llm.validate import SchemaError
from friday.tools.apps import APPS, App, build_apps
from friday.tools.desktop import DesktopApp
from friday.turn import PendingAction, run_turn


@dataclass
class StubClient:
    reply: str

    def complete(self, *, system: str, user: str, grammar: str) -> str:
        return self.reply

    def health(self) -> bool:
        return True


def _plan(app: str) -> str:
    return '{"action":{"name":"open_app","params":{"app":"%s"}}}' % app


# --- the merge -------------------------------------------------------------


def test_curated_ids_survive_and_win_collisions() -> None:
    # The eval fixtures, the prompt and the habits miner all speak these five.
    # A scanned entry that normalises to the same id must not shadow them.
    scanned = {"browser": DesktopApp(("some-other-browser",), "Other")}
    apps = build_apps(scanned)
    assert apps["browser"] == App(("brave",), "Brave")


def test_console_app_is_wrapped_in_the_terminal() -> None:
    # Spawning `btop` detached starts a headless process while Friday says
    # "Opened btop." — the ADR-043 shape. argv is built here, from the
    # curated terminal, never from a param.
    apps = build_apps({"btop": DesktopApp(("btop",), "btop++", needs_terminal=True)})
    assert apps["btop"].argv == ("foot", "-e", "btop")


def test_binary_name_becomes_a_second_id() -> None:
    # "Visual Studio Code" is `code` on the command line, and `code` is what a
    # user says.
    apps = build_apps({"visual_studio_code": DesktopApp(("/usr/bin/code",), "Visual Studio Code")})
    assert apps["code"].display == "Visual Studio Code"


def test_the_enum_is_the_app_table() -> None:
    assert set(schema.APP_ENUM) == set(APPS)
    assert len(APPS) > 5, "the scan found nothing — open_app is still five apps"


# --- what the enum still rejects (the thing that must not regress) ---------


def test_hostile_app_values_are_still_rejected() -> None:
    # The enum is the gate, exactly as before the widening: a path, an
    # injection, a Cyrillic confusable and a name that is simply not installed
    # all fail closed. `validate` raises; the turn loop turns that into none.
    for hostile in ("/bin/sh", "browser; rm -rf ~", "brоwser", "definitely_not_installed"):
        with pytest.raises(SchemaError):
            validate.validate(_plan(hostile))


def test_generic_launcher_is_not_an_app_id() -> None:
    # `Exec=env DESKTOPINTEGRATION=0 anytype` must not make "env" an app.
    apps = build_apps({"anytype": DesktopApp(("env", "FOO=1", "anytype"), "Anytype")})
    assert "env" not in apps
    assert apps["anytype"].display == "Anytype"


# --- the confirm gate ------------------------------------------------------


def test_settings_panel_is_confirmed_not_dispatched() -> None:
    # A real entry off this machine, not a stub: APPS is a frozen mapping on
    # purpose, and the point of the test is that the SCAN produced something
    # the confirm gate catches.
    key = next(k for k, v in APPS.items() if v.confirm)
    r = asyncio.run(run_turn(
        f"open {key}", StubClient(_plan(key)), request_id="t", dry_run=True,
    ))

    assert r.plan_name == "open_app"
    assert not r.dispatched, "a Settings panel dispatched without a confirm"
    assert isinstance(r.pending, PendingAction)
    assert r.pending.tool_id == "open_app"
    assert APPS[key].display in r.spoken


def test_ordinary_app_is_not_confirmed() -> None:
    r = asyncio.run(run_turn(
        "open my browser", StubClient(_plan("browser")), request_id="t", dry_run=True,
    ))
    assert r.pending is None, "an ordinary app must not ask for confirmation"


def test_the_planner_may_spell_an_app_id_the_way_a_human_says_it():
    """D34, measured live 2026-09-04. The planner heard "Easy Effects" and
    emitted `easy-effects`; the enum holds `easy_effects` and the turn failed
    closed, losing a real installed application. It has to guess the spelling —
    the grammar never enumerates param values (ADR-097) and the prompt lists
    only the common ids — so the validator folds the candidate through
    `desktop.app_key`, the same function that generated every id."""
    from friday.llm.validate import _validate_params as validate_params

    for spoken in ("easy-effects", "Easy Effects", "EASY_EFFECTS", "easy effects"):
        assert validate_params("open_app", {"app": spoken})["app"] == "easy_effects"

    # An id that is already exact is untouched, and takes the fast path.
    assert validate_params("open_app", {"app": "zen_browser"})["app"] == "zen_browser"


def test_the_spelling_fold_is_not_a_fuzzy_matcher():
    """The fold is `app_key`, which is a WHITELIST — casefold, then `[^a-z0-9]+`
    to underscore — so the adversarial fixtures still fail closed. A substring
    or fuzzy matcher would resolve the first of these to `browser`, which is
    exactly why one is permanently rejected (AS-8, ADR-097)."""
    from friday.llm.validate import AppNotInstalledError
    from friday.llm.validate import _validate_params as validate_params

    for hostile in (
        "browser; rm -rf ~",   # AS-8 -> browser_rm_rf
        "/bin/sh",             # AS-7 -> bin_sh
        "../../etc/passwd",    # -> etc_passwd
        "brаve",          # AS-9, Cyrillic a -> br_ve
        "brow",                # a real id's PREFIX must not resolve
        "browserr",            # nor a near-miss
    ):
        with pytest.raises(AppNotInstalledError) as exc:
            validate_params("open_app", {"app": hostile})

        # The rejection must name what the planner ACTUALLY emitted, not the
        # folded form. `E_TOOL_NOTFOUND: app 'jin_browser' not installed` is
        # what turned a session of bisecting into a grep on 2026-09-03, and
        # again on 2026-09-04 — folding before reporting would have logged
        # `easy_effects` for an input of `easy-effects` and hidden the defect
        # that was actually there. Applying the fold unconditionally still
        # fails closed, so only this assertion catches it.
        assert exc.value.app_name == hostile
