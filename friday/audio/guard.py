"""One guard for both PortAudio callbacks (audit M-A1).

sounddevice runs the callback on a PortAudio thread and catches whatever
escapes: it prints the traceback to stderr and then **stops calling back**.
The stream object stays open, `just selftest`'s `audio_devices` check still
passes, and wake / VAD / capture are dead for the rest of the process. That is
the silent-degradation shape this project has now paid for five times, so
nothing may escape a callback, and a callback that keeps failing must say so
once, loudly, with a code (ADR-067i, spec §4 `E_AUDIO_DEAD`).

Consecutive, not cumulative: one malformed frame in an hour is noise, five in
a row is a dead audio path.
"""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from ..errors import E_AUDIO_DEAD

log = logging.getLogger(__name__)

DEFAULT_LIMIT = 5


class CallbackGuard:
    """Runs an audio-thread callable, swallowing exceptions and counting them.

    `on_disable` fires once, when the consecutive-failure count first reaches
    `limit`. With `stop_calling` the guard then refuses to invoke the callable
    at all — the wake path's degradation, since a detector that cannot score is
    worse than no detector. The capture path keeps calling: its callback only
    gate-checks and copies, so there is nothing to disable and a recovered
    device should just resume filling the ring.
    """

    def __init__(
        self,
        name: str,
        *,
        limit: int = DEFAULT_LIMIT,
        on_disable: Callable[[], None] | None = None,
        stop_calling: bool = True,
    ) -> None:
        self.name = name
        self.limit = limit
        self.disabled = False
        self._on_disable = on_disable
        self._stop_calling = stop_calling
        self._consecutive = 0

    def run(self, fn: Callable[..., Any], *args: Any) -> None:
        """Call `fn(*args)`; never raise, whatever it does."""
        if self.disabled and self._stop_calling:
            return
        try:
            fn(*args)
        except Exception as exc:  # noqa: BLE001 - the whole point is that nothing escapes
            self._consecutive += 1
            if self._consecutive >= self.limit and not self.disabled:
                self.disabled = True
                # Never speak or log the exception body verbatim beyond its
                # type/message (spec §4): audio frames are not in it, but the
                # rule is the rule.
                log.error(
                    "%s %s audio callback failed %d times in a row (%s: %s); "
                    "%s. Restart the daemon once the audio device is back.",
                    E_AUDIO_DEAD,
                    self.name,
                    self._consecutive,
                    type(exc).__name__,
                    exc,
                    "detector disabled" if self._stop_calling else "still running degraded",
                )
                if self._on_disable is not None:
                    self._on_disable()
        else:
            self._consecutive = 0
