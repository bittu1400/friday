"""System telemetry and hardware state reader (Phase 4a, ADR-129).

Provides deterministic, fail-closed inspection of machine state:
  - battery: /sys/class/power_supply/
  - disk: shutil.disk_usage
  - ram: /proc/meminfo
  - network: nmcli via SUBPROCESS_ENV
  - window: hyprctl activewindow
  - media: playerctl

Code reads the state; an outcome string speaks it. The model never supplies
machine metrics (invariant #2, ADR-009, ADR-078).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
import subprocess

from .env import SUBPROCESS_ENV

log = logging.getLogger("friday.tools.status")


def get_battery() -> str:
    """Read local battery level and charging state."""
    try:
        power_dir = Path("/sys/class/power_supply")
        if not power_dir.is_dir():
            return "No battery detected."
        # Look for standard battery names (BAT0, BAT1, etc.)
        bats = sorted(
            p for p in power_dir.iterdir()
            if p.name.startswith("BAT") or (p / "type").exists() and (p / "type").read_text().strip().lower() == "battery"
        )
        if not bats:
            return "No battery detected."
        bat = bats[0]
        cap_file = bat / "capacity"
        stat_file = bat / "status"
        if cap_file.exists():
            cap = cap_file.read_text().strip()
            stat = stat_file.read_text().strip() if stat_file.exists() else "unknown"
            return f"Battery is at {cap} percent, {stat}."
    except Exception as e:
        log.warning("Failed to read battery status: %s", e)
    return "Unable to read battery status."


def get_disk() -> str:
    """Read root partition space."""
    try:
        u = shutil.disk_usage("/")
        free_gb = u.free / (1024 ** 3)
        total_gb = u.total / (1024 ** 3)
        return f"{free_gb:.0f} gigabytes free out of {total_gb:.0f} gigabytes on root."
    except Exception as e:
        log.warning("Failed to read disk space: %s", e)
    return "Unable to read disk usage."


def get_ram() -> str:
    """Read available and total memory from /proc/meminfo."""
    try:
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            data: dict[str, int] = {}
            for line in meminfo.read_text().splitlines():
                parts = line.split(":")
                if len(parts) == 2:
                    k = parts[0].strip()
                    val = parts[1].strip().split()[0]
                    if val.isdigit():
                        data[k] = int(val)
            if "MemTotal" in data and "MemAvailable" in data:
                total_gb = data["MemTotal"] / (1024 ** 2)
                avail_gb = data["MemAvailable"] / (1024 ** 2)
                return f"{avail_gb:.1f} gigabytes available out of {total_gb:.1f} gigabytes RAM."
    except Exception as e:
        log.warning("Failed to read RAM info: %s", e)
    return "Unable to read memory usage."


def get_network() -> str:
    """Check connectivity via nmcli."""
    try:
        r = subprocess.run(
            ["nmcli", "-t", "-f", "TYPE,STATE,CONNECTION", "device"],
            capture_output=True,
            text=True,
            env=SUBPROCESS_ENV,
            timeout=2.0,
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                parts = (line.split(":") + ["", ""])[:3]
                dev_type, state, conn = parts[0].lower(), parts[1].lower(), parts[2]
                if state == "connected":
                    if dev_type == "wifi":
                        return f"Wi-Fi connected to {conn}."
                    elif dev_type in ("ethernet", "wired"):
                        return f"Ethernet connected to {conn}."
        return "Network is disconnected."
    except Exception as e:
        log.warning("Failed to read network status: %s", e)
    return "Unable to read network status."


def get_window() -> str:
    """Inspect active window from Hyprland."""
    try:
        r = subprocess.run(
            ["hyprctl", "activewindow", "-j"],
            capture_output=True,
            text=True,
            env=SUBPROCESS_ENV,
            timeout=2.0,
        )
        if r.returncode == 0 and r.stdout.strip():
            d = json.loads(r.stdout)
            if d and d.get("mapped", True):
                cls = d.get("class", "")
                title = d.get("title", "")
                if cls or title:
                    short_title = title[:40] if title else "untitled"
                    return f"Active window is {cls} with title {short_title}."
        return "No active window."
    except Exception as e:
        log.warning("Failed to read active window: %s", e)
    return "Unable to read active window."


def get_media() -> str:
    """Read currently playing media via playerctl."""
    try:
        r = subprocess.run(
            ["playerctl", "metadata", "--format", "{{ artist }} - {{ title }}"],
            capture_output=True,
            text=True,
            env=SUBPROCESS_ENV,
            timeout=2.0,
        )
        if r.returncode == 0 and r.stdout.strip():
            return f"Now playing: {r.stdout.strip()}."
        return "No media playing."
    except Exception as e:
        log.warning("Failed to read media status: %s", e)
    return "No media playing."


def query_status(target: str = "all") -> str:
    """Return spoken system status string based on requested target."""
    t = target.lower() if target else "all"
    if t == "battery":
        return get_battery()
    elif t == "disk":
        return get_disk()
    elif t == "ram":
        return get_ram()
    elif t == "network":
        return get_network()
    elif t == "window":
        return get_window()
    elif t == "media":
        return get_media()
    else:  # "all"
        return f"{get_battery()} {get_disk()} {get_ram()} {get_network()}"
