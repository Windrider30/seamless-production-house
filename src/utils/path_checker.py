"""Locate FFmpeg, FFprobe, and RIFE binaries."""
import shutil
from pathlib import Path

from src.config import (
    BIN_DIR, DEV_FFMPEG_PATH,
    FFMPEG_EXE_NAME, FFPROBE_EXE_NAME, RIFE_EXE_NAME,
)

# Cached results after first check
_cache: dict[str, Path | None] = {}


def _find(name: str, dev_hint: Path | None = None) -> Path | None:
    """Return the first valid path for a binary, or None."""
    candidates = [
        BIN_DIR / name,                     # next to the exe (primary)
        *(([dev_hint] if dev_hint else [])), # dev machine path
    ]
    # Also search PATH as last resort
    found_on_path = shutil.which(name)
    if found_on_path:
        candidates.append(Path(found_on_path))

    for p in candidates:
        if p and p.is_file():
            return p
    return None


def get_ffmpeg() -> Path | None:
    if "ffmpeg" not in _cache:
        _cache["ffmpeg"] = _find(FFMPEG_EXE_NAME, DEV_FFMPEG_PATH)
    return _cache["ffmpeg"]


def get_ffprobe() -> Path | None:
    if "ffprobe" not in _cache:
        # ffprobe lives next to ffmpeg; try sibling of the found ffmpeg
        ffmpeg = get_ffmpeg()
        hint = ffmpeg.parent / FFPROBE_EXE_NAME if ffmpeg else None
        _cache["ffprobe"] = _find(FFPROBE_EXE_NAME, hint)
    return _cache["ffprobe"]


def get_rife() -> Path | None:
    if "rife" not in _cache:
        _cache["rife"] = _find(RIFE_EXE_NAME)
    return _cache["rife"]


def missing_engines() -> list[str]:
    """Return list of missing binary names (empty = all good)."""
    missing = []
    if not get_ffmpeg():
        missing.append(FFMPEG_EXE_NAME)
    if not get_rife():
        missing.append(RIFE_EXE_NAME)
    return missing


def invalidate_cache() -> None:
    """Call after a successful download so next check re-scans disk."""
    _cache.clear()
