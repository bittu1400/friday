"""The XDG desktop scan is a security surface: it is the one place where a
file NOT written by this project decides what Friday can launch (ADR-097).

These lock the skip rules. A `.desktop` file is data, and the machine's
package manager writes it — so every rule here fails CLOSED: an entry that
cannot be proven safe is not offered at all, rather than offered and
rejected later.
"""

from __future__ import annotations

from pathlib import Path

from friday.tools import desktop


def _write(d: Path, name: str, body: str) -> None:
    (d / name).write_text(body.strip() + "\n")


def test_plain_entry_becomes_a_launchable_app(tmp_path: Path) -> None:
    _write(tmp_path, "discord.desktop", """
[Desktop Entry]
Type=Application
Name=Discord
Exec=/usr/bin/discord --url -- %u
Categories=Network;InstantMessaging;
""")
    apps = desktop.scan([tmp_path])
    assert "discord" in apps
    entry = apps["discord"]
    # Field codes (%u) are dropped: they are launcher placeholders, and a
    # literal "%u" would be passed to the binary as an argument.
    assert entry.argv == ("/usr/bin/discord", "--url", "--")
    assert entry.display == "Discord"
    assert entry.confirm is False
    assert entry.needs_terminal is False


def test_nodisplay_and_hidden_are_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "a.desktop", """
[Desktop Entry]
Type=Application
Name=Agent
Exec=agent
NoDisplay=true
""")
    _write(tmp_path, "b.desktop", """
[Desktop Entry]
Type=Application
Name=Bee
Exec=bee
Hidden=true
""")
    assert desktop.scan([tmp_path]) == {}


def test_non_application_types_are_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "l.desktop", """
[Desktop Entry]
Type=Link
Name=Somewhere
URL=https://example.invalid
""")
    assert desktop.scan([tmp_path]) == {}


def test_root_escalating_exec_is_skipped(tmp_path: Path) -> None:
    # The chosen danger rule #1. pkexec pops a polkit password prompt, so a
    # misheard command becomes "type your root password".
    _write(tmp_path, "gparted.desktop", """
[Desktop Entry]
Type=Application
Name=GParted
Exec=pkexec gparted %f
Categories=System;
""")
    assert desktop.scan([tmp_path]) == {}


def test_shell_exec_is_skipped(tmp_path: Path) -> None:
    # Danger rule #3. Invariant #3 is argv-list, shell=False. Such an entry
    # would be rejected by ban.py at execution anyway — skipping it at scan
    # time means it never becomes a speakable id, so Friday refuses instead of
    # saying "Opened X" and then failing policy.
    _write(tmp_path, "w.desktop", """
[Desktop Entry]
Type=Application
Name=Wrapper
Exec=sh -c "foo && bar"
""")
    assert desktop.scan([tmp_path]) == {}


def test_settings_category_is_flagged_for_confirm(tmp_path: Path) -> None:
    # Danger rule #2, and the user's decision: NOT refused — confirm-gated, so
    # the capability survives but a misheard command cannot spawn one silently.
    _write(tmp_path, "gufw.desktop", """
[Desktop Entry]
Type=Application
Name=Firewall Configuration
Exec=gufw
Categories=GNOME;GTK;Settings;Security;X-GNOME-SystemSettings;
""")
    apps = desktop.scan([tmp_path])
    assert apps["firewall_configuration"].confirm is True


def test_terminal_true_is_flagged_not_launched_bare(tmp_path: Path) -> None:
    # A bare `Exec=btop` spawned detached is a headless process with no window
    # — the ADR-043 failure shape ("reported ok, nothing appeared"). The flag
    # lets apps.py wrap it in the terminal emulator it already owns.
    _write(tmp_path, "btop.desktop", """
[Desktop Entry]
Type=Application
Name=btop++
Exec=btop
Terminal=true
Categories=System;Monitor;
""")
    apps = desktop.scan([tmp_path])
    assert apps["btop"].needs_terminal is True
    assert apps["btop"].argv == ("btop",)


def test_missing_tryexec_is_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "ghost.desktop", """
[Desktop Entry]
Type=Application
Name=Ghost
Exec=ghost
TryExec=/nonexistent/ghost
""")
    assert desktop.scan([tmp_path]) == {}


def test_desktop_action_exec_is_ignored(tmp_path: Path) -> None:
    # firefox.desktop carries three Exec lines; only [Desktop Entry]'s counts.
    _write(tmp_path, "firefox.desktop", """
[Desktop Entry]
Type=Application
Name=Firefox
Exec=/usr/lib/firefox/firefox %u

[Desktop Action new-private-window]
Name=New Private Window
Exec=/usr/lib/firefox/firefox --private-window %u
""")
    assert desktop.scan([tmp_path])["firefox"].argv == ("/usr/lib/firefox/firefox",)


def test_malformed_file_does_not_abort_the_scan(tmp_path: Path) -> None:
    # The scan runs at daemon start. One bad file on the machine must not
    # take the assistant down with it.
    (tmp_path / "broken.desktop").write_text("this is not an ini file\x00\n")
    _write(tmp_path, "ok.desktop", """
[Desktop Entry]
Type=Application
Name=Fine
Exec=fine
""")
    assert "fine" in desktop.scan([tmp_path])


def test_later_directory_wins_by_desktop_id(tmp_path: Path) -> None:
    # XDG precedence: ~/.local/share/applications overrides /usr/share.
    sysd, userd = tmp_path / "sys", tmp_path / "user"
    sysd.mkdir(), userd.mkdir()
    _write(sysd, "code.desktop", """
[Desktop Entry]
Type=Application
Name=Code
Exec=/usr/bin/code
""")
    _write(userd, "code.desktop", """
[Desktop Entry]
Type=Application
Name=Code
Exec=/opt/code-insiders/code
""")
    assert desktop.scan([sysd, userd])["code"].argv == ("/opt/code-insiders/code",)


def test_field_code_inside_a_token_is_stripped(tmp_path: Path) -> None:
    """The filter was anchored (`^%[a-zA-Z]$`), so it only caught a field code
    that was a WHOLE token. Spotify ships `Exec=spotify --uri=%u`, and that
    reached the binary verbatim as `--uri=%u` — the one such entry among the
    162 scanned on this machine (found 2026-09-02). Strip in place, the way a
    launcher expands it, and drop only what empties out.
    """
    _write(tmp_path, "spotify.desktop", """
[Desktop Entry]
Type=Application
Name=Spotify
Exec=spotify --uri=%u
Categories=Audio;Music;
""")
    apps = desktop.scan([tmp_path])
    assert apps["spotify"].argv == ("spotify", "--uri=")
    assert not any("%" in a for a in apps["spotify"].argv)


def test_double_percent_survives_as_a_literal(tmp_path: Path) -> None:
    """`%%` is a literal percent in the Exec key. Stripping naively would eat
    the `%s` out of `%%s` and change the argument."""
    _write(tmp_path, "pct.desktop", """
[Desktop Entry]
Type=Application
Name=Pct
Exec=/usr/bin/pctdemo --label=100%%s %f
""")
    apps = desktop.scan([tmp_path])
    assert apps["pct"].argv == ("/usr/bin/pctdemo", "--label=100%s")
