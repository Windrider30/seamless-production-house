"""Pre-flight checks before starting a render."""
from __future__ import annotations

from pathlib import Path
import shutil

import psutil


def _drive_free_bytes(path: Path) -> int:
    try:
        return shutil.disk_usage(path).free
    except Exception:
        return 0


def estimate_output_bytes(clip_count: int, avg_clip_seconds: float,
                          resolution: tuple[int, int] | None) -> int:
    """Rough estimate: ~500 MB/hour at 1080p H.264."""
    total_seconds = clip_count * avg_clip_seconds
    w, h = resolution if resolution else (1920, 1080)
    scale = (w * h) / (1920 * 1080)
    bytes_per_sec = (500 * 1024 * 1024) / 3600 * scale
    return int(total_seconds * bytes_per_sec)


def check_disk_space(output_folder: Path, required_bytes: int) -> tuple[bool, str]:
    free = _drive_free_bytes(output_folder)
    if free < required_bytes:
        free_gb   = free / (1024 ** 3)
        needed_gb = required_bytes / (1024 ** 3)
        return False, (
            f"Not enough disk space on the output drive.\n"
            f"Available: {free_gb:.1f} GB  |  Needed: {needed_gb:.1f} GB\n"
            f"Free up space or choose a different output drive."
        )
    return True, ""


def check_clips_readable(clip_paths: list[Path]) -> list[str]:
    """Return list of paths that cannot be read."""
    return [str(p) for p in clip_paths if not p.is_file()]


def get_unique_output_path(folder: Path, filename: str) -> Path:
    """Append (1), (2)… suffix to avoid overwriting existing files."""
    path = folder / filename
    if not path.exists():
        return path
    stem, suffix = Path(filename).stem, Path(filename).suffix
    i = 1
    while (folder / f"{stem} ({i}){suffix}").exists():
        i += 1
    return folder / f"{stem} ({i}){suffix}"
