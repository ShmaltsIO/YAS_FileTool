"""Загрузка/сохранение настроек в config/settings.toml."""
from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    import tomli_w
except ImportError:
    tomli_w = None


def _project_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


CONFIG_PATH = _project_root() / "config" / "settings.toml"


@dataclass
class DuplicateSettings:
    hash_size: int = 16
    phash_threshold: int = 5
    dhash_threshold: int = 5
    verify_size: int = 384
    ar_tolerance: float = 0.02
    mean_diff_threshold: float = 0.05
    p99_diff_threshold: float = 0.15
    psnr_hard_threshold: float = 22.0
    color_hist_threshold: float = 0.15
    ssim_threshold: float = 0.96
    gradient_ssim_threshold: float = 0.90
    deep_check_default: bool = False


@dataclass
class RenameSettings:
    default_use_folder_prefix: bool = True
    default_postfix: str = "photo"
    default_add_subfolders: bool = False
    default_strip_root: bool = False


@dataclass
class ConverterSettings:
    jpeg_quality: int = 95
    webp_quality: int = 95
    video_crf: int = 20
    video_preset: str = "medium"
    audio_bitrate: str = "192k"


@dataclass
class AppSettings:
    duplicate: DuplicateSettings = field(default_factory=DuplicateSettings)
    rename: RenameSettings = field(default_factory=RenameSettings)
    converter: ConverterSettings = field(default_factory=ConverterSettings)


_settings: AppSettings | None = None


def settings() -> AppSettings:
    global _settings
    if _settings is None:
        _settings = load()
    return _settings


def load(path: Path | None = None) -> AppSettings:
    p = path or CONFIG_PATH
    if not p.exists():
        return AppSettings()
    try:
        with open(p, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return AppSettings()

    s = AppSettings()
    for section_name in ("duplicate", "rename", "converter"):
        section = getattr(s, section_name)
        for key, value in (data.get(section_name) or {}).items():
            if hasattr(section, key):
                setattr(section, key, value)
    return s


def save(s: AppSettings, path: Path | None = None) -> Path:
    if tomli_w is None:
        raise RuntimeError("pip install tomli-w")
    p = path or CONFIG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        tomli_w.dump(asdict(s), f)
    global _settings
    _settings = s
    _apply_to_modules(s)
    return p


def _apply_to_modules(s: AppSettings) -> None:
    """Пробрасывает значения в модули, где сейчас живут константы."""
    from . import core, converter

    d = s.duplicate
    core.PHASH_THRESHOLD = d.phash_threshold
    core.DHASH_THRESHOLD = d.dhash_threshold
    core.VERIFY_SIZE = d.verify_size
    core.AR_TOLERANCE = d.ar_tolerance
    core.MEAN_DIFF_THRESHOLD = d.mean_diff_threshold
    core.P99_DIFF_THRESHOLD = d.p99_diff_threshold
    core.PSNR_HARD_THRESHOLD = d.psnr_hard_threshold
    core.COLOR_HIST_THRESHOLD = d.color_hist_threshold
    core.SSIM_THRESHOLD = d.ssim_threshold
    core.GRADIENT_SSIM_THRESHOLD = d.gradient_ssim_threshold

    c = s.converter
    converter.JPEG_QUALITY = c.jpeg_quality
    converter.WEBP_QUALITY = c.webp_quality
    converter.VIDEO_CRF = c.video_crf
    converter.VIDEO_PRESET = c.video_preset
    converter.AUDIO_BITRATE = c.audio_bitrate
