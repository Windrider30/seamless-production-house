"""
OpenCV-based transition preview.
Uses a deque circular buffer (Bug #12) — never holds more than 100 frames in RAM.
Displays frames via PIL → CTkLabel (more stable than tkVideoPlayer).
"""
from __future__ import annotations

import threading
import time
from collections import deque
from pathlib import Path
from typing import Sequence

import customtkinter as ctk
from PIL import Image

from src.config import C

try:
    import cv2
    import numpy as np
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

PREVIEW_W, PREVIEW_H = 480, 270
MAX_FRAMES = 100        # circular buffer cap (Bug #12)
FPS_DISPLAY = 24        # playback speed in preview


def _extract_frames(video_path: Path, from_end: bool,
                    seconds: float, max_frames: int) -> list[Image.Image]:
    if not _CV2_OK:
        return []
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    src_fps      = cap.get(cv2.CAP_PROP_FPS) or 30
    grab_count   = min(max_frames, int(src_fps * seconds))

    if from_end:
        start = max(0, total_frames - grab_count)
    else:
        start = 0

    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    frames: list[Image.Image] = []
    for _ in range(grab_count):
        ret, frame = cap.read()
        if not ret:
            break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb).resize(
            (PREVIEW_W, PREVIEW_H), Image.LANCZOS
        )
        frames.append(img)
    cap.release()
    return frames


class PreviewPanel(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C["bg2"], corner_radius=10, **kwargs)
        self._buffer: deque[Image.Image] = deque(maxlen=MAX_FRAMES)
        self._playing = False
        self._play_thread: threading.Thread | None = None
        self._frame_idx = 0
        self._tk_image = None   # keep reference alive
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(
            self, text="TRANSITION PREVIEW",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=C["muted"], anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 4))

        # Video canvas
        self._canvas_lbl = ctk.CTkLabel(
            self, text="",
            fg_color=C["bg"],
            width=PREVIEW_W, height=PREVIEW_H,
            corner_radius=6,
        )
        self._canvas_lbl.pack(padx=12, pady=(0, 8))

        if not _CV2_OK:
            self._canvas_lbl.configure(
                text="Install opencv-python\nfor preview support",
                text_color=C["muted"],
                font=ctk.CTkFont(size=12),
            )

        # Controls row
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=12, pady=(0, 10))

        self._play_btn = ctk.CTkButton(
            ctrl, text="▶ Play", width=80, height=28,
            fg_color=C["emerald"], text_color=C["bg"],
            hover_color=C["emerald_lt"],
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._toggle_play,
            state="disabled",
        )
        self._play_btn.pack(side="left")

        self._trans_lbl = ctk.CTkLabel(
            ctrl, text="Select a clip to preview",
            font=ctk.CTkFont(size=11),
            text_color=C["text2"], anchor="w",
        )
        self._trans_lbl.pack(side="left", padx=12)

    # ── Public API ───────────────────────────────────────────────────────────

    def load_transition(self, clip_a: Path, clip_b: Path,
                        label: str = "") -> None:
        """Load last 2s of clip_a + first 2s of clip_b into the buffer."""
        self._stop_play()
        threading.Thread(
            target=self._load_worker, args=(clip_a, clip_b, label),
            daemon=True,
        ).start()

    def clear(self) -> None:
        self._stop_play()
        self._buffer.clear()
        self._canvas_lbl.configure(image=None, text="")
        self._play_btn.configure(state="disabled")
        self._trans_lbl.configure(text="Select a clip to preview")

    # ── Internal ─────────────────────────────────────────────────────────────

    def _load_worker(self, clip_a: Path, clip_b: Path, label: str) -> None:
        self.after(0, lambda: self._trans_lbl.configure(text="Loading…"))
        frames_a = _extract_frames(clip_a, from_end=True,  seconds=2.0, max_frames=50)
        frames_b = _extract_frames(clip_b, from_end=False, seconds=2.0, max_frames=50)
        combined = frames_a + frames_b

        self._buffer.clear()
        for f in combined[:MAX_FRAMES]:
            self._buffer.append(f)

        def done():
            self._trans_lbl.configure(
                text=label or f"{clip_a.name} → {clip_b.name}"
            )
            if self._buffer:
                self._show_frame(0)
                self._play_btn.configure(state="normal")

        self.after(0, done)

    def _show_frame(self, idx: int) -> None:
        if not self._buffer:
            return
        idx = idx % len(self._buffer)
        self._frame_idx = idx
        img = list(self._buffer)[idx]
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img,
                               size=(PREVIEW_W, PREVIEW_H))
        self._tk_image = ctk_img       # prevent GC
        self._canvas_lbl.configure(image=ctk_img, text="")

    def _toggle_play(self) -> None:
        if self._playing:
            self._stop_play()
        else:
            self._start_play()

    def _start_play(self) -> None:
        self._playing = True
        self._play_btn.configure(text="⏸ Pause")
        self._play_thread = threading.Thread(
            target=self._play_loop, daemon=True
        )
        self._play_thread.start()

    def _stop_play(self) -> None:
        self._playing = False
        try:
            self.after(0, lambda: self._play_btn.configure(text="▶ Play"))
        except Exception:
            pass

    def _play_loop(self) -> None:
        delay = 1.0 / FPS_DISPLAY
        n = len(self._buffer)
        while self._playing and n > 0:
            self.after(0, lambda i=self._frame_idx: self._show_frame(i))
            self._frame_idx = (self._frame_idx + 1) % n
            time.sleep(delay)
