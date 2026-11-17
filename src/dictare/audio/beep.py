"""Audio feedback sounds for dictare.

Provides bundled sound file paths and in-process audio playback.
Playback via sounddevice + soundfile (no external processes).
Bundled sounds are pre-loaded into memory at import time for zero-latency playback.

Thread safety: a queue preserves output ordering. While the engine is active,
sounddevice lifecycle calls are also routed through AudioManager's single
PortAudio owner, together with input open/close/reinit operations.

Key function:
    play_audio(source, pause_mic, controller) - shared entry point for all playback.
    - pause_mic=False: fire-and-forget via queue.
    - pause_mic=True: registers play_id, transitions to PLAYING state (mic muted),
      plays audio, waits for completion, then sends PlayCompleted to resume.
"""

from __future__ import annotations

import logging
import queue
import random
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Output device for beep playback (None = system default)
_output_device: str | int | None = None

def set_output_device(device: str | None) -> None:
    """Set the output device for beep playback.

    Args:
        device: Device name or None/empty for system default.
    """
    global _output_device
    _output_device = device or None

_SOUNDS_DIR = Path(__file__).parent / "sounds"

# Default bundled sound files
DEFAULT_SOUND_START = _SOUNDS_DIR / "up-beep.wav"
DEFAULT_SOUND_STOP = _SOUNDS_DIR / "down-beep.wav"
DEFAULT_SOUND_TRANSCRIBING = _SOUNDS_DIR / "typewriter.wav"
DEFAULT_SOUND_SUBMIT = _SOUNDS_DIR / "typewriter-burst.wav"
DEFAULT_SOUND_READY = _SOUNDS_DIR / "carriage-return.wav"
DEFAULT_SOUND_TRANSCRIBED = _SOUNDS_DIR / "pencil-write.wav"

# Multi-clip random selection for pencil-write sound
_PENCIL_WRITE_CLIPS: list[Path] = [
    p for p in (_SOUNDS_DIR / f"pencil-write-{i}.wav" for i in range(1, 6)) if p.exists()
] or [DEFAULT_SOUND_TRANSCRIBED]

def _pick_pencil_write() -> Path:
    """Return a random pencil-write clip path."""
    return random.choice(_PENCIL_WRITE_CLIPS)

# Map event names to their default bundled sound files
_DEFAULT_SOUNDS: dict[str, Path] = {
    "start": DEFAULT_SOUND_START,
    "stop": DEFAULT_SOUND_STOP,
    "transcribing": DEFAULT_SOUND_TRANSCRIBING,
    "ready": DEFAULT_SOUND_READY,
    "transcribed": DEFAULT_SOUND_TRANSCRIBED,
    "submit": DEFAULT_SOUND_SUBMIT,  # typewriter burst on submit
    "sent": DEFAULT_SOUND_READY,  # carriage-return on submit
}

# Pre-loaded sound cache: path -> (numpy_array, sample_rate)
_sound_cache: dict[str, tuple[np.ndarray, int]] = {}

def _preload_sounds() -> None:
    """Pre-load bundled sounds into memory at import time."""
    try:
        import soundfile as sf
    except ImportError:
        logger.debug("soundfile not available, sounds will be loaded on demand")
        return

    for path in {DEFAULT_SOUND_START, DEFAULT_SOUND_STOP, DEFAULT_SOUND_TRANSCRIBING, DEFAULT_SOUND_SUBMIT, DEFAULT_SOUND_READY, *_PENCIL_WRITE_CLIPS}:
        try:
            data, sr = sf.read(path)
            _sound_cache[str(path)] = (data, sr)
        except Exception:
            logger.debug("Failed to preload %s", path)

_preload_sounds()

# ---------------------------------------------------------------------------
# Audio playback queue — serializes all sounddevice output on one thread
# ---------------------------------------------------------------------------

_play_queue: queue.Queue[tuple[str, float, Callable[[], None] | None, int, Callable[[], None] | None] | None] = queue.Queue()
_play_generation = 0
_play_generation_lock = threading.RLock()
_feedback_suspended = False
_fallback_process: subprocess.Popen | None = None
_worker_started = False
_worker_lock = threading.Lock()
_audio_control_execute: Callable[[str, Callable[[], Any]], Any] | None = None


def set_audio_control_executor(
    executor: Callable[[str, Callable[[], Any]], Any] | None,
) -> None:
    """Route sounddevice lifecycle calls through the process audio owner."""
    global _audio_control_execute
    _audio_control_execute = executor


def _execute_audio_control(label: str, action: Callable[[], Any]) -> Any:
    """Execute an output lifecycle call through the configured owner."""
    executor = _audio_control_execute
    if executor is None:
        return action()
    return executor(label, action)


def stop_portaudio_output() -> None:
    """Stop active feedback playback before a global PortAudio reinit."""
    import sounddevice as sd

    from dictare.audio.capture import _run_with_timeout

    _execute_audio_control(
        "stop_output",
        lambda: _run_with_timeout(sd.stop, timeout_s=3.0, label="output_stop"),
    )

def _enqueue_sound(
    path: str, volume: float, on_complete: Callable[[], None] | None,
    on_cancel: Callable[[], None] | None = None,
) -> None:
    with _play_generation_lock:
        suspended = _feedback_suspended
        if not suspended:
            _play_queue.put((path, volume, on_complete, _play_generation, on_cancel))
    if suspended:
        for callback in (on_cancel, on_complete):
            if callback:
                try:
                    callback()
                except Exception:
                    pass


def _is_current_playback(generation: int) -> bool:
    with _play_generation_lock:
        return generation == _play_generation


def _play_if_current(generation: int, action: Callable[[], None]) -> bool:
    # Serialize the final native start with invalidation.
    with _play_generation_lock:
        if generation != _play_generation:
            return False
        action()
        return True


def cancel_pending_feedback() -> None:
    """Invalidate queued feedback and stop looping, but not active playback.

    This does not stop already-running native or subprocess audio. The caller
    must handle those paths separately before claiming full mute isolation.
    """
    global _play_generation
    with _play_generation_lock:
        _play_generation += 1
        stop_loop()


def suspend_feedback(*, stop_active: bool = True) -> None:
    """Suppress new feedback, cancel queued items, and optionally stop output."""
    global _feedback_suspended, _play_generation
    with _play_generation_lock:
        _feedback_suspended = True
        _play_generation += 1
        stop_loop()
        proc = _fallback_process
        if proc is not None:
            try:
                proc.terminate()
            except (ProcessLookupError, OSError):
                pass
    if proc is not None:
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=1.0)
    if stop_active:
        stop_portaudio_output()


def resume_feedback() -> None:
    """Permit newly requested feedback after strict mute ends."""
    global _feedback_suspended
    with _play_generation_lock:
        _feedback_suspended = False


def _ensure_worker() -> None:
    """Start the audio playback worker if not already running."""
    global _worker_started
    if _worker_started:
        return
    with _worker_lock:
        if _worker_started:
            return
        t = threading.Thread(target=_audio_worker, daemon=True, name="dictare-audio-out")
        t.start()
        _worker_started = True

def _audio_worker() -> None:
    """Single worker thread for all sounddevice output.

    Serializes sd.play()/sd.wait() calls to prevent concurrent access
    to PortAudio's global session (which is not thread-safe).

    Items carry a playback generation or ``None`` (shutdown).
    When *on_complete* is set the worker blocks with ``sd.wait()`` until
    playback finishes, then invokes the callback.  Otherwise it fires
    ``sd.play()`` and immediately processes the next item (fire-and-forget).
    """
    while True:
        item = _play_queue.get()
        if item is None:
            break

        path_str, volume, on_complete, generation, on_cancel = item
        cancelled = False
        try:
            if not _is_current_playback(generation):
                cancelled = True
                continue
            cached = _sound_cache.get(path_str)
            if cached is not None:
                data, sr = cached
            else:
                import soundfile as sf

                data, sr = sf.read(path_str)
                _sound_cache[path_str] = (data, sr)

            import sounddevice as sd

            from dictare.audio.capture import _run_with_timeout

            started = _execute_audio_control(
                "play_output",
                lambda: _run_with_timeout(
                    lambda: _play_if_current(
                        generation,
                        lambda: sd.play(
                            data * volume if volume != 1.0 else data,
                            sr,
                            device=_output_device,
                        ),
                    ),
                    timeout_s=3.0,
                    label="output_open",
                ),
            )
            if started is False:
                cancelled = True
                continue
            if on_complete:
                # sd.wait() can hang indefinitely on Linux (ALSA/PulseAudio).
                # Poll with timeout to prevent FSM getting stuck in PLAYING.
                import time as _time

                deadline = _time.monotonic() + _PLAYBACK_DEADLINE_S
                while sd.get_stream() and sd.get_stream().active:
                    if _time.monotonic() > deadline:
                        logger.warning(
                            "sd.wait() timed out after %.0fs — forcing completion",
                            _PLAYBACK_DEADLINE_S,
                        )
                        try:
                            stop_portaudio_output()
                        except Exception:
                            pass
                        break
                    _time.sleep(_PLAYBACK_POLL_S)
        except Exception:
            logger.debug("Audio playback failed for %s", path_str, exc_info=True)
            if _is_current_playback(generation):
                _play_sound_file_fallback(path_str, generation)
            else:
                cancelled = True
        finally:
            if cancelled and on_cancel:
                try:
                    on_cancel()
                except Exception:
                    pass
            if on_complete:
                try:
                    on_complete()
                except Exception:
                    pass

def play_wav_sync(path: str | Path, timeout_s: float = 15.0) -> bool:
    """Play a WAV file through the serialized audio worker, blocking until done.

    Use this from TTS engines instead of calling sd.play() directly — the
    worker thread is the only thread allowed to call sounddevice output APIs.

    Args:
        path: Path to the WAV file.
        timeout_s: Maximum seconds to wait for playback completion.

    Returns:
        True if playback completed, False if timed out or failed.
    """
    _ensure_worker()
    done = threading.Event()
    cancelled = threading.Event()
    _enqueue_sound(str(path), 1.0, done.set, cancelled.set)
    return done.wait(timeout=timeout_s) and not cancelled.is_set()

def get_sound_for_event(audio_config: Any, name: str) -> tuple[bool, str]:
    """Check if a sound event is enabled and return its file path.

    Considers the master switch (audio_feedback) and per-event config.
    For 'agent_announce', returns (enabled, "") since it uses TTS, not a file.

    Args:
        audio_config: AudioConfig instance.
        name: Event name (start, stop, transcribing, ready, sent, agent_announce).

    Returns:
        (enabled, path) — enabled=False means skip playback.
    """
    if not audio_config.audio_feedback:
        return False, ""

    sound_cfg = audio_config.sounds.get(name)
    if sound_cfg is None:
        # Unknown event or not configured — use default if available
        default = _DEFAULT_SOUNDS.get(name)
        return (True, str(default)) if default else (False, "")

    if not sound_cfg.enabled:
        return False, ""

    if name == "agent_announce":
        return True, ""  # TTS, no file path — volume read via get_volume_for_event()

    if sound_cfg.path:
        path = sound_cfg.path
    elif name == "transcribed":
        path = str(_pick_pencil_write())
    else:
        path = str(_DEFAULT_SOUNDS.get(name, ""))
    return True, path

def get_volume_for_event(audio_config: Any, name: str) -> float:
    """Return the configured volume for a sound event (0.0–1.0)."""
    sound_cfg = audio_config.sounds.get(name)
    if sound_cfg is None:
        return 1.0
    return sound_cfg.volume

def get_sound_path(name: str) -> Path:
    """Get path to a bundled sound file.

    Args:
        name: Filename (e.g., 'up-beep.wav', 'down-beep.wav')

    Returns:
        Path to the sound file.
    """
    return _SOUNDS_DIR / name

def play_sound_file(
    path: str | Path, *, volume: float = 1.0, on_complete: Callable[[], None] | None = None
) -> None:
    """Enqueue a sound file for playback on the audio worker thread.

    Non-blocking: returns immediately after enqueueing.
    Thread-safe: all sounddevice calls happen on a single worker thread.

    Args:
        path: Path to sound file (wav, etc.)
        volume: Playback volume multiplier (0.0–1.0, default 1.0).
        on_complete: Optional callback invoked after playback finishes.
            When set, the worker blocks (sd.wait) until done, then calls it.
    """
    _ensure_worker()
    _enqueue_sound(str(path), volume, on_complete)

# ---------------------------------------------------------------------------
# Loop support — plays a sound repeatedly until stop_loop() is called.
#
# The audio is pre-sliced into ~1s chunks so that stop_loop() takes effect
# within at most 1 second (no need for sd.stop() to interrupt a long play).
# ---------------------------------------------------------------------------

_LOOP_CHUNK_DURATION: float = 1.0     # seconds per chunk
_PLAYBACK_DEADLINE_S: float = 10.0    # max seconds to wait for sd.wait()
_PLAYBACK_POLL_S: float = 0.05        # poll interval while waiting for sd.wait()
_FALLBACK_CMD_TIMEOUT: int = 5        # seconds for afplay/paplay subprocess

_loop_active: threading.Event = threading.Event()
_loop_chunk_keys: list[str] = []   # cache keys for each 1s slice
_loop_chunk_pos: int = 0           # next chunk index (wraps around)
_loop_pending_timer: threading.Timer | None = None  # delayed start timer
_loop_volume: float = 1.0          # volume for current loop

def _enqueue_loop_next() -> None:
    """on_complete callback: schedule the next 1s chunk if still active."""
    global _loop_chunk_pos
    with _play_generation_lock:
        if not _loop_active.is_set() or not _loop_chunk_keys:
            return
        key = _loop_chunk_keys[_loop_chunk_pos % len(_loop_chunk_keys)]
        _loop_chunk_pos += 1
        _enqueue_sound(key, 1.0, _enqueue_loop_next)  # volume baked into chunk data

def _start_loop_now(path_str: str) -> None:
    """Internal: load, chunk, and kick off the loop immediately."""
    global _loop_chunk_keys, _loop_chunk_pos, _loop_pending_timer
    _loop_pending_timer = None

    if not _loop_active.is_set():
        return  # stop_loop() was called before the delay fired

    cached = _sound_cache.get(path_str)
    if cached is not None:
        data, sr = cached
    else:
        try:
            import soundfile as sf
            data, sr = sf.read(path_str)
            _sound_cache[path_str] = (data, sr)
        except Exception:
            logger.debug("_start_loop_now: failed to load %s", path_str, exc_info=True)
            return

    chunk_size = max(1, int(_LOOP_CHUNK_DURATION * sr))
    new_keys: list[str] = []
    volume = _loop_volume
    for i, start in enumerate(range(0, len(data), chunk_size)):
        chunk = data[start : start + chunk_size]
        if volume != 1.0:
            chunk = chunk * volume
        key = f"__loop_chunk_{i}__"
        _sound_cache[key] = (chunk, sr)
        new_keys.append(key)

    _loop_chunk_keys = new_keys
    _loop_chunk_pos = 0
    _ensure_worker()
    _enqueue_loop_next()

def start_loop(path: str | Path, volume: float = 1.0) -> None:
    """Start looping *path* in 1-second chunks until stop_loop() is called.

    Non-blocking.  Caller is responsible for the audio-duration threshold check
    (only call this when the recording was long enough to warrant feedback).

    Args:
        path: Path to sound file to loop.
        volume: Playback volume multiplier (0.0–1.0, default 1.0).
    """
    global _loop_pending_timer, _loop_volume

    with _play_generation_lock:
        if _feedback_suspended:
            return
        if _loop_pending_timer is not None:
            _loop_pending_timer.cancel()
            _loop_pending_timer = None
        _loop_volume = volume
        _loop_active.set()
    _start_loop_now(str(path))

def stop_loop() -> None:
    """Stop the loop after the current 1s chunk finishes."""
    global _loop_pending_timer
    with _play_generation_lock:
        if _loop_pending_timer is not None:
            _loop_pending_timer.cancel()
            _loop_pending_timer = None
        _loop_active.clear()

def is_looping() -> bool:
    """Return True if a loop is currently active."""
    return _loop_active.is_set()

def _play_sound_file_fallback(path_str: str, generation: int) -> None:
    """Play a fallback process that strict mute can terminate."""
    global _fallback_process
    commands = [["afplay", path_str]] if sys.platform == "darwin" else [
        ["paplay", path_str], ["aplay", "-q", path_str],
    ]
    for command in commands:
        try:
            with _play_generation_lock:
                if _feedback_suspended or generation != _play_generation:
                    return
                proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                _fallback_process = proc
            try:
                proc.wait(timeout=_FALLBACK_CMD_TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.terminate()
                proc.wait()
            finally:
                with _play_generation_lock:
                    if _fallback_process is proc:
                        _fallback_process = None
            return
        except FileNotFoundError:
            continue
        except Exception:
            return


def play_sound_file_async(path: str | Path, *, volume: float = 1.0) -> None:
    """Play a sound file asynchronously (non-blocking, fire-and-forget).

    Alias for play_sound_file() — kept for backward compatibility.
    play_sound_file() is already non-blocking (queue-based).

    Args:
        path: Path to sound file (wav, etc.)
        volume: Playback volume multiplier (0.0–1.0, default 1.0).
    """
    play_sound_file(path, volume=volume)

def play_audio(
    source: str | Path | Callable[[], None],
    *,
    pause_mic: bool = True,
    controller: Any = None,
    volume: float = 1.0,
) -> None:
    """Play audio, optionally pausing the microphone during playback.

    This is the shared entry point for all audio playback in dictare.

    File paths are dispatched through the audio worker queue (thread-safe).
    Callable sources (e.g., TTS via subprocess) run on their own thread
    because they don't use sounddevice.

    Args:
        source: Path to audio file, or blocking callable that produces audio.
        pause_mic: If True and controller available, mute mic during playback
            via the PLAYING state transition. If False, fire-and-forget.
        controller: StateController instance. Required for pause_mic=True.
    """
    is_callable = callable(source)

    # --- Callable source (TTS) — runs on its own thread ---
    if is_callable:
        fn: Callable[[], None] = source  # type: ignore[assignment]

        if not pause_mic or controller is None:
            threading.Thread(target=fn, daemon=True).start()
            return

        from dictare.core.fsm import AppState

        if controller.state == AppState.OFF:
            threading.Thread(target=fn, daemon=True).start()
            return

        from dictare.core.fsm import PlayCompleted, PlayStarted

        controller.send(PlayStarted(text="", source="audio"))

        def _play_with_events() -> None:
            try:
                fn()
            finally:
                try:
                    controller.send(PlayCompleted(source="audio"))
                except Exception:
                    pass

        threading.Thread(target=_play_with_events, daemon=True).start()
        return

    # --- File source — dispatched through the audio queue ---
    _path: str | Path = source  # type: ignore[assignment]

    if not pause_mic or controller is None:
        play_sound_file(_path, volume=volume)
        return

    from dictare.core.fsm import AppState

    if controller.state == AppState.OFF:
        play_sound_file(_path, volume=volume)
        return

    from dictare.core.fsm import PlayCompleted, PlayStarted

    controller.send(PlayStarted(text="", source="audio"))

    def on_complete() -> None:
        try:
            controller.send(PlayCompleted(source="audio"))
        except Exception:
            pass

    play_sound_file(_path, volume=volume, on_complete=on_complete)

def warmup_audio() -> None:
    """No-op, kept for API compatibility."""

# Legacy API - kept for backward compatibility
def play_beep_start() -> None:
    """Play beep indicating listening mode started."""
    play_sound_file_async(DEFAULT_SOUND_START)

def play_beep_stop() -> None:
    """Play beep indicating listening mode stopped."""
    play_sound_file_async(DEFAULT_SOUND_STOP)

def play_beep_sent() -> None:
    """Play beep indicating transcription was sent/written."""
    play_sound_file_async(DEFAULT_SOUND_START)

def play_beep_busy() -> None:
    """Play beep indicating system is busy (speech ignored)."""
    play_sound_file_async(DEFAULT_SOUND_STOP)

# TTS mode announcements per language (fallback to English for unsupported languages)
_MODE_PHRASES = {
    "it": {"transcription": "modalità trascrizione", "command": "modalità comandi"},
    "en": {"transcription": "transcription mode", "command": "command mode"},
}

# macOS voice names per language
_MACOS_VOICES = {
    "it": "Alice",
    "en": "Samantha",
}

def speak_mode(mode: str, language: str = "en") -> None:
    """Speak the current mode using OS TTS.

    Args:
        mode: Either "transcription" or "command"
        language: Language code (it, en, es, fr, de, pt)
    """
    # Get phrase for language, fallback to English
    phrases = _MODE_PHRASES.get(language, _MODE_PHRASES["en"])
    text = phrases.get(mode, mode)

    def _speak() -> None:
        try:
            if sys.platform == "darwin":
                # macOS: use 'say' command
                voice = _MACOS_VOICES.get(language, "Samantha")
                subprocess.run(
                    ["say", "-v", voice, text],
                    capture_output=True,
                    timeout=5,
                )
            else:
                # Linux: try espeak-ng, then espeak, then spd-say
                lang_code = language if language != "en" else "en-us"
                for cmd in [
                    ["espeak-ng", "-v", lang_code, text],
                    ["espeak", "-v", lang_code, text],
                    ["spd-say", "-l", language, text],
                ]:
                    try:
                        subprocess.run(cmd, capture_output=True, timeout=5)
                        break
                    except FileNotFoundError:
                        continue
        except Exception:
            pass  # Silently fail if TTS not available

    # Run in background thread to not block
    threading.Thread(target=_speak, daemon=True).start()
