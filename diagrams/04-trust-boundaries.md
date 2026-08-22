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
