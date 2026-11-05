"""Воспроизведение встроенных звуков: wav в assets/sounds/."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _sounds_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "yas_filetool" / "assets" / "sounds"
    return Path(__file__).parent / "assets" / "sounds"


def _play_file_windows(path: Path) -> bool:
    try:
        import winsound
        winsound.PlaySound(str(path),
                           winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    except Exception:
        return False


def _play_file_unix(path: Path) -> bool:
    players = [
        ("paplay", [str(path)]),
        ("aplay", ["-q", str(path)]),
        ("afplay", [str(path)]),                         # macOS
        ("ffplay", ["-nodisp", "-autoexit",
                    "-loglevel", "quiet", str(path)]),   # всегда есть через imageio-ffmpeg
    ]
    for exe, args in players:
        if not shutil.which(exe):
            continue
        try:
            subprocess.Popen(
                [exe, *args],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            return True
        except Exception:
            continue
    return False


def play_system(kind: str) -> None:
    """kind ∈ {'success', 'error', 'info'}."""
    path = _sounds_dir() / f"{kind}.wav"
    if path.exists():
        if sys.platform == "win32":
            if _play_file_windows(path):
                return
        elif _play_file_unix(path):
            return
    # fallback — Qt beep
    try:
        from PyQt6.QtWidgets import QApplication
        QApplication.beep()
    except Exception:
        pass
