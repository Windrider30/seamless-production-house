"""
Transition engine: morph (RIFE), crossfade (xfade), hard cut.

Key design principle: crossfade and morph only encode SHORT overlap segments
(a few seconds) — the caller is responsible for stream-copying the bulk of
each clip, which is essentially free.  This keeps CPU renders fast.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from src.config import BIN_DIR, RIFE_EXE_NAME, CROSSFADE_DURATION, TEMP_DIR
from src.engine.hardware import encoder_flags
from src.utils.path_checker import get_ffmpeg, get_ffprobe, get_rife

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


# ── Internal helpers ──────────────────────────────────────────────────────────

def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, creationflags=CREATE_NO_WINDOW,
                       capture_output=True)
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", errors="replace")[-400:]
        raise RuntimeError(f"FFmpeg error: {err}")


def get_duration(path: Path) -> float:
    """Return clip duration in seconds via ffprobe."""
    ffprobe = get_ffprobe()
    if not ffprobe:
        return 0.0
    try:
        r = subprocess.run(
            [str(ffprobe), "-v", "quiet", "-print_format", "json",
             "-show_format", str(path)],
            capture_output=True, text=True, timeout=8,
            creationflags=CREATE_NO_WINDOW,
        )
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def trim_stream_copy(src: Path, dest: Path,
                     start_sec: float = 0.0,
                     duration_sec: float | None = None) -> None:
    """
    Stream-copy trim — no re-encode, essentially instant.
    NOTE: only reliable when start_sec=0.  For mid-clip seeks use trim_reencode.
    """
    ffmpeg = str(get_ffmpeg())
    cmd = [ffmpeg, "-y"]
    if start_sec > 0.01:
        cmd += ["-ss", f"{start_sec:.3f}"]
    cmd += ["-i", str(src)]
    if duration_sec is not None:
        cmd += ["-t", f"{duration_sec:.3f}"]
    cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero", str(dest)]
    _run(cmd)


def trim_reencode(src: Path, dest: Path,
                  start_sec: float = 0.0,
                  duration_sec: float | None = None,
                  encoder: str | None = None) -> None:
    """
    Re-encode a segment with input-side seek so output timestamps are reset to 0.
    Essential for clean concat-demuxer concatenation — output-side seek keeps
    the source timestamps (e.g. starting at 5.0s), which causes the concat
    demuxer to freeze at the join point between segments.
    """
    from src.engine.hardware import encoder_flags
    ffmpeg = str(get_ffmpeg())
    enc = encoder_flags(encoder)
    cmd = [ffmpeg, "-y"]
    if start_sec > 0.01:
        cmd += ["-ss", f"{start_sec:.3f}"]   # input-side: fast + resets timestamps to 0
    cmd += ["-i", str(src)]
    if duration_sec is not None:
        cmd += ["-t", f"{duration_sec:.3f}"]
    # -bf 0: disable B-frames so DTS == PTS on every frame. Without this,
    # B-frames produce negative DTS at the start of each segment; when the
    # concat demuxer adds the previous segment's duration, DTS goes backward
    # across the join point and the decoder produces block corruption.
    cmd += enc + ["-bf", "0", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", str(dest)]
    _run(cmd)


def _extract_last_frame(clip: Path, out_png: Path) -> None:
    """Extract the very last frame of a clip."""
    dur = get_duration(clip)
    seek = max(0.0, dur - 0.1)
    _run([str(get_ffmpeg()), "-y",
          "-ss", f"{seek:.3f}", "-i", str(clip),
          "-frames:v", "1", "-q:v", "2", str(out_png)])


def _frames_to_clip(frame_dir: Path, fps: float, out: Path) -> None:
    ffmpeg = str(get_ffmpeg())
    # Add a silent audio track so the morph clip has an audio stream —
    # concat demuxer requires all segments to have the same stream layout.
    _run([ffmpeg, "-y",
          "-framerate", str(fps),
          "-i", str(frame_dir / "%08d.png"),
          "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-bf", "0",
          "-c:a", "aac", "-b:a", "192k",
          "-shortest", str(out)])


# ── Scene similarity ──────────────────────────────────────────────────────────

def scene_similarity(clip_a: Path, clip_b: Path) -> float:
    """
    Compare last frame of A to first frame of B via histogram correlation.
    Returns 0‒1 (1 = identical).  Falls back to 0.5 on any error so the
    caller can still pick a transition gracefully.
    """
    try:
        import cv2

        def _grab(path: Path, last: bool):
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                return None
            if last:
                n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, n - 2))
            ret, frame = cap.read()
            cap.release()
            return frame if ret else None

        fa = _grab(clip_a, last=True)
        fb = _grab(clip_b, last=False)
        if fa is None or fb is None:
            return 0.5

        def _hist(img):
            hsv = cv2.cvtColor(cv2.resize(img, (64, 64)), cv2.COLOR_BGR2HSV)
            h = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
            cv2.normalize(h, h)
            return h.flatten()

        return max(0.0, float(cv2.compareHist(_hist(fa), _hist(fb),
                                               cv2.HISTCMP_CORREL)))
    except Exception:
        return 0.5


# ── Transition builders ───────────────────────────────────────────────────────

def crossfade_transition(clip_a: Path, clip_b: Path, output: Path,
                         duration: float = CROSSFADE_DURATION,
                         encoder: str | None = None) -> None:
    """
    Fast crossfade: only extracts the short overlap region from each clip,
    runs xfade on those few seconds, outputs a SHORT transition segment.

    The caller (renderer) is responsible for stream-copying the bulk of
    each clip separately — this function only produces the overlap.
    """
    ffmpeg   = str(get_ffmpeg())
    enc_flags = encoder_flags(encoder)
    # Overlap equals exactly the crossfade duration so the renderer's body
    # trimming (which also trims by xfade_dur) aligns perfectly — no gaps,
    # no duplicate frames between body and transition segments.
    overlap  = duration

    tmp_path = TEMP_DIR / "xfade_tmp"
    tmp_path.mkdir(parents=True, exist_ok=True)
    try:
        tail_a   = tmp_path / "tail_a.mp4"
        head_b   = tmp_path / "head_b.mp4"

        # Re-encode the tail of clip_a so seek is accurate.
        # stream copy snaps to the nearest keyframe — libx264 default GOP is
        # 250 frames (~8.3s), so seeking to 7.5s in a 10s clip lands at frame 0,
        # making tail_a the full clip and duplicating content already in body_N.
        dur_a = get_duration(clip_a)
        ss_a  = max(0.0, dur_a - overlap)
        trim_reencode(clip_a, tail_a, start_sec=ss_a, duration_sec=overlap,
                      encoder=encoder)

        # Head of clip_b always starts at 0 (keyframe), so stream copy is fine.
        trim_stream_copy(clip_b, head_b, duration_sec=overlap)

        # xfade only these short clips (~1-2 seconds of encode work)
        tail_dur  = get_duration(tail_a)
        head_dur  = get_duration(head_b)
        offset    = max(0.0, tail_dur - duration)

        # Clamp the crossfade duration to the shortest available input.
        # If a clip is shorter than xfade_dur (e.g. a 2s clip with Ambient
        # genre at xfade=3s), acrossfade=d=3 on a 2s clip causes FFmpeg to
        # error out.  safe_dur ensures we never ask for more than each input
        # can provide, while keeping at least a 0.1s transition.
        safe_dur = max(0.1, min(duration, tail_dur, head_dur))

        # scale2ref scales head_b to match tail_a's dimensions before xfade.
        # xfade requires identical W×H on both inputs — this handles the case
        # where clips have different resolutions (e.g. portrait video + landscape photo).
        filter_graph = (
            f"[1:v][0:v]scale2ref[vb][va];"
            f"[va][vb]xfade=transition=dissolve:"
            f"duration={safe_dur}:offset={offset}[v];"
            f"[0:a][1:a]acrossfade=d={safe_dur}[a]"
        )
        _run([ffmpeg, "-y",
              "-i", str(tail_a), "-i", str(head_b),
              "-filter_complex", filter_graph,
              "-map", "[v]", "-map", "[a]",
              ] + enc_flags + ["-bf", "0", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", str(output)])
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def morph_transition(clip_a: Path, clip_b: Path, output: Path,
                     fps: float = 30.0, num_frames: int = 8,
                     duration: float = CROSSFADE_DURATION,
                     encoder: str | None = None) -> None:
    """
    RIFE motion-morph between last frame of A and first frame of B.
    Produces a SHORT morph clip (num_frames / fps seconds).
    Falls back to crossfade using the same duration if RIFE is unavailable.
    """
    rife = get_rife()
    if not rife:
        crossfade_transition(clip_a, clip_b, output,
                             duration=duration, encoder=encoder)
        return

    model_dir  = BIN_DIR / "rife-models"
    model_path: Path | None = None
    if model_dir.exists():
        candidates = sorted(model_dir.iterdir())
        if candidates:
            model_path = candidates[0]

    tmp_path = TEMP_DIR / "morph_tmp"
    tmp_path.mkdir(parents=True, exist_ok=True)
    rife_ok = False
    try:
        frame_a   = tmp_path / "frame_a.png"
        frame_b   = tmp_path / "frame_b.png"
        morph_dir = tmp_path / "morph"
        morph_dir.mkdir(exist_ok=True)

        _extract_last_frame(clip_a, frame_a)
        _run([str(get_ffmpeg()), "-y",
              "-i", str(clip_b), "-frames:v", "1", "-q:v", "2", str(frame_b)])

        rife_cmd = [str(rife),
                    "-0", str(frame_a), "-1", str(frame_b),
                    "-o", str(morph_dir), "-n", str(num_frames)]
        if model_path:
            rife_cmd += ["-m", str(model_path)]
        _run(rife_cmd)

        _frames_to_clip(morph_dir, fps, output)
        rife_ok = True
    except Exception:
        pass
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)

    if not rife_ok:
        # RIFE failed (no Vulkan support, driver too old, etc.) — use crossfade
        crossfade_transition(clip_a, clip_b, output,
                             duration=duration, encoder=encoder)


def concat_clips(clips: list[Path], output: Path) -> None:
    """
    Stream-copy concatenation of a list of clips into one file.
    All clips must share the same codec/resolution (guaranteed since they
    were all pre-converted).  Uses the concat demuxer — no re-encode.
    """
    if not clips:
        raise ValueError("concat_clips: empty clip list")

    ffmpeg = str(get_ffmpeg())
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    list_file = TEMP_DIR / "concat_clips_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for c in clips:
            safe = str(c).replace("\\", "/")
            f.write(f"file '{safe}'\n")

    try:
        _run([ffmpeg, "-y", "-f", "concat", "-safe", "0",
              "-i", str(list_file), "-c", "copy", str(output)])
    finally:
        list_file.unlink(missing_ok=True)


# Keep old name as alias so nothing else breaks
def hard_cut_join(clips: list[Path], output: Path,
                  encoder: str | None = None) -> None:
    concat_clips(clips, output)
