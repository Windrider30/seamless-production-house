"""Audio mixing: L-cut (audio leads video), music layering, fade-in/out."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from src.utils.path_checker import get_ffmpeg, get_ffprobe

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, creationflags=CREATE_NO_WINDOW,
                   capture_output=True)


def apply_lcut(video_path: Path, next_audio_path: Path, output: Path,
               lcut_seconds: float = 3.0,
               crossfade_seconds: float = 1.5) -> None:
    """
    L-cut: next clip's audio begins lcut_seconds before the video cut.
    Result: a clip whose audio fades from current → next while video still
    shows the current clip (cinema-standard technique).
    """
    ffmpeg = str(get_ffmpeg())
    # Mix: current audio fades out, next audio fades in, starting at
    # (duration - lcut_seconds)
    filter_complex = (
        f"[0:a]afifo[oa];"
        f"[1:a]atrim=0:{lcut_seconds},afade=t=in:st=0:d={crossfade_seconds}[na];"
        f"[oa]afade=t=out:st=-{lcut_seconds}:d={lcut_seconds}[fa];"
        f"[fa][na]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    cmd = [
        ffmpeg, "-y",
        "-i", str(video_path),
        "-i", str(next_audio_path),
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",
        str(output),
    ]
    _run(cmd)


def mix_music_under_video(video_path: Path, music_files: list[Path],
                          output: Path,
                          music_volume: float = 0.8,
                          fade_in_seconds: float = 2.0) -> None:
    """
    Loop / concatenate music tracks under the video for the full duration.
    Applies a 2-second fade-in on the first track (Bug #11).
    """
    if not music_files:
        # No music — just copy video through
        import shutil
        shutil.copy2(str(video_path), str(output))
        return

    ffmpeg = str(get_ffmpeg())

    # Concatenate music tracks using the concat FILTER (not demuxer).
    # The concat demuxer requires all inputs to share the same codec and
    # sample rate — mixed formats (MP3 + WAV + FLAC) or different sample
    # rates cause it to fail with AVERROR(ENOENT).  The concat filter
    # decodes each file independently and resamples to a common rate.
    import tempfile as tf
    loop_audio = Path(tf.mktemp(suffix="_music_loop.aac"))
    try:
        n = len(music_files)
        inputs: list[str] = []
        for mf in music_files:
            inputs += ["-i", str(mf)]

        if n == 1:
            fc = "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[aout]"
        else:
            concat_in = "".join(f"[{i}:a]" for i in range(n))
            fc = (
                f"{concat_in}concat=n={n}:v=0:a=1,"
                f"aformat=sample_rates=44100:channel_layouts=stereo[aout]"
            )

        _run([
            ffmpeg, "-y", *inputs,
            "-filter_complex", fc,
            "-map", "[aout]",
            "-c:a", "aac", "-b:a", "192k",
            str(loop_audio),
        ])

        # Replace the video's audio stream entirely with the music.
        # Original clip audio is discarded — for a montage app the music IS
        # the audio track, and mixing clip audio in causes the original sounds
        # (including any music already in a video clip) to bleed through.
        # -stream_loop -1 on the music input loops it indefinitely so it always
        # fills the full video duration. -shortest then cuts at video end.
        filter_complex = (
            f"[1:a]afade=t=in:st=0:d={fade_in_seconds},"
            f"volume={music_volume}[aout]"
        )

        cmd = [
            ffmpeg, "-y",
            "-i", str(video_path),
            "-stream_loop", "-1",   # loop music to fill full video length
            "-i", str(loop_audio),
            "-filter_complex", filter_complex,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(output),
        ]
        _run(cmd)
    finally:
        loop_audio.unlink(missing_ok=True)


def _get_duration(path: Path) -> float:
    """Quick ffprobe duration check."""
    import json
    probe = get_ffprobe()
    if not probe:
        return 0.0
    try:
        r = subprocess.run(
            [str(probe), "-v", "quiet", "-print_format", "json",
             "-show_format", str(path)],
            capture_output=True, text=True, timeout=8,
            creationflags=CREATE_NO_WINDOW,
        )
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def normalize_audio(video_path: Path, output: Path,
                    target_lufs: float = -14.0) -> None:
    """Single-pass loudness normalization + fade-out at end."""
    ffmpeg = str(get_ffmpeg())

    # Get actual duration so we can place the fade-out correctly
    duration = _get_duration(video_path)
    fade_dur = 3.0
    fade_start = max(0.0, duration - fade_dur)

    af = (
        f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11,"
        f"afade=t=out:st={fade_start:.3f}:d={fade_dur}"
    )

    _run([
        ffmpeg, "-y", "-i", str(video_path),
        "-af", af,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        # Write the moov atom (seek index) at the START of the file.
        # Without this the index lives at the end — any player opening the
        # file must seek to the very end to read the index before it can begin
        # decoding.  On a slow drive (USB, NAS, SD card) this causes the player
        # to appear completely locked up for many seconds or indefinitely.
        "-movflags", "+faststart",
        str(output),
    ])
