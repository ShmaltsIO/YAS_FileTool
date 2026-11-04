"""Поддерживаемые форматы"""
from __future__ import annotations

from pathlib import Path


IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".jfif", ".png", ".webp", ".bmp", ".gif",
    ".tiff", ".tif", ".heic", ".heif", ".avif",
}

VIDEO_EXTENSIONS = {
    ".mp4", ".avi", ".mkv", ".mov", ".webm", ".m4v",
    ".wmv", ".flv", ".mpg", ".mpeg", ".ts", ".3gp", ".ogv",
}

AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".opus",
    ".m4a", ".wma", ".aiff", ".aif", ".alac",
}

# Расширения, которые PIL умеет ПИСАТЬ (без доп. плагинов)
WRITABLE_FORMATS = {
    ".jpg": "JPEG", ".jpeg": "JPEG", ".jfif": "JPEG",
    ".png": "PNG", ".webp": "WEBP",
    ".bmp": "BMP", ".tiff": "TIFF", ".tif": "TIFF",
}

# None → «не конвертировать»
TARGET_FORMAT_CHOICES = [
    (None, "— не конвертировать —"),
    (".jpg", "JPEG (.jpg)"),
    (".png", "PNG (.png)"),
    (".webp", "WEBP (.webp)"),
    (".bmp", "BMP (.bmp)"),
    (".tiff", "TIFF (.tiff)"),
]

VIDEO_TARGETS = {
    ".mp4": "MP4 (H.264/AAC)",
    ".mkv": "MKV (H.264/AAC)",
    ".webm": "WEBM (VP9/Opus)",
    ".mov": "MOV (H.264/AAC)",
    ".avi": "AVI (MPEG-4)",
}

# GIF умеет и в картинки (первый кадр), и в видео (анимация)
GIF_TARGETS = {
    ".png": "PNG (первый кадр)",
    ".jpg": "JPEG (первый кадр)",
    ".webp": "WEBP (первый кадр)",
    ".mp4": "MP4 (анимация)",
    ".webm": "WEBM (анимация)",
    ".mkv": "MKV (анимация)",
}

AUDIO_TARGETS = {
    ".mp3": "MP3",
    ".wav": "WAV",
    ".flac": "FLAC",
    ".ogg": "OGG (Vorbis)",
    ".opus": "OPUS",
    ".m4a": "M4A (AAC)",
}

# Для unify-режима — только реальные форматы
UNIFY_TARGET_CHOICES = [c for c in TARGET_FORMAT_CHOICES if c[0] is not None]

def is_image(p: Path) -> bool:
    return p.suffix.lower() in IMAGE_EXTENSIONS

def is_video(p: Path) -> bool:
    return p.suffix.lower() in VIDEO_EXTENSIONS

def is_audio(p: Path) -> bool:
    return p.suffix.lower() in AUDIO_EXTENSIONS


def targets_for(src_ext: str) -> dict[str, str]:
    """Какой набор целей показывать для данного исходного расширения."""
    if src_ext in VIDEO_EXTENSIONS:
        # видео + аудио (извлечение звука)
        return {**VIDEO_TARGETS, **{k: f"{v} (звук)" for k, v in AUDIO_TARGETS.items()}}
    if src_ext in AUDIO_EXTENSIONS:
        return {k: v for k, v in AUDIO_TARGETS.items() if k != src_ext}
    if src_ext == ".gif":
        return GIF_TARGETS
    return {e: l for e, l in TARGET_FORMAT_CHOICES if e is not None}
