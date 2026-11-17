"""Standard paths for dictare data directory."""

from __future__ import annotations

import os
from pathlib import Path


def get_dictare_dir() -> Path:
    """Get the dictare data directory (~/.dictare)."""
    override = os.environ.get("DICTARE_RUNTIME_DIR")
    return Path(override).expanduser() if override else Path.home() / ".dictare"


def get_data_dir() -> Path:
    """Get the persistent data directory (~/.local/share/dictare)."""
    override = os.environ.get("DICTARE_DATA_DIR")
    return (
        Path(override).expanduser()
        if override
        else Path.home() / ".local" / "share" / "dictare"
    )


def get_pid_path() -> Path:
    """Get the engine PID file path."""
    return get_dictare_dir() / "engine.pid"
