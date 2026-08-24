# G12 — Action Surface Implementation Plan

**Goal:** Expand Friday's capabilities to system control (volume, brightness, media, wifi), Hyprland window/workspace management, notes storage, clipboard, file opening, and hands-free dictation, governed by a 3-tier confirmation policy and a hard ban on destructive commands.

**Spec:** `docs/superpowers/specs/2026-08-24-phase2-design.md` (§4 G12; ADR-057, ADR-058).

## Constraints
- **#2 / #3 No model-supplied path/URL/shell string:** All tools take closed enums or typed sanitized values; code constructs argv.
- **#10 No irreversible tools / Hard ban:** Shell/terminal execution, package removal, file deletion permanently banned in tool layer.
- **Confirm tiers:** Harmless (immediate), Consequential (spoken confirm), Dangerous (two-pass gated on G13).
- **Dictation isolation:** Dictated text is verbatim input typed directly into focused window, never parsed by planner; wake word paused.

---

## Tasks

### Task 1: Hard Ban & Extended Tool Registry (`friday/tools/ban.py`, `friday/tools/registry.py`)
- Define `BANNED_COMMANDS` denylist.
- Add system tools (`system_volume`, `system_brightness`, `system_media`, `system_wifi`).
- Add Hyprland tools (`hypr_workspace`, `hypr_window`).
- Add clipboard tools (`clipboard_read`, `clipboard_set`).
- Add `file_open` with placeholder alias dictionary.
- Define `RiskTier` (`HARMLESS`, `CONSEQUENTIAL`, `DANGEROUS`).

### Task 2: Notes Store in SQLite (`friday/store/notes.py`, `friday/store/migrations/003_notes.sql`)
- Table `notes` (`id TEXT PRIMARY KEY, created_at REAL, content TEXT`).
- Schema migration 003.
- `create_note(content)` and `read_notes()`.

### Task 3: Wayland Typer & Dictation (`friday/tools/typer.py`, `friday/audio/dictation.py`)
- `type_text(text: str)` using `ydotool` / `wtype` fail-soft.
- Explicit toggle ("start dictation" / "stop dictation").

### Task 4: Three-Tier Confirmation Engine (`friday/turn.py`, `friday/daemon.py`)
- Intercept consequential actions -> return pending confirmation -> require spoken affirmative.
- Dangerous actions fail closed until G13 speaker verification.

### Task 5: Schema & Grammar Update (`friday/llm/schema.py`, `plan.gbnf`, `prompt.py`)
- Update `PARAM_SCHEMA` and regenerate grammars.
- Update `SYSTEM_POLICY` and `CHAT_SYSTEM`.

### Task 6: Unit Tests & Eval Verification
- Comprehensive tests in `tests/test_action_surface.py`, `tests/test_dictation.py`, `tests/test_notes.py`.
- `pytest` all green, `just eval` 28/28.
