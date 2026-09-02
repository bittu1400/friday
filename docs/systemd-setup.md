# Friday Systemd Service Setup (G9, architecture.md §8)

Friday runs as three `systemd --user` units:
1. `friday-searxng.service` — SearXNG search proxy (127.0.0.1:8888, installed in G7)
2. `friday-llm.service` — llama-server with **Gemma 4 12B QAT** (127.0.0.1:8080).
   Qwen2.5-7B stays on disk as the rollback, but reverting reintroduces
   D19/D20/D21 (ADR-090).
3. `friday.service` — orchestrator & voice daemon (`python -m friday.voice_main`).
   **`Type=notify`, `WatchdogSec=10s`** since ADR-109: the daemon sends `READY=1`
   at the end of `Daemon.run()` and a heartbeat from an asyncio task, so a wedged
   event loop gets the service restarted. It also carries
   `Environment=ORT_DISABLE_TELEMETRY=1` (ADR-112).

## Installation

Link the unit files to your user systemd directory:

```bash
systemctl --user link "$PWD/deploy/systemd/friday-llm.service"
systemctl --user link "$PWD/deploy/systemd/friday.service"
systemctl --user daemon-reload
```

> **The units are SYMLINKS into `deploy/systemd/`. Editing the file is not
> deploying it.** `diff` will report the installed unit IDENTICAL to the repo
> while systemd keeps running the configuration it loaded at boot. This is not
> hypothetical: `Type=notify` + `WatchdogSec=10s` sat committed and documented
> for a whole session while `systemctl show` reported `Type=simple`,
> `WatchdogUSec=0`, `NeedDaemonReload=yes` — **the watchdog had never once
> fired.** After ANY change under `deploy/systemd/`:
>
> ```bash
> systemctl --user daemon-reload && systemctl --user restart friday
> systemctl --user show friday -p Type -p WatchdogUSec -p NRestarts
> ```
>
> Ask for `NeedDaemonReload=no`, a non-zero `WatchdogUSec`, and then leave it
> alone for a minute: **`NRestarts=0` across several watchdog periods is what
> proves the heartbeat is actually beating.** A `Type=notify` unit whose
> `READY=1` never arrives is killed at `TimeoutStartSec` (90 s here; startup
> measures ~5 s) and, with `Restart=always`, loops.

## Starting Services

```bash
# Start LLM server
systemctl --user start friday-llm

# Start voice daemon (will automatically start or wait for LLM server)
systemctl --user start friday

# Enable both to start on user login
systemctl --user enable friday-llm friday
```

## Checking Status & Logs

```bash
systemctl --user status friday-llm
systemctl --user status friday

# View streaming structured logs
journalctl --user -u friday -f
tail -f ~/.local/state/friday/friday.log
```

## Management with Just

```bash
just selftest              # Verify full system health across all components
just searxng status        # Check SearXNG proxy status
```

## Sandboxing & Security Guarantees
- **Loopback isolation**: `llama-server` and `SearXNG` bind strictly to `127.0.0.1`.
- **Systemd hardening**: `NoNewPrivileges=yes`, `ProtectSystem=strict`,
  `ReadWritePaths=` for the three Friday state directories.
- **`/tmp` is in `ReadWritePaths=` (ADR-115)** and must stay there.
  `ProtectSystem=strict` mounts everything not listed read-only, and `PrivateTmp`
  had been supplying the daemon's only *writable* `/tmp`. Removing that directive
  alone leaves `/tmp` **visible but read-only**, which is still broken —
  connecting to a unix socket needs write access to it, Chromium creates its own
  `/tmp/org.chromium.Chromium.*` when it is the first instance, and Python's
  `tempfile.gettempdir()` falls through to the `WorkingDirectory`, dropping two
  `tmp*/libespeak-ng.so` directories into the repo on every daemon start.
- **`PrivateTmp` is deliberately NOT set (ADR-115)** and must not be added back.
  A GUI app's session IPC lives in `/tmp`: Chromium/Brave keeps its singleton
  **socket** there and only a **symlink** to it in the profile under `$HOME`. A
  private `/tmp` therefore let a Friday-launched Brave see the shared lock, fail
  to reach the socket, and exit 0 in ~50 ms with no window — reported as a
  successful launch. It also hid `/tmp/.X11-unix`. The daemon runs as the user
  and launches the user's own apps, so the isolation separated the user from
  themselves and bought nothing.
- **`KillMode=process` (ADR-114)** and must not be left at systemd's default.
  Launched apps are children of the daemon and inherit its cgroup — a fork
  cannot leave a cgroup — so `control-group` SIGKILLed every app Friday had
  opened on any stop or restart, and the unit is `Restart=always` with a 10 s
  watchdog.
- Both are asserted by `tests/test_service_unit.py`, with demonstrated FAIL
  paths, because both are exactly the lines a later "harden the service" pass
  would put back.
- **Wayland integration**: Passes `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR`, `HYPRLAND_INSTANCE_SIGNATURE` for native application dispatch.
- **Fail-soft resilience**: The daemon tolerates `llama-server` startup delays and automatically recovers from server restarts.
