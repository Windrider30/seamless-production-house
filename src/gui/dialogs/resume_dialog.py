"""Ask the user whether to resume a previous render session."""
from __future__ import annotations

import customtkinter as ctk
from src.config import C
from src.utils import session as session_store


class ResumeDialog(ctk.CTkToplevel):
    """
    result: 'resume' | 'discard' | 'cancel'
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.result: str = "cancel"
        data = session_store.load() or {}
        ts = data.get("timestamp", "unknown time")
        clip_count = len(data.get("clips", []))
        done = len(data.get("render_progress", {}).get("temp_segments", []))

        self.title("Resume Previous Render?")
        self.geometry("440x240")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()

        ctk.CTkLabel(
            self, text="↩  Unfinished Render Found",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=C["emerald"],
        ).pack(pady=(24, 8))

        ctk.CTkLabel(
            self,
            text=(
                f"A render was interrupted on {ts[:19].replace('T', ' ')}.\n"
                f"{clip_count} clips  •  {done} segments already completed.\n\n"
                f"Would you like to pick up where you left off?"
            ),
            text_color=C["text"], justify="center",
        ).pack(padx=24, pady=(0, 20))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack()

        ctk.CTkButton(
            btn_frame, text="Resume Render",
            fg_color=C["emerald"], text_color=C["bg"],
            hover_color=C["emerald_lt"],
            font=ctk.CTkFont(weight="bold"),
            command=lambda: self._pick("resume"),
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_frame, text="Start Fresh",
            fg_color=C["card2"], text_color=C["text"],
            hover_color=C["border"],
            command=lambda: self._pick("discard"),
        ).pack(side="left", padx=8)

    def _pick(self, result: str) -> None:
        self.result = result
        if result == "discard":
            session_store.clear()
        self.destroy()
