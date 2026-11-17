"""Base TTS interface and shared playback utilities."""

from __future__ import annotations

import contextvars
import logging
import shutil
import subprocess
import sys
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

# Track every native player, not just the last one: cached speech may play
# concurrently. A scoped generation invalidates synthesis that completes late.
_audio_lock = threading.RLock()
_audio_processes: set[subprocess.Popen] = set()
_audio_generation = 0
_audio_suspended = False
_audio_scope: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "dictare_tts_audio_generation", default=None,
)
_audio_permit: contextvars.ContextVar[Callable[[], bool] | None] = contextvars.ContextVar(
    "dictare_tts_audio_permit", default=None,
)


def native_audio_generation() -> int:
    with _audio_lock:
        return -1 if _audio_suspended else _audio_generation


@contextmanager
def native_audio_scope(generation: int) -> Iterator[None]:
    """Bind a synthesis request to the playback generation in which it began."""
    token = _audio_scope.set(generation)
    try:
        yield
    finally:
        _audio_scope.reset(token)


@contextmanager
def native_playback_permit(check: Callable[[], bool]) -> Iterator[None]:
    """Bind worker playback to a revocable, fail-closed permit."""
    token = _audio_permit.set(check)
    try:
        yield
    finally:
        _audio_permit.reset(token)


def _native_permitted() -> bool:
    check = _audio_permit.get()
    if check is None:
        return True
    try:
        return check() is True
    except Exception:
        return False


def stop_audio_native(*, wait: bool = False) -> bool:
    """Interrupt all tracked players; optionally wait for them to exit."""
    with _audio_lock:
        processes = list(_audio_processes)
        for proc in processes:
            try:
                proc.terminate()
            except (ProcessLookupError, OSError):
                pass
    if wait:
        deadline = time.monotonic() + 2.0
        for proc in processes:
            try:
                proc.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    proc.wait(timeout=0.5)
                except (OSError, subprocess.TimeoutExpired):
                    return False
    return bool(processes) if not wait else True


def suspend_native_audio() -> None:
    """Invalidate prior speech requests and stop all active native players."""
    global _audio_generation, _audio_suspended
    with _audio_lock:
        _audio_generation += 1
        _audio_suspended = True
        stop_audio_native()


def resume_native_audio() -> None:
    """Allow only requests created after the most recent suspension."""
    global _audio_suspended
    with _audio_lock:
        _audio_suspended = False


def play_audio_native(path: str | Path, *, timeout: float = 120.0, volume: float = 1.0) -> bool:
    """Play a file via a native player if the current request is permitted."""
    path_str = str(path)
    if sys.platform == "darwin":
        cmd = ["afplay", "-v", str(volume), path_str]
    elif shutil.which("paplay"):
        cmd = ["paplay", f"--volume={int(volume * 65536)}", path_str]
    elif shutil.which("aplay"):
        cmd = ["aplay", "-q", path_str]
    else:
        logger.warning("No native audio player found (paplay/aplay)")
        return False

    with _audio_lock:
        generation = _audio_scope.get()
        if (_audio_suspended or (generation is not None and generation != _audio_generation)
                or not _native_permitted()):
            return False
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _audio_processes.add(proc)
    try:
        if not _native_permitted():
            proc.terminate()
            proc.wait(timeout=timeout)
            return False
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait()
    finally:
        with _audio_lock:
            _audio_processes.discard(proc)
    return True

class TTSEngine(ABC):
    """Abstract text-to-speech interface."""

    @abstractmethod
    def speak(
        self,
        text: str,
        *,
        voice: str | None = None,
        language: str | None = None,
        volume: float = 1.0,
    ) -> bool:
        """Speak text aloud.

        Args:
            text: Text to speak.
            voice: Per-request voice override (engine-dependent, optional).
            language: Per-request language override (engine-dependent, optional).
            volume: Playback volume (0.0–1.0).

        Returns:
            True if successful.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if TTS engine is available."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get engine name."""
        pass

    def check_cache(
        self,
        text: str,
        *,
        voice: str | None = None,
        language: str | None = None,
    ) -> Path | None:
        """Check if audio for *text* is already cached.

        Returns the WAV file path on cache hit, ``None`` on miss.
        Override in engines that support caching (e.g. Kokoro).
        """
        return None

    def list_voices(self) -> list[str]:
        """Return available voice names for this engine.

        Default: empty list (engine doesn't support voice listing).
        Override in subclasses that support it.
        """
        return []
