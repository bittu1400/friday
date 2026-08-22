# Diagram 00 — System Overview

Every box is a process or a hardware resource. Every line is a real
channel (function call, unix socket, pipe, device node). Nothing here is
aspirational; if a box is not in `progress.md` as a passed gate, it does
not exist yet.

```
   HARDWARE                       PROCESSES                        STORAGE
   ========                       =========                        =======

  +-------------+
  |  DMIC array |
  | (PipeWire)  |
  +------+------+
         |  PCM 16k mono
         |
         v
  +------+-------------------------------------------------------------+
  |                                                                    |
  |                    FRIDAY ORCHESTRATOR  (one process)              |
  |                    python 3.12 / asyncio / single event loop       |
  |                                                                    |
  |   +-----------+   +-----------+   +----------+   +-------------+   |
  |   |  INPUT    |   |   TURN    |   |  POLICY  |   |   OUTPUT    |   |
  |   |  router   |-->|  machine  |-->|  + tool  |-->|   speaker   |   |
  |   |           |   |  (FSM)    |   | registry |   |             |   |
  |   +-----+-----+   +-----+-----+   +----+-----+   +------+------+   |
  |         |               |              |                |         |
  +---------|---------------|--------------|----------------|---------+
            |               |              |                |
            |               |              |                |
      +-----+-----+   +-----+------+  +----+-----+   +------+------+
      |  evdev /  |   | llama-     |  | subproc  |   |  Kokoro-82M |
      |  hyprctl  |   | server     |  | execve   |   |  (CPU, in   |
      |  PTT      |   | (CUDA)     |  | argv[]   |   |  process)   |
      +-----------+   +-----+------+  +----+-----+   +------+------+
                            |              |                |
                            |              |                v
                      +-----+-----+        |         +-------------+
                      | RTX 5070  |        |         |  PipeWire   |
                      | 8GB GDDR7 |        |         |  sink       |
                      | sm_120    |        |         +-------------+
                      +-----------+        |
                                           v
                                    +-------------+
                                    |  Hyprland   |
                                    |  hyprctl    |
                                    +-------------+

            +-----------------+          +------------------------+
            | faster-whisper  |          |     ~/.local/state/friday/    |
            | large-v3-turbo  |          |                        |
            | int8  ON CPU    |          |  memory.db  (SQLite)   |
            | 24 cores        |          |  friday.log (rotated)  |
            +-----------------+          |  config.toml           |
                                         +------------------------+

            +-----------------+
            |  SearXNG        |   <-- ONLY egress point in the system
            |  127.0.0.1:8888 |
            +--------+--------+
                     |
                     v
                 [ internet ]
```

## Resource ownership (non-negotiable)

```
   RTX 5070 VRAM  -----> llama-server ONLY.  One CUDA context. No exceptions.
   CPU (24 cores) -----> whisper (8 threads) + kokoro (4 threads) + orchestrator
   System RAM     -----> everything CPU-side, ~3.5 GB total
   Network        -----> SearXNG on loopback only. Nothing else opens a socket.
```

Rationale in `adr.md` ADR-018. Violating this reintroduces the
multi-CUDA-context overhead (300-500 MB per process) that the original
blueprint budgeted for and this design eliminates.
