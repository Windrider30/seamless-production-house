from pathlib import Path
import sys

APP_NAME = "Seamless Production House"
APP_VERSION = "1.0.0"

# Resolve app root whether running as .exe or .py
if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).parent.parent

BIN_DIR = APP_DIR / "bin"
ASSETS_DIR = APP_DIR / "assets"
TEMP_DIR = APP_DIR / "temp"
SESSION_FILE = APP_DIR / "session.json"
LOG_FILE = APP_DIR / "seamless.log"

# Dev fallback path for FFmpeg (not used in distributed build)
DEV_FFMPEG_PATH = (
    Path("C:/Program Files/ShareX/ffmpeg.exe") if sys.platform == "win32" else None
)

# ── Colors (charcoal / emerald) ──────────────────────────────────────────────
C = {
    "bg":           "#1a1a2e",
    "bg2":          "#16213e",
    "card":         "#1e2a40",
    "card2":        "#243050",
    "border":       "#2d3a50",
    "emerald":      "#00d2a8",
    "emerald_dk":   "#009e7e",
    "emerald_lt":   "#33ffda",
    "text":         "#e8edf5",
    "text2":        "#8a9ab5",
    "muted":        "#556070",
    "success":      "#00d2a8",
    "warning":      "#f5a623",
    "error":        "#e74c3c",
    "white":        "#ffffff",
}

# ── Render constants ─────────────────────────────────────────────────────────
SEGMENT_DURATION    = 300   # 5 minutes per segment
L_CUT_SECONDS       = 3.0
CROSSFADE_DURATION  = 2.0
RIFE_FRAMES         = 8     # interpolated frames per morph
AUDIO_FADE_IN_SEC   = 2.0
SCENE_CHANGE_THRESH = 0.35  # 0‒1; below = scenes too different → crossfade

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv", ".webm", ".flv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
CLIP_EXTENSIONS  = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS
AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".flac", ".m4a", ".ogg", ".wma"}

# ── Genre configs ────────────────────────────────────────────────────────────
# transition: "morph" | "crossfade" | "cut"
GENRES: dict[str, dict] = {
    "Lofi": {
        "transition": "morph", "l_cut": True, "audio_fade": 1.5,
        "xfade_dur": 1.5, "scene_thresh": 0.40,
        "desc": "Smooth morphs with warm, lazy audio transitions",
    },
    "Jazz": {
        "transition": "morph", "l_cut": True, "audio_fade": 2.0,
        "xfade_dur": 1.5, "scene_thresh": 0.35,
        "desc": "Fluid morphs with sophisticated L-cuts",
    },
    "Country": {
        "transition": "morph", "l_cut": True, "audio_fade": 2.0,
        "xfade_dur": 2.0, "scene_thresh": 0.45,
        "desc": "Warm morphs with golden-hour storytelling pacing",
    },
    "Cinematic": {
        "transition": "crossfade", "l_cut": True, "audio_fade": 2.5,
        "xfade_dur": 2.5, "scene_thresh": 0.50,
        "desc": "Deep crossfades with cinematic breathing room",
    },
    "Ambient": {
        "transition": "crossfade", "l_cut": True, "audio_fade": 3.0,
        "xfade_dur": 3.0, "scene_thresh": 0.60,
        "desc": "Ultra-smooth dissolves for atmospheric content",
    },
    "Classical": {
        "transition": "crossfade", "l_cut": True, "audio_fade": 3.5,
        "xfade_dur": 3.0, "scene_thresh": 0.55,
        "desc": "Elegant dissolves with orchestral pacing",
    },
    "R&B / Soul": {
        "transition": "morph", "l_cut": True, "audio_fade": 2.0,
        "xfade_dur": 2.0, "scene_thresh": 0.40,
        "desc": "Smooth morphs with soulful audio blending",
    },
    "Pop": {
        "transition": "morph", "l_cut": True, "audio_fade": 1.0,
        "xfade_dur": 1.0, "scene_thresh": 0.35,
        "desc": "Polished morphs for bright, mainstream content",
    },
    "Reggae / Chill": {
        "transition": "crossfade", "l_cut": True, "audio_fade": 2.5,
        "xfade_dur": 2.0, "scene_thresh": 0.50,
        "desc": "Laid-back dissolves for island vibes",
    },
    "Hip-Hop": {
        "transition": "cut", "l_cut": True, "audio_fade": 0.8,
        "xfade_dur": 0.5, "scene_thresh": 0.25,
        "desc": "Punchy cuts with urban energy",
    },
    "Vlog": {
        "transition": "cut", "l_cut": True, "audio_fade": 0.5,
        "xfade_dur": 0.5, "scene_thresh": 0.30,
        "desc": "Casual cuts for authentic storytelling",
    },
    "High-Energy": {
        "transition": "cut", "l_cut": False, "audio_fade": 0.3,
        "xfade_dur": 0.3, "scene_thresh": 0.20,
        "desc": "Hard cuts synced to the beat",
    },
    "Rock": {
        "transition": "cut", "l_cut": False, "audio_fade": 0.4,
        "xfade_dur": 0.5, "scene_thresh": 0.20,
        "desc": "Hard-hitting cuts with raw energy",
    },
    "EDM": {
        "transition": "cut", "l_cut": False, "audio_fade": 0.2,
        "xfade_dur": 0.2, "scene_thresh": 0.15,
        "desc": "Rapid cuts built for peak-energy drops",
    },
    "Metal": {
        "transition": "cut", "l_cut": False, "audio_fade": 0.1,
        "xfade_dur": 0.1, "scene_thresh": 0.10,
        "desc": "Brutal hard cuts for maximum intensity",
    },
    "K-Pop": {
        "transition": "morph", "l_cut": False, "audio_fade": 0.5,
        "xfade_dur": 0.5, "scene_thresh": 0.25,
        "desc": "Fast morphs with polished K-pop aesthetics",
    },
    "Documentary": {
        "transition": "crossfade", "l_cut": True, "audio_fade": 2.0,
        "xfade_dur": 2.0, "scene_thresh": 0.50,
        "desc": "Clean dissolves with journalistic pacing",
    },
    "Corporate / Product": {
        "transition": "crossfade", "l_cut": False, "audio_fade": 1.5,
        "xfade_dur": 1.5, "scene_thresh": 0.45,
        "desc": "Professional transitions for brand content",
    },
    "Nature / Travel": {
        "transition": "crossfade", "l_cut": True, "audio_fade": 2.5,
        "xfade_dur": 2.5, "scene_thresh": 0.50,
        "desc": "Sweeping dissolves for scenic content",
    },
}

GENRE_NAMES = list(GENRES.keys())

# ── Content types ────────────────────────────────────────────────────────────
CONTENT_TYPES: dict[str, dict] = {
    "Music Video": {
        "clip_hold": 3.0, "beat_sync": True,
        "desc": "Beat-matched cuts for music-driven content",
    },
    "Product Showcase": {
        "clip_hold": 5.0, "beat_sync": False,
        "desc": "Longer holds to showcase product details",
    },
    "Lofi / Ambient": {
        "clip_hold": 8.0, "beat_sync": False,
        "desc": "Slow-paced for background or ambient content",
    },
}

CONTENT_TYPE_NAMES = list(CONTENT_TYPES.keys())

# ── Resolution / FPS options ─────────────────────────────────────────────────
RESOLUTION_OPTIONS = {
    "Source (Match Clips)": None,
    "3840×2160  (4K)":      (3840, 2160),
    "2560×1440  (1440p)":   (2560, 1440),
    "1920×1080  (1080p)":   (1920, 1080),
    "1280×720   (720p)":    (1280, 720),
    "1080×1920  (Vertical 1080p)": (1080, 1920),
    "1080×1080  (Square)":  (1080, 1080),
}

FPS_OPTIONS = {
    "Source (Match Clips)": None,
    "24 fps  (Cinematic)":  24,
    "30 fps  (Standard)":   30,
    "60 fps  (Smooth)":     60,
    "120 fps (HFR)":        120,
}

# ── Downloader URLs ──────────────────────────────────────────────────────────
RIFE_GITHUB_REPO   = "nihui/rife-ncnn-vulkan"
FFMPEG_RELEASE_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
_exe = ".exe" if sys.platform == "win32" else ""
FFMPEG_EXE_NAME  = f"ffmpeg{_exe}"
FFPROBE_EXE_NAME = f"ffprobe{_exe}"
RIFE_EXE_NAME    = f"rife-ncnn-vulkan{_exe}"
