"""Dialog shown when FFmpeg or RIFE binaries are missing."""
from __future__ import annotations

import threading
import customtkinter as ctk

from src.config import C
from src.utils.downloader import download_all
from src.utils.path_checker import invalidate_cache


class MissingEngineDialog(ctk.CTkToplevel):
    def __init__(self, parent, missing: list[str], on_done: callable):
        super().__init__(parent)
        self._on_done = on_done
        self.title("Missing Engines")
        self.geometry("480x320")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()
        self._build(missing)

    def _build(self, missing: list[str]) -> None:
        ctk.CTkLabel(
            self, text="⚙  Missing Engines",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=C["emerald"],
        ).pack(pady=(24, 8))

        items = "\n".join(f"  •  {m}" for m in missing)
        ctk.CTkLabel(
            self,
            text=(
                f"The following required components were not found:\n\n"
                f"{items}\n\n"
                f"Click below to download and install them automatically.\n"
                f"This only needs to happen once."
            ),
            text_color=C["text"],
            justify="left",
            wraplength=420,
        ).pack(padx=24, pady=(0, 16))

        self._status = ctk.CTkLabel(self, text="", text_color=C["text2"])
        self._status.pack()

        self._bar = ctk.CTkProgressBar(
            self, width=400, progress_color=C["emerald"],
            fg_color=C["card"],
        )
        self._bar.set(0)
        self._bar.pack(pady=(4, 16))

        self._btn = ctk.CTkButton(
            self,
            text="Download & Install Automatically",
            fg_color=C["emerald"], text_color=C["bg"],
            hover_color=C["emerald_lt"],
            font=ctk.CTkFont(weight="bold"),
            command=self._start_download,
        )
        self._btn.pack()

    def _start_download(self) -> None:
        self._btn.configure(state="disabled", text="Downloading…")
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self) -> None:
        def progress(msg: str, fraction: float) -> None:
            self.after(0, lambda: self._status.configure(text=msg))
            self.after(0, lambda: self._bar.set(fraction))

        errors = download_all(progress)
        invalidate_cache()

        def finish():
            if errors:
                self._status.configure(
                    text="\n".join(errors), text_color=C["error"]
                )
                self._btn.configure(state="normal", text="Retry")
            else:
                self._status.configure(
                    text="All engines installed successfully!",
                    text_color=C["success"],
                )
                self.after(1200, self._close)

        self.after(0, finish)

    def _close(self) -> None:
        self.destroy()
        self._on_done()
