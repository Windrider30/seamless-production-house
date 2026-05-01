"""CPU-only encoder configuration.

GPU encoding (NVENC/AMF) has been removed because it interacts poorly with
software filters (drawtext), requires driver-specific workarounds, and can
cause media players to hang or lock up on some hardware.  libx264 is universally
supported, produces clean output that every player can handle, and is more than
fast enough for the clip lengths this app produces.
"""
from __future__ import annotations


def detect_encoder() -> str:
    return "libx264"


def encoder_flags(encoder: str | None = None) -> list[str]:
    """Return FFmpeg flags for libx264 (CPU encoding)."""
    return ["-c:v", "libx264", "-preset", "faster", "-crf", "23",
            "-pix_fmt", "yuv420p"]


def is_gpu() -> bool:
    return False


def gpu_warning() -> str | None:
    return None
