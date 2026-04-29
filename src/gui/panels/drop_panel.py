"""Drag-and-drop zone for clips folder and music folder."""
from __future__ import annotations

import os
from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from src.config import C, VIDEO_EXTENSIONS, IMAGE_EXTENSIONS, CLIP_EXTENSIONS, AUDIO_EXTENSIONS

try:
    from tkinterdnd2 import DND_FILES
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False


def _parse_drop(data: str, widget) -> list[str]:
    """Convert raw tkdnd event data to a list of clean path strings."""
    try:
        return widget.tk.splitlist(data)
    except Exception:
        return [data]


def _collect_files(raw_paths: list[str], extensions: set[str]) -> list[Path]:
    result: list[Path] = []
    for raw in raw_paths:
        p = Path(raw)
        if p.is_dir():
            for ext in extensions:
                result.extend(p.glob(f"*{ext}"))
                result.extend(p.glob(f"*{ext.upper()}"))
        elif p.suffix.lower() in extensions:
            result.append(p)
    return sorted(set(result))


class DropZone(ctk.CTkFrame):
    """
    A single drop target.
    extensions: set of file extensions to accept.
    on_files: called with list[Path] when files are received.
    label:  display label inside the zone.
    icon:   emoji shown large.
    """
    def __init__(self, parent, label: str, icon: str,
                 extensions: set[str],
                 on_files: Callable[[list[Path]], None],
                 **kwargs):
        super().__init__(parent,
                         fg_color=C["card"],
                         border_color=C["border"],
                         border_width=2,
                         corner_radius=12,
                         **kwargs)
        self._extensions = extensions
        self._on_files = on_files
        self._loaded_count = 0

        self._icon_lbl = ctk.CTkLabel(
            self, text=icon,
            font=ctk.CTkFont(size=36),
            text_color=C["emerald"],
        )
        self._icon_lbl.pack(pady=(20, 4))

        self._title_lbl = ctk.CTkLabel(
            self, text=label,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=C["text"],
        )
        self._title_lbl.pack()

        self._sub_lbl = ctk.CTkLabel(
            self, text="Drag & drop a folder, or",
            font=ctk.CTkFont(size=11),
            text_color=C["text2"],
        )
        self._sub_lbl.pack(pady=(2, 0))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=(6, 20))

        ctk.CTkButton(
            btn_row, text="Browse Files",
            fg_color="transparent",
            border_color=C["emerald"],
            border_width=1,
            text_color=C["emerald"],
            hover_color=C["card2"],
            width=110, height=28,
            font=ctk.CTkFont(size=11),
            command=self._browse_files,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            btn_row, text="Browse Folder",
            fg_color="transparent",
            border_color=C["border"],
            border_width=1,
            text_color=C["text2"],
            hover_color=C["card2"],
            width=110, height=28,
            font=ctk.CTkFont(size=11),
            command=self._browse_folder,
        ).pack(side="left")

        if _DND_AVAILABLE:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
            for child in self.winfo_children():
                try:
                    child.drop_target_register(DND_FILES)
                    child.dnd_bind("<<Drop>>", self._on_drop)
                except Exception:
                    pass

    def _on_drop(self, event) -> None:
        raw = _parse_drop(event.data, self)
        files = _collect_files(raw, self._extensions)
        if files:
            self._set_count(len(files))
            self._on_files(files)

    def _browse_files(self) -> None:
        ext_list = " ".join(f"*{e}" for e in sorted(self._extensions))
        picked = filedialog.askopenfilenames(
            title="Select Files",
            filetypes=[("Supported files", ext_list), ("All files", "*.*")],
        )
        if picked:
            files = [Path(p) for p in picked]
            self._set_count(len(files))
            self._on_files(files)

    def _browse_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select Folder")
        if folder:
            files = _collect_files([folder], self._extensions)
            if files:
                self._set_count(len(files))
                self._on_files(files)

    def _set_count(self, n: int) -> None:
        self._loaded_count = n
        if self._extensions == AUDIO_EXTENSIONS:
            ext_word = "tracks"
        elif self._extensions == CLIP_EXTENSIONS:
            ext_word = "clips / photos"
        else:
            ext_word = "clips"
        self._sub_lbl.configure(
            text=f"✓  {n} {ext_word} loaded",
            text_color=C["success"],
        )
        self.configure(border_color=C["emerald"])

    def reset(self) -> None:
        self._loaded_count = 0
        self._sub_lbl.configure(text="Drag & drop a folder, or", text_color=C["text2"])
        self.configure(border_color=C["border"])


class DropPanel(ctk.CTkFrame):
    """Side-by-side clips + music drop zones."""
    def __init__(self, parent,
                 on_clips: Callable[[list[Path]], None],
                 on_music: Callable[[list[Path]], None],
                 **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.clips_zone = DropZone(
            self, label="Drop Clips & Photos Here", icon="🎬",
            extensions=CLIP_EXTENSIONS,
            on_files=on_clips,
        )
        self.clips_zone.pack(side="left", expand=True, fill="both", padx=(0, 6))

        self.music_zone = DropZone(
            self, label="Drop Music Here", icon="🎵",
            extensions=AUDIO_EXTENSIONS,
            on_files=on_music,
        )
        self.music_zone.pack(side="left", expand=True, fill="both", padx=(6, 0))
