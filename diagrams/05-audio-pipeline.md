# Diagram 05 — Audio Pipeline and Half-Duplex Gate

## Signal path

```
   +-------------------+
   | Dual array DMIC   |
   | Realtek / SOF     |
   +---------+---------+
             |
             v
   +---------+---------+
   | PipeWire 1.6.8    |
   | source            |
   | 48 kHz f32 stereo |
   +---------+---------+
             |
             v
   +---------+---------+
   | sounddevice       |  InputStream, blocksize 1024, callback
   | (PortAudio ->     |  non-blocking, never allocate in callback
   |  pipewire-pulse)  |
   +---------+---------+
             |
             v
   +---------+---------+
   | resample 16 kHz   |
   | mono, s16         |
   +---------+---------+
             |
             v
   +---------+---------+          +--------------------+
   | ring buffer       |--------->|  MIC GATE          |
   | 15 s, preallocated|          |  open only while   |
   +---------+---------+          |  state==CAPTURING  |
             |                    +--------------------+
             v
   +---------+---------+
   | faster-whisper    |  language="en" hardcoded (no detect pass)
   | small.en (ADR-042)|  compute_type="int8", device="cpu", beam_size=1
   | CPU, 8 threads    |  vad_filter=True, hotwords=domain vocab
   +---------+---------+  p95 741 ms measured (large-v3-turbo was 2.7 s)
             |
             v
        transcript text


        speech text
             |
             v
   +---------+---------+
   | Kokoro-82M (ONNX) |  voice af_bella (G5, ADR-005/039), single preset
   | CPU, 8 threads    |  RTF ~0.14 -> faster than realtime
   | 24 kHz f32        |
   +---------+---------+
             |
             v
   +---------+---------+
   | sounddevice       |  OutputStream
   | OutputStream      |
   +---------+---------+
             |
             v
   +---------+---------+
   | PipeWire sink     |
   | Acer speakers     |
   +-------------------+
```

## Half-duplex gate — why Friday does not hear herself

Speakers and mic array sit ~10 cm apart in the same chassis. Without a
gate, TTS output is transcribed as user input and the assistant talks to
itself in a loop.

```
    time --->

    state:   IDLE      CAPTURING     ...processing...      SPEAKING       IDLE
             |         |                                   |              |
    mic:     CLOSED    OPEN =========  CLOSED  ============ CLOSED ====== CLOSED
                       ^         ^                          ^
                       |         |                          |
                  PTT press  PTT release              TTS playing
                                                            |
                                                            |  PTT press here
                                                            v
                                                    +---------------+
                                                    |   BARGE-IN    |
                                                    | stop playback |
                                                    | drop turn     |
                                                    | -> CAPTURING  |
                                                    +---------------+
```

Phase 1 implementation: a single boolean checked in the input callback.
Nine lines of code. Ships day one.

**Not** in Phase 1: acoustic echo cancellation, simultaneous listen-while-
speaking, overlapping turns. If a wake word is ever added (Phase 2), AEC
becomes mandatory, not optional — PipeWire's `module-echo-cancel` with
the WebRTC backend is the path. Recorded as OQ-12.

## Latency budget — end of speech to first audio

```
                       p50 target   p95 ceiling
   whisper (CPU)         250 ms        800 ms
   planning turn         900 ms       3000 ms
   validate + exec        50 ms        100 ms
   kokoro first chunk    180 ms        600 ms
   pipewire               20 ms         20 ms
                        --------     ---------
   TOTAL TTFA           ~1400 ms      ~4500 ms

   These are LATENCY TARGETS, not timeouts.  The hard per-stage timeouts
   that abort a turn live in diagram 01 and are deliberately much larger
   (planning aborts at 10 s, not 3 s) — a slow turn should finish late,
   not fail.  Exceeding a p95 ceiling is a performance bug to record in
   progress.md, not a runtime error.
```

Do **not** build streaming/chunked TTFA optimization before gate G6.
Measure the real number first, then decide whether ~1.4 s is actually a
problem. Recorded as ADR-020 and OQ-09.
