"""`friday-say`: speak a line, or audition voices (G5, ADR-040).

    uv run python -m friday.audio.say "Hello, I'm Friday."
    uv run python -m friday.audio.say --voice af_heart "Testing."
    uv run python -m friday.audio.say --audition        # bella/heart/sky

The 20-utterance / no-clipping acceptance is a listening test — run this and
judge with your ears through the laptop speakers.
"""

from __future__ import annotations

import argparse
import sys

from .. import config
from .tts import Speaker

_AUDITION = [
    "af_bella",
    "af_heart",
    "af_sky",
]
_LINE = "Hi, I'm Friday. It's twenty-four degrees and sunny. I opened Brave for you."


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="friday-say")
    ap.add_argument("text", nargs="?", default=_LINE)
    ap.add_argument("--voice", default=config.KOKORO_VOICE)
    ap.add_argument(
        "--audition",
        action="store_true",
        help="speak the same line in af_bella / af_heart / af_sky",
    )
    args = ap.parse_args(argv)

    voices = _AUDITION if args.audition else [args.voice]
    for v in voices:
        sp = Speaker.create(
            config.KOKORO_MODEL,
            config.KOKORO_VOICES,
            voice=v,
            fallback=config.KOKORO_VOICE_FALLBACK,
            threads=config.KOKORO_THREADS,
        )
        if sp is None:
            print(
                f"cannot load voice {v!r} — model missing at {config.KOKORO_MODEL} "
                "or no audio device",
                file=sys.stderr,
            )
            return 1
        print(f"[{sp.voice}] {args.text}")
        sp.say(args.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
