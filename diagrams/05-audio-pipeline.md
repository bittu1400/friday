# Diagram 05 — Audio Pipeline (AEC, Wake, VAD, Speaker Verification, STT, TTS)

## Signal path (Phase 2, G10–G13)

```
   +-------------------+
   | Mic Array Input   |
   | PipeWire 16kHz f32|
   +---------+---------+
             |
             v
   +---------+---------+          +--------------------+
   | WebRTC APM AEC    |<---------| FarEndRef (TTS tap)| (Polyphase resample 24k->16k)
   | Echo Cancellation |          | Reference Ring     |
   +---------+---------+          +--------------------+
             |
             v (Clean Near-End 16kHz PCM)
   +---------+---------+--------------------+--------------------+
   |                   |                    |                    |
   v                   v                    v                    v
+--+--------------+ +--+---------------+ +--+---------------+ +--+---------------+
| openWakeWord    | | WebRTC VAD       | | SpeakerVerifier   | | DictationManager  |
| hey_jarvis.onnx | | SpeechGate       | | 3D-Speaker CAM++  | | Verbatim Typer    |
| (CPU, 80ms chunk| | 20ms frames, M=2 | | 512-dim embedding | | (ydotool / wtype) |
+--------+--------+ +--+---------------+ +--+---------------+ +--+---------------+
         |             |                    |                    |
         | on_wake     | on_speech_end      | is_match           | typed chars
         v             v                    v                    v
   +-----+-------------+--------------------+--------------------+
   |                     Turn State / Daemon                      |
   +------------------------------+-------------------------------+
                                  |
                                  v
   +------------------------------+-------------------------------+
   | faster-whisper small.en (CPU int8, beam=1)                   |
   +------------------------------+-------------------------------+
                                  |
                                  v
                            transcript text
                                  |
                                  v
                            speech text
                                  |
                                  v
   +------------------------------+-------------------------------+
   | Kokoro-82M (ONNX CPU, voice af_bella, 24kHz f32)             |
   +------------------------------+-------------------------------+
                                  |
            +---------------------+---------------------+
            |                                           |
            v                                           v
   +--------+----------+                       +--------+----------+
   | FarEndRef Tap     |                       | sounddevice       |
   | resample 24k->16k |                       | OutputStream      |
   +-------------------+                       +--------+----------+
                                                        |
                                                        v
                                               +--------+----------+
                                               | PipeWire sink     |
                                               | Speakers          |
                                               +-------------------+
```

## Acoustic Echo Cancellation & Barge-In

Speakers and mic array sit in the same laptop chassis. WebRTC APM AEC cleans the near-end
signal using the synthesized TTS reference from `FarEndRef`, preventing self-triggering while
allowing the user's voice to be detected mid-playback for **hands-free barge-in**.

```
    time --->

    state:   IDLE      CAPTURING     ...processing...      SPEAKING (AEC active)   IDLE
             |         |                                   |                      |
    AEC:     PASS-THRU PASS-THRU     PASS-THRU             CANCELLING ECHO        PASS-THRU
             |         |                                   |                      |
             |         v                                   v                      |
             |    VAD trailing silence               User speaks over TTS         |
             |    triggers turn                      triggers barge-in            |
             |                                             |                      |
             |                                             v                      |
             |                                     +---------------+              |
             |                                     |   BARGE-IN    |              |
             |                                     | stop playback |              |
             |                                     | -> CAPTURING  |              |
             |                                     +---------------+              |
```

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
