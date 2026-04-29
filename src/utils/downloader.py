"""Auto-download FFmpeg and RIFE ncnn-vulkan into BIN_DIR."""
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from typing import Callable
import requests

from src.config import (
    BIN_DIR, FFMPEG_RELEASE_URL,
    FFMPEG_EXE_NAME, FFPROBE_EXE_NAME,
    RIFE_GITHUB_REPO, RIFE_EXE_NAME,
)

ProgressCallback = Callable[[str, float], None]   # (message, 0.0‒1.0)


def _download_bytes(url: str, progress: ProgressCallback | None) -> bytes:
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    buf = io.BytesIO()
    downloaded = 0
    chunk_size = 1024 * 64
    for chunk in resp.iter_content(chunk_size):
        buf.write(chunk)
        downloaded += len(chunk)
        if progress and total:
            progress("Downloading…", downloaded / total * 0.8)
    buf.seek(0)
    return buf.read()


def _extract_file(data: bytes, src_name: str, dest: Path,
                  progress: ProgressCallback | None) -> None:
    if progress:
        progress(f"Extracting {dest.name}…", 0.85)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for member in zf.namelist():
            if Path(member).name == src_name:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src_f, open(dest, "wb") as dst_f:
                    dst_f.write(src_f.read())
                return
    raise FileNotFoundError(f"{src_name} not found inside zip")


def _extract_dir(data: bytes, prefix: str, dest_dir: Path,
                 progress: ProgressCallback | None) -> None:
    """Extract all files whose zip path contains prefix into dest_dir."""
    if progress:
        progress(f"Extracting model files…", 0.90)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        members = [m for m in zf.namelist() if prefix in m and not m.endswith("/")]
        for i, member in enumerate(members):
            name = Path(member).name
            with zf.open(member) as src_f:
                (dest_dir / name).write_bytes(src_f.read())
            if progress:
                progress("Extracting model files…", 0.90 + (i / max(len(members), 1)) * 0.09)


def download_ffmpeg(progress: ProgressCallback | None = None) -> None:
    """Download FFmpeg essentials build and extract ffmpeg + ffprobe."""
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    if progress:
        progress("Fetching FFmpeg…", 0.0)
    data = _download_bytes(FFMPEG_RELEASE_URL, progress)
    _extract_file(data, FFMPEG_EXE_NAME, BIN_DIR / FFMPEG_EXE_NAME, progress)
    try:
        _extract_file(data, FFPROBE_EXE_NAME, BIN_DIR / FFPROBE_EXE_NAME, progress)
    except FileNotFoundError:
        pass  # ffprobe optional
    if progress:
        progress("FFmpeg ready.", 1.0)


def _get_rife_release_url() -> str:
    api = f"https://api.github.com/repos/{RIFE_GITHUB_REPO}/releases/latest"
    resp = requests.get(api, timeout=30)
    resp.raise_for_status()
    assets = resp.json().get("assets", [])
    for asset in assets:
        name: str = asset["name"]
        if "windows" in name.lower() and name.endswith(".zip"):
            return asset["browser_download_url"]
    raise RuntimeError("Could not find Windows RIFE release asset on GitHub.")


def download_rife(progress: ProgressCallback | None = None) -> None:
    """Download latest RIFE ncnn-vulkan for Windows and install into BIN_DIR."""
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    if progress:
        progress("Looking up latest RIFE release…", 0.02)
    url = _get_rife_release_url()
    data = _download_bytes(url, progress)
    # Extract the main exe
    _extract_file(data, RIFE_EXE_NAME, BIN_DIR / RIFE_EXE_NAME, progress)
    # Extract model directory (rife-v4.x folders contain .bin/.param)
    _extract_dir(data, "rife-v4", BIN_DIR / "rife-models", progress)
    if progress:
        progress("RIFE ready.", 1.0)


def download_all(progress: ProgressCallback | None = None) -> list[str]:
    """Download both engines. Returns list of error messages (empty = success)."""
    errors: list[str] = []
    try:
        download_ffmpeg(progress)
    except Exception as exc:
        errors.append(f"FFmpeg download failed: {exc}")
    try:
        download_rife(progress)
    except Exception as exc:
        errors.append(f"RIFE download failed: {exc}")
    return errors
