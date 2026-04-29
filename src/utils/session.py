"""Save and restore render sessions to/from session.json."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import SESSION_FILE


def _serialize(obj: Any) -> Any:
    if isinstance(obj, Path):
        return os.fsencode(obj).decode("utf-8", errors="replace")
    raise TypeError(f"Not serializable: {type(obj)}")


def save(state: dict) -> None:
    state["timestamp"] = datetime.now().isoformat()
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(
        json.dumps(state, default=_serialize, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load() -> dict | None:
    if not SESSION_FILE.exists():
        return None
    try:
        return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def clear() -> None:
    try:
        SESSION_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def has_resumable() -> bool:
    data = load()
    if not data:
        return False
    progress = data.get("render_progress", {})
    return bool(progress.get("temp_segments"))
