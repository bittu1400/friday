# Diagram 03 — Memory Budget (VRAM and System RAM)

Numbers are **targets to verify at gate G1**, not guarantees. Record the
measured values in `progress.md`. If measurement disagrees with this
diagram, the diagram is wrong — fix the diagram.

## VRAM — RTX 5070 Mobile, 8151 MiB total

```
   8151 MiB  +===================================================+  physical
             |                                                   |
             |   ~500 MiB   driver / framebuffer reserve         |
   7650 MiB  +---------------------------------------------------+  observed free
             |                                                   |
             |   ~1150 MiB  HEADROOM ABOVE THE CEILING           |
             |              (do not spend; absorbs fragmentation,|
             |               batch spikes, a stray CUDA client)  |
   6500 MiB  +===================================================+  WORKING CEILING
             |                                                   |
             |   ~876 MiB   unallocated slack below the ceiling  |
             |                                                   |
   5624 MiB  +---------------------------------------------------+  measured target
             |                                                   |
             |   ~400 MiB   CUDA context (llama-server, the ONLY |
             |              CUDA process in the system)          |
   5224 MiB  +---------------------------------------------------+
             |                                                   |
             |   ~300 MiB   compute buffers / graph / scratch    |
             |                                                   |
   4924 MiB  +---------------------------------------------------+
             |                                                   |
             |   ~224 MiB   KV cache, 8192 ctx, q8_0 K and V     |
             |                                                   |
   4700 MiB  +---------------------------------------------------+
             |                                                   |
             |                                                   |
             |   ~4700 MiB  Qwen2.5-7B-Instruct  Q4_K_M weights  |
             |              every layer offloaded to the GPU     |
             |                                                   |
      0 MiB  +===================================================+

   projected total in use:  4700 + 224 + 300 + 400  =  5624 MiB
   working ceiling:                                    6500 MiB
   slack:                                               876 MiB
```

### KV cache arithmetic (Qwen2.5-7B: 28 layers, 4 KV heads GQA, head_dim 128)

```
   per token = 28 layers x 2 (K,V) x 4 heads x 128 dim x bytes_per_elem

                        fp16 (2 B)      q8_0 (~1 B)
        per token        57344 B          28672 B
                        = 56 KiB         = 28 KiB

        ctx 2048          112 MiB           56 MiB
        ctx 4096          224 MiB          112 MiB
        ctx 8192          448 MiB          224 MiB   <-- CHOSEN
        ctx 16384         896 MiB          448 MiB
```

The original blueprint capped context at 2048 to "prevent KV-cache
overflow". The overflow it feared costs 224 MiB. See ADR-003.

## System RAM — 15405 MiB total, ~9100 MiB available at idle

```
   +--------------------------------------------------------------+
   |                                                              |
   |  faster-whisper large-v3-turbo, int8, CPU        ~1600 MiB    |
   |  (resident; model stays loaded between turns)                |
   |                                                              |
   +--------------------------------------------------------------+
   |                                                              |
   |  Kokoro-82M + espeak-ng + misaki phonemizer      ~700 MiB     |
   |                                                              |
   +--------------------------------------------------------------+
   |                                                              |
   |  Orchestrator: python 3.12, asyncio, sqlite3     ~350 MiB     |
   |                                                              |
   +--------------------------------------------------------------+
   |                                                              |
   |  Audio ring buffers (15 s @ 16 kHz mono s16)      ~1 MiB      |
   |  TTS output buffers                               ~20 MiB     |
   |                                                              |
   +--------------------------------------------------------------+
   |                                                              |
   |  llama-server host-side (weights are on GPU)     ~300 MiB     |
   |                                                              |
   +--------------------------------------------------------------+

        TOTAL FRIDAY RSS  ~3000 MiB     of ~9100 MiB available
        remaining for the desktop and a browser:  ~6100 MiB
```

## CPU thread allocation — 24 cores (8 P-cores + 16 E-cores)

```
   P-cores  0-7    |========|  whisper (8 threads, int8, latency-critical)
   E-cores  8-11   |====|      kokoro  (4 threads, RTF ~0.15, plenty)
   E-cores 12-13   |==|        orchestrator event loop + sqlite
   E-cores 14-23   |==========| free for the desktop
```

Set explicitly:

```bash
faster_whisper.WhisperModel(..., device="cpu", compute_type="int8", cpu_threads=8)
```

Do not leave thread counts at default — an unpinned whisper will grab all
24 cores and make Hyprland stutter mid-sentence.

## The claim this diagram replaces

Gemini's review projected a ~9.65 GiB peak and an OOM risk, charging the
compositor (0.4 GiB) and the browser (1.5 GiB) to the RTX 5070. On a
hybrid-graphics laptop, Hyprland and Firefox render on the **Intel iGPU**
unless `AQ_DRM_DEVICES` forces otherwise. Verify at gate G1:

```bash
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
```

Empty output with a browser open means ~1.9 GiB of that projection does
not exist. Record the result in `progress.md` G1.
