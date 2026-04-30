"""Real-time progress dashboard: bar, current action label, ETA."""
from __future__ import annotations

import time
import customtkinter as ctk

from src.config import C


class ProgressPanel(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C["card"], corner_radius=10, **kwargs)
        self._start_time: float | None = None
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(
            self, text="RENDER PROGRESS",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=C["muted"], anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 4))

        self._action_lbl = ctk.CTkLabel(
            self, text="Idle — waiting to start",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C["text"], anchor="w",
            wraplength=260, justify="left",
        )
        self._action_lbl.pack(fill="x", padx=14, pady=(0, 6))

        self._bar = ctk.CTkProgressBar(
            self, mode="determinate",
            progress_color=C["emerald"],
            fg_color=C["bg"],
            corner_radius=4, height=14,
        )
        self._bar.set(0)
        self._bar.pack(fill="x", padx=14, pady=(0, 6))

        detail_row = ctk.CTkFrame(self, fg_color="transparent")
        detail_row.pack(fill="x", padx=14, pady=(0, 12))

        self._pct_lbl = ctk.CTkLabel(
            detail_row, text="0%",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=C["emerald"],
        )
        self._pct_lbl.pack(side="left")

        self._eta_lbl = ctk.CTkLabel(
            detail_row, text="",
            font=ctk.CTkFont(size=11),
            text_color=C["text2"],
        )
        self._eta_lbl.pack(side="right")

    def start(self) -> None:
        self._start_time = time.time()
        self._pulse_active = False
        self.update(0.0, "Starting render…")

    def pulse(self, message: str) -> None:
        """Switch bar to indeterminate pulsing mode for long blocking ops."""
        self._action_lbl.configure(text=message, text_color=C["text"])
        self._bar.configure(mode="indeterminate")
        self._pulse_active = True
        self._bar.start()

    def unpulse(self, fraction: float, message: str) -> None:
        """Return to determinate mode after a long op finishes."""
        self._pulse_active = False
        self._bar.stop()
        self._bar.configure(mode="determinate")
        self.update(fraction, message)

    def update(self, fraction: float, message: str) -> None:  # noqa: A003
        self._bar.set(fraction)
        self._action_lbl.configure(text=message)
        pct = int(fraction * 100)
        self._pct_lbl.configure(text=f"{pct}%")

        if self._start_time and fraction > 0.01:
            elapsed = time.time() - self._start_time
            total_est = elapsed / fraction
            remaining = max(0, total_est - elapsed)
            self._eta_lbl.configure(text=f"ETA: {self._fmt_time(remaining)}")
        else:
            self._eta_lbl.configure(text="")

    def finish(self, message: str = "Render complete!") -> None:
        self._bar.set(1.0)
        self._action_lbl.configure(text=message, text_color=C["success"])
        self._pct_lbl.configure(text="100%")
        self._eta_lbl.configure(text="Done!")

    def reset(self) -> None:
        self._start_time = None
        self._bar.set(0)
        self._action_lbl.configure(text="Idle — waiting to start", text_color=C["text"])
        self._pct_lbl.configure(text="0%")
        self._eta_lbl.configure(text="")

    def error(self, message: str) -> None:
        self._action_lbl.configure(text=f"⚠  {message}", text_color=C["error"])

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        if h:
            return f"{h}h {m}m"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"
