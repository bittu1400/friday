"""Audio I/O. G5 ships voice OUT (tts.py); capture/STT/gate land at G6.

Invariant #6 / ADR-018: audio is CPU-only. TTS is kokoro-onnx on the
onnxruntime CPU provider — no torch, no CUDA in this package (ADR-039).
"""
