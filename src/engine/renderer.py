"""
Main render orchestrator.
Runs in a background thread — never call GUI methods directly from here.
Communicate via the progress_callback and status_callback.
"""
from __future__ import annotations

import atexit
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

import textwrap as _textwrap

from src.config import (
    GENRES, CONTENT_TYPES, SEGMENT_DURATION,
    L_CUT_SECONDS, VIDEO_EXTENSIONS, IMAGE_EXTENSIONS, TEMP_DIR,
    TRANSITION_STYLES,
)
from src.engine.hardware import detect_encoder, encoder_flags
from src.engine.transitions import (
    scene_similarity, morph_transition,
    crossfade_transition, hard_cut_join,
    concat_clips, get_duration, trim_stream_copy, trim_reencode,
)
from src.engine.audio_mixer import mix_music_under_video, normalize_audio
from src.utils import session as session_store
from src.utils.path_checker import get_ffmpeg, get_ffprobe
from src.utils.logger import log_error, log_info, friendly
from src.utils import preflight

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Track live subprocesses so atexit can kill them (Bug #4)
_active_procs: list[subprocess.Popen] = []


@atexit.register
def _kill_orphans() -> None:
    for p in _active_procs:
        try:
            p.kill()
        except Exception:
            pass


ProgressCB = Callable[[float, str], None]   # (0.0‒1.0, message)
ErrorCB    = Callable[[str], None]


def _run_ffmpeg(cmd: list[str],
                progress_cb: ProgressCB | None = None,
                base_fraction: float = 0.0,
                fraction_range: float = 0.0,
                total_frames: int = 0) -> None:
    """
    Run an FFmpeg command.  If progress_cb + total_frames are supplied,
    injects -progress pipe:1 and parses frame= lines for live updates.
    """
    use_progress = progress_cb and total_frames > 0

    if use_progress:
        # Insert -progress pipe:1 before the output path (last arg)
        inject = ["-progress", "pipe:1", "-nostats"]
        full_cmd = cmd[:-1] + inject + [cmd[-1]]
        proc = subprocess.Popen(
            full_cmd, creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    else:
        proc = subprocess.Popen(
            cmd, creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    _active_procs.append(proc)

    if use_progress:
        # Drain stderr in a background thread — if stderr fills the OS pipe
        # buffer (~4 KB on Windows) while we're reading stdout line-by-line,
        # FFmpeg blocks writing stderr, stdout stalls, and we deadlock.
        stderr_chunks: list[bytes] = []
        drain = threading.Thread(
            target=lambda: stderr_chunks.append(proc.stderr.read()),
            daemon=True,
        )
        drain.start()

        for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line.startswith("frame="):
                try:
                    frame = int(line.split("=")[1])
                    frac = base_fraction + min(frame / total_frames, 1.0) * fraction_range
                    progress_cb(frac, f"Encoding… frame {frame}/{total_frames}")
                except ValueError:
                    pass

        proc.wait()
        drain.join()
        stderr_text = stderr_chunks[0].decode("utf-8", errors="replace") if stderr_chunks else ""
    else:
        _, stderr_bytes = proc.communicate()
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")

    _active_procs.remove(proc)

    if proc.returncode not in (0, None):
        log_info(f"FFmpeg cmd: {' '.join(str(c) for c in cmd)}")
        log_info(f"FFmpeg stderr: {stderr_text}")
        raise RuntimeError(f"FFmpeg exited {proc.returncode}: {stderr_text[-300:]}")


def _probe_streams(src: Path) -> tuple[bool, int, int]:
    """
    Returns (has_audio, width, height) for a clip.
    Fast ffprobe call — used before pre-convert to decide what flags to add.
    """
    import json as _json
    probe = str(get_ffprobe())
    try:
        r = subprocess.run(
            [probe, "-v", "quiet", "-print_format", "json",
             "-show_streams", str(src)],
            capture_output=True, text=True,
            creationflags=CREATE_NO_WINDOW, timeout=8,
        )
        streams = _json.loads(r.stdout).get("streams", [])
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        vs = next((s for s in streams if s.get("codec_type") == "video"), {})
        return has_audio, int(vs.get("width", 0)), int(vs.get("height", 0))
    except Exception:
        return False, 0, 0


def preconvert_clip(src: Path, dest: Path, encoder: str,
                    progress_cb: ProgressCB | None = None,
                    base_fraction: float = 0.0,
                    fraction_range: float = 0.0,
                    hold_duration: float = 5.0,
                    target_resolution: tuple[int, int] | None = None) -> None:
    """
    Re-encode any clip (or still image) to a normalised H.264/AAC MP4.
    - Still images: converted to video at hold_duration seconds
    - Adds a silent stereo audio track if the clip has no audio
    - Normalises to 30fps and 44100Hz stereo so all clips concat cleanly
    - target_resolution: if set, all clips are scaled/padded to (W, H) so that
      the concat demuxer and xfade filter always receive uniform dimensions.
    """
    ffmpeg = str(get_ffmpeg())
    enc = encoder_flags(encoder)
    is_image = src.suffix.lower() in IMAGE_EXTENSIONS

    if target_resolution:
        tw, th = target_resolution
        scale_vf = (
            f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
            f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:black,"
            "setsar=1,format=yuv420p,fps=30"
        )
    else:
        scale_vf = (
            "scale=trunc(iw/2)*2:trunc(ih/2)*2,"
            "pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:black,"
            "setsar=1,format=yuv420p,fps=30"
        )

    if is_image:
        cmd = [
            ffmpeg, "-y",
            "-loop", "1", "-framerate", "30", "-i", str(src),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-vf", scale_vf,
        ] + enc + [
            "-t", f"{hold_duration:.3f}",
            "-g", "90",
            "-bf", "0",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart",
            "-shortest",
            str(dest),
        ]
        total_frames = int(hold_duration * 30)
        _run_ffmpeg(cmd, progress_cb, base_fraction, fraction_range, total_frames)
        return

    has_audio, w, h = _probe_streams(src)

    inputs: list[str] = ["-i", str(src)]
    if not has_audio:
        inputs += ["-f", "lavfi",
                   "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    video_filters = ["-vf", scale_vf]

    cmd = [ffmpeg, "-y"] + inputs + video_filters + enc + [
        "-g", "90",                  # keyframe every 3 s — fast seeking, no decoder spin
        "-bf", "0",                  # no B-frames — clean DTS for concat demuxer
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        "-shortest",
        str(dest),
    ]

    total_frames = 0
    if progress_cb:
        try:
            import json as _json
            probe = str(get_ffprobe())
            r = subprocess.run(
                [probe, "-v", "quiet", "-print_format", "json",
                 "-show_streams", str(src)],
                capture_output=True, text=True,
                creationflags=CREATE_NO_WINDOW, timeout=8,
            )
            streams = _json.loads(r.stdout).get("streams", [])
            vs = next((s for s in streams if s.get("codec_type") == "video"), {})
            dur = float(vs.get("duration", 0) or 0)
            total_frames = int(dur * 30)
        except Exception:
            pass

    _run_ffmpeg(cmd, progress_cb, base_fraction, fraction_range, total_frames)


def _get_clip_width(clip: Path) -> int:
    """Return the video stream width in pixels, or 1920 as a safe default."""
    ffprobe = get_ffprobe()
    if not ffprobe:
        return 1920
    import json as _j
    try:
        r = subprocess.run(
            [str(ffprobe), "-v", "quiet", "-print_format", "json",
             "-show_streams", "-select_streams", "v:0", str(clip)],
            capture_output=True, text=True, timeout=8,
            creationflags=CREATE_NO_WINDOW,
        )
        streams = _j.loads(r.stdout).get("streams", [])
        return int(streams[0].get("width", 1920)) if streams else 1920
    except Exception:
        return 1920


def _wrap_for_drawtext(escaped_text: str, font_size: int, video_w: int) -> str:
    """
    Word-wrap pre-escaped drawtext text so it fits inside video_w pixels.
    Returns text with drawtext literal newlines (\\n = backslash + n).
    Proportional fonts average roughly 0.55× font_size per character.
    """
    chars_per_line = max(8, int(video_w / (font_size * 0.55)))
    lines = _textwrap.wrap(escaped_text, width=chars_per_line,
                           break_long_words=True, break_on_hyphens=False)
    return "\\n".join(lines) if lines else escaped_text


def apply_text_overlay(
    src: Path,
    dest: Path,
    text: str,
    font_path: str | None,
    font_size: int,
    color: str,
    position: str,
    text_duration: float,
    encoder: str,
    start_time: float = 0.0,
) -> None:
    """
    Burn a text overlay into a clip using FFmpeg drawtext.
    Text is written to a temp file so any characters (quotes, colons, etc.)
    are handled safely without shell-escaping headaches.
    """
    if not text.strip():
        return

    ffmpeg = str(get_ffmpeg())
    # Always use software encoder for text overlay — NVENC/AMF + drawtext
    # (a software-only filter) can fail silently on many driver versions.
    # Intro/outro clips are short so CPU speed is not a concern.
    sw_enc = ["-c:v", "libx264", "-preset", "faster", "-crf", "23",
              "-pix_fmt", "yuv420p"]

    clip_dur = get_duration(src)
    # vis_dur: how long text is shown; capped so text ends before clip ends
    vis_dur  = min(text_duration, max(0.5, clip_dur - start_time - 0.5))
    end_time = start_time + vis_dur

    y_map = {
        "Top":    "h*0.08",
        "Center": "(h-text_h)/2",
        "Bottom": "h*0.82-text_h",
    }
    y_expr = y_map.get(position, "(h-text_h)/2")

    # Escape text for the drawtext text= option.
    # In FFmpeg's filter option string a single-quote starts a "quoted string"
    # mode that suppresses the : separator — any unmatched ' causes a parse
    # error.  Order matters: escape \ first so subsequent \-prefixes aren't
    # doubled, then escape ' and :, then %% for drawtext's strftime formatter.
    escaped_text = (
        text
        .replace("\\", "\\\\")
        .replace("'",  "\\'")
        .replace(":",  "\\:")
        .replace("%",  "%%")
    )

    # Auto word-wrap: split the text into multiple lines so it never overflows
    # the frame.  We do this on the already-escaped text so the wrap width
    # calculation uses the same characters that will appear on screen.
    video_w = _get_clip_width(src)
    escaped_text = _wrap_for_drawtext(escaped_text, font_size, video_w)

    # FFmpeg 8.1 broke both \: and single-quote quoting for Windows drive-letter
    # colons (C:) inside filter option values — the option parser splits on ALL
    # colons before quoting is applied.
    # Fix: use text= instead of textfile= (no path in the filter at all), and
    # strip the drive letter from the fontfile path so C:/path → /path.
    # FFmpeg resolves /path relative to the current drive (C:), so the file is
    # found correctly as long as it's on the same drive as the binary (it always
    # is — both live under APP_DIR).
    import re as _re
    def _nodrive(p: str) -> str:
        return _re.sub(r'^[A-Za-z]:', '', p.replace("\\", "/"))

    parts = [
        f"text={escaped_text}",
        f"fontsize={font_size}",
        f"fontcolor={color}",
        "x=(w-text_w)/2",
        f"y={y_expr}",
        # Dark box behind text for readability.
        # Use hex alpha (0xRRGGBBAA) instead of color@alpha notation —
        # the @ char can confuse FFmpeg 8.1's filter option tokenizer.
        "box=1",
        "boxcolor=0x00000088",
        "boxborderw=12",
        # Drop shadow for depth
        "shadowcolor=0x000000CC",
        "shadowx=2",
        "shadowy=2",
        # enable= MUST be last: FFmpeg 8.1's timeline expression parser
        # greedily consumes the option tokens that follow it (treating
        # ':box=' as part of the expression), leaving '1' as a dangling
        # token that fails option-name validation.  Placing enable last
        # means there is nothing after it for the greedy parser to eat.
        f"enable=between(t\\,{start_time:.2f}\\,{end_time:.2f})",
    ]
    if font_path and Path(font_path).exists():
        # Copy font to the output's directory so it's on the same drive as the
        # exe.  _nodrive strips the Windows drive letter (C:) from the path so
        # FFmpeg's filter option parser doesn't choke on the colon — but the
        # resulting /Windows/Fonts/... path is resolved relative to the CURRENT
        # DRIVE.  If the app is installed on D: the system fonts are on C: and
        # the path silently resolves wrong.  A local copy always lives on the
        # same drive as the exe, so _nodrive always produces a correct path.
        import shutil as _shutil
        font_copy = dest.parent / ("_overlay_font" + Path(font_path).suffix)
        _shutil.copy2(font_path, str(font_copy))
        parts.insert(1, f"fontfile={_nodrive(str(font_copy))}")

    drawtext = "drawtext=" + ":".join(parts)
    cmd = [ffmpeg, "-y", "-i", str(src),
           "-vf", drawtext,
           ] + sw_enc + [
        "-c:a", "copy",
        str(dest),
    ]
    _run_ffmpeg(cmd)


def concat_segments(segments: list[Path], output: Path, encoder: str) -> None:
    """Losslessly join completed segments into the final file."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    list_file = TEMP_DIR / "concat_segments_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for s in segments:
            safe = str(s).replace("\\", "/")
            f.write(f"file '{safe}'\n")
    try:
        _run_ffmpeg([
            str(get_ffmpeg()), "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output),
        ])
    finally:
        list_file.unlink(missing_ok=True)


class RenderJob:
    def __init__(
        self,
        clips: list[Path],
        music_files: list[Path],
        genre: str,
        content_type: str,
        output_path: Path,
        resolution: tuple[int, int] | None,
        fps: int | None,
        progress_cb: ProgressCB,
        error_cb: ErrorCB,
        resume_segments: list[str] | None = None,
        resume_from_clip: int = 0,
        loop_clips: bool = False,
        pin_intro: bool = False,
        pin_outro: bool = False,
        intro_text: str = "",
        outro_text: str = "",
        text_font_path: str = "",
        text_size: int = 60,
        text_color: str = "white",
        text_position: str = "Center",
        text_duration: float = 3.0,
        slideshow_resolution: tuple[int, int] | None = None,
        slideshow_hold: float | None = None,
        transition_style: str = "Auto (genre default)",
        transition_duration: float = 0.0,
    ):
        self.clips = clips
        self.music_files = music_files
        self.genre_cfg = GENRES.get(genre, GENRES["Lofi"])
        self.content_cfg = CONTENT_TYPES.get(content_type, CONTENT_TYPES["Music Video"])
        self.output_path = output_path
        self.resolution = resolution
        self.fps = fps
        self.progress_cb = progress_cb
        self.error_cb = error_cb
        self.encoder = detect_encoder()
        self.loop_clips = loop_clips
        self.pin_intro = pin_intro
        self.pin_outro = pin_outro
        self.intro_text = intro_text
        self.outro_text = outro_text
        self.text_font_path = text_font_path
        self.text_size = text_size
        self.text_color = text_color
        self.text_position = text_position
        self.text_duration = text_duration
        self.slideshow_resolution = slideshow_resolution
        self.slideshow_hold = slideshow_hold
        self.transition_style = transition_style or "Auto (genre default)"
        self.transition_duration = transition_duration  # 0.0 means "use genre default"
        self.cancelled = False
        self.temp_dir = TEMP_DIR / "render"
        # Clear stale temp files unless resuming a previous session
        if not resume_segments:
            import shutil
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.completed_segments: list[Path] = [
            Path(s) for s in (resume_segments or [])
        ]
        self.start_clip = resume_from_clip

    def cancel(self) -> None:
        self.cancelled = True

    # ── Internal helpers ────────────────────────────────────────────────────

    def _report(self, fraction: float, msg: str) -> None:
        self.progress_cb(min(1.0, max(0.0, fraction)), msg)

    def _save_session(self, current_clip: int) -> None:
        session_store.save({
            "clips":       [str(c) for c in self.clips],
            "music_files": [str(m) for m in self.music_files],
            "genre":       next(
                k for k, v in GENRES.items() if v is self.genre_cfg
            ),
            "content_type": next(
                k for k, v in CONTENT_TYPES.items() if v is self.content_cfg
            ),
            "output_path": str(self.output_path),
            "render_progress": {
                "current_clip":    current_clip,
                "total_clips":     len(self.clips),
                "temp_segments":   [str(s) for s in self.completed_segments],
            },
        })

    def _choose_transition(self, clip_a: Path, clip_b: Path) -> str:
        # User override trumps genre setting
        style_mode, _ = TRANSITION_STYLES.get(
            self.transition_style, (None, None)
        )
        if style_mode is not None:
            return style_mode  # "crossfade", "morph", or "cut"

        # Genre default with scene-similarity morph gate
        preferred = self.genre_cfg["transition"]
        if preferred == "morph":
            sim = scene_similarity(clip_a, clip_b)
            if sim < self.genre_cfg["scene_thresh"]:
                return "crossfade"
        return preferred

    # ── Main run ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        try:
            self._run_pipeline()
        except Exception as exc:
            log_error(exc, "Render pipeline")
            self.error_cb(str(exc))

    def _run_pipeline(self) -> None:
        total = len(self.clips)
        if total == 0:
            self.error_cb("No clips loaded.")
            return

        # ── Step 1: Pre-convert all clips to normalised H.264/AAC ────────
        # Photo Slideshow: use the user-specified canvas so every photo is
        # scaled/padded to the SAME size regardless of its original dimensions.
        # This prevents the size-mismatch crashes that plague mixed-orientation
        # photo sets (portrait vs landscape vs square).
        # All other modes: derive target from the first clip.
        target_resolution: tuple[int, int] | None = None
        if self.content_cfg.get("force_resolution") and self.slideshow_resolution:
            target_resolution = self.slideshow_resolution
        elif self.clips:
            _, fw, fh = _probe_streams(self.clips[0])
            if fw and fh:
                # Force even dimensions for H.264 (chroma sub-sampling)
                target_resolution = (fw // 2 * 2, fh // 2 * 2)

        # Photo Slideshow: override clip_hold with user-selected duration,
        # then guarantee each photo has at least 2 s of fully-visible body
        # after the transition overlap regions are removed from both ends.
        hold_duration = float(self.content_cfg["clip_hold"])
        if self.slideshow_hold is not None:
            hold_duration = self.slideshow_hold

        if self.content_cfg.get("force_resolution"):
            xfade = float(self.genre_cfg["xfade_dur"])
            if self.genre_cfg["transition"] != "cut":
                min_hold = 2.0 * xfade + 2.0
                if hold_duration < min_hold:
                    hold_duration = min_hold

        converted: list[Path] = []
        for i, clip in enumerate(self.clips[self.start_clip:], start=self.start_clip):
            if self.cancelled:
                return
            base = i / total * 0.25
            self._report(base, f"Pre-converting clip {i+1}/{total}…")
            dest = self.temp_dir / f"conv_{i:04d}.mp4"
            if not dest.exists():
                try:
                    preconvert_clip(
                        clip, dest, self.encoder,
                        progress_cb=self.progress_cb,
                        base_fraction=base,
                        fraction_range=(1 / total * 0.25),
                        hold_duration=hold_duration,
                        target_resolution=target_resolution,
                    )
                except Exception as exc:
                    log_error(exc, f"clip {i}")
                    self.error_cb(friendly(exc, i))
                    return
            converted.append(dest)

        if self.start_clip > 0:
            pre = [self.temp_dir / f"conv_{i:04d}.mp4"
                   for i in range(self.start_clip)]
            converted = pre + converted

        # ── Optional: Burn text into intro / outro ───────────────────────
        # Text applies whenever the user typed something — pin state is
        # independent (pin controls looping, not text visibility).
        #
        # start_time for outro: the outro clip's body is trimmed from
        # xfade_dur onward (the left end is consumed by the transition from
        # the previous clip).  If we burned the text at t=0 the transition
        # trim would erase most of it.  Shift the text to start at xfade_dur
        # so it sits squarely inside the visible body portion.
        _xfade = float(self.genre_cfg["xfade_dur"])
        _has_transitions = (self.genre_cfg["transition"] != "cut")

        if self.intro_text.strip() and len(converted) > 0:
            self._report(0.26, "Applying intro text overlay…")
            text_path = self.temp_dir / "text_intro.mp4"
            try:
                apply_text_overlay(
                    converted[0], text_path,
                    text=self.intro_text,
                    font_path=self.text_font_path or None,
                    font_size=self.text_size,
                    color=self.text_color,
                    position=self.text_position,
                    text_duration=self.text_duration,
                    encoder=self.encoder,
                    start_time=0.0,
                )
                converted[0] = text_path
            except Exception as exc:
                log_error(exc, "intro text overlay")
                self._report(0.26, f"Intro text failed — check log")

        if self.outro_text.strip() and len(converted) > 1:
            self._report(0.27, "Applying outro text overlay…")
            text_path = self.temp_dir / "text_outro.mp4"
            # Outro body starts at xfade_dur (left side eaten by transition)
            outro_start = _xfade if _has_transitions else 0.0
            try:
                apply_text_overlay(
                    converted[-1], text_path,
                    text=self.outro_text,
                    font_path=self.text_font_path or None,
                    font_size=self.text_size,
                    color=self.text_color,
                    position=self.text_position,
                    text_duration=self.text_duration,
                    encoder=self.encoder,
                    start_time=outro_start,
                )
                converted[-1] = text_path
            except Exception as exc:
                log_error(exc, "outro text overlay")
                self._report(0.27, f"Outro text failed — check log")

        # ── Optional: Loop clips to fill music duration ──────────────────
        if self.loop_clips and self.music_files and len(converted) > 0:
            import math
            music_dur = sum(get_duration(m) for m in self.music_files)

            use_intro = self.pin_intro and len(converted) >= 2
            use_outro = self.pin_outro and len(converted) >= (3 if use_intro else 2)

            if use_intro and use_outro:
                head, middle, tail = [converted[0]], converted[1:-1], [converted[-1]]
            elif use_intro:
                head, middle, tail = [converted[0]], converted[1:], []
            elif use_outro:
                head, middle, tail = [], converted[:-1], [converted[-1]]
            else:
                head, middle, tail = [], converted, []

            head_dur   = sum(get_duration(c) for c in head)
            tail_dur   = sum(get_duration(c) for c in tail)
            middle_dur = sum(get_duration(c) for c in middle)
            n_middle   = len(middle)

            if middle_dur > 0 and n_middle > 0:
                # Use the RENDERED duration for the repeat calculation, not the
                # raw clip duration. With xfade transitions, each clip-to-clip
                # junction removes xfade_dur from the output.  Using raw
                # durations causes far too few repeats and a video that ends
                # well before the music does.
                #
                # Formula (derived from total_rendered = Σdurs - (n-1)*xfade):
                #   repeats = ceil(
                #       (music_dur - head_dur - tail_dur + xfade) /
                #       (middle_dur - n_middle * xfade)
                #   )
                # For "cut" transitions xfade=0 this reduces to the old formula.
                # Use the user-overridden xfade_dur if set; else genre default.
                loop_xfade = (
                    float(self.transition_duration)
                    if self.transition_duration > 0
                    else float(self.genre_cfg["xfade_dur"])
                )
                xfade_dur_loop = loop_xfade
                eff_denom = middle_dur - n_middle * xfade_dur_loop
                if eff_denom <= 0:
                    eff_denom = middle_dur   # safety: clips shorter than xfade
                eff_numer = music_dur - head_dur - tail_dur + xfade_dur_loop
                repeats = math.ceil(eff_numer / eff_denom)
                repeats = max(1, repeats)
                if repeats > 1:
                    self._report(0.25, f"Looping {n_middle} clips ×{repeats} to fill {music_dur:.0f}s of music…")
                    middle = middle * repeats
            converted = head + middle + tail

        # ── Step 2: Build concat parts list ─────────────────────────────
        #
        # For each clip we emit:
        #   body_N  — stream-copy of the clip MINUS the overlap regions
        #             (no re-encode, essentially instant)
        #   trans_N — short encoded transition segment between clip N and N+1
        #             (only a few seconds — fast even on CPU)
        #
        # Final order: body_0, trans_01, body_1, trans_12, …, body_N
        #
        # Resolve effective transition mode and speed from user overrides.
        _style_mode, _style_xfade = TRANSITION_STYLES.get(
            self.transition_style, (None, None)
        )
        trans_type = _style_mode if _style_mode is not None else self.genre_cfg["transition"]
        xfade_dur  = (
            float(self.transition_duration)
            if self.transition_duration > 0
            else float(self.genre_cfg["xfade_dur"])
        )
        # The specific FFmpeg xfade filter name (e.g. "wipeleft"); falls back
        # to "dissolve" when the style is auto/morph/cut.
        xfade_type = _style_xfade if _style_xfade else "dissolve"
        concat_parts: list[Path] = []
        segment_parts: list[Path] = []
        segment_dur = 0.0
        seg_idx = len(self.completed_segments)
        stitched: list[Path] = list(self.completed_segments)
        n_converted = len(converted)

        for i, clip in enumerate(converted):
            if self.cancelled:
                return

            fraction = 0.25 + (i / max(n_converted, 1)) * 0.65
            self._report(fraction, f"Building sequence: clip {i+1}/{n_converted}…")

            clip_dur = get_duration(clip)
            is_first = (i == 0)
            is_last  = (i == n_converted - 1)
            uses_transition = (trans_type != "cut")

            # Body: re-encode everything except the overlap regions
            body_start = xfade_dur if (uses_transition and not is_first) else 0.0
            body_end   = (clip_dur - xfade_dur) if (uses_transition and not is_last) else clip_dur
            body_dur   = body_end - body_start

            if body_dur > 0.05:
                body_path = self.temp_dir / f"body_{i:04d}.mp4"
                try:
                    # Re-encode (not stream-copy) so the body has accurate
                    # timestamps starting at 0 with a keyframe on frame 0.
                    # Stream-copy with input-side -ss snaps to the nearest
                    # keyframe (often 0 on an 8s GOP), causing duplicate
                    # content and timestamp gaps in the final concat.
                    trim_reencode(clip, body_path, body_start, body_dur,
                                  encoder=self.encoder)
                    segment_parts.append(body_path)
                    segment_dur += body_dur
                except Exception as exc:
                    log_error(exc, f"body trim clip {i}")
                    self.error_cb(friendly(exc, i))
                    return

            # Transition to next clip
            if not is_last:
                next_clip  = converted[i + 1]
                trans_path = self.temp_dir / f"trans_{i:04d}.mp4"
                actual_type = self._choose_transition(clip, next_clip)

                try:
                    if actual_type == "morph":
                        self._report(fraction, f"Morphing clip {i+1} → {i+2} of {n_converted}…")
                        morph_transition(clip, next_clip, trans_path,
                                         fps=float(self.fps or 30),
                                         duration=xfade_dur,
                                         transition_type=xfade_type,
                                         encoder=self.encoder)
                    elif actual_type == "crossfade":
                        self._report(fraction, f"Cross-fading clip {i+1} → {i+2} of {n_converted}…")
                        crossfade_transition(clip, next_clip, trans_path,
                                             duration=xfade_dur,
                                             transition_type=xfade_type,
                                             encoder=self.encoder)
                    # "cut" — no transition file, bodies already adjacent
                except Exception as exc:
                    log_error(exc, f"transition {i}")
                    self.error_cb(friendly(exc, i))
                    return

                if trans_path.exists():
                    segment_parts.append(trans_path)
                    segment_dur += xfade_dur

            # Flush a 5-minute segment when full
            if segment_dur >= SEGMENT_DURATION and segment_parts:
                self._report(fraction, f"Saving segment {seg_idx + 1}…")
                seg_path = self.temp_dir / f"segment_{seg_idx:03d}.mp4"
                concat_clips(segment_parts, seg_path)
                stitched.append(seg_path)
                self._save_session(i)
                segment_parts = []
                segment_dur   = 0.0
                seg_idx      += 1

        # Final partial segment
        if segment_parts:
            seg_path = self.temp_dir / f"segment_{seg_idx:03d}.mp4"
            concat_clips(segment_parts, seg_path)
            stitched.append(seg_path)

        # ── Step 3: Join all segments ─────────────────────────────────────
        self._report(0.90, "Joining segments…")
        no_music = self.temp_dir / "no_music.mp4"
        concat_segments(stitched, no_music, self.encoder)

        # ── Step 4: Mix music ─────────────────────────────────────────────
        self._report(0.93, "Mixing music…")
        with_music = self.temp_dir / "with_music.mp4"
        mix_music_under_video(no_music, self.music_files, with_music)

        # ── Step 5: Loudness master ───────────────────────────────────────
        self._report(0.97, "Mastering audio…")
        normalize_audio(with_music, self.output_path)

        session_store.clear()
        # Clean up all temp files now that the output is finalised
        import shutil as _shutil
        _shutil.rmtree(self.temp_dir, ignore_errors=True)
        self._report(1.0, "Render complete!")
        log_info(f"Render complete → {self.output_path}")
