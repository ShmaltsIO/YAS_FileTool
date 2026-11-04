"""Чистая логика: скан, хеши, группировка, перенос и отчёт."""
from __future__ import annotations

import csv
import shutil
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Iterable

import imagehash
import numpy as np
from PIL import Image, ImageFile, ImageOps
from scipy.ndimage import gaussian_filter, sobel

from .utils.fileutils import _sha256, unique_target
from .formats import IMAGE_EXTENSIONS

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None


# --- Хеши ---
HASH_SIZE = 16
PHASH_THRESHOLD = 5
DHASH_THRESHOLD = 5

# --- Верификация ---
VERIFY_SIZE = 384
AR_TOLERANCE = 0.02

# Всегда включённые (быстрые) метрики
MEAN_DIFF_THRESHOLD  = 0.05   # средняя |a-b| по всем пикселям
P99_DIFF_THRESHOLD   = 0.15   # 99-й перцентиль |a-b| — ловит локальные вставки
PSNR_HARD_THRESHOLD  = 22.0   # ниже — точно разные (порог "грубого" отсева)
COLOR_HIST_THRESHOLD = 0.15   # chi-square, довольно свободный
SSIM_THRESHOLD       = 0.95   # основная проверка

# Только при deep_check=True (медленные)
GRADIENT_SSIM_THRESHOLD = 0.90


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def collect_images(folders: Iterable[str], recursive: bool) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for folder in folders:
        root = Path(folder)
        if not root.exists() or not root.is_dir():
            continue
        it = root.rglob("*") if recursive else root.iterdir()
        for p in it:
            if p.is_file() and is_image(p):
                try:
                    rp = p.resolve()
                except OSError:
                    continue
                if rp not in seen:
                    seen.add(rp)
                    out.append(rp)
    return out


# ---------------------------------------------------------------------------
# Хеши
# ---------------------------------------------------------------------------

def _hash_one(path_str: str):
    try:
        with Image.open(path_str) as img:
            img = ImageOps.exif_transpose(img)
            if min(img.size) < 32:
                return path_str, None, None, "image too small"
            # 512 достаточно для hash_size=16 (нужно 64×64 внутри)
            img.thumbnail((512, 512))
            img = img.convert("RGB")
            ph = imagehash.phash(img, hash_size=HASH_SIZE)
            dh = imagehash.dhash(img, hash_size=HASH_SIZE)
        return path_str, ph, dh, None
    except Exception as e:
        return path_str, None, None, f"{type(e).__name__}: {e}"


def compute_hashes(
    paths: list[Path],
    progress_cb: Callable[[int, int, str | None], None] | None = None,
    max_workers: int = 8,
) -> dict[Path, tuple[imagehash.ImageHash, imagehash.ImageHash]]:
    result: dict[Path, tuple[imagehash.ImageHash, imagehash.ImageHash]] = {}
    total = len(paths)
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_hash_one, str(p)): p for p in paths}
        for fut in as_completed(futures):
            path_str, ph, dh, err = fut.result()
            if ph is not None and dh is not None:
                result[Path(path_str)] = (ph, dh)
            done += 1
            if progress_cb:
                progress_cb(done, total, err)
    return result


# ---------------------------------------------------------------------------
# 256-битный Хэмминг (матрица)
# ---------------------------------------------------------------------------

def _hash_to_chunks(h: imagehash.ImageHash, n_chunks: int = 4) -> list[int]:
    v = int(str(h), 16)
    return [(v >> (64 * i)) & ((1 << 64) - 1) for i in range(n_chunks)]


def _popcount_u64(x: np.ndarray) -> np.ndarray:
    x = x - ((x >> np.uint64(1)) & np.uint64(0x5555555555555555))
    x = (x & np.uint64(0x3333333333333333)) + ((x >> np.uint64(2)) & np.uint64(0x3333333333333333))
    x = (x + (x >> np.uint64(4))) & np.uint64(0x0F0F0F0F0F0F0F0F)
    return (x * np.uint64(0x0101010101010101)) >> np.uint64(56)


def _hamming_256(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a: (N, 4) uint64, b: (M, 4) uint64 -> (N, M) uint16."""
    total = np.zeros((a.shape[0], b.shape[0]), dtype=np.uint16)
    for c in range(4):
        xor = np.bitwise_xor(a[:, c, None], b[None, :, c])
        total += _popcount_u64(xor).astype(np.uint16)
    return total


# ---------------------------------------------------------------------------
# Второй этап: Метрики
# ---------------------------------------------------------------------------

def _to_np_rgb(img: Image.Image, size: int) -> np.ndarray:
    return np.asarray(
        img.convert("RGB").resize((size, size), Image.LANCZOS),
        dtype=np.float32) / 255.0


def _ssim_2d(a: np.ndarray, b: np.ndarray, sigma: float = 1.0) -> float:
    c1, c2 = 0.01 ** 2, 0.03 ** 2
    mu_a = gaussian_filter(a, sigma)
    mu_b = gaussian_filter(b, sigma)
    mu_a2, mu_b2 = mu_a * mu_a, mu_b * mu_b
    mu_ab = mu_a * mu_b
    sig_a2 = gaussian_filter(a * a, sigma) - mu_a2
    sig_b2 = gaussian_filter(b * b, sigma) - mu_b2
    sig_ab = gaussian_filter(a * b, sigma) - mu_ab
    num = (2 * mu_ab + c1) * (2 * sig_ab + c2)
    den = (mu_a2 + mu_b2 + c1) * (sig_a2 + sig_b2 + c2)
    return float(np.mean(num / den))


def _ssim_rgb(a: np.ndarray, b: np.ndarray, sigma: float = 1.0) -> float:
    return float(np.mean([_ssim_2d(a[..., c], b[..., c], sigma) for c in range(3)]))


def _gradient_map(gray: np.ndarray) -> np.ndarray:
    gx = sobel(gray, axis=1)
    gy = sobel(gray, axis=0)
    g = np.sqrt(gx * gx + gy * gy)
    m = g.max()
    return g / m if m > 1e-8 else g


def _hsv_hist_chi2(img: Image.Image) -> np.ndarray:
    arr = np.asarray(img.convert("HSV"), dtype=np.uint8)
    hist, _ = np.histogramdd(
        arr.reshape(-1, 3),
        bins=(32, 16, 16),
        range=((0, 256), (0, 256), (0, 256)),
    )
    h = hist.flatten().astype(np.float64)
    s = h.sum()
    return h / s if s > 0 else h


def _verify_pair(path1: Path, path2: Path,
                 deep_check: bool = False) -> tuple[bool, dict]:
    """Каскадная проверка с early exit.

    Порядок: cheap → expensive. Как только какая-то метрика провалилась —
    дальше не считаем.
    """
    try:
        with Image.open(path1) as im1, Image.open(path2) as im2:
            im1 = ImageOps.exif_transpose(im1)
            im2 = ImageOps.exif_transpose(im2)
            ar1 = im1.width / im1.height
            ar2 = im2.width / im2.height
            ar_diff = abs(ar1 - ar2) / max(ar1, ar2)
            if ar_diff > AR_TOLERANCE:
                return False, {"fail": "aspect_ratio",
                               "ar_diff": round(ar_diff, 4)}

            a = _to_np_rgb(im1, VERIFY_SIZE)
            b = _to_np_rgb(im2, VERIFY_SIZE)
            h1 = _hsv_hist_chi2(im1)
            h2 = _hsv_hist_chi2(im2)

        metrics: dict = {}

        # --- 1. PSNR (1 мс, грубый отсев) ---
        mse = float(np.mean((a - b) ** 2))
        psnr = 100.0 if mse < 1e-10 else 10.0 * np.log10(1.0 / mse)
        metrics["psnr"] = round(psnr, 2)
        if psnr < PSNR_HARD_THRESHOLD:
            metrics["fail"] = "psnr"
            return False, metrics

        # --- 2. Mean + P99 (2 мс, ловит локальные вставки) ---
        diff = np.abs(a - b).mean(axis=2)  # (H, W), 0..1
        mean_diff = float(diff.mean())
        p99_diff = float(np.percentile(diff, 99))
        metrics["mean_diff"] = round(mean_diff, 4)
        metrics["p99_diff"] = round(p99_diff, 4)
        if mean_diff > MEAN_DIFF_THRESHOLD:
            metrics["fail"] = "mean_diff"
            return False, metrics
        if p99_diff > P99_DIFF_THRESHOLD:
            metrics["fail"] = "p99_diff"
            return False, metrics

        # --- 3. Color histogram (5 мс) ---
        chi2 = float(np.sum((h1 - h2) ** 2 / (h1 + h2 + 1e-10)))
        metrics["color_chi2"] = round(chi2, 4)
        if chi2 > COLOR_HIST_THRESHOLD:
            metrics["fail"] = "color"
            return False, metrics

        # --- 4. SSIM (15 мс, основная проверка) ---
        ssim_full = _ssim_rgb(a, b, sigma=1.0)
        metrics["ssim"] = round(ssim_full, 4)
        if ssim_full < SSIM_THRESHOLD:
            metrics["fail"] = "ssim"
            return False, metrics

        # --- 5. Gradient SSIM (20 мс, только при deep_check) ---
        if deep_check:
            ga = _gradient_map(a.mean(axis=2))
            gb = _gradient_map(b.mean(axis=2))
            grad_ssim = _ssim_2d(ga, gb, sigma=1.0)
            metrics["grad_ssim"] = round(grad_ssim, 4)
            if grad_ssim < GRADIENT_SSIM_THRESHOLD:
                metrics["fail"] = "grad_ssim"
                return False, metrics

        return True, metrics

    except Exception as e:
        return False, {"fail": "error",
                       "error": f"{type(e).__name__}: {e}"}


# ---------------------------------------------------------------------------
# Группировка
# ---------------------------------------------------------------------------

def group_duplicates(
    hashes: dict[Path, tuple[imagehash.ImageHash, imagehash.ImageHash]],
    verify: bool = True,
    deep_check: bool = False,
    log_cb: Callable[[str], None] | None = None,
) -> tuple[list[list[Path]], list[dict]]:
    """Возвращает (группы, отклонённые_пары с метриками)."""
    n = len(hashes)
    if n < 2:
        return [], []
    items = list(hashes.items())
    ph_arr = np.array([_hash_to_chunks(h[0]) for _, h in items], dtype=np.uint64)
    dh_arr = np.array([_hash_to_chunks(h[1]) for _, h in items], dtype=np.uint64)

    ph_d = _hamming_256(ph_arr, ph_arr)
    dh_d = _hamming_256(dh_arr, dh_arr)
    cand = (ph_d <= PHASH_THRESHOLD) & (dh_d <= DHASH_THRESHOLD)
    np.fill_diagonal(cand, False)

    rows, cols = np.where(np.triu(cand, k=1))
    pairs = list(zip(rows.tolist(), cols.tolist()))

    rejected: list[dict] = []
    accepted: list[tuple[int, int]] = []

    for i, j in pairs:
        p1 = items[i][0]
        p2 = items[j][0]
        if verify:
            ok, m = _verify_pair(p1, p2, deep_check=deep_check)
            entry = {
                "file_a": str(p1),
                "file_b": str(p2),
                "phash_dist": int(ph_d[i, j]),
                "dhash_dist": int(dh_d[i, j]),
                **m,
            }
            if not ok:
                rejected.append(entry)
                continue
            accepted.append((i, j))
        else:
            accepted.append((i, j))

    if log_cb:
        log_cb(
            f"Кандидатов по хешам: {len(pairs)}, "
            f"прошли верификацию: {len(accepted)}, "
            f"отклонено: {len(rejected)}")
        # Сводка причин отказа
        from collections import Counter
        reasons = Counter()
        for r in rejected:
            for reason in (r.get("fail", "unknown")).split(","):
                key = reason.split("<")[0].split(">")[0]
                reasons[key] += 1
        for k, v in reasons.most_common():
            log_cb(f"  отклонено по {k}: {v}")

    parent = list(range(n))
    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    for i, j in accepted:
        union(i, j)

    groups: dict[int, list[Path]] = defaultdict(list)
    for i, (p, _) in enumerate(items):
        groups[find(i)].append(p)
    return [g for g in groups.values() if len(g) > 1], rejected


# ---------------------------------------------------------------------------
# Перенос + отчёт + хеш
# ---------------------------------------------------------------------------


def process_groups(
    groups: list[list[Path]],
    protected_set: set[Path],
    dest_folder: Path,
    report_path: Path,
    move_cb: Callable[[Path, Path], None] | None = None,
) -> list[dict]:
    dest_folder.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    for gid, group in enumerate(groups, start=1):
        protected = [f for f in group if f in protected_set]
        movable = [f for f in group if f not in protected_set]
        if not movable:
            continue

        if protected:
            original = protected[0]
            to_move = movable
            reason = "matched_protected"
        else:
            original = min(movable, key=lambda p: (p.stat().st_mtime, str(p).lower()))
            to_move = [f for f in movable if f != original]
            reason = "internal_duplicate"

        for src in to_move:
            try:
                st = src.stat()          # метаданные ДО переноса
                sha = _sha256(src)       # хеш ДО переноса
                tgt = unique_target(dest_folder / src.name)
                shutil.move(str(src), str(tgt))
                rows.append({
                    "group": gid,
                    "moved_from": str(src),
                    "moved_to": str(tgt),
                    "matched_original": str(original),
                    "reason": reason,
                    "size": st.st_size,
                    "sha256": sha,
                })
                if move_cb:
                    move_cb(src, tgt)
            except Exception as e:
                rows.append({
                    "group": gid,
                    "moved_from": str(src),
                    "moved_to": "",
                    "matched_original": str(original),
                    "reason": f"error: {type(e).__name__}: {e}",
                    "size": 0,
                    "sha256": "",
                })

    with open(report_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "group", "moved_from", "moved_to",
            "matched_original", "reason", "size", "sha256",
        ])
        writer.writeheader()
        writer.writerows(rows)

    return rows


# ---------------------------------------------------------------------------
# Откат по отчёту
# ---------------------------------------------------------------------------

def rollback_from_report(
    report_path: Path,
    log_cb: Callable[[str], None] | None = None,
) -> tuple[int, int, str]:
    """Возвращает (restored, failed, путь_к_отчёту_отката)."""
    log = log_cb or (lambda _m: None)

    with open(report_path, "r", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    restored = 0
    failed = 0
    rb_rows: list[dict] = []

    for row in rows:
        moved_to = (row.get("moved_to") or "").strip()
        moved_from = (row.get("moved_from") or "").strip()
        expected_sha = (row.get("sha256") or "").strip()
        if not moved_to or not moved_from:
            continue

        src = Path(moved_to)
        dst = Path(moved_from)

        if not src.exists():
            log(f"SKIP (нет файла): {src}")
            failed += 1
            rb_rows.append({"from": str(src), "to": str(dst), "status": "missing"})
            continue

        if dst.exists():
            cand = unique_target(dst.parent / dst.name)
            log(f"NOTE (цель занята, переименую): {dst} → {cand}")
            dst = cand

        if expected_sha:
            try:
                actual = _sha256(src)
            except Exception as e:
                log(f"SKIP (ошибка чтения): {src}: {e}")
                failed += 1
                rb_rows.append({"from": str(src), "to": str(dst), "status": "read_error"})
                continue
            if actual != expected_sha:
                log(f"SKIP (sha256 не совпал): {src}")
                failed += 1
                rb_rows.append({"from": str(src), "to": str(dst), "status": "hash_mismatch"})
                continue

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            log(f"✓ {src} → {dst}")
            restored += 1
            rb_rows.append({"from": str(src), "to": str(dst), "status": "restored"})
        except Exception as e:
            log(f"FAIL: {src}: {e}")
            failed += 1
            rb_rows.append({"from": str(src), "to": str(dst), "status": f"error: {e}"})

    rb_path = report_path.with_name(report_path.stem + "_rollback" + report_path.suffix)
    with open(rb_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=["from", "to", "status"])
        writer.writeheader()
        writer.writerows(rb_rows)

    return restored, failed, str(rb_path)


def audit_report(report_path: Path,
                 log_cb: Callable[[str], None] | None = None
                 ) -> tuple[Path, dict]:
    """Прогоняет верификацию по парам moved_from ↔ matched_original."""
    log = log_cb or (lambda _m: None)
    with open(report_path, "r", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    results: list[dict] = []
    counts = {"ok": 0, "suspicious": 0, "missing": 0}

    for row in rows:
        moved_to = row.get("moved_to", "").strip()
        original = row.get("matched_original", "").strip()
        moved_from = row.get("moved_from", "").strip()
        if not moved_to or not original:
            continue
        if not Path(moved_to).exists() or not Path(original).exists():
            counts["missing"] += 1
            results.append({
                "original": original,
                "moved": moved_to,
                "verdict": "missing_file",
                "details": "",
            })
            continue

        ok, m = _verify_pair(Path(moved_to), Path(original))
        verdict = "ok" if ok else "suspicious"
        counts[verdict] += 1
        log(f"[{verdict.upper()}] {Path(moved_to).name} ↔ {Path(original).name}  {m}")
        results.append({
            "original": original,
            "moved": moved_to,
            "verdict": verdict,
            "details": m.get("fail", ""),
            "ssim": m.get("ssim", ""),
            "grad_ssim": m.get("grad_ssim", ""),
            "local_max": m.get("local_max", ""),
            "psnr": m.get("psnr", ""),
        })

    out = report_path.with_name(report_path.stem + "_audit.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["original", "moved", "verdict", "details",
                        "ssim", "grad_ssim", "local_max", "psnr"],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(results)
    return out, counts
