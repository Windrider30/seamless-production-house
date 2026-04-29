"""
Seamless Production House — entry point.
Run with: C:/Python313/python.exe main.py
"""
import sys
import os

# Ensure UTF-8 for all file I/O (Bug #14)
if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path so `src` is importable when run as .exe
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.gui.app import App


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
