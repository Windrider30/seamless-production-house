"""Detect available GPU encoder and build the right FFmpeg video codec flags."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from src.utils.path_checker import get_ffmpeg

# Cached result
_encoder_cache: str | None = None

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _run_ffmpeg(args: list[str]) -> str:
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        return ""
    try:
        result = subprocess.run(
            [str(ffmpeg)] + args,
            capture_output=True, text=True, timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        return result.stdout + result.stderr
    except Exception:
        return ""


def _test_encoder(enc: str) -> bool:
    """
    Do a real 1-second test encode to confirm the encoder actually works
    end-to-end (driver version, API support, etc.).
    Returns True only if the encode succeeds.
    """
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        return False
    flags = encoder_flags(enc)
    cmd = [
        str(ffmpeg), "-y",
        "-f", "lavfi", "-i", "color=black:size=128x128:rate=25:duration=1",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
    ] + flags + [
        "-c:a", "aac", "-t", "1",
        "-f", "null", "-",          # discard output — just tests the encoder
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=20,
                           creationflags=CREATE_NO_WINDOW)
        return r.returncode == 0
    except Exception:
        return False


def detect_encoder() -> str:
    """
    Return the best working encoder: tries h264_nvenc → h264_amf → libx264.
    Does a real test encode for GPU encoders so driver/API mismatches are
    caught here rather than mid-render.
    """
    global _encoder_cache
    if _encoder_cache:
        return _encoder_cache

    available = _run_ffmpeg(["-hide_banner", "-encoders"])

    candidates: list[str] = []
    if "h264_nvenc" in available:
        candidates.append("h264_nvenc")
    if "h264_amf" in available:
        candidates.append("h264_amf")
    candidates.append("libx264")   # always present

    for enc in candidates:
        if enc == "libx264" or _test_encoder(enc):
            _encoder_cache = enc
            return enc

    _encoder_cache = "libx264"
    return "libx264"


def encoder_flags(encoder: str | None = None) -> list[str]:
    """Return FFmpeg flags for the selected encoder."""
    enc = encoder or detect_encoder()
    if enc == "h264_nvenc":
        # No -pix_fmt here — adding a software format filter breaks NVENC
        # when the input is already yuv420p H.264 (all AI clip sources are)
        return ["-c:v", "h264_nvenc", "-preset", "p4",
                "-rc", "constqp",
                "-init_qpI", "21", "-init_qpP", "23", "-init_qpB", "25"]
    if enc == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "balanced",
                "-qp_i", "22", "-qp_p", "24"]
    # libx264 CPU — 'faster' preset gives a good speed/quality balance on CPU
    return ["-c:v", "libx264", "-preset", "faster", "-crf", "23",
            "-pix_fmt", "yuv420p"]


def is_gpu() -> bool:
    return detect_encoder() != "libx264"


def gpu_warning() -> str | None:
    if not is_gpu():
        return (
            "No compatible GPU encoder found.\n"
            "The render will use your CPU (libx264), which is slower.\n"
            "An RTX/AMD GPU would significantly speed this up."
        )
    return None
