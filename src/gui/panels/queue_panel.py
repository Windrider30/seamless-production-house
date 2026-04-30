"""Scrollable, paginated clip queue. Handles 500+ clips without lag (Bug #15)."""
from __future__ import annotations

import subprocess
import json
from pathlib import Path
from typing import Callable

import sys

import customtkinter as ctk

from src.config import C, IMAGE_EXTENSIONS
from src.utils.path_checker import get_ffmpeg, get_ffprobe

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
PAGE_SIZE = 50  # clips shown per page


def _probe_clip(path: Path) -> dict:
    """Return basic clip metadata via ffprobe."""
    ffprobe_path = get_ffprobe()
    if not ffprobe_path:
        return {}
    try:
        result = subprocess.run(
            [str(ffprobe_path), "-v", "quiet", "-print_format", "json",
             "-show_streams", "-show_format", str(path)],
            capture_output=True, text=True, timeout=8,
            creationflags=CREATE_NO_WINDOW,
        )
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        duration = float(fmt.get("duration", 0))
        video_stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
            {}
        )
        w = video_stream.get("width", 0)
        h = video_stream.get("height", 0)
        return {"duration": duration, "width": w, "height": h}
    except Exception:
        return {}


class ClipRow(ctk.CTkFrame):
    def __init__(self, parent, index: int, path: Path,
                 on_remove: Callable[[int], None],
                 on_move: Callable[[int, int], None],
                 is_first: bool, is_last: bool,
                 show_intro_badge: bool = False,
                 show_outro_badge: bool = False,
                 **kwargs):
        super().__init__(parent, fg_color=C["card"], corner_radius=6, **kwargs)
        self._index = index
        self._path = path

        num_lbl = ctk.CTkLabel(
            self, text=f"{index+1:>3}.",
            font=ctk.CTkFont(size=11),
            text_color=C["muted"], width=36,
        )
        num_lbl.pack(side="left", padx=(8, 4))

        name_lbl = ctk.CTkLabel(
            self, text=path.name,
            font=ctk.CTkFont(size=12),
            text_color=C["text"],
            anchor="w",
        )
        name_lbl.pack(side="left", expand=True, fill="x", padx=(0, 4))

        if show_intro_badge:
            ctk.CTkLabel(
                self, text="🎬 Intro",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=C["emerald"],
            ).pack(side="left", padx=(0, 6))
        elif show_outro_badge:
            ctk.CTkLabel(
                self, text="🎬 Outro",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=C["emerald"],
            ).pack(side="left", padx=(0, 6))

        self._meta_lbl = ctk.CTkLabel(
            self, text="…",
            font=ctk.CTkFont(size=10),
            text_color=C["text2"], width=130,
        )
        self._meta_lbl.pack(side="left", padx=(0, 8))

        remove_btn = ctk.CTkButton(
            self, text="✕", width=24, height=24,
            fg_color="transparent",
            text_color=C["error"],
            hover_color=C["card2"],
            font=ctk.CTkFont(size=11),
            command=lambda: on_remove(index),
        )
        remove_btn.pack(side="right", padx=(0, 6))

        dn_btn = ctk.CTkButton(
            self, text="↓", width=24, height=24,
            fg_color="transparent",
            text_color=C["text2"] if not is_last else C["muted"],
            hover_color=C["card2"],
            font=ctk.CTkFont(size=13),
            state="normal" if not is_last else "disabled",
            command=lambda: on_move(index, index + 1),
        )
        dn_btn.pack(side="right", padx=(0, 2))

        up_btn = ctk.CTkButton(
            self, text="↑", width=24, height=24,
            fg_color="transparent",
            text_color=C["text2"] if not is_first else C["muted"],
            hover_color=C["card2"],
            font=ctk.CTkFont(size=13),
            state="normal" if not is_first else "disabled",
            command=lambda: on_move(index, index - 1),
        )
        up_btn.pack(side="right", padx=(0, 2))

        # Probe metadata in background thread
        import threading
        threading.Thread(target=self._load_meta, daemon=True).start()

    def _load_meta(self) -> None:
        is_photo = self._path.suffix.lower() in IMAGE_EXTENSIONS
        meta = _probe_clip(self._path)
        if meta:
            w = meta.get("width", 0)
            h = meta.get("height", 0)
            if is_photo:
                label = f"{w}×{h}  📷 Photo"
            else:
                dur  = meta.get("duration", 0)
                mins = int(dur // 60)
                secs = int(dur % 60)
                label = f"{w}×{h}  {mins}:{secs:02d}"
        else:
            label = "📷 Photo" if is_photo else "—"
        try:
            self.after(0, lambda: self._meta_lbl.configure(text=label))
        except Exception:
            pass


class QueuePanel(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._clips: list[Path] = []
        self._page = 0
        self._pin_intro = False
        self._pin_outro = False
        self._build()

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            header, text="Clip Queue",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C["text2"],
        ).pack(side="left")

        self._count_lbl = ctk.CTkLabel(
            header, text="",
            font=ctk.CTkFont(size=11),
            text_color=C["muted"],
        )
        self._count_lbl.pack(side="left", padx=8)

        self._clear_btn = ctk.CTkButton(
            header, text="Clear All",
            fg_color="transparent",
            text_color=C["error"],
            hover_color=C["card"],
            width=70, height=24,
            font=ctk.CTkFont(size=11),
            command=self.clear,
        )
        self._clear_btn.pack(side="right")

        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color=C["bg2"], corner_radius=8,
        )
        self._scroll.pack(fill="both", expand=True)

        # Pagination bar
        pager = ctk.CTkFrame(self, fg_color="transparent")
        pager.pack(fill="x", pady=(4, 0))

        self._prev_btn = ctk.CTkButton(
            pager, text="◀ Prev", width=80, height=24,
            fg_color=C["card"], text_color=C["text2"],
            hover_color=C["card2"],
            font=ctk.CTkFont(size=11),
            command=self._prev_page,
        )
        self._prev_btn.pack(side="left")

        self._page_lbl = ctk.CTkLabel(
            pager, text="", font=ctk.CTkFont(size=11),
            text_color=C["text2"],
        )
        self._page_lbl.pack(side="left", padx=12)

        self._next_btn = ctk.CTkButton(
            pager, text="Next ▶", width=80, height=24,
            fg_color=C["card"], text_color=C["text2"],
            hover_color=C["card2"],
            font=ctk.CTkFont(size=11),
            command=self._next_page,
        )
        self._next_btn.pack(side="left")

    # ── Public API ───────────────────────────────────────────────────────────

    def set_clips(self, clips: list[Path]) -> None:
        self._clips = list(clips)
        self._page = 0
        self._render_page()

    def get_clips(self) -> list[Path]:
        return list(self._clips)

    def set_pins(self, pin_intro: bool, pin_outro: bool) -> None:
        self._pin_intro = pin_intro
        self._pin_outro = pin_outro
        self._render_page()

    def clear(self) -> None:
        self._clips = []
        self._page = 0
        self._render_page()

    # ── Private ──────────────────────────────────────────────────────────────

    def _remove_clip(self, index: int) -> None:
        if 0 <= index < len(self._clips):
            self._clips.pop(index)
            self._render_page()

    def _move_clip(self, from_idx: int, to_idx: int) -> None:
        if 0 <= from_idx < len(self._clips) and 0 <= to_idx < len(self._clips):
            clip = self._clips.pop(from_idx)
            self._clips.insert(to_idx, clip)
            # Keep the moved clip visible by jumping to its page
            self._page = to_idx // PAGE_SIZE
            self._render_page()

    def _render_page(self) -> None:
        for widget in self._scroll.winfo_children():
            widget.destroy()

        total = len(self._clips)
        self._count_lbl.configure(
            text=f"({total} clips)" if total else ""
        )

        if total == 0:
            ctk.CTkLabel(
                self._scroll,
                text="No clips loaded yet.\nDrop a folder above to begin.",
                text_color=C["muted"],
                font=ctk.CTkFont(size=12),
                justify="center",
            ).pack(pady=30)
            self._page_lbl.configure(text="")
            self._prev_btn.configure(state="disabled")
            self._next_btn.configure(state="disabled")
            return

        start = self._page * PAGE_SIZE
        end   = min(start + PAGE_SIZE, total)

        for i, clip in enumerate(self._clips[start:end], start=start):
            is_intro = self._pin_intro and i == 0
            is_outro = self._pin_outro and i == total - 1 and total >= (3 if self._pin_intro else 2)
            row = ClipRow(
                self._scroll, i, clip,
                on_remove=self._remove_clip,
                on_move=self._move_clip,
                is_first=(i == 0),
                is_last=(i == total - 1),
                show_intro_badge=is_intro,
                show_outro_badge=is_outro,
            )
            row.pack(fill="x", pady=2, padx=2)

        max_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        self._page_lbl.configure(
            text=f"Page {self._page + 1} / {max_pages}  "
                 f"(showing {start+1}–{end} of {total})"
        )
        self._prev_btn.configure(state="normal" if self._page > 0 else "disabled")
        self._next_btn.configure(
            state="normal" if self._page < max_pages - 1 else "disabled"
        )

    def _prev_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._render_page()

    def _next_page(self) -> None:
        total = len(self._clips)
        max_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
        if self._page < max_pages - 1:
            self._page += 1
            self._render_page()
