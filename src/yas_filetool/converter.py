"""Логика конвертации файлов между форматами."""
from __future__ import annotations

import csv
import subprocess
import shutil
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable

from PIL import Image, ImageFile, ImageOps
from .utils.fileutils import unique_target
from .formats import *


# --- Бинарник ffmpeg ---
try:
    import imageio_ffmpeg
    _BUNDLED_FFMPEG: str | None = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    _BUNDLED_FFMPEG = None


ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None


# Значения из настроек (переопределяются в _apply_to_modules)
JPEG_QUALITY = 95
WEBP_QUALITY = 95
VIDEO_CRF = 20
VIDEO_PRESET = "medium"
AUDIO_BITRATE = "192k"


def get_ffmpeg() -> str | None:
    """Путь к ffmpeg: bundled (imageio-ffmpeg) → system."""
    if _BUNDLED_FFMPEG and Path(_BUNDLED_FFMPEG).exists():
        return _BUNDLED_FFMPEG
    return shutil.which("ffmpeg")


def _ffmpeg_audio_codecs(target_ext: str) -> list[str]:
    if target_ext == ".mp3":
        return ["-c:a", "libmp3lame", "-q:a", "2"]
    if target_ext == ".wav":
        return ["-c:a", "pcm_s16le"]
    if target_ext == ".flac":
        return ["-c:a", "flac", "-compression_level", "5"]
    if target_ext == ".ogg":
        return ["-c:a", "libvorbis", "-q:a", "5"]
    if target_ext == ".opus":
        return ["-c:a", "libopus", "-b:a", AUDIO_BITRATE]
    if target_ext == ".m4a":
        return ["-c:a", "aac", "-b:a", AUDIO_BITRATE]
    return []


def _extract_audio(src: Path, dst: Path, target_ext: str, progress_cb=None) -> None:
    """Видео → аудио: только звуковая дорожка."""
    ff = get_ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg не найден")
    duration = _probe_duration_sec(ff, src)
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(src), "-vn", *_ffmpeg_audio_codecs(target_ext),
           str(dst)]
    #subprocess.run(cmd, capture_output=True, text=True, timeout=3600, check=True)
    _run_ffmpeg_with_progress(cmd, duration, progress_cb)


def iter_media(folder: Path, recursive: bool) -> Iterable[Path]:
    it = folder.rglob("*") if recursive else folder.iterdir()
    for p in it:
        try:
            if p.is_file() and (is_image(p) or is_video(p) or is_audio(p)):
                yield p.resolve()
        except OSError:
            continue


def scan_extensions(folders: list[str], recursive: bool) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for f in folders:
        root = Path(f)
        if not root.is_dir():
            continue
        for p in iter_media(root, recursive):
            counts[p.suffix.lower()] += 1
    return dict(counts)


@dataclass
class ConversionJob:
    src: Path
    dst: Path
    target_ext: str
    action: str       # 'convert' | 'rename' | 'copy'
    overwrite: bool


def build_jobs(
    folders: list[str],
    recursive: bool,
    mapping: dict[str, str],          # {'.jpg': '.png', ...}
    overwrite: bool,
    move_dir: str | None,
    unify_target: str | None,
) -> list[ConversionJob]:
    jobs: list[ConversionJob] = []
    move_path = Path(move_dir) if move_dir else None

    for folder in folders:
        root = Path(folder)
        if not root.is_dir():
            continue
        for src in iter_media(root, recursive):
            src_ext = src.suffix.lower()
            target_ext = unify_target if unify_target else mapping.get(src_ext)
            if not target_ext or target_ext == src_ext:
                # unify+move: копия "как есть"
                if target_ext == src_ext and move_path and unify_target:
                    dst = unique_target(move_path / src.name)
                    jobs.append(ConversionJob(src, dst, src_ext, "copy", False))
                continue

            # --- Определяем тип конвертации и действие ---
            if src_ext in VIDEO_EXTENSIONS:
                if target_ext in VIDEO_EXTENSIONS:
                    action = "video"
                elif target_ext in AUDIO_EXTENSIONS:
                    action = "extract_audio"
                else:
                    continue
            elif src_ext in AUDIO_EXTENSIONS:
                if target_ext in AUDIO_EXTENSIONS:
                    action = "audio"
                else:
                    continue
            elif src_ext == ".gif":
                action = "gif_to_video" if target_ext in VIDEO_EXTENSIONS else "convert"
            else:
                if target_ext not in WRITABLE_FORMATS:
                    continue  # картинка → видео не поддерживаем
                src_pil = WRITABLE_FORMATS.get(src_ext)
                tgt_pil = WRITABLE_FORMATS.get(target_ext)
                action = "rename" if src_pil == tgt_pil else "convert"

            # --- Куда пишем ---
            if move_path:
                dst = unique_target(move_path / (src.stem + target_ext))
            else:
                dst = src.with_suffix(target_ext)
                if not overwrite:
                    dst = unique_target(dst)

            jobs.append(ConversionJob(src, dst, target_ext, action, overwrite))

    return jobs


def _prepare_for_save(img: Image.Image, target: str) -> tuple[Image.Image, dict]:
    kwargs: dict = {}
    if target == "JPEG":
        if img.mode == "P":
            img = img.convert("RGBA")
        if img.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        kwargs["quality"] = JPEG_QUALITY
        kwargs["optimize"] = True
    elif target == "BMP":
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
    elif target == "WEBP":
        kwargs["quality"] = WEBP_QUALITY
        kwargs["method"] = 4
    elif target == "PNG":
        kwargs["optimize"] = True
    elif target == "TIFF":
        kwargs["compression"] = "tiff_deflate"
    return img, kwargs


def convert_one(job: ConversionJob, progress_cb=None) -> dict:
    try:
        job.dst.parent.mkdir(parents=True, exist_ok=True)

        if job.action == "copy":
            shutil.copy2(job.src, job.dst)

        elif job.action == "rename":
            if job.overwrite:
                shutil.move(str(job.src), str(job.dst))
            else:
                shutil.copy2(job.src, job.dst)

        elif job.action == "audio":
            _convert_audio(job.src, job.dst, job.target_ext, progress_cb)
            if job.overwrite and job.src != job.dst and job.src.exists():
                job.src.unlink()

        elif job.action == "extract_audio":
            _extract_audio(job.src, job.dst, job.target_ext, progress_cb)
            if job.overwrite and job.src != job.dst and job.src.exists():
                job.src.unlink()

        elif job.action == "video":
            _convert_video(job.src, job.dst, job.target_ext, progress_cb)
            if job.overwrite and job.src != job.dst and job.src.exists():
                job.src.unlink()

        elif job.action == "gif_to_video":
            _convert_gif_to_video(job.src, job.dst, job.target_ext, progress_cb)
            if job.overwrite and job.src != job.dst and job.src.exists():
                job.src.unlink()

        elif job.action == "convert":
            with Image.open(job.src) as img:
                img = ImageOps.exif_transpose(img)
                img.load()   # форсируем чтение, чтобы не держать src открытым во время save
                target = WRITABLE_FORMATS[job.target_ext]
                img, save_kwargs = _prepare_for_save(img, target)
                img.save(job.dst, format=target, **save_kwargs)
            if job.overwrite and job.src != job.dst and job.src.exists():
                job.src.unlink()

        return {
            "status": "ok",
            "src": str(job.src),
            "dst": str(job.dst),
            "action": job.action,
            "overwrite": "yes" if job.overwrite else "no",
        }
    except Exception as e:
        return {
            "status": f"error: {type(e).__name__}: {e}",
            "src": str(job.src),
            "dst": str(job.dst),
            "action": job.action,
            "overwrite": "yes" if job.overwrite else "no",
        }


def write_report(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["src", "dst", "action", "overwrite", "status"])
        w.writeheader()
        w.writerows(rows)


def rollback(report_path: Path,
             log_cb: Callable[[str], None] | None = None
             ) -> tuple[int, int, int]:
    """Удаляет созданные файлы. Возвращает (deleted, skipped, unrecoverable)."""
    log = log_cb or (lambda _m: None)
    with open(report_path, "r", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    deleted = skipped = unrecoverable = 0
    for row in rows:
        if row.get("status") != "ok":
            continue
        overwrite = row.get("overwrite") == "yes"
        dst = Path(row["dst"])

        if overwrite:
            unrecoverable += 1
            log(f"SKIP (оригинал удалён, откат невозможен): {dst}")
            continue

        if not dst.exists():
            skipped += 1
            log(f"SKIP (нет файла): {dst}")
            continue

        try:
            dst.unlink()
            deleted += 1
            log(f"✗ удалён {dst}")
        except OSError as e:
            skipped += 1
            log(f"FAIL: {dst}: {e}")

    return deleted, skipped, unrecoverable


def _ffmpeg_video_codecs(target_ext: str) -> list[str]:
    if target_ext in (".mp4", ".m4v", ".mov"):
        return ["-c:v", "libx264", "-crf", str(VIDEO_CRF),
                "-preset", VIDEO_PRESET,
                "-c:a", "aac", "-b:a", AUDIO_BITRATE,
                "-movflags", "+faststart"]
    if target_ext == ".mkv":
        return ["-c:v", "libx264", "-crf", str(VIDEO_CRF),
                "-preset", VIDEO_PRESET,
                "-c:a", "aac", "-b:a", AUDIO_BITRATE]
    if target_ext == ".webm":
        return ["-c:v", "libvpx-vp9", "-crf", str(VIDEO_CRF),
                "-b:v", "0", "-c:a", "libopus", "-b:a", "128k"]
    if target_ext == ".avi":
        return ["-c:v", "mpeg4", "-qscale:v", "4", "-c:a", "libmp3lame"]
    return []


def _run_ffmpeg(cmd: list[str]) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg: {res.stderr.strip()[:500]}")


def _probe_duration_sec(ff: str, src: Path) -> float:
    try:
        res = subprocess.run(
            [ff, "-hide_banner", "-i", str(src)],
            capture_output=True, text=True, timeout=30)
    except Exception:
        return 0.0
    for line in res.stderr.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            try:
                t = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = t.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
            except Exception:
                return 0.0
    return 0.0


def _run_ffmpeg_with_progress(
    cmd: list[str],
    duration_sec: float,
    progress_cb=None,
) -> None:
    """Запускает ffmpeg, парсит -progress pipe:1, шлёт проценты."""
    full = cmd[:1] + ["-progress", "pipe:1", "-nostats"] + cmd[1:]
    proc = subprocess.Popen(
        full, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1)
    try:
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_ms=") and duration_sec > 0:
                try:
                    us = int(line.split("=")[1])
                    pct = min(100.0, 100.0 * us / (duration_sec * 1_000_000))
                    if progress_cb:
                        progress_cb(pct)
                except ValueError:
                    pass
            elif line == "progress=end":
                if progress_cb:
                    progress_cb(100.0)
    finally:
        proc.wait()
    if proc.returncode != 0:
        err = proc.stderr.read() or ""
        raise RuntimeError(err.strip()[:500])


def _convert_video(src: Path, dst: Path, target_ext: str, progress_cb=None) -> None:
    ff = get_ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg не найден")
    duration = _probe_duration_sec(ff, src)
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(src), *_ffmpeg_video_codecs(target_ext), str(dst)]
    _run_ffmpeg_with_progress(cmd, duration, progress_cb)


def _convert_audio(src: Path, dst: Path, target_ext: str, progress_cb=None) -> None:
    ff = get_ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg не найден")
    duration = _probe_duration_sec(ff, src)
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(src), "-vn", *_ffmpeg_audio_codecs(target_ext),
           str(dst)]
    #subprocess.run(cmd, capture_output=True, text=True, timeout=3600, check=True)
    _run_ffmpeg_with_progress(cmd, duration, progress_cb)


def _convert_gif_to_video(src: Path, dst: Path, target_ext: str, progress_cb=None) -> None:
    ff = get_ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg не найден (установите imageio-ffmpeg)")
    duration = _probe_duration_sec(ff, src)
    # без звука + pix_fmt для совместимости с плеерами
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(src), *_ffmpeg_video_codecs(target_ext),
           "-an", "-pix_fmt", "yuv420p", str(dst)]
    _run_ffmpeg_with_progress(cmd, duration, progress_cb)
