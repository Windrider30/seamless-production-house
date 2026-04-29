"""Genre, content type, output path, resolution, and FPS settings."""
from __future__ import annotations

import os
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from src.config import (
    APP_DIR, C, GENRE_NAMES, GENRES,
    CONTENT_TYPE_NAMES, CONTENT_TYPES,
    RESOLUTION_OPTIONS, FPS_OPTIONS,
)


def _label(parent, text: str, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent, text=text,
        font=ctk.CTkFont(size=11),
        text_color=C["text2"],
        anchor="w", **kw,
    )


class SettingsPanel(ctk.CTkScrollableFrame):
    def __init__(self, parent, on_pin_change=None, **kwargs):
        super().__init__(parent, fg_color=C["bg2"], corner_radius=10, **kwargs)
        default_out = APP_DIR / "output"
        default_out.mkdir(exist_ok=True)
        self._output_dir = default_out
        self._on_pin_change = on_pin_change
        self._build()

    def _build(self) -> None:
        pad = {"padx": 12, "pady": (0, 10)}

        # ── Section: Content ─────────────────────────────────────────────
        self._section("CONTENT")

        _label(self, "Content Type").pack(fill="x", padx=12, pady=(0, 2))
        self._content_type_var = ctk.StringVar(value=CONTENT_TYPE_NAMES[0])
        self._content_dd = ctk.CTkComboBox(
            self, values=CONTENT_TYPE_NAMES,
            variable=self._content_type_var,
            fg_color=C["card"], button_color=C["emerald"],
            border_color=C["border"],
            dropdown_fg_color=C["card2"],
            text_color=C["text"],
            font=ctk.CTkFont(size=12),
            command=self._on_content_change,
        )
        self._content_dd.pack(fill="x", **pad)

        self._content_desc = ctk.CTkLabel(
            self, text=CONTENT_TYPES[CONTENT_TYPE_NAMES[0]]["desc"],
            font=ctk.CTkFont(size=10), text_color=C["muted"],
            wraplength=220, justify="left", anchor="w",
        )
        self._content_desc.pack(fill="x", padx=12, pady=(0, 12))

        # ── Section: Genre ───────────────────────────────────────────────
        self._section("GENRE")

        _label(self, "Music Genre").pack(fill="x", padx=12, pady=(0, 2))
        self._genre_var = ctk.StringVar(value=GENRE_NAMES[0])
        self._genre_dd = ctk.CTkComboBox(
            self, values=GENRE_NAMES,
            variable=self._genre_var,
            fg_color=C["card"], button_color=C["emerald"],
            border_color=C["border"],
            dropdown_fg_color=C["card2"],
            text_color=C["text"],
            font=ctk.CTkFont(size=12),
            command=self._on_genre_change,
        )
        self._genre_dd.pack(fill="x", **pad)

        self._genre_desc = ctk.CTkLabel(
            self, text=GENRES[GENRE_NAMES[0]]["desc"],
            font=ctk.CTkFont(size=10), text_color=C["muted"],
            wraplength=220, justify="left", anchor="w",
        )
        self._genre_desc.pack(fill="x", padx=12, pady=(0, 12))

        # transition badge
        self._trans_badge = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=C["emerald"],
            anchor="w",
        )
        self._trans_badge.pack(fill="x", padx=12, pady=(0, 12))
        self._refresh_badge(GENRE_NAMES[0])

        # ── Section: Output ──────────────────────────────────────────────
        self._section("OUTPUT")

        _label(self, "Output Folder").pack(fill="x", padx=12, pady=(0, 2))
        folder_row = ctk.CTkFrame(self, fg_color="transparent")
        folder_row.pack(fill="x", padx=12, pady=(0, 4))

        self._folder_lbl = ctk.CTkLabel(
            folder_row,
            text=self._short_path(self._output_dir),
            font=ctk.CTkFont(size=11),
            text_color=C["text2"], anchor="w",
        )
        self._folder_lbl.pack(side="left", expand=True, fill="x")

        ctk.CTkButton(
            folder_row, text="…", width=32, height=26,
            fg_color=C["card"], text_color=C["emerald"],
            hover_color=C["card2"],
            command=self._browse_output,
        ).pack(side="right")

        _label(self, "Filename").pack(fill="x", padx=12, pady=(4, 2))
        self._filename_entry = ctk.CTkEntry(
            self,
            placeholder_text="seamless_output.mp4",
            fg_color=C["card"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=12),
        )
        self._filename_entry.insert(0, "seamless_output.mp4")
        self._filename_entry.pack(fill="x", **pad)

        self._loop_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self, text="Loop clips to fill music",
            variable=self._loop_var,
            fg_color=C["emerald"], hover_color=C["emerald_dk"],
            border_color=C["border"],
            text_color=C["text2"],
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=12, pady=(0, 4))
        ctk.CTkLabel(
            self, text="Repeat your clips until the music ends",
            font=ctk.CTkFont(size=10), text_color=C["muted"],
            anchor="w",
        ).pack(fill="x", padx=30, pady=(0, 6))

        self._pin_intro_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self, text="First clip is intro (play once)",
            variable=self._pin_intro_var,
            fg_color=C["emerald"], hover_color=C["emerald_dk"],
            border_color=C["border"],
            text_color=C["text2"],
            font=ctk.CTkFont(size=11),
            command=self._on_pins_changed,
        ).pack(anchor="w", padx=28, pady=(0, 2))

        self._pin_outro_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self, text="Last clip is outro (play once)",
            variable=self._pin_outro_var,
            fg_color=C["emerald"], hover_color=C["emerald_dk"],
            border_color=C["border"],
            text_color=C["text2"],
            font=ctk.CTkFont(size=11),
            command=self._on_pins_changed,
        ).pack(anchor="w", padx=28, pady=(0, 10))

        # ── Section: Format ──────────────────────────────────────────────
        self._section("FORMAT")

        _label(self, "Resolution").pack(fill="x", padx=12, pady=(0, 2))
        res_keys = list(RESOLUTION_OPTIONS.keys())
        self._res_var = ctk.StringVar(value=res_keys[0])
        ctk.CTkComboBox(
            self, values=res_keys,
            variable=self._res_var,
            fg_color=C["card"], button_color=C["emerald"],
            border_color=C["border"],
            dropdown_fg_color=C["card2"],
            text_color=C["text"],
            font=ctk.CTkFont(size=12),
        ).pack(fill="x", **pad)

        _label(self, "Frame Rate").pack(fill="x", padx=12, pady=(0, 2))
        fps_keys = list(FPS_OPTIONS.keys())
        self._fps_var = ctk.StringVar(value=fps_keys[0])
        ctk.CTkComboBox(
            self, values=fps_keys,
            variable=self._fps_var,
            fg_color=C["card"], button_color=C["emerald"],
            border_color=C["border"],
            dropdown_fg_color=C["card2"],
            text_color=C["text"],
            font=ctk.CTkFont(size=12),
        ).pack(fill="x", **pad)

    def _section(self, title: str) -> None:
        ctk.CTkLabel(
            self, text=title,
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=C["muted"], anchor="w",
        ).pack(fill="x", padx=12, pady=(14, 2))
        ctk.CTkFrame(self, height=1, fg_color=C["border"]).pack(
            fill="x", padx=12, pady=(0, 8)
        )

    def _short_path(self, p: Path) -> str:
        try:
            return str(p).replace(str(Path.home()), "~")
        except Exception:
            return str(p)

    def _browse_output(self) -> None:
        folder = filedialog.askdirectory(title="Select Output Folder",
                                         initialdir=str(self._output_dir))
        if folder:
            self._output_dir = Path(folder)
            self._folder_lbl.configure(text=self._short_path(self._output_dir))

    def _on_pins_changed(self) -> None:
        if self._on_pin_change:
            self._on_pin_change(self._pin_intro_var.get(), self._pin_outro_var.get())

    def _on_genre_change(self, value: str) -> None:
        cfg = GENRES.get(value, {})
        self._genre_desc.configure(text=cfg.get("desc", ""))
        self._refresh_badge(value)

    def _on_content_change(self, value: str) -> None:
        cfg = CONTENT_TYPES.get(value, {})
        self._content_desc.configure(text=cfg.get("desc", ""))

    def _refresh_badge(self, genre: str) -> None:
        cfg = GENRES.get(genre, {})
        t = cfg.get("transition", "cut")
        icons = {"morph": "⟳ Morph", "crossfade": "◌ Crossfade", "cut": "✂ Hard Cut"}
        lcut = "  +  L-Cut" if cfg.get("l_cut") else ""
        self._trans_badge.configure(text=f"{icons.get(t, t)}{lcut}")

    # ── Read-back API ────────────────────────────────────────────────────────

    @property
    def genre(self) -> str:
        return self._genre_var.get()

    @property
    def content_type(self) -> str:
        return self._content_type_var.get()

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    @property
    def filename(self) -> str:
        name = self._filename_entry.get().strip() or "seamless_output.mp4"
        if not name.endswith(".mp4"):
            name += ".mp4"
        return name

    @property
    def resolution(self) -> tuple[int, int] | None:
        return RESOLUTION_OPTIONS.get(self._res_var.get())

    @property
    def fps(self) -> int | None:
        return FPS_OPTIONS.get(self._fps_var.get())

    @property
    def loop_clips(self) -> bool:
        return self._loop_var.get()

    @property
    def pin_intro(self) -> bool:
        return self._pin_intro_var.get()

    @property
    def pin_outro(self) -> bool:
        return self._pin_outro_var.get()
