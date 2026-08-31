# Diagram 00 — System Overview

Every box is a process or a hardware resource. Every line is a real
channel (function call, unix socket, pipe, device node). Nothing here is
aspirational; if a box is not in `progress.md` as a passed gate, it does
not exist yet.

```
   HARDWARE                       PROCESSES                        STORAGE
   ========                       =========                        =======

  +-------------+
  | PipeWire    |
  | Mic Source  |
  +------+------+
         |  PCM 16k mono, ALWAYS ON since G10 (the mic stream never closes;
         |  the FSM's mic_open gate decides what is KEPT — ADR-014)
         v
  +------+----------------------------------------------+
  |  PortAudio callback -> CallbackGuard (M-A1)          |
  |    WebRTC APM AEC  -> openWakeWord "hey_jarvis"      |
  |                    -> Silero VAD / SpeechGate          |
  |                    -> SpeakerVerifier (off by dflt)  |
  |  Three trigger sources reach the FSM: WAKE, PTT,     |
  |  BARGE (voice barge OFF by default, ADR-064).        |
  |  A fourth event source is not audio at all: the      |
  |  proactive Scheduler (reminders/timers, G11).        |
  +------+----------------------------------------------+
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
      |  Hyprland |   | llama-     |  | subproc  |   |  Kokoro-82M |
      |  PTT bind |   | server     |  | execve   |   |  (CPU, in   |
      |  toggle   |   | (CUDA)     |  | argv[]   |   |  process)   |
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
                                    |  spawn      |
                                    +-------------+

            +-----------------+          +---------------------------+
            | faster-whisper  |          |  ~/.local/state/friday    |
            | small.en (int8) |          |  (0700; every file 0600)  |
            | ON CPU          |          |                           |
            | 8 threads       |          |  memory.db  (SQLite, WAL) |
            +-----------------+          |  memory.db-wal / -shm     |
                                         |  friday.log (rotated)     |
                                         |  voiceprint.npy (G13, if  |
                                         |    enrolled — absent here)|
                                         |  DISABLED (panic flag,    |
                                         |    absent = armed)        |
                                         +---------------------------+

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
   CPU (24 cores) -----> whisper (8 threads) + kokoro (8 threads) + orchestrator
   System RAM     -----> everything CPU-side.  MEASURED 2026-08-29: the voice
                         daemon's RSS is ~1.6 GB with whisper + kokoro +
                         openWakeWord + the AEC all resident (the ~3.5 GB
                         figure was the Phase 1 budget, before those loaded)
   Network        -----> SearXNG on loopback only. Nothing else opens a socket.
```

Rationale in `adr.md` ADR-018. Violating this reintroduces the
multi-CUDA-context overhead (300-500 MB per process) that the original
blueprint budgeted for and this design eliminates.
