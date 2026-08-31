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
   | Echo Cancellation |          | Reference Ring     |  <-- D18: the DEVICE runs
   +---------+---------+          +--------------------+      48 kHz and a SOF DSP
             |    ^                                           sits after this tap, so
             |    +-- measured 2026-08-30: this does NOT      the reference is not what
             |        cancel, it GATES.  It keeps only 68     the speaker emitted.
             |        of 243 frames of a human speaking       OQ-32 / OQ-52.
             |        over playback (DTLN-aec keeps 152).
             |
             v (Clean Near-End 16kHz PCM)
   +---------+---------+--------------------+--------------------+
   |                   |                    |                    |
   v                   v                    v                    v
+--+--------------+ +--+---------------+ +--+---------------+ +--+---------------+
| openWakeWord    | | Silero VAD (*)   | | SpeakerVerifier   | | DictationManager  |
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
   |   fallback 1: Kokoro af_heart   (missing voice VECTOR only)   |
   |   fallback 2: Supertonic-3 F1, 2 steps, 44.1kHz  (ADR-085)    |
   |               engine-level; OPTIONAL dep, inert until         |
   |               `uv add supertonic` (OQ-55)                     |
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

(*) **Silero since ADR-095 (2026-08-31); `webrtcvad` is the fallback and was the cause of D3.** Measured 2026-08-30 on the 20 real DMIC clips through
this exact `SpeechGate`: it emits end-of-speech on only **15 of 20**, because on the failures it
calls 83-100 % of frames speech *including room noise*, so trailing silence never accumulates and
the capture runs to the 15 s cap. Silero ends **20/20** at 0.15 % of one core. OQ-39 / OQ-51.

## Acoustic Echo Cancellation & Barge-In

Speakers and mic array sit in the same laptop chassis. WebRTC APM AEC cleans the near-end
signal using the synthesized TTS reference from `FarEndRef`, preventing self-triggering while
allowing the user's voice to be detected mid-playback for **hands-free barge-in**.

**That last clause is the design intent, not the measured behaviour.** Voice barge-in is OFF
by default (ADR-064) because the canceller manages -5 to -10 dB on this real path against
-52 dB synthetic. Measured 2026-08-30: it does not cancel selectively, it **gates** — of 243
frames of a human speaking over playback it keeps 68, while DTLN-aec keeps 152. It removes
the echo by removing the room, the user included. See OQ-32, OQ-52, and D18 for the reason
(the reference is resampled and post-DSP, so no canceller here has been fed the right
signal). `scripts/aec_bench.py --talk` is the preservation test that shows it.

```
    time --->

    state:   IDLE      CAPTURING     ...processing...      SPEAKING (AEC active)   IDLE
             |         |                                   |                      |
    AEC:     PASS-THRU PASS-THRU     PASS-THRU             GATING (see above)     PASS-THRU
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

## The PortAudio boundary (added 2026-08-29, M-A1)

Both input streams enter Python through a sounddevice callback running on a
PortAudio thread, and both go through one `CallbackGuard`
(`friday/audio/guard.py`):

```
   PortAudio thread                          consequence if it escapes
   ----------------                          -------------------------
   wake.py    _sd_callback -> guard.run(_on_frame)   sounddevice prints the
   capture.py _sd_callback -> guard.run(_write)      traceback and NEVER CALLS
                                                     BACK AGAIN.  The stream
                                                     object stays open, the
                                                     `audio_devices` self-test
                                                     still passes, and wake,
                                                     VAD, barge-in and capture
                                                     are dead for the rest of
                                                     the process.

   guard: swallow -> count CONSECUTIVE failures -> past the limit (5),
          log E_AUDIO_DEAD once at ERROR and degrade:
            wake    -> detector = None (stream stays open; PTT still works)
            capture -> keeps running (it only gate-checks and copies, so
                       there is nothing to disable)
```

One transient bad frame costs nothing: the count resets on the next success.

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
