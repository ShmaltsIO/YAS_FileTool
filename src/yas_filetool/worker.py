"""QThread-обёртка над core."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from . import core


class DupFinderWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, mode, search_folders, search_recursive,
                 protected_folders, protected_recursive, dest_folder,
                 deep_check: bool = False):
        super().__init__()
        self.mode = mode
        self.search_folders = search_folders
        self.search_recursive = search_recursive
        self.protected_folders = protected_folders
        self.protected_recursive = protected_recursive
        self.dest_folder = dest_folder
        self.deep_check = deep_check

    def run(self) -> None:
        try:
            self._run_impl()
        except Exception:
            import traceback
            self.error_signal.emit(traceback.format_exc())

    def _run_impl(self) -> None:
        self.log_signal.emit(
            f"Пороги: pHash/dHash ≤ {core.PHASH_THRESHOLD}/"
            f"{core.DHASH_THRESHOLD} (256-бит), SSIM ≥ {core.SSIM_THRESHOLD}"
        )
        self.log_signal.emit("=== Сканирование ===")
        search_files = core.collect_images(self.search_folders, self.search_recursive)
        self.log_signal.emit(f"Файлов поиска: {len(search_files)}")

        protected_files: list[Path] = []
        if self.mode == "two":
            protected_files = core.collect_images(
                self.protected_folders, self.protected_recursive)
            self.log_signal.emit(f"Защищённых: {len(protected_files)}")
            p_set = set(protected_files)
            search_files = [f for f in search_files if f not in p_set]

        all_files = search_files + protected_files
        if not all_files:
            self.log_signal.emit("Нет файлов.")
            self.finished_signal.emit({"report": "", "moved": 0, "groups": 0})
            return

        self.log_signal.emit("=== Хеширование ===")

        def cb(done: int, total: int, err: str | None) -> None:
            self.progress_signal.emit(done, total)

        hashes = core.compute_hashes(all_files, progress_cb=cb)
        failed = len(all_files) - len(hashes)
        self.log_signal.emit(
            f"Хеши: {len(hashes)} / {len(all_files)}"
            + (f" (пропущено: {failed})" if failed else ""))

        self.log_signal.emit("=== Группировка + верификация ===")
        self.log_signal.emit(
            f"Верификация: каскад + deep_check={'ON' if self.deep_check else 'OFF'}")
        groups, rejected = core.group_duplicates(
            hashes, verify=True,
            deep_check=self.deep_check, log_cb=self.log_signal.emit)

        # --- CSV с отклонёнными парами ---
        dest = Path(self.dest_folder)
        dest.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        rejected_path = dest / f"rejected_{ts}.csv"
        if rejected:
            fieldnames = [
                "file_a", "file_b", "phash_dist", "dhash_dist",
                "ssim", "grad_ssim", "local_max", "local_xy",
                "psnr", "color_chi2", "fail", "error",
            ]
            with open(rejected_path, "w", newline="",
                      encoding="utf-8-sig") as fh:
                writer = csv.DictWriter(fh, fieldnames=fieldnames,
                                        extrasaction="ignore")
                writer.writeheader()
                for r in rejected:
                    row = dict(r)
                    if "local_xy" in row:
                        row["local_xy"] = str(row["local_xy"])
                    writer.writerow(row)
            self.log_signal.emit(
                f"Отклонённых пар с метриками: {len(rejected)}")
            self.log_signal.emit(f"Отчёт по отклонённым: {rejected_path}")

        self.log_signal.emit(f"Групп дубликатов: {len(groups)}")
        if not groups:
            self.finished_signal.emit({"report": "", "moved": 0, "groups": 0})
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = dest / f"report_{ts}.csv"

        self.log_signal.emit("=== Перенос ===")
        rows = core.process_groups(
            groups, set(protected_files), dest, report_path,
            move_cb=lambda s, t: self.log_signal.emit(f"→ {s}  ➜  {t}"),
        )
        moved = sum(1 for r in rows if r["moved_to"])
        self.log_signal.emit(f"Перемещено: {moved}")
        self.log_signal.emit(f"Отчёт: {report_path}")
        self.finished_signal.emit(
            {"report": str(report_path), "moved": moved, "groups": len(groups)})


class RollbackWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, report_path: str):
        super().__init__()
        self.report_path = Path(report_path)

    def run(self) -> None:
        try:
            restored, failed, rb_path = core.rollback_from_report(
                self.report_path, log_cb=self.log_signal.emit)
            self.finished_signal.emit(
                {"restored": restored, "failed": failed, "rollback_report": rb_path})
        except Exception:
            import traceback
            self.error_signal.emit(traceback.format_exc())

class RenameWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, checked_folders, use_folder_prefix, custom_prefix,
                 postfix, add_subfolder_names, strip_root, report_dir):
        super().__init__()
        self.checked_folders = checked_folders
        self.use_folder_prefix = use_folder_prefix
        self.custom_prefix = custom_prefix
        self.postfix = postfix
        self.add_subfolder_names = add_subfolder_names
        self.strip_root = strip_root
        self.report_dir = report_dir

    def run(self) -> None:
        try:
            self._run_impl()
        except Exception:
            import traceback
            self.error_signal.emit(traceback.format_exc())

    def _run_impl(self) -> None:
        from . import rename

        self.log_signal.emit("=== Построение плана ===")
        plans = rename.build_plans(
            self.checked_folders,
            self.use_folder_prefix,
            self.custom_prefix,
            self.postfix,
            self.add_subfolder_names,
            self.strip_root,
        )
        if not plans:
            self.log_signal.emit("Нет файлов для переименования.")
            self.finished_signal.emit(
                {"total": 0, "renamed": 0, "errors": 0, "report": ""})
            return

        total = sum(len(p.files) for p in plans)
        self.log_signal.emit(f"Папок: {len(plans)}, файлов: {total}")

        self.log_signal.emit("=== Проверка конфликтов ===")
        errors = rename.check_conflicts(plans)
        if errors:
            for e in errors:
                self.log_signal.emit(f"CONFLICT: {e}")
            self.error_signal.emit(
                "Обнаружены конфликты — переименование отменено. "
                "Подробности в журнале."
            )
            return

        self.log_signal.emit("=== Переименование ===")
        rows = rename.execute(plans, log_cb=self.log_signal.emit)

        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = Path(self.report_dir) / f"rename_report_{ts}.csv"
        rename.write_report(rows, report_path)

        renamed = sum(1 for r in rows if r["status"] == "renamed")
        errs = sum(1 for r in rows if r["status"].startswith("error"))
        self.log_signal.emit(
            f"Готово. Переименовано: {renamed}, ошибок: {errs}")
        self.log_signal.emit(f"Отчёт: {report_path}")
        self.finished_signal.emit({
            "total": total,
            "renamed": renamed,
            "errors": errs,
            "report": str(report_path),
        })

class ConverterWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    file_progress_signal = pyqtSignal(str, float)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, jobs, report_path):
        super().__init__()
        self.jobs = jobs
        self.report_path = Path(report_path)

    def run(self) -> None:
        try:
            self._run_impl()
        except Exception:
            import traceback
            self.error_signal.emit(traceback.format_exc())

    def _run_impl(self) -> None:
        from . import converter

        total = len(self.jobs)
        self.log_signal.emit(f"Заданий: {total}")
        rows: list[dict] = []

        for i, job in enumerate(self.jobs, 1):
            self.log_signal.emit(f"→ {job.src.name}")
            self.file_progress_signal.emit(job.src.name, 0.0)

            def cb(pct: float, name=job.src.name) -> None:
                self.file_progress_signal.emit(name, pct)

            r = converter.convert_one(job, progress_cb=cb)
            rows.append({
                "src": r["src"],
                "dst": r["dst"],
                "action": r["action"],
                "overwrite": r["overwrite"],
                "status": r["status"],
            })
            if r["status"] != "ok":
                self.log_signal.emit(f"ERROR {job.src.name}: {r['status']}")
            else:
                self.file_progress_signal.emit(job.src.name, 100.0)
                self.log_signal.emit(
                    f"✓ [{job.action}] {job.src.name} → {job.dst.name}")
            self.progress_signal.emit(i, total)

        converter.write_report(rows, self.report_path)
        ok = sum(1 for r in rows if r["status"] == "ok")
        errs = len(rows) - ok
        self.log_signal.emit(f"Готово. Успешно: {ok}, ошибок: {errs}")
        self.log_signal.emit(f"Отчёт: {self.report_path}")
        self.finished_signal.emit({
            "total": total, "ok": ok, "errors": errs,
            "report": str(self.report_path)})


class ConvertRollbackWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, report_path):
        super().__init__()
        self.report_path = Path(report_path)

    def run(self) -> None:
        try:
            from . import converter
            deleted, skipped, unrecoverable = converter.rollback(
                self.report_path, log_cb=self.log_signal.emit)
            self.finished_signal.emit({
                "deleted": deleted,
                "skipped": skipped,
                "unrecoverable": unrecoverable})
        except Exception:
            import traceback
            self.error_signal.emit(traceback.format_exc())


class AuditWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, report_path):
        super().__init__()
        self.report_path = Path(report_path)

    def run(self) -> None:
        try:
            from . import core
            out, counts = core.audit_report(
                self.report_path, log_cb=self.log_signal.emit)
            self.finished_signal.emit({
                "audit_path": str(out),
                "ok": counts["ok"],
                "suspicious": counts["suspicious"],
                "missing": counts["missing"],
            })
        except Exception:
            import traceback
            self.error_signal.emit(traceback.format_exc())
