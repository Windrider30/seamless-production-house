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
    SLIDESHOW_RESOLUTIONS, TEXT_COLORS, TEXT_POSITIONS,
    TRANSITION_STYLES, OUTPUT_PRESETS, WATERMARK_POSITIONS,
    available_fonts,
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

        # ── Section: Intro / Outro Text ──────────────────────────────────
        self._section("INTRO / OUTRO TEXT")

        ctk.CTkLabel(
            self, text="Leave blank for no text overlay.",
            font=ctk.CTkFont(size=10), text_color=C["muted"], anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 6))

        _label(self, "Intro Text").pack(fill="x", padx=12, pady=(0, 2))
        self._intro_text_entry = ctk.CTkEntry(
            self, placeholder_text="e.g.  Opening Title",
            fg_color=C["card"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=12),
        )
        self._intro_text_entry.pack(fill="x", **pad)

        _label(self, "Outro Text").pack(fill="x", padx=12, pady=(0, 2))
        self._outro_text_entry = ctk.CTkEntry(
            self, placeholder_text="e.g.  Thanks for watching",
            fg_color=C["card"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=12),
        )
        self._outro_text_entry.pack(fill="x", **pad)

        # Font picker
        _label(self, "Font").pack(fill="x", padx=12, pady=(0, 2))
        font_row = ctk.CTkFrame(self, fg_color="transparent")
        font_row.pack(fill="x", padx=12, pady=(0, 10))

        self._fonts = available_fonts()           # [(name, path), ...]
        font_names = [f[0] for f in self._fonts] or ["(no system fonts found)"]
        self._font_var = ctk.StringVar(value=font_names[0])
        self._font_dd = ctk.CTkComboBox(
            font_row, values=font_names,
            variable=self._font_var,
            fg_color=C["card"], button_color=C["emerald"],
            border_color=C["border"], dropdown_fg_color=C["card2"],
            text_color=C["text"], font=ctk.CTkFont(size=12),
        )
        self._font_dd.pack(side="left", expand=True, fill="x", padx=(0, 6))

        ctk.CTkButton(
            font_row, text="Browse…", width=72, height=28,
            fg_color=C["card2"], text_color=C["text"],
            hover_color=C["border"],
            font=ctk.CTkFont(size=11),
            command=self._browse_font,
        ).pack(side="right")

        # Font size
        size_row = ctk.CTkFrame(self, fg_color="transparent")
        size_row.pack(fill="x", padx=12, pady=(0, 4))
        _label(size_row, "Font Size").pack(side="left")
        self._font_size_lbl = ctk.CTkLabel(
            size_row, text="60",
            font=ctk.CTkFont(size=11), text_color=C["emerald"], width=30,
        )
        self._font_size_lbl.pack(side="right")

        self._font_size_slider = ctk.CTkSlider(
            self, from_=20, to=120, number_of_steps=100,
            button_color=C["emerald"], button_hover_color=C["emerald_lt"],
            progress_color=C["emerald_dk"], fg_color=C["card"],
            command=lambda v: self._font_size_lbl.configure(text=str(int(v))),
        )
        self._font_size_slider.set(60)
        self._font_size_slider.pack(fill="x", padx=12, pady=(0, 8))

        # Color + Position on one row
        cp_row = ctk.CTkFrame(self, fg_color="transparent")
        cp_row.pack(fill="x", padx=12, pady=(0, 10))

        color_col = ctk.CTkFrame(cp_row, fg_color="transparent")
        color_col.pack(side="left", expand=True, fill="x", padx=(0, 6))
        _label(color_col, "Color").pack(anchor="w")
        self._text_color_var = ctk.StringVar(value="White")
        ctk.CTkComboBox(
            color_col, values=list(TEXT_COLORS.keys()),
            variable=self._text_color_var,
            fg_color=C["card"], button_color=C["emerald"],
            border_color=C["border"], dropdown_fg_color=C["card2"],
            text_color=C["text"], font=ctk.CTkFont(size=12),
        ).pack(fill="x")

        pos_col = ctk.CTkFrame(cp_row, fg_color="transparent")
        pos_col.pack(side="right", expand=True, fill="x")
        _label(pos_col, "Position").pack(anchor="w")
        self._text_pos_var = ctk.StringVar(value="Center")
        ctk.CTkComboBox(
            pos_col, values=TEXT_POSITIONS,
            variable=self._text_pos_var,
            fg_color=C["card"], button_color=C["emerald"],
            border_color=C["border"], dropdown_fg_color=C["card2"],
            text_color=C["text"], font=ctk.CTkFont(size=12),
        ).pack(fill="x")

        # Visible-for duration
        dur_row = ctk.CTkFrame(self, fg_color="transparent")
        dur_row.pack(fill="x", padx=12, pady=(0, 4))
        _label(dur_row, "Visible for").pack(side="left")
        self._text_dur_lbl = ctk.CTkLabel(
            dur_row, text="3.0 s",
            font=ctk.CTkFont(size=11), text_color=C["emerald"], width=42,
        )
        self._text_dur_lbl.pack(side="right")

        self._text_dur_slider = ctk.CTkSlider(
            self, from_=0.5, to=15.0, number_of_steps=145,
            button_color=C["emerald"], button_hover_color=C["emerald_lt"],
            progress_color=C["emerald_dk"], fg_color=C["card"],
            command=lambda v: self._text_dur_lbl.configure(
                text=f"{v:.1f} s"),
        )
        self._text_dur_slider.set(3.0)
        self._text_dur_slider.pack(fill="x", padx=12, pady=(0, 10))

        # ── Section: Transitions ─────────────────────────────────────────
        self._section("TRANSITIONS")

        ctk.CTkLabel(
            self, text='Override the genre\'s default transition. "Auto" uses the genre setting.',
            font=ctk.CTkFont(size=10), text_color=C["muted"],
            wraplength=220, justify="left", anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 6))

        _label(self, "Transition Style").pack(fill="x", padx=12, pady=(0, 2))
        self._trans_style_var = ctk.StringVar(value="Auto (genre default)")
        ctk.CTkComboBox(
            self, values=list(TRANSITION_STYLES.keys()),
            variable=self._trans_style_var,
            fg_color=C["card"], button_color=C["emerald"],
            border_color=C["border"], dropdown_fg_color=C["card2"],
            text_color=C["text"], font=ctk.CTkFont(size=12),
        ).pack(fill="x", **pad)

        # Duration override
        tdur_row = ctk.CTkFrame(self, fg_color="transparent")
        tdur_row.pack(fill="x", padx=12, pady=(0, 2))
        _label(tdur_row, "Transition Duration").pack(side="left")

        self._trans_auto_var = ctk.BooleanVar(value=True)
        self._trans_auto_chk = ctk.CTkCheckBox(
            tdur_row, text="Auto",
            variable=self._trans_auto_var,
            fg_color=C["emerald"], hover_color=C["emerald_dk"],
            border_color=C["border"],
            text_color=C["text2"], font=ctk.CTkFont(size=10),
            width=60,
            command=self._on_trans_auto_toggle,
        )
        self._trans_auto_chk.pack(side="right")

        self._trans_dur_lbl = ctk.CTkLabel(
            self, text="1.5 s",
            font=ctk.CTkFont(size=11), text_color=C["muted"], anchor="e",
        )
        self._trans_dur_lbl.pack(fill="x", padx=12, pady=(0, 2))

        self._trans_dur_slider = ctk.CTkSlider(
            self, from_=0.2, to=4.0, number_of_steps=76,
            button_color=C["emerald"], button_hover_color=C["emerald_lt"],
            progress_color=C["emerald_dk"], fg_color=C["card"],
            state="disabled",
            command=self._on_trans_dur_slide,
        )
        self._trans_dur_slider.set(1.5)
        self._trans_dur_slider.pack(fill="x", padx=12, pady=(0, 10))

        # ── Section: Effects ─────────────────────────────────────────────
        self._section("EFFECTS")

        self._ken_burns_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self, text="Ken Burns  (photos only)",
            variable=self._ken_burns_var,
            fg_color=C["emerald"], hover_color=C["emerald_dk"],
            border_color=C["border"],
            text_color=C["text2"],
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=12, pady=(0, 2))
        ctk.CTkLabel(
            self, text="Slow zoom / pan on still images — cycles 4 styles",
            font=ctk.CTkFont(size=10), text_color=C["muted"], anchor="w",
        ).pack(fill="x", padx=30, pady=(0, 10))

        # ── Section: Watermark ───────────────────────────────────────────
        self._section("WATERMARK")

        self._wm_enable_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self, text="Enable Watermark / Logo",
            variable=self._wm_enable_var,
            fg_color=C["emerald"], hover_color=C["emerald_dk"],
            border_color=C["border"],
            text_color=C["text2"],
            font=ctk.CTkFont(size=11),
            command=self._on_wm_toggle,
        ).pack(anchor="w", padx=12, pady=(0, 6))

        # File row
        self._wm_path: str = ""
        wm_file_row = ctk.CTkFrame(self, fg_color="transparent")
        wm_file_row.pack(fill="x", padx=12, pady=(0, 6))
        self._wm_lbl = ctk.CTkLabel(
            wm_file_row, text="No file selected",
            font=ctk.CTkFont(size=10), text_color=C["muted"],
            anchor="w",
        )
        self._wm_lbl.pack(side="left", expand=True, fill="x")
        self._wm_browse_btn = ctk.CTkButton(
            wm_file_row, text="Browse…", width=72, height=26,
            fg_color=C["card2"], text_color=C["text"],
            hover_color=C["border"],
            font=ctk.CTkFont(size=11),
            command=self._browse_watermark,
            state="disabled",
        )
        self._wm_browse_btn.pack(side="right")

        _label(self, "Position").pack(fill="x", padx=12, pady=(0, 2))
        self._wm_pos_var = ctk.StringVar(value=WATERMARK_POSITIONS[0])
        self._wm_pos_dd = ctk.CTkComboBox(
            self, values=WATERMARK_POSITIONS,
            variable=self._wm_pos_var,
            fg_color=C["card"], button_color=C["emerald"],
            border_color=C["border"], dropdown_fg_color=C["card2"],
            text_color=C["text"], font=ctk.CTkFont(size=12),
            state="disabled",
        )
        self._wm_pos_dd.pack(fill="x", **pad)

        op_row = ctk.CTkFrame(self, fg_color="transparent")
        op_row.pack(fill="x", padx=12, pady=(0, 2))
        _label(op_row, "Opacity").pack(side="left")
        self._wm_op_lbl = ctk.CTkLabel(
            op_row, text="80%",
            font=ctk.CTkFont(size=11), text_color=C["muted"], width=36,
        )
        self._wm_op_lbl.pack(side="right")
        self._wm_op_slider = ctk.CTkSlider(
            self, from_=10, to=100, number_of_steps=90,
            button_color=C["emerald"], button_hover_color=C["emerald_lt"],
            progress_color=C["emerald_dk"], fg_color=C["card"],
            state="disabled",
            command=lambda v: self._wm_op_lbl.configure(text=f"{int(v)}%"),
        )
        self._wm_op_slider.set(80)
        self._wm_op_slider.pack(fill="x", padx=12, pady=(0, 4))

        sz_row = ctk.CTkFrame(self, fg_color="transparent")
        sz_row.pack(fill="x", padx=12, pady=(0, 2))
        _label(sz_row, "Size  (% of video width)").pack(side="left")
        self._wm_sz_lbl = ctk.CTkLabel(
            sz_row, text="15%",
            font=ctk.CTkFont(size=11), text_color=C["muted"], width=36,
        )
        self._wm_sz_lbl.pack(side="right")
        self._wm_sz_slider = ctk.CTkSlider(
            self, from_=5, to=40, number_of_steps=35,
            button_color=C["emerald"], button_hover_color=C["emerald_lt"],
            progress_color=C["emerald_dk"], fg_color=C["card"],
            state="disabled",
            command=lambda v: self._wm_sz_lbl.configure(text=f"{int(v)}%"),
        )
        self._wm_sz_slider.set(15)
        self._wm_sz_slider.pack(fill="x", padx=12, pady=(0, 10))

        # ── Section: Photo Slideshow ──────────────────────────────────────
        self._section("PHOTO SLIDESHOW")

        ctk.CTkLabel(
            self, text='Only used when Content Type is "Photo Slideshow".',
            font=ctk.CTkFont(size=10), text_color=C["muted"],
            wraplength=220, justify="left", anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 6))

        _label(self, "Canvas Resolution").pack(fill="x", padx=12, pady=(0, 2))
        slide_res_keys = list(SLIDESHOW_RESOLUTIONS.keys())
        self._slide_res_var = ctk.StringVar(value=slide_res_keys[0])
        ctk.CTkComboBox(
            self, values=slide_res_keys,
            variable=self._slide_res_var,
            fg_color=C["card"], button_color=C["emerald"],
            border_color=C["border"], dropdown_fg_color=C["card2"],
            text_color=C["text"], font=ctk.CTkFont(size=12),
        ).pack(fill="x", **pad)

        hold_row = ctk.CTkFrame(self, fg_color="transparent")
        hold_row.pack(fill="x", padx=12, pady=(0, 4))
        _label(hold_row, "Photo Hold Duration").pack(side="left")
        self._slide_hold_lbl = ctk.CTkLabel(
            hold_row, text="5.0 s",
            font=ctk.CTkFont(size=11), text_color=C["emerald"], width=42,
        )
        self._slide_hold_lbl.pack(side="right")

        self._slide_hold_slider = ctk.CTkSlider(
            self, from_=1.0, to=30.0, number_of_steps=290,
            button_color=C["emerald"], button_hover_color=C["emerald_lt"],
            progress_color=C["emerald_dk"], fg_color=C["card"],
            command=lambda v: self._slide_hold_lbl.configure(
                text=f"{v:.1f} s"),
        )
        self._slide_hold_slider.set(5.0)
        self._slide_hold_slider.pack(fill="x", padx=12, pady=(0, 10))

        # ── Section: Format ──────────────────────────────────────────────
        self._section("FORMAT")

        _label(self, "Preset").pack(fill="x", padx=12, pady=(0, 2))
        preset_keys = list(OUTPUT_PRESETS.keys())
        self._preset_var = ctk.StringVar(value=preset_keys[0])
        ctk.CTkComboBox(
            self, values=preset_keys,
            variable=self._preset_var,
            fg_color=C["card"], button_color=C["emerald"],
            border_color=C["border"], dropdown_fg_color=C["card2"],
            text_color=C["text"], font=ctk.CTkFont(size=12),
            command=self._on_preset_change,
        ).pack(fill="x", **pad)

        _label(self, "Resolution").pack(fill="x", padx=12, pady=(0, 2))
        res_keys = list(RESOLUTION_OPTIONS.keys())
        self._res_var = ctk.StringVar(value=res_keys[0])
        self._res_dd = ctk.CTkComboBox(
            self, values=res_keys,
            variable=self._res_var,
            fg_color=C["card"], button_color=C["emerald"],
            border_color=C["border"],
            dropdown_fg_color=C["card2"],
            text_color=C["text"],
            font=ctk.CTkFont(size=12),
            command=lambda _: self._preset_var.set("Custom"),
        )
        self._res_dd.pack(fill="x", **pad)

        _label(self, "Frame Rate").pack(fill="x", padx=12, pady=(0, 2))
        fps_keys = list(FPS_OPTIONS.keys())
        self._fps_var = ctk.StringVar(value=fps_keys[0])
        self._fps_dd = ctk.CTkComboBox(
            self, values=fps_keys,
            variable=self._fps_var,
            fg_color=C["card"], button_color=C["emerald"],
            border_color=C["border"],
            dropdown_fg_color=C["card2"],
            text_color=C["text"],
            font=ctk.CTkFont(size=12),
            command=lambda _: self._preset_var.set("Custom"),
        )
        self._fps_dd.pack(fill="x", **pad)

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

    def _browse_font(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Font File",
            filetypes=[("Font files", "*.ttf *.otf *.ttc"), ("All files", "*.*")],
        )
        if path:
            name = Path(path).stem
            # Add to the dropdown and select it
            self._fonts.append((name, path))
            names = [f[0] for f in self._fonts]
            self._font_dd.configure(values=names)
            self._font_var.set(name)

    def _on_trans_auto_toggle(self) -> None:
        if self._trans_auto_var.get():
            self._trans_dur_slider.configure(state="disabled")
            self._trans_dur_lbl.configure(text_color=C["muted"])
        else:
            self._trans_dur_slider.configure(state="normal")
            self._trans_dur_lbl.configure(text_color=C["emerald"])

    def _on_trans_dur_slide(self, v: float) -> None:
        self._trans_dur_lbl.configure(text=f"{v:.1f} s")

    def _on_wm_toggle(self) -> None:
        state = "normal" if self._wm_enable_var.get() else "disabled"
        color = C["emerald"] if self._wm_enable_var.get() else C["muted"]
        self._wm_browse_btn.configure(state=state)
        self._wm_pos_dd.configure(state=state)
        self._wm_op_slider.configure(state=state)
        self._wm_sz_slider.configure(state=state)
        self._wm_op_lbl.configure(text_color=color)
        self._wm_sz_lbl.configure(text_color=color)

    def _browse_watermark(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select Watermark / Logo",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
        )
        if path:
            self._wm_path = path
            from pathlib import Path as _P
            self._wm_lbl.configure(
                text=_P(path).name, text_color=C["text2"],
            )

    def _on_preset_change(self, value: str) -> None:
        preset = OUTPUT_PRESETS.get(value, {})
        if not preset:
            return
        if "res" in preset:
            self._res_var.set(preset["res"])
        if "fps" in preset:
            self._fps_var.set(preset["fps"])

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

    @property
    def intro_text(self) -> str:
        return self._intro_text_entry.get().strip()

    @property
    def outro_text(self) -> str:
        return self._outro_text_entry.get().strip()

    @property
    def text_font_path(self) -> str:
        selected = self._font_var.get()
        for name, path in self._fonts:
            if name == selected:
                return path
        return ""

    @property
    def text_size(self) -> int:
        return int(self._font_size_slider.get())

    @property
    def text_color(self) -> str:
        return TEXT_COLORS.get(self._text_color_var.get(), "white")

    @property
    def text_position(self) -> str:
        return self._text_pos_var.get()

    @property
    def text_duration(self) -> float:
        return round(self._text_dur_slider.get(), 1)

    @property
    def slideshow_resolution(self) -> tuple[int, int] | None:
        return SLIDESHOW_RESOLUTIONS.get(self._slide_res_var.get())

    @property
    def slideshow_hold(self) -> float:
        return round(self._slide_hold_slider.get(), 1)

    @property
    def transition_style(self) -> str:
        return self._trans_style_var.get()

    @property
    def transition_duration(self) -> float:
        """Returns 0.0 when Auto is checked (renderer uses genre default)."""
        if self._trans_auto_var.get():
            return 0.0
        return round(self._trans_dur_slider.get(), 2)

    @property
    def ken_burns(self) -> bool:
        return self._ken_burns_var.get()

    @property
    def watermark_path(self) -> str:
        return self._wm_path if self._wm_enable_var.get() else ""

    @property
    def watermark_position(self) -> str:
        return self._wm_pos_var.get()

    @property
    def watermark_opacity(self) -> float:
        return round(self._wm_op_slider.get() / 100, 2)

    @property
    def watermark_size_pct(self) -> int:
        return int(self._wm_sz_slider.get())
