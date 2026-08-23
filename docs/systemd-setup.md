# Friday Systemd Service Setup (G9, architecture.md §8)

Friday runs as three `systemd --user` units:
1. `friday-searxng.service` — SearXNG search proxy (127.0.0.1:8888, installed in G7)
2. `friday-llm.service` — llama-server with Qwen2.5-7B (127.0.0.1:8080)
3. `friday.service` — orchestrator & voice daemon (`python -m friday.voice_main`)

## Installation

Link the unit files to your user systemd directory:

```bash
systemctl --user link "$PWD/deploy/systemd/friday-llm.service"
systemctl --user link "$PWD/deploy/systemd/friday.service"
systemctl --user daemon-reload
```

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
