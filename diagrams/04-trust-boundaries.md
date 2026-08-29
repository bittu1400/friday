# Diagram 04 — Trust Zones and Privilege

Read with `threat-model.md`. Anything crossing a `#####` line is
attacker-influenceable and must be treated as hostile input.

```
  #####################################################################
  #                                                                   #
  #   ZONE 0 — CODE      (trusted, written by you, reviewed, in git)  #
  #                                                                   #
  #     tool_registry.py    app IDs -> argv[]                         #
  #     policy.py           per-action risk class                     #
  #     grammars/*.gbnf     sampler constraints                       #
  #     templates.py        outcome -> speech strings                 #
  #     schema.py           strict validation, unknown fields reject   #
  #                                                                   #
  #   Only Zone 0 ever constructs an argv array or a file path.       #
  #                                                                   #
  #####################################################################
              ^                                        ^
              |                                        |
     reads (never executes)                   reads (never executes)
              |                                        |
  #####################################################################
  #                                                                   #
  #   ZONE 1 — USER INPUT      (semi-trusted: the human, but noisy)   #
  #                                                                   #
  #     STT transcript          may be misheard                       #
  #     typed text              may be pasted from anywhere           #
  #     stored preferences      written in a past session             #
  #                                                                   #
  #   Threat: a mis-transcription ("delete" heard for "select").      #
  #   Control: destructive class requires TYPED confirmation, never   #
  #            a spoken "yes".                                        #
  #                                                                   #
  #####################################################################
              |
              |  becomes prompt context
              v
  #####################################################################
  #                                                                   #
  #   ZONE 2 — MODEL OUTPUT    (UNTRUSTED. it is a text generator.)   #
  #                                                                   #
  #     {thought, action, speech}                                     #
  #                                                                   #
  #   Never: a path, a shell string, a URL to fetch, an argv element. #
  #   Only:  an opaque ID from a closed enum + typed params.          #
  #                                                                   #
  #   Grammar constrains SYNTAX.  Validator constrains SEMANTICS.     #
  #   Registry constrains CAPABILITY.  All three, always.             #
  #                                                                   #
  #####################################################################
              |
              |  action=web_search only
              v
  #####################################################################
  #                                                                   #
  #   ZONE 3 — INTERNET        (HOSTILE. assume adversarial.)         #
  #                                                                   #
  #     search result titles, snippets, page text                     #
  #                                                                   #
  #   Control: content from Zone 3 may only ever reach a model turn   #
  #            whose grammar has action enum = ["none"].              #
  #            There is no code path from Zone 3 to an executor.      #
  #                                                                   #
  #####################################################################
```

## Privilege ladder — keep every rung as low as it goes

```
   HIGHEST   root                        <-- Friday NEVER runs as root
      |
      |      group: input                <-- reads EVERY keystroke on a
      |      (raw evdev)                     device. avoid. see ADR-013.
      |
      |      user session + hyprctl      <-- can launch anything the user
      |                                      can. this is the real blast
      |                                      radius. bounded by registry.
      |
      |      user session, no hyprctl    <-- text mode, search, memory
      |
   LOWEST    read-only, no egress        <-- gate G3 target state
```

Phase 1 ships at the "user session + hyprctl" rung, with the registry as
the only thing standing between a mis-transcription and an arbitrary
launch. That is why the registry is code, not config, and not a
directory listing.

## What `~/friday/scripts/` is NOT

```
   +-----------------------------------------------------------+
   |  A directory allowlist is not a security boundary:         |
   |                                                            |
   |    ../                 path traversal                      |
   |    symlink -> /bin/sh  escape by link                      |
   |    chmod +w script     later modified by anything          |
   |    #!/usr/bin/env      shebang resolves through PATH        |
   |    $IFS, $LD_PRELOAD   inherited environment               |
   |    stat-then-exec      TOCTOU race                          |
   |                                                            |
   |  Replaced by: a static registry of tool ID -> absolute      |
   |  canonical path + fixed argv + fixed cwd + fixed env +      |
   |  timeout.  Model supplies an ID.  Never a path.            |
   +-----------------------------------------------------------+
```

The `timeout` in that box was aspirational until 2026-08-29 (`ToolSpec.timeout_s`
was dead config). It is real now, and it means two different things (ADR-073):

```
   COMMAND (detach=False)   wpctl, brightnessctl, playerctl, nmcli, hyprctl
                            await(timeout_s) -> SIGKILL the whole process GROUP
                            on expiry; a non-zero exit is the verdict (ERROR).

   LAUNCH  (detach=True)    the GUI apps + file_open.  0.4 s grace, then left
                            alone: it must OUTLIVE the turn (ADR-043), and its
                            exit code means nothing (a single-instance handoff
                            exits non-zero ON SUCCESS).  Because the launch
                            cannot be verified, it speaks "Launching X.", never
                            "Opened X."
```

The Hyprland tools' argv element is a Lua expression on Hyprland 0.56
(`hl.dsp.focus{workspace=2}`). No parameter is formatted into it: a closed-set
param SELECTS one of sixteen import-time constants, so Zone 0 still owns every
byte that reaches the compositor (ADR-074).
