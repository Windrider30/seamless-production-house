"""Scrollable, paginated clip queue. Handles 500+ clips without lag (Bug #15)."""
from __future__ import annotations

import subprocess
import json
import time
from pathlib import Path
from typing import Callable

import sys

import customtkinter as ctk

from src.config import C, IMAGE_EXTENSIONS, TITLE_CARDS_DIR, TITLE_CARD_BG_COLORS, TEXT_COLORS
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
        self._is_title_card = path.suffix.lower() == ".titlecard"

        num_lbl = ctk.CTkLabel(
            self, text=f"{index+1:>3}.",
            font=ctk.CTkFont(size=11),
            text_color=C["muted"], width=36,
        )
        num_lbl.pack(side="left", padx=(8, 4))

        # Title cards show their text; clips show filename
        if self._is_title_card:
            try:
                tc_data = json.loads(path.read_text(encoding="utf-8"))
                display_name = f'"{tc_data.get("text", path.stem)}"'
            except Exception:
                display_name = path.stem
        else:
            display_name = path.name

        name_lbl = ctk.CTkLabel(
            self, text=display_name,
            font=ctk.CTkFont(size=12),
            text_color=C["text"],
            anchor="w",
        )
        name_lbl.pack(side="left", expand=True, fill="x", padx=(0, 4))

        if self._is_title_card:
            ctk.CTkLabel(
                self, text="T Card",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=C["warning"],
            ).pack(side="left", padx=(0, 6))
        elif show_intro_badge:
            ctk.CTkLabel(
                self, text="Intro",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=C["emerald"],
            ).pack(side="left", padx=(0, 6))
        elif show_outro_badge:
            ctk.CTkLabel(
                self, text="Outro",
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
        if self._is_title_card:
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                dur  = float(data.get("duration", 5.0))
                label = f"Title Card  {dur:.1f}s"
            except Exception:
                label = "Title Card"
            try:
                self.after(0, lambda: self._meta_lbl.configure(text=label))
            except Exception:
                pass
            return

        is_photo = self._path.suffix.lower() in IMAGE_EXTENSIONS
        meta = _probe_clip(self._path)
        if meta:
            w = meta.get("width", 0)
            h = meta.get("height", 0)
            if is_photo:
                label = f"{w}×{h}  Photo"
            else:
                dur  = meta.get("duration", 0)
                mins = int(dur // 60)
                secs = int(dur % 60)
                label = f"{w}×{h}  {mins}:{secs:02d}"
        else:
            label = "Photo" if is_photo else "—"
        try:
            self.after(0, lambda: self._meta_lbl.configure(text=label))
        except Exception:
            pass


class QueuePanel(ctk.CTkFrame):
    def __init__(self, parent, on_add_titlecard: Callable[[Path], None] | None = None,
                 **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._clips: list[Path] = []
        self._page = 0
        self._pin_intro = False
        self._pin_outro = False
        self._on_add_titlecard = on_add_titlecard
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

        ctk.CTkButton(
            header, text="+ Title Card",
            fg_color=C["card2"], text_color=C["warning"],
            hover_color=C["border"],
            width=88, height=24,
            font=ctk.CTkFont(size=11),
            command=self._show_title_card_dialog,
        ).pack(side="right", padx=(0, 6))

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

    # ── Title card dialog ────────────────────────────────────────────────────

    def _show_title_card_dialog(self) -> None:
        dlg = ctk.CTkToplevel(self)
        dlg.title("Add Title Card")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.configure(fg_color=C["bg2"])
        dlg.grab_set()

        pad = {"padx": 14, "pady": (0, 8)}

        ctk.CTkLabel(dlg, text="Title Card Text",
                     font=ctk.CTkFont(size=11), text_color=C["text2"],
                     anchor="w").pack(fill="x", padx=14, pady=(14, 2))
        txt = ctk.CTkTextbox(dlg, height=80, fg_color=C["card"],
                             border_color=C["border"], text_color=C["text"],
                             font=ctk.CTkFont(size=13))
        txt.pack(fill="x", padx=14, pady=(0, 10))

        row1 = ctk.CTkFrame(dlg, fg_color="transparent")
        row1.pack(fill="x", padx=14, pady=(0, 8))

        # Background color
        bg_col = ctk.CTkFrame(row1, fg_color="transparent")
        bg_col.pack(side="left", expand=True, fill="x", padx=(0, 8))
        ctk.CTkLabel(bg_col, text="Background", font=ctk.CTkFont(size=11),
                     text_color=C["text2"], anchor="w").pack(anchor="w")
        bg_var = ctk.StringVar(value=list(TITLE_CARD_BG_COLORS.keys())[0])
        ctk.CTkComboBox(bg_col, values=list(TITLE_CARD_BG_COLORS.keys()),
                        variable=bg_var, fg_color=C["card"],
                        button_color=C["emerald"], border_color=C["border"],
                        dropdown_fg_color=C["card"], text_color=C["text"],
                        font=ctk.CTkFont(size=12)).pack(fill="x")

        # Text color
        tc_col = ctk.CTkFrame(row1, fg_color="transparent")
        tc_col.pack(side="right", expand=True, fill="x")
        ctk.CTkLabel(tc_col, text="Text Color", font=ctk.CTkFont(size=11),
                     text_color=C["text2"], anchor="w").pack(anchor="w")
        tc_var = ctk.StringVar(value=list(TEXT_COLORS.keys())[0])
        ctk.CTkComboBox(tc_col, values=list(TEXT_COLORS.keys()),
                        variable=tc_var, fg_color=C["card"],
                        button_color=C["emerald"], border_color=C["border"],
                        dropdown_fg_color=C["card"], text_color=C["text"],
                        font=ctk.CTkFont(size=12)).pack(fill="x")

        # Font size
        fs_row = ctk.CTkFrame(dlg, fg_color="transparent")
        fs_row.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(fs_row, text="Font Size", font=ctk.CTkFont(size=11),
                     text_color=C["text2"]).pack(side="left")
        fs_lbl = ctk.CTkLabel(fs_row, text="80", font=ctk.CTkFont(size=11),
                              text_color=C["emerald"], width=30)
        fs_lbl.pack(side="right")
        fs_slider = ctk.CTkSlider(dlg, from_=30, to=150, number_of_steps=120,
                                  button_color=C["emerald"],
                                  button_hover_color=C["emerald_lt"],
                                  progress_color=C["emerald_dk"],
                                  fg_color=C["card"],
                                  command=lambda v: fs_lbl.configure(text=str(int(v))))
        fs_slider.set(80)
        fs_slider.pack(fill="x", padx=14, pady=(0, 8))

        # Duration
        dur_row = ctk.CTkFrame(dlg, fg_color="transparent")
        dur_row.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(dur_row, text="Duration", font=ctk.CTkFont(size=11),
                     text_color=C["text2"]).pack(side="left")
        dur_lbl = ctk.CTkLabel(dur_row, text="5.0 s", font=ctk.CTkFont(size=11),
                               text_color=C["emerald"], width=42)
        dur_lbl.pack(side="right")
        dur_slider = ctk.CTkSlider(dlg, from_=1.0, to=20.0, number_of_steps=190,
                                   button_color=C["emerald"],
                                   button_hover_color=C["emerald_lt"],
                                   progress_color=C["emerald_dk"],
                                   fg_color=C["card"],
                                   command=lambda v: dur_lbl.configure(text=f"{v:.1f} s"))
        dur_slider.set(5.0)
        dur_slider.pack(fill="x", padx=14, pady=(0, 14))

        def _add() -> None:
            text = txt.get("1.0", "end").strip()
            if not text:
                return
            TITLE_CARDS_DIR.mkdir(parents=True, exist_ok=True)
            spec = {
                "text":       text,
                "bg_color":   TITLE_CARD_BG_COLORS.get(bg_var.get(), "0x000000"),
                "text_color": TEXT_COLORS.get(tc_var.get(), "white"),
                "font_size":  int(fs_slider.get()),
                "duration":   round(dur_slider.get(), 1),
            }
            tc_path = TITLE_CARDS_DIR / f"titlecard_{int(time.time() * 1000)}.titlecard"
            tc_path.write_text(json.dumps(spec), encoding="utf-8")
            self._clips.append(tc_path)
            self._render_page()
            if self._on_add_titlecard:
                self._on_add_titlecard(tc_path)
            dlg.destroy()

        ctk.CTkButton(dlg, text="Add to Queue",
                      fg_color=C["emerald"], text_color=C["bg"],
                      hover_color=C["emerald_lt"],
                      font=ctk.CTkFont(size=13, weight="bold"),
                      height=38, command=_add).pack(
            fill="x", padx=14, pady=(0, 14))

        # Centre dialog over parent
        dlg.update_idletasks()
        pw = self.winfo_toplevel().winfo_x()
        py = self.winfo_toplevel().winfo_y()
        pw2 = self.winfo_toplevel().winfo_width()
        py2 = self.winfo_toplevel().winfo_height()
        dw, dh = dlg.winfo_width(), dlg.winfo_height()
        dlg.geometry(f"+{pw + (pw2 - dw)//2}+{py + (py2 - dh)//2}")

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
