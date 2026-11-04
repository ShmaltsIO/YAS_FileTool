"""Логика переименования файлов."""
from __future__ import annotations

import csv
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class FilePlan:
    old_path: Path
    new_path: Path


@dataclass
class FolderPlan:
    folder: Path
    files: list[FilePlan]


def build_plans(
    checked_folders: list[tuple[Path, Path]],   # (folder_path, root_path)
    use_folder_prefix: bool,
    custom_prefix: str,
    postfix: str,
    add_subfolder_names: bool,
    strip_root: bool = False,
) -> list[FolderPlan]:
    """Составляет план: какое имя получит каждый файл в каждой папке."""
    plans: list[FolderPlan] = []

    for folder, root in checked_folders:
        try:
            files = sorted(
                [f for f in folder.iterdir() if f.is_file()],
                key=lambda p: p.name.lower(),
            )
        except OSError:
            continue

        if not files:
            continue

        # --- префикс ---
        if use_folder_prefix:
            if add_subfolder_names:
                try:
                    if strip_root:
                        rel = folder.relative_to(root)
                        parts = rel.parts
                        prefix = "_".join(parts) if parts else folder.name
                    else:
                        rel = folder.relative_to(root.parent)
                        prefix = "_".join(rel.parts)
                except ValueError:
                    prefix = folder.name
            else:
                prefix = folder.name
        else:
            prefix = custom_prefix

        prefix = prefix.strip("_ ").strip()
        postfix_clean = postfix.strip("_ ").strip()
        parts = [p for p in (prefix, postfix_clean) if p]
        base = "_".join(parts)

        count = len(files)
        pad = len(str(count))   # 5 → 1, 19 → 2, 122 → 3

        file_plans: list[FilePlan] = []
        for i, f in enumerate(files, 1):
            num = str(i).zfill(pad)
            stem = f"{base}_{num}" if base else num
            new_name = f"{stem}{f.suffix}"     # расширение как было
            file_plans.append(FilePlan(f, folder / new_name))

        plans.append(FolderPlan(folder, file_plans))

    return plans


def check_conflicts(plans: list[FolderPlan]) -> list[str]:
    """Проверка: уникальность целей, отсутствие чужих файлов на их месте."""
    errors: list[str] = []
    for plan in plans:
        old_names = {fp.old_path.name for fp in plan.files}
        new_names = [fp.new_path.name for fp in plan.files]

        if len(set(new_names)) != len(new_names):
            errors.append(f"{plan.folder}: коллизия новых имён (баг нумерации)")
            continue

        for fp in plan.files:
            if not fp.old_path.exists():
                errors.append(f"{fp.old_path}: файл пропал")
                continue
            if fp.new_path == fp.old_path:
                continue
            if fp.new_path.exists() and fp.new_path.name not in old_names:
                errors.append(
                    f"{plan.folder}: «{fp.new_path.name}» уже существует "
                    f"и не участвует в переименовании"
                )
    return errors


def execute(
    plans: list[FolderPlan],
    log_cb: Callable[[str], None] | None = None,
) -> list[dict]:
    """Двухпроходное переименование: old → temp → new."""
    log = log_cb or (lambda _m: None)
    rows: list[dict] = []

    for plan in plans:
        log(f"Папка: {plan.folder}  ({len(plan.files)} файлов)")

        moves: list[tuple[Path, Path, Path]] = []  # (old, temp, final)

        # --- Pass 1: old → temp ---
        for fp in plan.files:
            if fp.old_path == fp.new_path:
                rows.append({
                    "folder": str(plan.folder),
                    "old_name": fp.old_path.name,
                    "new_name": fp.new_path.name,
                    "status": "skipped_same",
                })
                continue
            temp = plan.folder / f".rename_tmp_{uuid.uuid4().hex[:12]}"
            try:
                fp.old_path.rename(temp)
                moves.append((fp.old_path, temp, fp.new_path))
            except OSError as e:
                rows.append({
                    "folder": str(plan.folder),
                    "old_name": fp.old_path.name,
                    "new_name": fp.new_path.name,
                    "status": f"error_pass1: {e}",
                })

        # --- Pass 2: temp → final ---
        for old, temp, final in moves:
            try:
                temp.rename(final)
                rows.append({
                    "folder": str(plan.folder),
                    "old_name": old.name,
                    "new_name": final.name,
                    "status": "renamed",
                })
            except OSError as e:
                try:
                    temp.rename(old)          # попытка отката
                except OSError:
                    pass
                rows.append({
                    "folder": str(plan.folder),
                    "old_name": old.name,
                    "new_name": final.name,
                    "status": f"error_pass2: {e}",
                })

    return rows


def write_report(rows: list[dict], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["folder", "old_name", "new_name", "status"],
        )
        writer.writeheader()
        writer.writerows(rows)