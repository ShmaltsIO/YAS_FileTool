"""Обёртки над QMessageBox + мультивыбор папок."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QFileDialog, QListView, QTreeView, QAbstractItemView, QMessageBox,
)


# ---------------------------------------------------------------------------
# Универсальные обёртки
# ---------------------------------------------------------------------------

def confirm(parent, title: str, text: str) -> bool:
    """Да/Нет. Возвращает True, если пользователь нажал «Да»."""
    return QMessageBox.question(
        parent, title, text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,   # default — «Нет»
    ) == QMessageBox.StandardButton.Yes


def info(parent, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


def error(parent, title: str, text: str) -> None:
    QMessageBox.critical(parent, title, text)


def warn(parent, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


def info_box(parent, title: str, lines: list[str]) -> None:
    """Универсальное «готово» с набором строк статистики."""
    QMessageBox.information(parent, title, "\n".join(lines))


# ---------------------------------------------------------------------------
# Специфичные подтверждения (чтобы не собирать текст по 5 раз)
# ---------------------------------------------------------------------------

def confirm_overwrite(parent, n_jobs: int) -> bool:
    return confirm(
        parent, "Подтвердите перезапись",
        f"Перезапись ВКЛЮЧЕНА.\n\n"
        f"Оригиналы будут удалены после создания новых файлов.\n"
        f"Заданий: {n_jobs}\n\n"
        f"Откат для этой операции невозможен (данные будут "
        f"окончательно перезаписаны). Продолжить?",
    )


def confirm_rollback_duplicates(parent, report_path: str) -> bool:
    return confirm(
        parent, "Подтверждение",
        f"Восстановить файлы по отчёту?\n{report_path}\n\n"
        f"Проверка SHA256 защитит от перезаписи изменённых файлов.",
    )


def confirm_convert_rollback(parent, report_path: str) -> bool:
    return confirm(
        parent, "Подтверждение",
        f"Удалить файлы, созданные конвертером по этому отчёту?\n"
        f"{report_path}\n\n"
        f"Оригиналы (если ещё на месте) и файлы, созданные с "
        f"перезаписью, затронуты НЕ будут.",
    )


def confirm_rename(parent, n_folders: int, n_files: int,
                   report_dir: str) -> bool:
    return confirm(
        parent, "Подтверждение",
        f"Переименовать файлы в {n_folders} папках?\n"
        f"Всего файлов: {n_files}\n\n"
        f"Отчёт: {report_dir}\n\n"
        f"Программа ничего не удаляет. Все переименования атомарные "
        f"(через временные имена).",
    )


# ---------------------------------------------------------------------------
# Диалоги типа "готово"
# ---------------------------------------------------------------------------

def show_duplicates_done(parent, info: dict) -> None:
    info_box(parent, "Готово", [
        f"Групп дубликатов: {info.get('groups', 0)}",
        f"Перемещено файлов: {info.get('moved', 0)}",
        f"Отчёт: {info.get('report') or '(нет)'}",
    ])


def show_rename_done(parent, info: dict) -> None:
    info_box(parent, "Готово", [
        f"Всего файлов: {info.get('total', 0)}",
        f"Переименовано: {info.get('renamed', 0)}",
        f"Ошибок: {info.get('errors', 0)}",
        f"Отчёт: {info.get('report') or '(нет)'}",
    ])


def show_convert_done(parent, info: dict) -> None:
    info_box(parent, "Готово", [
        f"Всего заданий: {info.get('total', 0)}",
        f"Успешно: {info.get('ok', 0)}",
        f"Ошибок: {info.get('errors', 0)}",
        f"Отчёт: {info.get('report') or '(нет)'}",
    ])


def show_rollback_done(parent, info: dict) -> None:
    info_box(parent, "Откат завершён", [
        f"Восстановлено: {info.get('restored', 0)}",
        f"Пропущено/ошибок: {info.get('failed', 0)}",
        f"Отчёт откока: {info.get('rollback_report') or '(нет)'}",
    ])


def show_audit_done(parent, info: dict) -> None:
    info_box(parent, "Аудит завершён", [
        f"Совпало: {info.get('ok', 0)}",
        f"Подозрительных: {info.get('suspicious', 0)}  ← проверить вручную",
        f"Файл(ы) отсутствуют: {info.get('missing', 0)}",
        f"Отчёт: {info.get('audit_path') or '(нет)'}",
    ])


def show_convert_rollback_done(parent, info: dict) -> None:
    info_box(parent, "Откат завершён", [
        f"Удалено файлов: {info.get('deleted', 0)}",
        f"Пропущено/ошибок: {info.get('skipped', 0)}",
        f"Невосстановимых (overwrite): {info.get('unrecoverable', 0)}",
    ])


# ---------------------------------------------------------------------------
# Выбор папок (мультивыбор через non-native диалог)
# ---------------------------------------------------------------------------

def choose_directories(parent, title: str) -> list[str]:
    """Диалог выбора ОДНОЙ или НЕСКОЛЬКИХ папок (Ctrl/Shift+клик)."""
    dialog = QFileDialog(parent, title)
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
    for view in dialog.findChildren((QListView, QTreeView)):
        view.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
    if dialog.exec() == QFileDialog.DialogCode.Accepted:
        return dialog.selectedFiles()
    return []


def choose_file(parent, title: str, filter: str = "CSV (*.csv);;Все файлы (*)") -> str:
    """Возвращает путь к файлу или пустую строку."""
    path, _ = QFileDialog.getOpenFileName(parent, title, "", filter)
    return path
