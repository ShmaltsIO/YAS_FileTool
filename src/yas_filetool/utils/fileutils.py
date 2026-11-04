"""Общие файловые хелперы."""
from __future__ import annotations

import hashlib
from pathlib import Path


def unique_target(dst: Path) -> Path:
    if not dst.exists():
        return dst
    stem, suffix = dst.stem, dst.suffix
    i = 1
    while True:
        cand = dst.parent / f"{stem}_{i}{suffix}"
        if not cand.exists():
            return cand
        i += 1


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
