"""Bound a press-and-hold gesture when a release event can be lost.

This gate owns gesture lifetime only. Its caller owns microphone state and must
interpret timeout/cancellation as discard, rather than completing a prompt.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Literal

logger = logging.getLogger(__name__)

HoldEnd = Literal["released", "timeout", "cancelled"]


class HoldGate:
    """Serialize press, release and cancellation, with a fail-closed deadline."""

    def __init__(
        self,
        on_start: Callable[[], None],
        on_end: Callable[[HoldEnd], None],
        *,
        timeout: float,
    ) -> None:
        if timeout <= 0:
            raise ValueError("Hold timeout must be positive")
        self._on_start = on_start
        self._on_end = on_end
        self._timeout = timeout
        self._lock = threading.RLock()
        self._generation = 0
        self._active = False
        self._timer: threading.Timer | None = None

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    def press(self) -> bool:
        """Begin one gesture; repeated key-down events do not restart it."""
        with self._lock:
            if self._active:
                return False
            self._generation += 1
            generation = self._generation
            self._active = True
            timer = threading.Timer(self._timeout, self._expire, args=(generation,))
            timer.daemon = True
            self._timer = timer
            try:
                timer.start()
                self._on_start()
            except BaseException:
                self._active = False
                self._timer = None
                timer.cancel()
                # Start can fail after partially opening capture. Always tell the
                # owner to discard; retain the original error if cleanup fails.
                try:
                    self._on_end("cancelled")
                except Exception:
                    logger.exception("Failed to cancel a partially started hold")
                raise
            return True

    def release(self) -> bool:
        """Finish a live gesture after its matching physical release."""
        return self._finish("released")

    def cancel(self) -> bool:
        """Cancel a live gesture on shutdown, mode change or transport failure."""
        return self._finish("cancelled")

    def _expire(self, generation: int) -> None:
        with self._lock:
            if self._active and self._generation == generation:
                self._finish("timeout")

    def _finish(self, reason: HoldEnd) -> bool:
        with self._lock:
            if not self._active:
                return False
            self._active = False
            timer, self._timer = self._timer, None
            if timer is not None:
                timer.cancel()
            self._on_end(reason)
            return True
