"""Hyprland window listing and targeting utilities (Phase 4a, ADR-129).

Provides:
  - list_windows: query hyprctl clients and build concise spoken summary
  - focus_app: find open client matching app and dispatch focus
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import subprocess

from .apps import APPS
from .env import SUBPROCESS_ENV

log = logging.getLogger("friday.tools.windows")


def list_windows() -> str:
    """Return a plain-English spoken summary of open windows and workspaces."""
    try:
        r = subprocess.run(
            ["hyprctl", "clients", "-j"],
            capture_output=True,
            text=True,
            env=SUBPROCESS_ENV,
            timeout=2.0,
        )
        if r.returncode == 0 and r.stdout.strip():
            clients = json.loads(r.stdout)
            active = [c for c in clients if c.get("mapped") and not c.get("hidden")]
            if not active:
                return "No windows are open."
            items = []
            for c in active:
                cls = c.get("class") or "window"
                ws = c.get("workspace", {}).get("name") or "unknown"
                items.append(f"{cls} on workspace {ws}")
            if len(items) == 1:
                return f"You have 1 open window: {items[0]}."
            elif len(items) <= 5:
                summary = ", ".join(items[:-1]) + f", and {items[-1]}"
                return f"You have {len(items)} open windows: {summary}."
            else:
                summary = ", ".join(items[:5])
                return f"You have {len(items)} open windows: {summary}, and {len(items)-5} others."
    except Exception as e:
        log.warning("Failed to list windows: %s", e)
    return "Unable to list open windows."


def focus_app(app_key: str) -> tuple[bool, str]:
    """Focus an existing window matching app_key.

    Returns (success, spoken_reply).
    """
    app = APPS.get(app_key)
    display = app.display if app is not None else app_key

    # Targets to match against window class, initialClass, or title
    targets = {app_key.lower()}
    if app is not None:
        targets.add(app.display.lower())
        if app.argv:
            targets.add(Path(app.argv[0]).name.lower())

    # Common canonical brand resolutions
    if app_key == "browser":
        targets.update({"brave", "brave-browser", "firefox", "chromium", "zen", "zen-browser"})
    elif app_key == "terminal":
        targets.update({"foot", "kitty", "alacritty", "wezterm"})
    elif app_key == "editor":
        targets.update({"code", "codium", "zed", "nvim", "neovim"})

    try:
        r = subprocess.run(
            ["hyprctl", "clients", "-j"],
            capture_output=True,
            text=True,
            env=SUBPROCESS_ENV,
            timeout=2.0,
        )
        if r.returncode == 0 and r.stdout.strip():
            clients = json.loads(r.stdout)
            matched = None
            for c in clients:
                if not c.get("mapped") or c.get("hidden"):
                    continue
                cls = (c.get("class") or "").lower()
                init_cls = (c.get("initialClass") or "").lower()
                title = (c.get("title") or "").lower()

                # Priority 1: exact class match
                if cls in targets or init_cls in targets:
                    matched = c
                    break
                # Priority 2: substring in class
                if any(t in cls or t in init_cls for t in targets):
                    matched = c
                    break
                # Priority 3: title contains target
                if any(t in title for t in targets):
                    matched = c
                    break

            if matched:
                addr = matched.get("address")
                dispatch_cmd = f'hl.dsp.focus{{window="address:{addr}"}}'
                res = subprocess.run(
                    ["hyprctl", "dispatch", dispatch_cmd],
                    capture_output=True,
                    text=True,
                    env=SUBPROCESS_ENV,
                    timeout=2.0,
                )
                if res.returncode == 0:
                    return True, f"Focused {display}."
                return False, f"Failed to focus {display}."

            return False, f"No open window found for {display}."
    except Exception as e:
        log.warning("Failed to focus window for app %s: %s", app_key, e)
        return False, f"Unable to focus {display}."

    return False, f"No open window found for {display}."
