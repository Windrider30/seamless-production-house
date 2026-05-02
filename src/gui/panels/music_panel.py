"""Scrollable music playlist with per-track remove buttons."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import customtkinter as ctk

from src.config import C


class MusicPlaylistPanel(ctk.CTkFrame):
    """
    Shows the loaded music tracks as a scrollable list.
    Each row has the track filename and an X button to remove it.
    on_remove(index) is called when the user removes a track.
    """

    def __init__(self, parent,
                 on_remove: Callable[[int], None],
                 **kwargs):
        super().__init__(parent, fg_color=C["card"],
                         border_color=C["border"], border_width=1,
                         corner_radius=10, **kwargs)
        self._on_remove = on_remove
        self._tracks: list[Path] = []

        # Header row
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(8, 4))

        self._header_lbl = ctk.CTkLabel(
            hdr, text="Music Playlist  (0 tracks)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C["emerald"], anchor="w",
        )
        self._header_lbl.pack(side="left", expand=True, fill="x")

        ctk.CTkButton(
            hdr, text="Clear All",
            width=72, height=24,
            fg_color="transparent",
            text_color=C["text2"],
            hover_color=C["card2"],
            border_color=C["border"], border_width=1,
            font=ctk.CTkFont(size=10),
            command=self._clear_all,
        ).pack(side="right")

        # Scrollable track list (fixed height so it doesn't push layout around)
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color=C["bg2"],
            height=110, corner_radius=6,
        )
        self._scroll.pack(fill="x", padx=8, pady=(0, 8))

    # ── Public API ────────────────────────────────────────────────────────────

    def set_tracks(self, tracks: list[Path]) -> None:
        self._tracks = list(tracks)
        self._rebuild()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _rebuild(self) -> None:
        # Remove all existing rows
        for w in self._scroll.winfo_children():
            w.destroy()

        count = len(self._tracks)
        self._header_lbl.configure(
            text=f"Music Playlist  ({count} track{'s' if count != 1 else ''})"
        )

        for idx, track in enumerate(self._tracks):
            row = ctk.CTkFrame(self._scroll, fg_color="transparent")
            row.pack(fill="x", pady=1)

            # Track number badge
            ctk.CTkLabel(
                row,
                text=f"{idx + 1}.",
                font=ctk.CTkFont(size=10),
                text_color=C["muted"],
                width=22, anchor="e",
            ).pack(side="left")

            # Filename (truncated if too long)
            name = track.stem
            if len(name) > 38:
                name = name[:35] + "…"
            ctk.CTkLabel(
                row, text=name,
                font=ctk.CTkFont(size=11),
                text_color=C["text"],
                anchor="w",
            ).pack(side="left", expand=True, fill="x", padx=(4, 4))

            # X remove button — capture idx in default arg
            ctk.CTkButton(
                row, text="✕",
                width=24, height=22,
                fg_color="transparent",
                text_color=C["error"],
                hover_color=C["card2"],
                font=ctk.CTkFont(size=10),
                command=lambda i=idx: self._remove(i),
            ).pack(side="right")

    def _remove(self, idx: int) -> None:
        self._on_remove(idx)

    def _clear_all(self) -> None:
        # Remove from the end so indices stay valid during iteration
        for i in range(len(self._tracks) - 1, -1, -1):
            self._on_remove(i)
