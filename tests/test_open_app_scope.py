"""`open_app` reaches every installed application, not five (ADR-097).

Two things are locked here, and they are the two the user decided:

  - a Settings panel is launchable but CONFIRMED, never dispatched straight
    off a phrase match — so a misheard command cannot silently open the
    firewall;
  - an ordinary application asks ONCE and is then remembered — `Risk.FIRST_USE`
    (ADR-120, Phase 3 criterion 3.5). Until 2026-09-04 it dispatched with no
    ceremony at all; the owner chose the ask-once tier over the safer
    plumbing-only option, and OQ-69 is the measurement of whether the burden is
    tolerable, because the eval gate structurally cannot see it.

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


def test_an_ordinary_app_asks_once_and_is_then_remembered(tmp_path) -> None:
    """`Risk.FIRST_USE`, end to end through `run_turn` (criterion 3.5).

    The store starts empty, so the first turn must ASK; the answer is recorded
    by the handshake, and the second identical turn must dispatch without a
    question. Both halves matter: a tier that always asks is `ALWAYS` wearing
    the wrong name, and one that never asks is `LOW`.
    """
    from friday.store.approvals import ApprovalStore
    from friday.store.db import Database
    from friday.turn import resolve_pending

    approvals = ApprovalStore(Database(tmp_path / "a.db"))

    first = asyncio.run(run_turn(
        "open my browser", StubClient(_plan("browser")), request_id="t1",
        dry_run=True, approvals=approvals,
    ))
    assert not first.dispatched, "an unapproved app dispatched without asking"
    assert isinstance(first.pending, PendingAction)
    assert "I'll remember." in first.spoken
    assert approvals.list_approvals() == []

    asyncio.run(resolve_pending(
        first.pending, "yes", prefs=None, audit=None, request_id="t1",
        dry_run=True, approvals=approvals,
    ))
    assert [a.subject for a in approvals.list_approvals()] == ["browser"]

    second = asyncio.run(run_turn(
        "open my browser", StubClient(_plan("browser")), request_id="t2",
        dry_run=True, approvals=approvals,
    ))
    assert second.pending is None, "an approved app asked again"
    assert second.dispatched


def test_a_declined_first_use_records_nothing_and_asks_again(tmp_path) -> None:
    """"no" is not "not yet decided" — but it is also not a stored decision.
    Design §3.3: a decline records the audit row and stores NOTHING, so the
    next attempt asks rather than being permanently refused."""
    from friday.store.approvals import ApprovalStore
    from friday.store.db import Database
    from friday.turn import resolve_pending

    approvals = ApprovalStore(Database(tmp_path / "a.db"))
    r = asyncio.run(run_turn(
        "open my browser", StubClient(_plan("browser")), request_id="t1",
        dry_run=True, approvals=approvals,
    ))
    asyncio.run(resolve_pending(
        r.pending, "no", prefs=None, audit=None, request_id="t1",
        dry_run=True, approvals=approvals,
    ))
    assert approvals.list_approvals() == []

    again = asyncio.run(run_turn(
        "open my browser", StubClient(_plan("browser")), request_id="t2",
        dry_run=True, approvals=approvals,
    ))
    assert isinstance(again.pending, PendingAction)


def test_an_approval_for_a_changed_binary_asks_again(tmp_path) -> None:
    """Criterion 3.9 at the turn level, not just the store's.

    `desktop.app_key` resolves a collision with `setdefault`, first wins, so an
    uninstall-then-install can rebind an id to a different binary. A grant is
    keyed to the argv's fingerprint, so the stale one does not apply.
    """
    from friday.store.approvals import ApprovalStore, fingerprint
    from friday.store.db import Database

    approvals = ApprovalStore(Database(tmp_path / "a.db"))
    approvals.approve("app", "browser", fingerprint(("some-other-browser",)))

    r = asyncio.run(run_turn(
        "open my browser", StubClient(_plan("browser")), request_id="t",
        dry_run=True, approvals=approvals,
    ))
    assert isinstance(r.pending, PendingAction), "a stale approval was honoured"


def test_first_use_without_a_store_asks_every_time() -> None:
    """Degrade in the safe direction: an approval that cannot be recorded must
    not be assumed. `run_turn` with no `approvals` asks, every time."""
    r = asyncio.run(run_turn(
        "open my browser", StubClient(_plan("browser")), request_id="t",
        dry_run=True,
    ))
    assert isinstance(r.pending, PendingAction)


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


def test_a_vendor_path_supplies_the_name_a_human_actually_says():
    """D33, measured live 2026-09-04. Android Studio's generated id was
    `android_studio_panda_4_2025_3_4_patch_1` — the `.desktop` Name with the
    release in it — and its binary alias was `studio`, so nothing a person would
    say could reach it. The planner emitted `android_studio` 3x and
    `android_studio_panda_4` once; every one failed closed.

    A vendor that installs to `.../<app-name>/bin/<exe>` has written the known
    name into the path already."""
    from friday.tools.apps import APPS

    for spoken, exe in (
        ("android_studio", "studio"),
        ("intellij_idea", "idea"),
        ("pycharm", "pycharm"),
        ("webstorm", "webstorm"),
        ("dataspell", "dataspell"),
    ):
        assert spoken in APPS, f"{spoken} unreachable"
        assert APPS[spoken].argv[0].endswith(f"/bin/{exe}")


def test_the_path_alias_drops_filesystem_furniture_and_ambiguity():
    """The rule must not turn `/usr/bin/discord` into an app called `usr`, and
    must not resolve an alias that two different entries claim. Measured:
    `/usr/lib/jvm/java-26-openjdk/bin/{jshell,jconsole}` produce ONE candidate
    alias for TWO entries, and picking either silently would be the `setdefault`
    hazard `argv_sha256` exists to catch (ADR-120). Ambiguous is dropped."""
    from friday.tools.apps import APPS

    for furniture in ("usr", "local", "opt", "bin", "lib", "jre", "jvm", "share"):
        assert furniture not in APPS

    assert "java_26_openjdk" not in APPS  # ambiguous: jshell AND jconsole
    # ...while both entries themselves remain reachable under their own ids.
    assert "openjdk_java_26_shell" in APPS
    assert "openjdk_java_26_console" in APPS
