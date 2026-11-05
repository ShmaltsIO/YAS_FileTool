"""Версия приложения: pyproject.toml + git-инфо."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

try:
    from importlib.metadata import version as _pkg_version, PackageNotFoundError
except ImportError:
    _pkg_version = None
    PackageNotFoundError = Exception

PKG_NAME = "yas_filetool"


def _read_from_init() -> Optional[str]:
    try:
        from . import __version__
        return __version__
    except Exception:
        return None


def _read_from_pyproject() -> Optional[str]:
    try:
        import tomllib
        root = Path(__file__).resolve().parents[2]
        p = root / "pyproject.toml"
        if not p.exists():
            return None
        with open(p, "rb") as f:
            data = tomllib.load(f)
        return ((data.get("project") or {}).get("version")
                or (data.get("tool", {}).get("poetry") or {}).get("version"))
    except Exception:
        return None


def _git_info() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """(hash, commit_count, tag) — то, что удалось получить."""
    try:
        cwd = Path(__file__).resolve().parents[2]
        if not (cwd / ".git").exists():
            return None, None, None

        def run(*args: str) -> str:
            return subprocess.check_output(
                ["git", *args], cwd=cwd, stderr=subprocess.DEVNULL,
                text=True).strip()

        h = run("rev-parse", "--short", "HEAD")
        n = run("rev-list", "--count", "HEAD")
        try:
            tag = run("describe", "--tags", "--exact-match")
        except subprocess.CalledProcessError:
            tag = None
        return h, n, tag
    except Exception:
        return None, None, None


def base_version() -> str:
    if _pkg_version is not None:
        try:
            return _pkg_version(PKG_NAME)
        except PackageNotFoundError:
            pass
    return _read_from_init() or _read_from_pyproject() or "0.0.0"


def full_version() -> str:
    """'v1.1.0' на теге, иначе '1.0.0+42.gabc1234'."""
    v = base_version()
    h, n, tag = _git_info()
    if tag:
        return tag
    if h and n:
        return f"{v}+{n}.g{h}"
    return v


def version_lines() -> list[str]:
    h, n, tag = _git_info()
    lines = [f"Версия: {base_version()}"]
    if tag:
        lines.append(f"Релиз: {tag}")
    elif h:
        lines.append(f"Сборка: {n} коммитов, HEAD {h}")
    else:
        lines.append("Сборка: релиз (git-инфо недоступно)")
    return lines
