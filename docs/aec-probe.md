# AEC probes — the harness for OQ-32

> **2026-08-30: for comparing CANDIDATE cancellers, use
> [`scripts/aec_bench.py`](../scripts/aec_bench.py) (`just bench-aec`) instead.**
> It drives none / WebRTC APM / DTLN-aec over ONE capture, aligns the reference
> with GCC-PHAT, refuses to print a row if `pywebrtc_audio` silently fell back
> to `NullAec`, discards captures with audio XRUNs, and has a `--talk`
> **preservation** mode — which is what showed that the incumbent gates rather
> than cancels (68 of 243 frames of a human kept, vs DTLN's 152).
>
> This file is still the reference for the ORIGINAL measurement (-52 dB
> synthetic, -5 to -10 dB real, 58 ms lag, `stream_delay_ms` is not the lever)
> and its two probes still run. The numbers-to-beat table below stands.

Written 2026-08-25 while diagnosing ADR-064 (Friday interrupting herself).
These two scripts reproduce the echo path **with no human present**: they play
real TTS through the speaker and listen on the real mic. Nothing is written to
disk (invariant #7).

Any candidate echo canceller for **OQ-32** must be measured with these, on this
laptop, before it is adopted (CLAUDE.md rule 7).

## Numbers to beat

| condition | suppression | barge events in one reply |
| :-- | --: | --: |
| synthetic echo, perfectly aligned reference | −52 dB | — |
| real room, reference absent (40 % of frames) | 0 dB | — |
| real room, reference present, before the callback fix | −15.6 dB | 1 short / 8 long |
| real room, reference from playback callback (current) | −9.7 dB | 9 |

`stream_delay_ms` is not the lever — 0/30/60/90/120 ms give
−5.1/−4.9/−5.1/−4.9/−3.9 dB. Measured speaker→mic lag is **58 ms** with
envelope correlation **0.53**, so the reference content is correct; the
canceller does not converge on this acoustic path.

**A candidate is only interesting if it reaches roughly −30 dB or better on the
real path with barge events at zero.** Below that, the VAD still hears Friday.

## Probe 1 — does Friday barge in on herself?

Records, for every frame of playback: whether a far-end reference was present,
mic RMS, post-AEC RMS, and whether the VAD called it speech. Then counts barge
events. Set `PROBE_TEXT` to control reply length — the short/long split matters,
because the old 5 s ring cap only broke on long replies.

```python
"""Reproduce the barge-in-cuts-off-Friday loop with real speaker + real mic."""
import sys, time, threading, os
sys.path.insert(0, "/home/bittusah/Projects/Personal/Intern/friday")
import numpy as np
from friday import config
from friday.audio import aec, vad, wake
from friday.audio.tts import Speaker

far_ref = wake.FarEndRef()
aec_proc = aec.create(enabled=config.AEC_ENABLED, sample_rate=16000,
                      frame_ms=config.AEC_FRAME_MS)
vad_det = vad.create(mode=config.VAD_AGGRESSIVENESS, sample_rate=16000)
det = wake.create_detector(config.WAKE_MODEL)  # 2026-08-29: create_detector
# no longer takes `threshold=` — it accepted and IGNORED it. The threshold is
# WakeListener's, and it is passed below where it actually does something.
speaker = Speaker.create(config.KOKORO_MODEL, config.KOKORO_VOICES,
                         voice=config.KOKORO_VOICE,
                         fallback=config.KOKORO_VOICE_FALLBACK,
                         threads=config.KOKORO_THREADS, far_ref=far_ref)

speaking, barges, stats = threading.Event(), [], []

class Probe:
    """Sits where the AEC sits, recording what crosses the boundary."""
    def __init__(self, inner): self._i = inner
    def process(self, near, far):
        clean = self._i.process(near, far)
        if speaking.is_set():
            stats.append((far is not None,
                          float(np.sqrt((np.asarray(near, np.float32) ** 2).mean())),
                          float(np.sqrt((np.asarray(clean, np.float32) ** 2).mean())),
                          vad_det.is_speech(clean) if vad_det else False))
        return clean

listener = wake.WakeListener(
    detector=det, vad=vad_det, aec=Probe(aec_proc), far_ref=far_ref,
    callbacks=wake.WakeCallbacks(on_wake=lambda: None, on_speech_end=lambda: None,
                                 on_barge=lambda: barges.append(time.monotonic() - t0)),
    threshold=config.WAKE_THRESHOLD,
    frame_len=(16000 * config.WAKE_FRAME_MS) // 1000,
    refractory_s=config.WAKE_REFRACTORY_S,
    is_idle=lambda: False, is_speaking=lambda: speaking.is_set(),
)
assert listener.start(), "no audio input"
time.sleep(1.0)

TEXT = os.environ.get("PROBE_TEXT", "Opened Brave.")
t0 = time.monotonic(); speaking.set()
speaker.say(TEXT)
speaking.clear(); time.sleep(0.3); listener.stop()

with_ref = [s for s in stats if s[0]]
without  = [s for s in stats if not s[0]]
print(f"frames during playback : {len(stats)}")
print(f"far reference present  : {len(with_ref)}/{len(stats)} frames")
for label, grp in (("WITH reference", with_ref), ("NO reference", without)):
    if not grp:
        print(f"{label:16}: no frames"); continue
    n = np.array([g[1] for g in grp]); c = np.array([g[2] for g in grp])
    v = sum(1 for g in grp if g[3])
    print(f"{label:16}: {len(grp):4d} frames | mic {n.mean():.4f} -> clean {c.mean():.4f} "
          f"= {20*np.log10(c.mean()/n.mean()+1e-12):6.1f} dB | voiced {v}/{len(grp)}")
print(f"BARGE EVENTS           : {len(barges)}  at {[f'{b:.2f}s' for b in barges]}")
```

**Read it like this.** `far reference present` well below 100 % means the
reference feed is broken, not the canceller — fix that first. `NO reference`
rows always read 0.0 dB (the AEC is a passthrough when `far is None`).
`BARGE EVENTS` above zero with nobody in the room is the actual bug.

## Probe 2 — delay sweep on one captured pass

Captures a single real echo pass, then replays it offline through the canceller
at several `stream_delay_ms` settings. Fast and repeatable — no speaker needed
after the capture, so it is the right tool for comparing candidate libraries.

```python
"""Capture one real echo pass, then replay it at several stream_delay_ms."""
import sys, time, threading
sys.path.insert(0, "/home/bittusah/Projects/Personal/Intern/friday")
import numpy as np, sounddevice as sd
from friday import config
from friday.audio import wake, vad
from friday.audio.tts import Speaker

far_ref = wake.FarEndRef()
speaker = Speaker.create(config.KOKORO_MODEL, config.KOKORO_VOICES,
                         voice=config.KOKORO_VOICE,
                         fallback=config.KOKORO_VOICE_FALLBACK,
                         threads=config.KOKORO_THREADS, far_ref=far_ref)
near_c, far_c, speaking = [], [], threading.Event()

def cb(indata, frames, t, status):
    if not speaking.is_set(): return
    f = far_ref.read(frames)
    near_c.append(indata[:, 0].copy())
    far_c.append(f if f is not None else np.zeros(frames, np.float32))

st = sd.InputStream(samplerate=16000, channels=1, dtype="float32",
                    blocksize=320, callback=cb)
st.start(); time.sleep(0.4); speaking.set()
speaker.say("Testing one two three four five six seven eight nine ten.")
time.sleep(0.2); speaking.clear(); st.stop(); st.close()

near = np.concatenate(near_c); far = np.concatenate(far_c)
n = min(len(near), len(far)); near, far = near[:n], far[:n]
vd = vad.create(mode=config.VAD_AGGRESSIVENESS, sample_rate=16000)
base = np.sqrt((near ** 2).mean())
print(f"captured {n/16000:.2f}s  near RMS {base:.4f}\n")

# envelope cross-correlation gives the true speaker->mic lag
def env(x, w=160): return np.convolve(np.abs(x), np.ones(w)/w, mode="same")
en, ef = env(near), env(far); en -= en.mean(); ef -= ef.mean()
c = np.correlate(en, ef, mode="full"); lag = c.argmax() - (len(ef) - 1)
print(f"lag {lag/16:.1f} ms  correlation "
      f"{c.max()/(np.linalg.norm(en)*np.linalg.norm(ef)+1e-12):.3f}\n")

import pywebrtc_audio
print(f"{'delay_ms':>9} {'suppression':>12} {'voiced frames':>15}")
for d in (0, 30, 60, 90, 120):
    ec = pywebrtc_audio.EchoCanceller(sample_rate=16000, num_channels=1,
                                      stream_delay_ms=d)
    out = [ec.process(near[i:i+160], far[i:i+160]) for i in range(0, n - 160, 160)]
    o = np.concatenate(out)
    total = list(range(0, len(o) - 320, 320))
    voiced = sum(1 for i in total if vd.is_speech(o[i:i+320]))
    print(f"{d:>9} {20*np.log10(np.sqrt((o**2).mean())/base+1e-12):>11.1f} dB "
          f"{voiced:>8}/{len(total)}")
```

## Sanity check before trusting either probe

A canceller that cannot cancel a perfect echo is broken outright, and that is
worth ruling out in five seconds before blaming the room:

```python
p = aec.create(enabled=True, sample_rate=16000, frame_ms=config.AEC_FRAME_MS)
tone = (0.3*np.sin(2*np.pi*440*np.arange(16000)/16000)).astype(np.float32)
out = np.concatenate([p.process(tone[i:i+320], tone[i:i+320])
                      for i in range(0, 16000, 320)])
# current library: -52.2 dB
```

## Turning barge-in back on

Voice barge-in is off by default (ADR-064). Once a canceller clears the bar:

```bash
FRIDAY_BARGE_VAD_ENABLE=1 just voice
```

Do not flip the default until probe 1 reports zero barge events on a long reply
with nobody in the room.
