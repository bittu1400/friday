"""Friday — local-first voice and text assistant. See CLAUDE.md."""

import os

# onnxruntime 1.29.0 opens an HTTPS connection to *.events.data.microsoft.com
# (Microsoft's telemetry ingestion) on IMPORT — not on inference, and not only
# on Windows. Measured on this machine: a process whose entire body is
# `import onnxruntime` holds two ESTAB sockets to 20.x/52.x Azure addresses
# within ~15-45 s. A bare interpreter and `import numpy` stay clean over the
# same window, so the attribution is not ambient noise.
#
# `onnxruntime.disable_telemetry_events()` does NOT stop it — tested. Only this
# environment variable does, and it must be set BEFORE the library is imported,
# which is why it lives here: `friday/__init__.py` runs ahead of every
# `friday.*` module, and ORT is imported lazily inside SileroVad.__init__ and
# tts.py. Five components route through onnxruntime (Silero VAD, openWakeWord,
# Kokoro TTS, CAM++ speaker verification, sherpa-onnx), so there is no single
# call site to guard instead.
#
# `setdefault`, not assignment: an owner who wants to turn it back on can.
# Invariant #8 and FR-60. Found by `tests/test_egress.py` (ADR-110) the day it
# was written; see ADR-112.
os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")
