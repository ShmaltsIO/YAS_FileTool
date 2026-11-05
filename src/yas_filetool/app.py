"""GUI на PyQt6: три вкладки — поиск дубликатов, переименование пачки файлов и конвертация файлов."""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QAction, QKeySequence, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QCheckBox, QRadioButton,
    QButtonGroup, QLabel, QProgressBar, QMessageBox,
    QGroupBox, QLineEdit, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QSpinBox, QDoubleSpinBox,
)

from .converter import get_ffmpeg
from .worker import (
    DupFinderWorker, RollbackWorker, RenameWorker,
    ConverterWorker, ConvertRollbackWorker, AuditWorker,
)

from .gui.widgets import *
from .gui.dialogs import (confirm_rollback_duplicates, confirm_rename,
                         confirm_overwrite, confirm_convert_rollback,
                         show_duplicates_done, show_rename_done,
                         show_convert_done, show_convert_rollback_done,
                         show_rollback_done, show_audit_done)


SUPPORT_URL = "https://boosty.to/"
REPO_URL = "https://github.com/ShmaltsIO"
BUG_REPORT_URL = "https://github.com/ShmaltsIO/YAS_FileTool/issues"


def _play(kind: str) -> None:
    """kind ∈ {'success', 'error'}."""
    from . import config
    s = config.settings().sound
    if not s.enabled:
        return
    if kind == "success" and not s.on_success:
        return
    if kind == "error" and not s.on_error:
        return
    from .sounds import play_system
    play_system(kind)


# ===========================================================================
# Вкладка 1: поиск дубликатов (старая логика)
# ===========================================================================

class DuplicateFinderTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.worker = None
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        top = QWidget()
        lay = QVBoxLayout(top)  # всё, что было в self, теперь в top
        lay.setContentsMargins(0, 0, 0, 0)

        mode_box = QGroupBox("Режим работы")
        ml = QVBoxLayout(mode_box)
        self.rb_single = QRadioButton(
            "Одна папка: найти все дубликаты в папках поиска")
        self.rb_two = QRadioButton(
            "Две папки: дубликаты ищутся в поисковых папках с учётом "
            "защищённых (защищённые не двигаются)")
        self.rb_single.setChecked(True)
        self.mode_grp = QButtonGroup()
        self.mode_grp.addButton(self.rb_single)
        self.mode_grp.addButton(self.rb_two)
        ml.addWidget(self.rb_single)
        ml.addWidget(self.rb_two)
        lay.addWidget(mode_box)

        sb = QGroupBox("1. Папки поиска (отсюда переносим дубликаты)")
        sl = QVBoxLayout(sb)
        self.search_list = FolderList()
        sl.addWidget(self.search_list)
        self.cb_search_rec = QCheckBox("Рекурсивно (включая подпапки)")
        self.cb_search_rec.setChecked(True)
        sl.addWidget(self.cb_search_rec)
        lay.addWidget(sb)

        self.prot_box = QGroupBox("2. Защищённые папки (не трогаем!)")
        pl = QVBoxLayout(self.prot_box)
        self.prot_list = FolderList()
        pl.addWidget(self.prot_list)
        self.cb_prot_rec = QCheckBox("Рекурсивно (включая подпапки)")
        self.cb_prot_rec.setChecked(True)
        pl.addWidget(self.cb_prot_rec)
        lay.addWidget(self.prot_box)

        db = QGroupBox("3. Куда перемещать дубликаты (сюда же пишется отчёт)")
        dl = QHBoxLayout(db)
        self.dest_edit = QLineEdit()
        self.dest_edit.setReadOnly(True)
        self.dest_btn = QPushButton("Выбрать…")
        dl.addWidget(self.dest_edit)
        dl.addWidget(self.dest_btn)
        self.dest_btn.clicked.connect(self._choose_dest)
        lay.addWidget(db)

        self.start_btn = QPushButton("Начать поиск и перемещение")
        self.start_btn.setMinimumHeight(36)
        self.start_btn.clicked.connect(self._start)
        lay.addWidget(self.start_btn)

        self.cb_deep = QCheckBox(
            "Глубокая проверка (gradient SSIM) — медленнее, меньше ложных")
        self.cb_deep.setChecked(False)  # по умолчанию выкл
        self.cb_deep.setToolTip(
            "Дополнительная проверка на структурные различия (края/контуры).\n"
            "Стоит ~20 мс на пару. Включайте, если всё ещё видите ложные.")
        lay.addWidget(self.cb_deep)

        rb_box = QGroupBox("Откат")
        rbl = QHBoxLayout(rb_box)
        self.rollback_btn = QPushButton("Откатить по отчёту…")
        self.rollback_btn.clicked.connect(self._start_rollback)
        rbl.addWidget(self.rollback_btn)
        lay.addWidget(rb_box)

        self.audit_btn = QPushButton("Проверить отчёт…")
        self.audit_btn.clicked.connect(self._start_audit)
        rbl.addWidget(self.audit_btn)

        self.progress = QProgressBar()
        lay.addWidget(self.progress)

        # lay.addWidget(QLabel("Журнал:"))
        # self.log = QTextEdit()
        # self.log.setReadOnly(True)
        # lay.addWidget(self.log, 1)

        self.log = CollapsibleLog()
        #lay.addWidget(self.log, 1)
        outer.addWidget(make_scroll_splitter(top, self.log), 1)

        self.rb_single.toggled.connect(self._on_mode_change)
        self._on_mode_change()

    def _on_mode_change(self) -> None:
        self.prot_box.setEnabled(self.rb_two.isChecked())

    def _choose_dest(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Выберите папку назначения")
        if d:
            self.dest_edit.setText(d)

    def _validate(self) -> bool:
        search = self.search_list.folders()
        dest = self.dest_edit.text()
        if not search:
            QMessageBox.warning(self, "Ошибка", "Добавьте хотя бы одну папку поиска.")
            return False
        if not dest:
            QMessageBox.warning(self, "Ошибка", "Выберите папку назначения.")
            return False

        def _resolve(p: str) -> Path | None:
            try:
                return Path(p).resolve()
            except OSError:
                return None

        dest_p = _resolve(dest)
        if dest_p is None:
            QMessageBox.warning(self, "Ошибка", "Некорректная папка назначения.")
            return False

        groups_to_check = [("поиска", search)]
        if self.rb_two.isChecked():
            prot = self.prot_list.folders()
            if not prot:
                QMessageBox.warning(
                    self, "Ошибка",
                    "Добавьте хотя бы одну защищённую папку (режим двух папок).")
                return False
            groups_to_check.append(("защищённых", prot))

            for s in search:
                sp = _resolve(s)
                if sp is None:
                    continue
                for p in prot:
                    pp = _resolve(p)
                    if pp is None:
                        continue
                    if sp == pp or sp in pp.parents or pp in sp.parents:
                        QMessageBox.warning(
                            self, "Ошибка",
                            f"Папки пересекаются (нельзя в двух категориях):\n"
                            f"{s}\n{p}")
                        return False

        for label, lst in groups_to_check:
            for f in lst:
                fp = _resolve(f)
                if fp is None:
                    continue
                if dest_p == fp or fp in dest_p.parents:
                    QMessageBox.warning(
                        self, "Ошибка",
                        f"Папка назначения не должна быть внутри папки {label}:\n"
                        f"{dest}\n← {f}")
                    return False
        return True

    def _start(self) -> None:
        if not self._validate():
            return
        self.log.clear()
        self.progress.setValue(0)
        self.start_btn.setEnabled(False)
        self.rollback_btn.setEnabled(False)

        mode = "two" if self.rb_two.isChecked() else "single"
        self.worker = DupFinderWorker(
            mode=mode,
            search_folders=self.search_list.folders(),
            search_recursive=self.cb_search_rec.isChecked(),
            protected_folders=self.prot_list.folders() if mode == "two" else [],
            protected_recursive=self.cb_prot_rec.isChecked(),
            dest_folder=self.dest_edit.text(),
            deep_check=self.cb_deep.isChecked(),
        )
        self.worker.log_signal.connect(self.log.append)
        self.worker.progress_signal.connect(self._on_progress)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.error_signal.connect(self._on_error)
        self.worker.start()

    def _on_progress(self, done: int, total: int) -> None:
        if total:
            self.progress.setMaximum(total)
            self.progress.setValue(done)

    def _on_finished(self, info: dict) -> None:
        self.start_btn.setEnabled(True)
        self.rollback_btn.setEnabled(True)
        self.progress.setValue(self.progress.maximum())
        show_duplicates_done(self, info)
        _play("success")

    def _on_error(self, tb: str) -> None:
        self.start_btn.setEnabled(True)
        self.rollback_btn.setEnabled(True)
        self.log.append("ОШИБКА:\n" + tb)
        QMessageBox.critical(self, "Ошибка",
                             "Произошла ошибка. Подробности в журнале.")
        _play("error")

    def _start_rollback(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите CSV-отчёт", "", "CSV (*.csv);;Все файлы (*)")
        if not path:
            return
        if not confirm_rollback_duplicates(self, path):
            return
        self.log.clear()
        self.rollback_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.worker = RollbackWorker(path)
        self.worker.log_signal.connect(self.log.append)
        self.worker.finished_signal.connect(self._on_rollback_done)
        self.worker.error_signal.connect(self._on_error)
        self.worker.start()

    def _on_rollback_done(self, info: dict) -> None:
        self.rollback_btn.setEnabled(True)
        self.start_btn.setEnabled(True)
        show_rollback_done(self, info)
        _play("success")

    def _start_audit(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите CSV-отчёт дубликатов", "",
            "CSV (*.csv);;Все файлы (*)")
        if not path:
            return
        self.log.clear()
        self.audit_btn.setEnabled(False)
        self.worker = AuditWorker(path)
        self.worker.log_signal.connect(self.log.append)
        self.worker.finished_signal.connect(self._on_audit_done)
        self.worker.error_signal.connect(self._on_error)
        self.worker.start()

    def _on_audit_done(self, info: dict) -> None:
        self.audit_btn.setEnabled(True)
        show_audit_done(self, info)
        _play("success")


# ===========================================================================
# Вкладка 2: переименование файлов
# ===========================================================================

class RenameTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.worker = None
        self.roots: list[Path] = []
        self.excluded: set[str] = set()   # пути, снятые с галочки
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        #lay = QVBoxLayout(self)
        outer = QVBoxLayout(self)

        top = QWidget()
        lay = QVBoxLayout(top)  # всё, что было в self, теперь в top
        lay.setContentsMargins(0, 0, 0, 0)

        lay.addWidget(QLabel(
            "Папки для переименования. Подпапки появляются, если включён "
            "режим «рекурсивно». Снимите галочку, чтобы исключить папку."))

        self.tree = QTreeWidget()
        self.tree.setMinimumHeight(140)
        self.tree.setHeaderLabels(["Папка", "Файлов"])
        self.tree.setColumnWidth(0, 520)
        self.tree.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self.tree, 1)

        row = QHBoxLayout()
        self.add_btn = QPushButton("Добавить папку…")
        self.remove_btn = QPushButton("Удалить выбранные корни")
        self.rescan_btn = QPushButton("Обновить дерево")
        row.addWidget(self.add_btn)
        row.addWidget(self.remove_btn)
        row.addWidget(self.rescan_btn)
        row.addStretch()
        lay.addLayout(row)

        # --- Параметры имён ---
        opt = QGroupBox("Параметры имён")
        ol = QVBoxLayout(opt)

        self.cb_recursive = QCheckBox(
            "Рекурсивно (показывать подпапки в дереве)")
        self.cb_recursive.setChecked(True)
        ol.addWidget(self.cb_recursive)

        self.cb_use_folder = QCheckBox(
            "Начинать имя файла с названия папки")
        self.cb_use_folder.setChecked(True)
        ol.addWidget(self.cb_use_folder)

        r = QHBoxLayout()
        r.addWidget(QLabel("Свой префикс:"))
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText("например: img")
        self.prefix_edit.setEnabled(False)
        r.addWidget(self.prefix_edit)
        ol.addLayout(r)

        r = QHBoxLayout()
        r.addWidget(QLabel("Постфикс:"))
        self.postfix_edit = QLineEdit()
        self.postfix_edit.setPlaceholderText("например: photo")
        r.addWidget(self.postfix_edit)
        ol.addLayout(r)

        self.cb_add_subfolders = QCheckBox(
            "Добавлять имена подпапок в имя файла")
        self.cb_add_subfolders.setChecked(False)
        self.cb_add_subfolders.setEnabled(False)
        ol.addWidget(self.cb_add_subfolders)

        self.cb_strip_root = QCheckBox(  # NEW
            "Убирать имя корневой папки из подпапок")
        self.cb_strip_root.setChecked(False)
        self.cb_strip_root.setEnabled(False)
        self.cb_strip_root.setToolTip(
            "Пример: файл в summer_2026/Heap получит префикс «Heap», "
            "а не «summer_2026_Heap».")
        ol.addWidget(self.cb_strip_root)

        lay.addWidget(opt)

        # --- Куда отчёт ---
        r = QHBoxLayout()
        r.addWidget(QLabel("Отчёт сохранить в:"))
        self.report_edit = QLineEdit()
        self.report_edit.setPlaceholderText(
            "по умолчанию — рядом с первой добавленной папкой")
        self.report_btn = QPushButton("…")
        r.addWidget(self.report_edit)
        r.addWidget(self.report_btn)
        lay.addLayout(r)

        # --- Кнопки ---
        r = QHBoxLayout()
        self.preview_btn = QPushButton("Предпросмотр")
        self.rename_btn = QPushButton("Переименовать")
        self.rename_btn.setMinimumHeight(34)
        r.addWidget(self.preview_btn)
        r.addWidget(self.rename_btn)
        lay.addLayout(r)

        lay.addWidget(QLabel("Предпросмотр (первые 5 файлов из каждой папки):"))
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(180)
        lay.addWidget(self.preview)

        # lay.addWidget(QLabel("Журнал:"))
        # self.log = QTextEdit()
        # self.log.setReadOnly(True)
        # lay.addWidget(self.log, 1)
        self.log = CollapsibleLog()
        #lay.addWidget(self.log, 1)

        outer.addWidget(make_scroll_splitter(top, self.log), 1)

        # --- Сигналы ---
        self.add_btn.clicked.connect(self._add_folder)
        self.remove_btn.clicked.connect(self._remove_selected_roots)
        self.rescan_btn.clicked.connect(self._rebuild_tree)
        self.cb_recursive.toggled.connect(self._on_option_changed)
        self.cb_use_folder.toggled.connect(self._on_option_changed)
        self.report_btn.clicked.connect(self._choose_report_dir)
        self.preview_btn.clicked.connect(self._do_preview)
        self.rename_btn.clicked.connect(self._do_rename)
        self.cb_add_subfolders.toggled.connect(self._on_option_changed)

        self._on_option_changed()

    # ------------------------------------------------------------------
    def _on_option_changed(self) -> None:
        use_folder = self.cb_use_folder.isChecked()
        recursive = self.cb_recursive.isChecked()
        self.prefix_edit.setEnabled(not use_folder)

        add_sub_available = use_folder and recursive
        self.cb_add_subfolders.setEnabled(add_sub_available)

        if not add_sub_available:
            self.cb_add_subfolders.setChecked(False)

        # strip_root доступен только когда включён add_subfolders
        strip_available = add_sub_available and self.cb_add_subfolders.isChecked()
        self.cb_strip_root.setEnabled(strip_available)
        if not strip_available:
            self.cb_strip_root.setChecked(False)

        self._rebuild_tree()

    def _choose_report_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Куда сохранять отчёты")
        if d:
            self.report_edit.setText(d)

    # ------------------------------------------------------------------
    def _add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Выберите папку")
        if not d:
            return
        p = Path(d).resolve()
        if p in self.roots:
            return
        self.roots.append(p)
        self._rebuild_tree()

    def _remove_selected_roots(self) -> None:
        changed = False
        for item in self.tree.selectedItems():
            if item.parent() is not None:
                continue
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if not data:
                continue
            p = Path(data[0])
            if p in self.roots:
                self.roots.remove(p)
                changed = True
        if changed:
            self._rebuild_tree()

    # ------------------------------------------------------------------
    def _rebuild_tree(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        for root in self.roots:
            self._add_root_to_tree(root)
        self.tree.blockSignals(False)

    def _add_root_to_tree(self, root: Path) -> None:
        item = QTreeWidgetItem([root.name or str(root), ""])
        item.setData(0, Qt.ItemDataRole.UserRole, (str(root), str(root)))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        state = (Qt.CheckState.Unchecked
                 if str(root) in self.excluded
                 else Qt.CheckState.Checked)
        item.setCheckState(0, state)
        self.tree.addTopLevelItem(item)

        if self.cb_recursive.isChecked():
            self._populate_children(item, root, root)
        else:
            self._update_file_count(item, root)

    def _populate_children(self, parent_item, folder: Path, root: Path) -> None:
        self._update_file_count(parent_item, folder)
        try:
            subdirs = sorted(
                [d for d in folder.iterdir() if d.is_dir()],
                key=lambda p: p.name.lower())
        except OSError:
            return
        for sub in subdirs:
            child = QTreeWidgetItem([sub.name, ""])
            child.setData(0, Qt.ItemDataRole.UserRole, (str(sub), str(root)))
            child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            state = (Qt.CheckState.Unchecked
                     if str(sub) in self.excluded
                     else Qt.CheckState.Checked)
            child.setCheckState(0, state)
            parent_item.addChild(child)
            self._populate_children(child, sub, root)

    def _update_file_count(self, item: QTreeWidgetItem, folder: Path) -> None:
        try:
            count = sum(1 for f in folder.iterdir() if f.is_file())
        except OSError:
            count = 0
        item.setText(1, str(count))

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        path = data[0]
        if item.checkState(0) == Qt.CheckState.Checked:
            self.excluded.discard(path)
        else:
            self.excluded.add(path)

    # ------------------------------------------------------------------
    def _collect_checked(self) -> list[tuple[Path, Path]]:
        result: list[tuple[Path, Path]] = []

        def walk(item: QTreeWidgetItem) -> None:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and item.checkState(0) == Qt.CheckState.Checked:
                result.append((Path(data[0]), Path(data[1])))
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return result

    def _current_params(self) -> tuple:
        return (
            self.cb_use_folder.isChecked(),
            self.prefix_edit.text(),
            self.postfix_edit.text(),
            self.cb_add_subfolders.isChecked() and self.cb_use_folder.isChecked(),
            self.cb_strip_root.isChecked() and self.cb_add_subfolders.isChecked(),
        )

    def _do_preview(self) -> None:
        from . import rename
        checked = self._collect_checked()
        if not checked:
            QMessageBox.warning(self, "Ошибка", "Нет отмеченных папок.")
            return

        use_folder, prefix, postfix, add_sub, strip_root = self._current_params()
        plans = rename.build_plans(checked, use_folder, prefix, postfix, add_sub, strip_root)
        if not plans:
            self.preview.setPlainText("Нет файлов для переименования.")
            return

        lines: list[str] = []
        for plan in plans:
            lines.append(f"📁 {plan.folder}   ({len(plan.files)} файлов)")
            for fp in plan.files[:5]:
                lines.append(f"    {fp.old_path.name}  →  {fp.new_path.name}")
            if len(plan.files) > 5:
                lines.append(f"    … и ещё {len(plan.files) - 5}")
            lines.append("")

        self.preview.setPlainText("\n".join(lines))

        errors = rename.check_conflicts(plans)
        if errors:
            self.preview.append("\n⚠ Конфликты (переименование будет отменено):")
            for e in errors:
                self.preview.append(f"   • {e}")

    def _do_rename(self) -> None:
        from . import rename
        checked = self._collect_checked()
        if not checked:
            QMessageBox.warning(self, "Ошибка", "Нет отмеченных папок.")
            return

        # отчёт
        report_dir = self.report_edit.text().strip()
        if not report_dir:
            if self.roots:
                report_dir = str(self.roots[0].parent)
            else:
                report_dir = str(Path.home())

        # быстрая проверка конфликтов до подтверждения
        use_folder, prefix, postfix, add_sub, strip_root = self._current_params()
        plans = rename.build_plans(checked, use_folder, prefix, postfix, add_sub, strip_root)
        if not plans:
            QMessageBox.information(self, "Нет файлов",
                                    "В отмеченных папках нет файлов.")
            return
        errors = rename.check_conflicts(plans)
        if errors:
            QMessageBox.critical(
                self, "Конфликты",
                "Переименование невозможно:\n\n" + "\n".join(errors[:10])
                + ("\n…" if len(errors) > 10 else ""))
            return

        total = sum(len(p.files) for p in plans)
        if not confirm_rename(self, len(checked), total, report_dir):
            return

        self.log.clear()
        self.rename_btn.setEnabled(False)
        self.preview_btn.setEnabled(False)

        self.worker = RenameWorker(
            checked, use_folder, prefix, postfix,
            add_sub, strip_root, report_dir)
        self.worker.log_signal.connect(self.log.append)
        self.worker.finished_signal.connect(self._on_rename_done)
        self.worker.error_signal.connect(self._on_rename_error)
        self.worker.start()

    def _on_rename_done(self, info: dict) -> None:
        self.rename_btn.setEnabled(True)
        self.preview_btn.setEnabled(True)
        self._rebuild_tree()
        show_rename_done(self, info)
        _play("success")

    def _on_rename_error(self, tb: str) -> None:
        self.rename_btn.setEnabled(True)
        self.preview_btn.setEnabled(True)
        self.log.append("ОШИБКА:\n" + tb)
        QMessageBox.critical(self, "Ошибка",
                             "Подробности в журнале.")
        _play("error")


class ConverterTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.worker = None
        self._build_ui()

    def _build_ui(self) -> None:
        from . import converter

        #lay = QVBoxLayout(self)
        outer = QVBoxLayout(self)

        top = QWidget()
        lay = QVBoxLayout(top)  # всё, что было в self, теперь в top
        lay.setContentsMargins(0, 0, 0, 0)

        # --- Индикатор ffMPEG ---
        ff = get_ffmpeg()
        ff_status = QLabel(
            f"ffmpeg: {'✓ ' + Path(ff).name if ff else '✗ не найден — видео недоступно'}")
        ff_status.setStyleSheet(
            "color: #2f855a;" if ff else "color: #c53030;")
        lay.addWidget(ff_status)

        # --- 1. Папки ---
        fb = QGroupBox("1. Папки с файлами")
        fl = QVBoxLayout(fb)
        self.folder_list = FolderList()
        fl.addWidget(self.folder_list)
        self.cb_recursive = QCheckBox("Рекурсивно (включая подпапки)")
        self.cb_recursive.setChecked(True)
        self.cb_recursive.toggled.connect(self._scan_formats)
        fl.addWidget(self.cb_recursive)
        self.rescan_btn = QPushButton("Обновить список форматов")
        self.rescan_btn.clicked.connect(self._scan_formats)
        fl.addWidget(self.rescan_btn)
        lay.addWidget(fb)

        # автоматически сканировать при добавлении/удалении папок
        self.folder_list.list.model().rowsInserted.connect(
            lambda *_: self._scan_formats())
        self.folder_list.list.model().rowsRemoved.connect(
            lambda *_: self._scan_formats())

        # --- 2. Форматы ---
        df = QGroupBox("2. Форматы и целевые значения")
        dl = QVBoxLayout(df)

        r = QHBoxLayout()
        self.cb_unify = QCheckBox("Привести к единому формату:")
        self.cb_unify.toggled.connect(self._on_unify_toggled)
        r.addWidget(self.cb_unify)
        self.unify_combo = QComboBox()
        for ext, label in converter.UNIFY_TARGET_CHOICES:
            self.unify_combo.addItem(label, ext)
        self.unify_combo.setEnabled(False)
        r.addWidget(self.unify_combo)
        r.addStretch()
        dl.addLayout(r)

        self.format_table = QTableWidget(0, 3)
        self.format_table.setMinimumHeight(100)
        self.format_table.setHorizontalHeaderLabels(
            ["Расширение", "Файлов", "Целевой формат"])
        self.format_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self.format_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self.format_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        self.format_table.verticalHeader().setVisible(False)
        dl.addWidget(self.format_table, 1)
        lay.addWidget(df, 1)

        # --- 3. Опции ---
        ob = QGroupBox("3. Опции")
        ol = QVBoxLayout(ob)
        self.cb_overwrite = QCheckBox(
            "Перезаписать исходный файл "
            "(⚠ оригинал будет удалён после конвертации)")
        ol.addWidget(self.cb_overwrite)

        r = QHBoxLayout()
        self.cb_move = QCheckBox("Перенести файлы нового формата в:")
        self.cb_move.toggled.connect(self._on_move_toggled)
        r.addWidget(self.cb_move)
        self.move_edit = QLineEdit()
        self.move_edit.setReadOnly(True)
        self.move_edit.setEnabled(False)
        r.addWidget(self.move_edit)
        self.move_btn = QPushButton("…")
        self.move_btn.setEnabled(False)
        self.move_btn.clicked.connect(self._choose_move_dir)
        r.addWidget(self.move_btn)
        ol.addLayout(r)
        lay.addWidget(ob)

        self.current_label = QLabel("")
        self.current_bar = QProgressBar()
        self.current_bar.setRange(0, 100)
        self.current_bar.setValue(0)
        self.current_bar.setVisible(False)
        lay.addWidget(self.current_label)
        lay.addWidget(self.current_bar)

        # --- Кнопки ---
        r = QHBoxLayout()
        self.preview_btn = QPushButton("Предпросмотр")
        self.preview_btn.clicked.connect(self._do_preview)
        self.convert_btn = QPushButton("Конвертировать")
        self.convert_btn.setMinimumHeight(34)
        self.convert_btn.clicked.connect(self._do_convert)
        self.rollback_btn = QPushButton("Откат по отчёту…")
        self.rollback_btn.clicked.connect(self._do_rollback)
        r.addWidget(self.preview_btn)
        r.addWidget(self.convert_btn)
        r.addWidget(self.rollback_btn)
        lay.addLayout(r)

        self.progress = QProgressBar()
        lay.addWidget(self.progress)

        # lay.addWidget(QLabel("Журнал:"))
        # self.log = QTextEdit()
        # self.log.setReadOnly(True)
        # lay.addWidget(self.log, 1)
        self.log = CollapsibleLog()
        #lay.addWidget(self.log, 1)
        outer.addWidget(make_scroll_splitter(top, self.log), 1)

    # ------------------------------------------------------------------
    def _on_unify_toggled(self, checked: bool) -> None:
        self.unify_combo.setEnabled(checked)
        self.format_table.setColumnHidden(2, checked)

    def _on_move_toggled(self, checked: bool) -> None:
        self.move_edit.setEnabled(checked)
        self.move_btn.setEnabled(checked)

    def _choose_move_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Куда перемещать")
        if d:
            self.move_edit.setText(d)

    # ------------------------------------------------------------------
    def _scan_formats(self) -> None:
        from . import converter
        folders = self.folder_list.folders()
        if not folders:
            self.format_table.setRowCount(0)
            return

        # запомним текущий выбор
        prev: dict[str, str | None] = {}
        for row in range(self.format_table.rowCount()):
            it = self.format_table.item(row, 0)
            combo = self.format_table.cellWidget(row, 2)
            if it and combo:
                prev[it.text()] = combo.currentData()

        counts = converter.scan_extensions(
            folders, self.cb_recursive.isChecked())
        self.log.append(
            f"Обнаружено расширений: {len(counts)} "
            f"(файлов всего: {sum(counts.values())})")

        self.format_table.setRowCount(0)
        for ext in sorted(counts.keys()):
            row = self.format_table.rowCount()
            self.format_table.insertRow(row)
            self.format_table.setItem(row, 0, QTableWidgetItem(ext))
            self.format_table.setItem(row, 1, QTableWidgetItem(str(counts[ext])))

            targets = converter.targets_for(ext)

            combo = QComboBox()
            combo.addItem("— не конвертировать —", None)
            for tgt_ext, label in targets.items():
                combo.addItem(label, tgt_ext)

            prev_target = prev.get(ext)
            if prev_target is not None:
                for i in range(combo.count()):
                    if combo.itemData(i) == prev_target:
                        combo.setCurrentIndex(i)
                        break
            else:
                combo.setCurrentIndex(0)   # «не конвертировать» по умолчанию

            self.format_table.setCellWidget(row, 2, combo)

    # ------------------------------------------------------------------
    def _current_mapping(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for row in range(self.format_table.rowCount()):
            it = self.format_table.item(row, 0)
            combo = self.format_table.cellWidget(row, 2)
            if not it or not combo:
                continue
            ext = it.text()
            target = combo.currentData()
            if target and target != ext:
                mapping[ext] = target
        return mapping

    def _build_jobs(self):
        from . import converter
        unify = self.unify_combo.currentData() if self.cb_unify.isChecked() else None
        move = self.move_edit.text().strip() or None
        return converter.build_jobs(
            self.folder_list.folders(),
            self.cb_recursive.isChecked(),
            self._current_mapping(),
            self.cb_overwrite.isChecked(),
            move,
            unify,
        )

    # ------------------------------------------------------------------
    def _do_preview(self) -> None:
        jobs = self._build_jobs()
        self.log.clear()
        if not jobs:
            self.log.append("Нет действий (все строки = «не конвертировать»).")
            return

        lines = [f"Заданий: {len(jobs)}"]
        by_action: dict[str, int] = {}
        for job in jobs:
            by_action[job.action] = by_action.get(job.action, 0) + 1
        lines.append("Разбивка: " + ", ".join(f"{k}: {v}" for k, v in by_action.items()))
        lines.append("")

        # Предупреждения о типах операций
        video_count = sum(1 for j in jobs if j.action in ("video", "gif_to_video"))
        if video_count:
            lines.append(
                f"⚠ Видео-конвертация: {video_count} файлов. "
                f"Это может занять несколько минут (ffmpeg, 1–5 мин на файл).")
            lines.append("")

        # предупреждения о перезаписи
        overwrite_conflicts = [
            j for j in jobs if j.overwrite and j.dst.exists() and j.dst != j.src
        ]
        if overwrite_conflicts:
            lines.append("⚠ ВНИМАНИЕ: будут перезаписаны существующие файлы:")
            for j in overwrite_conflicts[:10]:
                lines.append(f"   • {j.dst}")
            if len(overwrite_conflicts) > 10:
                lines.append(f"   … и ещё {len(overwrite_conflicts) - 10}")
            lines.append("")

        ACTION_LABEL = {
            "convert": "convert",
            "rename": "rename",
            "copy": "copy",
            "video": "video",
            "gif_to_video": "gif→video",
        }

        for job in jobs[:50]:
            lines.append(
                f"[{ACTION_LABEL.get(job.action, job.action)}] "
                f"{job.src.name} → {job.dst}")

        if len(jobs) > 50:
            lines.append(f"… и ещё {len(jobs) - 50}")

        self.log.append("\n".join(lines))

    def _do_convert(self) -> None:
        jobs = self._build_jobs()
        if not jobs:
            QMessageBox.information(self, "Пусто", "Нечего конвертировать.")
            return

        overwrite = self.cb_overwrite.isChecked()
        if overwrite:
            if not confirm_overwrite(self, len(jobs)):
                return

        # путь отчёта
        folders = self.folder_list.folders()
        report_dir = Path(folders[0]).parent if folders else Path.home()
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = report_dir / f"convert_report_{ts}.csv"

        self.log.clear()
        self.progress.setValue(0)
        self.progress.setMaximum(len(jobs))
        self.convert_btn.setEnabled(False)
        self.preview_btn.setEnabled(False)
        self.rollback_btn.setEnabled(False)

        self.worker = ConverterWorker(jobs, report_path)
        self.worker.log_signal.connect(self.log.append)
        self.worker.progress_signal.connect(
            lambda done, total: self.progress.setValue(done))
        self.worker.file_progress_signal.connect(self._on_file_progress)
        self.worker.finished_signal.connect(self._on_done)
        self.worker.error_signal.connect(self._on_error)
        self.worker.start()

    def _on_done(self, info: dict) -> None:
        self.convert_btn.setEnabled(True)
        self.preview_btn.setEnabled(True)
        self.rollback_btn.setEnabled(True)
        self.progress.setValue(self.progress.maximum())

        self.current_bar.setVisible(False)
        self.current_label.clear()

        self._scan_formats()   # обновим счётчики (могли поменяться)
        show_convert_done(self, info)
        _play("success")

    def _on_error(self, tb: str) -> None:
        self.convert_btn.setEnabled(True)
        self.preview_btn.setEnabled(True)
        self.rollback_btn.setEnabled(True)

        self.current_bar.setVisible(False)
        self.current_label.clear()

        self.log.append("ОШИБКА:\n" + tb)
        QMessageBox.critical(self, "Ошибка", "Подробности в журнале.")
        _play("error")

    def _do_rollback(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите CSV-отчёт конвертера", "",
            "CSV (*.csv);;Все файлы (*)")
        if not path:
            return
        if not confirm_convert_rollback(self, path):
            return

        self.log.clear()
        self.rollback_btn.setEnabled(False)
        self.convert_btn.setEnabled(False)
        self.worker = ConvertRollbackWorker(path)
        self.worker.log_signal.connect(self.log.append)
        self.worker.finished_signal.connect(self._on_rollback_done)
        self.worker.error_signal.connect(self._on_error)
        self.worker.start()

    def _on_rollback_done(self, info: dict) -> None:
        self.rollback_btn.setEnabled(True)
        self.convert_btn.setEnabled(True)
        show_convert_rollback_done(self, info)
        _play("success")

    def _on_file_progress(self, name: str, pct: float) -> None:
        self.current_label.setText(f"Конвертирую: {name}")
        self.current_bar.setVisible(True)
        self.current_bar.setValue(int(pct))
        if pct >= 100.0:
            self.current_label.setText(f"Конвертирую: {name} — Готово!")


class SettingsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        from . import config
        self._cfg = config.settings()
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        top = QWidget()
        lay = QVBoxLayout(top)
        lay.setContentsMargins(0, 0, 0, 0)

        # ---------- Дубликаты ----------
        gb = QGroupBox("Поиск дубликатов")
        gl = QVBoxLayout(gb)
        d = self._cfg.duplicate

        self.sp_phash = self._spin(gl, "pHash threshold (0..64)", d.phash_threshold, 0, 32)
        self.sp_dhash = self._spin(gl, "dHash threshold (0..64)", d.dhash_threshold, 0, 32)
        self.sp_ssim = self._dspin(gl, "SSIM threshold", d.ssim_threshold, 0.5, 1.0, 0.005)
        self.sp_p99 = self._dspin(gl, "P99 abs diff threshold", d.p99_diff_threshold, 0.01, 0.5, 0.01)
        self.sp_mean = self._dspin(gl, "Mean abs diff threshold", d.mean_diff_threshold, 0.01, 0.3, 0.005)
        self.sp_psnr = self._dspin(gl, "PSNR hard threshold (dB)", d.psnr_hard_threshold, 10.0, 50.0, 1.0)
        self.sp_grad = self._dspin(gl, "Gradient SSIM (deep check)", d.gradient_ssim_threshold, 0.5, 1.0, 0.01)
        self.cb_deep = QCheckBox("Включить глубокую проверку по умолчанию")
        self.cb_deep.setChecked(d.deep_check_default)
        gl.addWidget(self.cb_deep)
        lay.addWidget(gb)

        # ---------- Переименование ----------
        gb2 = QGroupBox("Переименование")
        gl2 = QVBoxLayout(gb2)
        r = self._cfg.rename
        self.cb_rename_folder = QCheckBox("Начинать имя с папки по умолчанию")
        self.cb_rename_folder.setChecked(r.default_use_folder_prefix)
        gl2.addWidget(self.cb_rename_folder)
        row = QHBoxLayout()
        row.addWidget(QLabel("Постфикс по умолчанию:"))
        self.ed_postfix = QLineEdit(r.default_postfix)
        row.addWidget(self.ed_postfix)
        gl2.addLayout(row)
        lay.addWidget(gb2)

        # ---------- Конвертер ----------
        gb3 = QGroupBox("Конвертер")
        gl3 = QVBoxLayout(gb3)
        c = self._cfg.converter
        self.sp_jpeg = self._spin(gl3, "JPEG quality", c.jpeg_quality, 50, 100)
        self.sp_webp = self._spin(gl3, "WEBP quality", c.webp_quality, 50, 100)
        self.sp_crf = self._spin(gl3, "Video CRF (0..51, ниже=качественнее)", c.video_crf, 0, 51)
        self.sp_preset = QComboBox()
        for pr in ("ultrafast", "fast", "medium", "slow", "veryslow"):
            self.sp_preset.addItem(pr)
        self.sp_preset.setCurrentText(c.video_preset)
        row = QHBoxLayout()
        row.addWidget(QLabel("Video preset:"))
        row.addWidget(self.sp_preset)
        gl3.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Audio bitrate:"))
        self.ed_audio = QLineEdit(c.audio_bitrate)
        row.addWidget(self.ed_audio)
        gl3.addLayout(row)
        lay.addWidget(gb3)

        # --- Звук ---
        from .sounds import play_system
        from . import config
        snd = config.SoundSettings()

        gb_sound = QGroupBox("Звук")
        sl = QVBoxLayout(gb_sound)

        self.cb_sound_enabled = QCheckBox("Включить звуковые уведомления")
        self.cb_sound_enabled.setChecked(self._cfg.sound.enabled)
        sl.addWidget(self.cb_sound_enabled)

        self.cb_sound_success = QCheckBox("Звук при успешном завершении")
        self.cb_sound_success.setChecked(self._cfg.sound.on_success)
        sl.addWidget(self.cb_sound_success)

        self.cb_sound_error = QCheckBox("Звук при ошибке")
        self.cb_sound_error.setChecked(self._cfg.sound.on_error)
        sl.addWidget(self.cb_sound_error)

        row = QHBoxLayout()
        for label, kind in [("Успех", "success"), ("Ошибка", "error")]:
            b = QPushButton(f"Прослушать: {label}")
            b.clicked.connect(lambda _=False, k=kind: play_system(k))
            row.addWidget(b)
        sl.addLayout(row)
        lay.addWidget(gb_sound)

        # --- Тема ---
        gb_theme = QGroupBox("Тема оформления")
        tl = QVBoxLayout(gb_theme)
        self.theme_combo = QComboBox()
        for label, val in [
            ("Системная", "auto"),
            ("Светлая", "light"),
            ("Тёмная", "dark"),
        ]:
            self.theme_combo.addItem(label, val)
        for i in range(self.theme_combo.count()):
            if self.theme_combo.itemData(i) == self._cfg.ui.theme:
                self.theme_combo.setCurrentIndex(i)
                break
        # предпросмотр без сохранения
        self.theme_combo.currentIndexChanged.connect(self._preview_theme)
        tl.addWidget(self.theme_combo)
        lay.addWidget(gb_theme)

        # ---------- Кнопки ----------
        r = QHBoxLayout()
        self.save_btn = QPushButton("Сохранить в config/settings.toml")
        self.save_btn.setMinimumHeight(34)
        self.save_btn.clicked.connect(self._save)
        reset_btn = QPushButton("Сбросить к дефолтам")
        reset_btn.clicked.connect(self._reset)
        r.addWidget(self.save_btn)
        r.addWidget(reset_btn)
        lay.addLayout(r)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(top)
        outer.addWidget(scroll)

        self.status = QLabel("")
        outer.addWidget(self.status)

    def _spin(self, parent, label: str, value: int, lo: int, hi: int):
        row = QHBoxLayout()
        row.addWidget(QLabel(label + ":"))
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setValue(value)
        row.addWidget(sp)
        row.addStretch()
        parent.addLayout(row)
        return sp

    def _dspin(self, parent, label: str, value: float, lo: float, hi: float, step: float):
        row = QHBoxLayout()
        row.addWidget(QLabel(label + ":"))
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setSingleStep(step)
        sp.setDecimals(3)
        sp.setValue(value)
        row.addWidget(sp)
        row.addStretch()
        parent.addLayout(row)
        return sp

    def _collect(self):
        from . import config
        s = config.AppSettings()
        s.duplicate = config.DuplicateSettings(
            phash_threshold=self.sp_phash.value(),
            dhash_threshold=self.sp_dhash.value(),
            ssim_threshold=self.sp_ssim.value(),
            p99_diff_threshold=self.sp_p99.value(),
            mean_diff_threshold=self.sp_mean.value(),
            psnr_hard_threshold=self.sp_psnr.value(),
            gradient_ssim_threshold=self.sp_grad.value(),
            deep_check_default=self.cb_deep.isChecked(),
        )
        s.rename = config.RenameSettings(
            default_use_folder_prefix=self.cb_rename_folder.isChecked(),
            default_postfix=self.ed_postfix.text(),
        )
        s.converter = config.ConverterSettings(
            jpeg_quality=self.sp_jpeg.value(),
            webp_quality=self.sp_webp.value(),
            video_crf=self.sp_crf.value(),
            video_preset=self.sp_preset.currentText(),
            audio_bitrate=self.ed_audio.text(),
        )
        s.sound = config.SoundSettings(
            enabled=self.cb_sound_enabled.isChecked(),
            on_success=self.cb_sound_success.isChecked(),
            on_error=self.cb_sound_error.isChecked(),
        )
        s.ui = config.UISettings(theme=self.theme_combo.currentData())
        return s

    def _save(self) -> None:
        from . import config
        try:
            path = config.save(self._collect())
            self.status.setText(f"✓ Сохранено в {path}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def _reset(self) -> None:
        from . import config
        s = config.AppSettings()
        self.sp_phash.setValue(s.duplicate.phash_threshold)
        self.sp_ssim.setValue(s.duplicate.ssim_threshold)
        self.sp_p99.setValue(s.duplicate.p99_diff_threshold)

        self.cb_sound_enabled.setChecked(s.sound.enabled)
        self.cb_sound_success.setChecked(s.sound.on_success)
        self.cb_sound_error.setChecked(s.sound.on_error)

        for i in range(self.theme_combo.count()):
            if self.theme_combo.itemData(i) == s.ui.theme:
                self.theme_combo.setCurrentIndex(i)
                break

        self.status.setText("Сброшено (не сохранено — нажмите Сохранить)")

    def _preview_theme(self) -> None:
        from PyQt6.QtWidgets import QApplication
        from .gui.themes import apply_theme
        mode = self.theme_combo.currentData()
        apply_theme(QApplication.instance(), mode)


class HelpTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._build_ui()

    def _build_ui(self) -> None:
        from . import version as ver
        from . import config

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        w = QWidget()
        lay = QVBoxLayout(w)

        # --- Заголовок ---
        title = QLabel("YAS File Tool")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        lay.addWidget(title)
        sub = QLabel(
            "Поиск дубликатов, переименование, конвертация медиа.")
        sub.setStyleSheet("color: gray;")
        lay.addWidget(sub)

        # --- Версия + зависимости ---
        vb = QGroupBox("Версия")
        vl = QVBoxLayout(vb)
        for line in ver.version_lines():
            lbl = QLabel(line)
            lbl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            vl.addWidget(lbl)
        vl.addWidget(QLabel(self._deps_info()))
        lay.addWidget(vb)

        # --- Быстрый старт ---
        qs = QGroupBox("Быстрый старт")
        ql = QVBoxLayout(qs)
        ql.addWidget(QLabel(
            "<b>Поиск дубликатов.</b> Добавьте папки → укажите папку "
            "назначения → «Начать поиск». Отчёт сохраняется туда же.<br><br>"
            "<b>Переименование.</b> Добавьте папки → снимите галочки с "
            "ненужных → настройте шаблон → «Предпросмотр» → "
            "«Переименовать».<br><br>"
            "<b>Конвертер.</b> Добавьте папки → выберите целевой формат "
            "для каждого расширения (или «Привести к единому формату») → "
            "«Конвертировать». Для видео/аудио нужен ffmpeg — он уже "
            "встроен."))
        lay.addWidget(qs)

        # --- Пути и логи ---
        pb = QGroupBox("Файлы и пути")
        pl = QVBoxLayout(pb)
        for label, path in [
            ("Настройки:", str(config.CONFIG_PATH)),
        ]:
            pl.addWidget(QLabel(f"<b>{label}</b> {path}"))
        lay.addWidget(pb)

        # --- Горячие клавиши ---
        hb = QGroupBox("Горячие клавиши")
        hl = QVBoxLayout(hb)
        hl.addWidget(QLabel(
            "F11 — полный экран\n"
            "Esc — выйти из полного экрана\n"
            "Ctrl+Shift+M — развернуть/восстановить окно"))
        lay.addWidget(hb)

        # --- Ссылки ---
        lb = QGroupBox("Ссылки")
        ll = QHBoxLayout(lb)

        def _open(url: str):
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(url))

        b1 = QPushButton("GitHub")
        b1.clicked.connect(lambda: _open(REPO_URL))
        ll.addWidget(b1)

        b2 = QPushButton("Сообщить об ошибке")
        b2.clicked.connect(lambda: _open(BUG_REPORT_URL))
        ll.addWidget(b2)

        # b3 = QPushButton("♥ Поддержать проект")
        # b3.setStyleSheet("background: #e05a5a; color: white; "
        #                  "padding: 6px 12px; font-weight: bold;")
        # b3.clicked.connect(lambda: _open(SUPPORT_URL))
        # ll.addWidget(b3)
        lay.addWidget(lb)

        # --- Лицензия ---
        lic = QGroupBox("Лицензия")
        lil = QVBoxLayout(lic)
        lil.addWidget(QLabel(
            "MIT License — свободное использование, модификация и "
            "распространение. Предоставляется «как есть», без гарантий. "
            "Автор не несёт ответственности за потерю данных."))
        lay.addWidget(lic)

        lay.addStretch()
        scroll.setWidget(w)
        outer.addWidget(scroll)

    def _deps_info(self) -> str:
        parts: list[str] = []
        try:
            from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
            parts.append(f"Qt {QT_VERSION_STR} / PyQt {PYQT_VERSION_STR}")
        except Exception:
            pass
        try:
            import PIL
            parts.append(f"Pillow {PIL.__version__}")
        except Exception:
            pass
        try:
            from .converter import get_ffmpeg
            ff = get_ffmpeg()
            parts.append(f"ffmpeg: {'✓' if ff else '✗ не найден'}")
        except Exception:
            pass
        return "  •  ".join(parts)

    def _copy_diagnostics(self) -> None:
        import platform, sys
        from . import version as ver
        from . import config
        lines = [
            *ver.version_lines(),
            f"OS: {platform.platform()}",
            f"Python: {sys.version.split()[0]}",
            self._deps_info(),
            f"Config: {config.CONFIG_PATH}",
        ]
        QApplication.clipboard().setText("\n".join(lines))
        QMessageBox.information(self, "Скопировано",
                                "Информация о системе в буфере обмена.")


# ===========================================================================
# Главное окно
# ===========================================================================

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("YAS File Tool")
        self.setMinimumSize(800, 600)
        self.resize(1024, 768)

        tabs = QTabWidget()
        tabs.addTab(DuplicateFinderTab(), "Поиск дубликатов")
        tabs.addTab(RenameTab(), "Переименовать файлы")
        tabs.addTab(ConverterTab(), "Конвертер")
        tabs.addTab(SettingsTab(), "Настройки")
        tabs.addTab(HelpTab(), "Справка")
        self.setCentralWidget(tabs)

        # --- Меню «Вид» ---
        view_menu = self.menuBar().addMenu("Вид")

        self.fs_action = QAction("Полноэкранный режим (F11)", self)
        self.fs_action.setShortcut(QKeySequence("F11"))
        self.fs_action.setCheckable(True)
        self.fs_action.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(self.fs_action)

        max_action = QAction("Развернуть окно (Ctrl+Shift+M)", self)
        max_action.setShortcut(QKeySequence("Ctrl+Shift+M"))
        max_action.triggered.connect(self.showMaximized)
        view_menu.addAction(max_action)

        normal_action = QAction("Обычный размер (Ctrl+Shift+N)", self)
        normal_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
        normal_action.triggered.connect(self.showNormal)
        view_menu.addAction(normal_action)

    def _toggle_fullscreen(self, checked: bool) -> None:
        if checked:
            self.showFullScreen()
        else:
            self.showNormal()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        # Держим галочку F11 в актуальном состоянии
        if event.type() == event.Type.WindowStateChange:
            self.fs_action.setChecked(self.isFullScreen())


def _resource_dir(subfolder: str = "") -> Path:
    base = Path(__file__).parent / "assets"
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "yas_filetool" / "assets"
    return base / subfolder if subfolder else base


def app_icon() -> QIcon:
    images = _resource_dir("images")
    for name in ("icon.png", "icon.svg"):
        p = images / name
        if p.exists():
            return QIcon(str(p))
    return QIcon()


def main() -> None:
    app = QApplication(sys.argv)

    app.setApplicationName("YAS File Tool")
    app.setWindowIcon(app_icon())

    from . import config
    config._apply_to_modules(config.settings())

    from .gui.themes import apply_theme
    apply_theme(app, config.settings().ui.theme)


    w = MainWindow()
    w.setWindowIcon(app_icon())
    w.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
