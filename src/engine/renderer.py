"""
Main render orchestrator.
Runs in a background thread — never call GUI methods directly from here.
Communicate via the progress_callback and status_callback.
"""
from __future__ import annotations

import atexit
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable

from src.config import (
    GENRES, CONTENT_TYPES, SEGMENT_DURATION,
    L_CUT_SECONDS, VIDEO_EXTENSIONS, IMAGE_EXTENSIONS, TEMP_DIR,
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


def concat_segments(segments: list[Path], output: Path, encoder: str) -> None:
    """Losslessly join completed segments into the final file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                    delete=False, encoding="utf-8") as f:
        for s in segments:
            f.write(f"file '{str(s)}'\n")
        list_file = f.name
    try:
        _run_ffmpeg([
            str(get_ffmpeg()), "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            str(output),
        ])
    finally:
        Path(list_file).unlink(missing_ok=True)


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
        preferred = self.genre_cfg["transition"]
        if preferred == "morph":
            sim = scene_similarity(clip_a, clip_b)
            if sim < self.genre_cfg["scene_thresh"]:
                return "crossfade"   # scenes too different → fallback
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
        # Determine target resolution from the first clip so all output clips
        # share identical dimensions — required for the concat demuxer (stream
        # copy across segments) and the xfade filter (same-size inputs).
        target_resolution: tuple[int, int] | None = None
        if self.clips:
            _, fw, fh = _probe_streams(self.clips[0])
            if fw and fh:
                # Force even dimensions for H.264 (chroma sub-sampling)
                target_resolution = (fw // 2 * 2, fh // 2 * 2)

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
                        hold_duration=float(self.content_cfg["clip_hold"]),
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

            if middle_dur > 0:
                remaining = music_dur - head_dur - tail_dur
                if remaining > middle_dur:
                    repeats = math.ceil(remaining / middle_dur)
                    self._report(0.25, f"Looping {len(middle)} clips ×{repeats} to fill {music_dur:.0f}s of music…")
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
        trans_type = self.genre_cfg["transition"]
        xfade_dur  = float(self.genre_cfg["xfade_dur"])
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
                                         encoder=self.encoder)
                    elif actual_type == "crossfade":
                        self._report(fraction, f"Cross-fading clip {i+1} → {i+2} of {n_converted}…")
                        crossfade_transition(clip, next_clip, trans_path,
                                             duration=xfade_dur,
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
        self._report(1.0, "Render complete!")
        log_info(f"Render complete → {self.output_path}")
