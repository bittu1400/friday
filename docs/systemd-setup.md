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
- **Systemd hardening**: `NoNewPrivileges=yes`, `PrivateTmp=yes`, `ProtectSystem=strict`.
- **Wayland integration**: Passes `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR`, `HYPRLAND_INSTANCE_SIGNATURE` for native application dispatch.
- **Fail-soft resilience**: The daemon tolerates `llama-server` startup delays and automatically recovers from server restarts.
