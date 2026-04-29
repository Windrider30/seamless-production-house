"""User-friendly error logging — never show raw tracebacks in the GUI."""
from __future__ import annotations

import logging
import traceback
from pathlib import Path

from src.config import LOG_FILE

# Use a flushing handler so every write hits disk immediately
_handler = logging.FileHandler(str(LOG_FILE), encoding="utf-8", delay=False)
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

class _FlushHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

_flushing_handler = _FlushHandler(str(LOG_FILE), encoding="utf-8", delay=False)
_flushing_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
    handlers=[_flushing_handler],
)

_FRIENDLY: dict[str, str] = {
    "codec not currently supported": "Clip #{n} uses an unsupported codec. Try converting it to H.264 first.",
    "no such file or directory":     "Clip #{n} could not be found. It may have been moved or deleted.",
    "invalid data found":            "Clip #{n} appears to be corrupted or not a valid video file.",
    "moov atom not found":           "Clip #{n} is incomplete — it may have not finished downloading.",
    "permission denied":             "Cannot write to the output folder. Check that it isn't read-only.",
    "no space left":                 "The output drive is full. Free up space and try again.",
    "different format":              "Clip #{n} is a different format from the rest. It will be pre-converted automatically.",
}


def friendly(exc: Exception, clip_index: int | None = None) -> str:
    msg = str(exc).lower()
    n = clip_index + 1 if clip_index is not None else "?"
    for key, template in _FRIENDLY.items():
        if key in msg:
            return template.replace("{n}", str(n))
    return f"An unexpected error occurred on clip #{n}. See seamless.log for details."


def log_error(exc: Exception, context: str = "") -> None:
    logging.error("%s\n%s", context, traceback.format_exc())


def log_info(msg: str) -> None:
    logging.info(msg)
