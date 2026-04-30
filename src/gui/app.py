"""
Main application window.
Mixes CTk with TkinterDnD.DnDWrapper for drag-and-drop support.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import customtkinter as ctk

from src.config import C, APP_NAME, APP_VERSION, TEMP_DIR
from src.engine.hardware import detect_encoder, gpu_warning
from src.engine.renderer import RenderJob
from src.gui.dialogs.missing_engine import MissingEngineDialog
from src.gui.dialogs.resume_dialog import ResumeDialog
from src.gui.panels.drop_panel import DropPanel
from src.gui.panels.queue_panel import QueuePanel
from src.gui.panels.settings_panel import SettingsPanel
from src.gui.panels.progress_panel import ProgressPanel
from src.gui.panels.preview_panel import PreviewPanel
from src.utils import session as session_store
from src.utils.path_checker import missing_engines
from src.utils import preflight
from src.utils.logger import log_info

try:
    from tkinterdnd2 import TkinterDnD

    class _Base(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self):
            super().__init__()
            self.TkdndVersion = TkinterDnD._require(self)

except ImportError:
    _Base = ctk.CTk  # type: ignore[misc]


class App(_Base):
    def __init__(self):
        super().__init__()
        self._clips: list[Path] = []
        self._music: list[Path] = []
        self._render_job: RenderJob | None = None
        self._rendering = False

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")
        self._apply_dpi_scaling()

        self.title(f"{APP_NAME}  v{APP_VERSION}")
        self.minsize(1280, 820)
        self.configure(fg_color=C["bg"])
        self._set_icon()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self.after(100, self._startup_checks)

    # ── DPI scaling (Bug #2) ─────────────────────────────────────────────────
    def _apply_dpi_scaling(self) -> None:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        try:
            import tkinter as tk
            tmp = tk.Tk()
            tmp.withdraw()
            dpi = tmp.winfo_fpixels("1i")
            tmp.destroy()
            if dpi >= 192:
                ctk.set_widget_scaling(2.0)
            elif dpi >= 144:
                ctk.set_widget_scaling(1.5)
        except Exception:
            pass

    # ── Icon (Bug #6) — programmatically generated so no .ico needed ─────────
    def _set_icon(self) -> None:
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGBA", (64, 64), (26, 26, 46, 255))
            draw = ImageDraw.Draw(img)
            draw.ellipse([8, 8, 56, 56], fill=(0, 210, 168, 255))
            draw.polygon([(26, 18), (26, 46), (46, 32)], fill=(26, 26, 46, 255))
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                img.save(f.name)
                self.iconphoto(True, ctk.CTkImage(light_image=img, dark_image=img))
        except Exception:
            pass

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        # Header
        self._build_header()

        # Body: left column + right column
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        body.columnconfigure(0, weight=3, minsize=480)
        body.columnconfigure(1, weight=2, minsize=300)
        body.rowconfigure(0, weight=1)

        self._build_left(body)
        self._build_right(body)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=C["bg2"], corner_radius=0, height=60)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text=f"  ▶  {APP_NAME}",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=C["emerald"],
        ).pack(side="left", padx=20)

        self._gpu_lbl = ctk.CTkLabel(
            header, text="",
            font=ctk.CTkFont(size=11),
            text_color=C["text2"],
        )
        self._gpu_lbl.pack(side="right", padx=20)

        ctk.CTkLabel(
            header,
            text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=11),
            text_color=C["muted"],
        ).pack(side="right", padx=4)

    def _build_left(self, parent) -> None:
        col = ctk.CTkFrame(parent, fg_color="transparent")
        col.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        col.rowconfigure(1, weight=1)
        col.columnconfigure(0, weight=1)

        # Drop zones
        self._drop_panel = DropPanel(
            col,
            on_clips=self._on_clips_dropped,
            on_music=self._on_music_dropped,
        )
        self._drop_panel.grid(row=0, column=0, sticky="ew", pady=(8, 8))

        # Clip queue
        self._queue = QueuePanel(col)
        self._queue.grid(row=1, column=0, sticky="nsew")

    def _build_right(self, parent) -> None:
        col = ctk.CTkFrame(parent, fg_color="transparent")
        col.grid(row=0, column=1, sticky="nsew")
        col.rowconfigure(0, weight=1)
        col.columnconfigure(0, weight=1)

        # Tab view: Settings | Preview
        tabs = ctk.CTkTabview(
            col, fg_color=C["bg2"],
            segmented_button_fg_color=C["card"],
            segmented_button_selected_color=C["emerald"],
            segmented_button_selected_hover_color=C["emerald_dk"],
            segmented_button_unselected_color=C["card"],
            segmented_button_unselected_hover_color=C["card2"],
            text_color=C["text"],
            text_color_disabled=C["muted"],
        )
        tabs.grid(row=0, column=0, sticky="nsew", pady=(8, 8))
        tabs.add("⚙  Settings")
        tabs.add("👁  Preview")

        # — Settings tab —
        stab = tabs.tab("⚙  Settings")
        stab.columnconfigure(0, weight=1)
        stab.rowconfigure(0, weight=1)
        self._settings = SettingsPanel(stab, on_pin_change=self._on_pin_change)
        self._settings.grid(row=0, column=0, sticky="nsew")

        # — Preview tab —
        ptab = tabs.tab("👁  Preview")
        ptab.columnconfigure(0, weight=1)
        ptab.rowconfigure(0, weight=1)
        self._preview = PreviewPanel(ptab)
        self._preview.grid(row=0, column=0, sticky="nsew")

        # Action buttons
        action_frame = ctk.CTkFrame(col, fg_color=C["card"], corner_radius=10)
        action_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        btn_row = ctk.CTkFrame(action_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=10)

        self._preflight_btn = ctk.CTkButton(
            btn_row, text="Pre-Flight Check",
            fg_color=C["card2"], text_color=C["text"],
            hover_color=C["border"],
            font=ctk.CTkFont(size=12),
            command=self._run_preflight,
        )
        self._preflight_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self._start_btn = ctk.CTkButton(
            btn_row, text="▶  START RENDER",
            fg_color=C["emerald"], text_color=C["bg"],
            hover_color=C["emerald_lt"],
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44,
            command=self._start_render,
        )
        self._start_btn.pack(side="left", expand=True, fill="x")

        self._cancel_btn = ctk.CTkButton(
            action_frame, text="Cancel Render",
            fg_color="transparent", text_color=C["error"],
            hover_color=C["card"],
            font=ctk.CTkFont(size=11),
            command=self._cancel_render,
            state="disabled",
        )
        self._cancel_btn.pack(pady=(0, 8))

        # Progress
        self._progress = ProgressPanel(col)
        self._progress.grid(row=2, column=0, sticky="ew")

    # ── Start-up ─────────────────────────────────────────────────────────────
    def _startup_checks(self) -> None:
        # 1. Check for missing binaries
        missing = missing_engines()
        if missing:
            MissingEngineDialog(self, missing, on_done=self._after_engines_ready)
            return
        self._after_engines_ready()

    def _after_engines_ready(self) -> None:
        # 2. Detect GPU
        enc = detect_encoder()
        warn = gpu_warning()
        if warn:
            self._gpu_lbl.configure(text="⚠ CPU Mode", text_color=C["warning"])
            self._show_toast(warn, color=C["warning"])
        else:
            self._gpu_lbl.configure(text=f"GPU: {enc}", text_color=C["success"])

        # 3. Resume session?
        if session_store.has_resumable():
            dlg = ResumeDialog(self)
            self.wait_window(dlg)
            if dlg.result == "resume":
                self._restore_session()

    def _restore_session(self) -> None:
        data = session_store.load()
        if not data:
            return
        self._clips = [Path(p) for p in data.get("clips", []) if Path(p).exists()]
        self._music = [Path(p) for p in data.get("music_files", []) if Path(p).exists()]
        self._queue.set_clips(self._clips)
        progress = data.get("render_progress", {})
        self._show_toast(
            f"Session restored: {len(self._clips)} clips, "
            f"{len(progress.get('temp_segments', []))} segments already done.",
            color=C["success"],
        )

    # ── Drop handlers ────────────────────────────────────────────────────────
    def _on_clips_dropped(self, clips: list[Path]) -> None:
        self._clips = clips
        self._queue.set_clips(clips)
        # Wire up queue clicks to preview
        log_info(f"Loaded {len(clips)} clips.")

    def _on_music_dropped(self, music: list[Path]) -> None:
        # Accumulate: add new tracks to the existing playlist so the user
        # can build a multi-song playlist by loading files one at a time.
        combined = list(dict.fromkeys(self._music + music))  # preserve order, deduplicate
        self._music = combined
        # Update the drop zone label to show the running total
        self._drop_panel.music_zone._set_count(len(self._music))
        log_info(f"Added {len(music)} music track(s). Playlist total: {len(self._music)}")

    # ── Pre-flight ────────────────────────────────────────────────────────────
    def _run_preflight(self) -> None:
        issues: list[str] = []

        if not self._clips:
            issues.append("No clips loaded.")

        output_dir = self._settings.output_dir
        if not output_dir.exists():
            try:
                output_dir.mkdir(parents=True)
            except Exception:
                issues.append(f"Cannot create output folder: {output_dir}")

        req_bytes = preflight.estimate_output_bytes(
            len(self._clips), 5.0, self._settings.resolution
        )
        ok, msg = preflight.check_disk_space(output_dir, req_bytes)
        if not ok:
            issues.append(msg)

        unreadable = preflight.check_clips_readable(self._clips)
        if unreadable:
            issues.append(f"{len(unreadable)} clip(s) could not be found on disk.")

        if issues:
            self._show_toast("Pre-flight failed:\n" + "\n".join(issues),
                             color=C["error"], duration_ms=6000)
        else:
            self._show_toast("Pre-flight passed! Ready to render.", color=C["success"])

    # ── Render ────────────────────────────────────────────────────────────────
    def _start_render(self) -> None:
        if self._rendering:
            return
        if not self._clips:
            self._show_toast("Drop some clips first!", color=C["warning"])
            return

        output_dir = self._settings.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = preflight.get_unique_output_path(
            output_dir, self._settings.filename
        )
        TEMP_DIR.mkdir(parents=True, exist_ok=True)

        # Save session before starting
        session_store.save({
            "clips": [str(c) for c in self._clips],
            "music_files": [str(m) for m in self._music],
            "genre": self._settings.genre,
            "content_type": self._settings.content_type,
            "output_path": str(output_path),
            "render_progress": {},
        })

        self._rendering = True
        self._start_btn.configure(state="disabled")
        self._cancel_btn.configure(state="normal")
        self._progress.reset()   # clear any stale error from previous run
        self._progress.start()

        self._render_job = RenderJob(
            clips=self._clips,
            music_files=self._music,
            genre=self._settings.genre,
            content_type=self._settings.content_type,
            output_path=output_path,
            resolution=self._settings.resolution,
            fps=self._settings.fps,
            progress_cb=self._on_progress,
            error_cb=self._on_render_error,
            loop_clips=self._settings.loop_clips,
            pin_intro=self._settings.pin_intro,
            pin_outro=self._settings.pin_outro,
            intro_text=self._settings.intro_text,
            outro_text=self._settings.outro_text,
            text_font_path=self._settings.text_font_path,
            text_size=self._settings.text_size,
            text_color=self._settings.text_color,
            text_position=self._settings.text_position,
            text_duration=self._settings.text_duration,
            slideshow_resolution=self._settings.slideshow_resolution,
            slideshow_hold=self._settings.slideshow_hold,
        )
        threading.Thread(target=self._render_job.run, daemon=True).start()

    def _on_pin_change(self, pin_intro: bool, pin_outro: bool) -> None:
        self._queue.set_pins(pin_intro, pin_outro)

    def _cancel_render(self) -> None:
        if self._render_job:
            self._render_job.cancel()
        self._reset_render_ui()
        self._progress.error("Render cancelled.")

    def _on_progress(self, fraction: float, message: str) -> None:
        self.after(0, lambda: self._progress.update(fraction, message))
        if fraction >= 1.0:
            self.after(0, self._on_render_done)

    def _on_render_done(self) -> None:
        self._progress.finish()
        self._reset_render_ui()
        self._show_toast("Render complete! File saved to Videos folder.",
                         color=C["success"], duration_ms=5000)

    def _on_render_error(self, message: str) -> None:
        self.after(0, lambda: self._progress.error(message))
        self.after(0, self._reset_render_ui)
        self.after(0, lambda: self._show_toast(message, color=C["error"],
                                                duration_ms=8000))

    def _reset_render_ui(self) -> None:
        self._rendering = False
        self._start_btn.configure(state="normal")
        self._cancel_btn.configure(state="disabled")

    # ── Toast notification ────────────────────────────────────────────────────
    def _show_toast(self, message: str, color: str = C["text2"],
                    duration_ms: int = 3500) -> None:
        toast = ctk.CTkToplevel(self)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(fg_color=C["card"])

        ctk.CTkLabel(
            toast, text=message,
            text_color=color,
            font=ctk.CTkFont(size=12),
            wraplength=360, justify="left",
            padx=16, pady=12,
        ).pack()

        # Position bottom-right of main window
        self.update_idletasks()
        x = self.winfo_x() + self.winfo_width() - 420
        y = self.winfo_y() + self.winfo_height() - 120
        toast.geometry(f"+{x}+{y}")
        toast.after(duration_ms, toast.destroy)

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def _on_close(self) -> None:
        if self._render_job:
            self._render_job.cancel()
        self.destroy()
