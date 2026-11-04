from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QFileDialog, QTextEdit, QToolButton,
    QScrollArea, QSplitter,
)

# ===========================================================================
# Общий помощник для списка папок (используется в обеих вкладках)
# ===========================================================================
class CollapsibleLog(QWidget):
    """Журнал с кликабельным заголовком «▶/▼». Работает как QTextEdit."""

    def __init__(self, title: str = "Журнал") -> None:
        super().__init__()
        self._title = title

        self.header = QToolButton()
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setText(f"▼ {title}")
        self.header.setStyleSheet(
            "QToolButton { border: none; font-weight: bold; padding: 2px 0; "
            "text-align: left; }"
            "QToolButton:hover { color: #2b6cb0; }")
        self.header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.header.toggled.connect(self._on_toggled)

        self.text = QTextEdit()
        self.text.setReadOnly(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(self.header)
        lay.addWidget(self.text, 1)

    def _on_toggled(self, checked: bool) -> None:
        self.text.setVisible(checked)
        arrow = "▼" if checked else "▶"
        self.header.setText(f"{arrow} {self._title}")

    # --- делегируем популярные методы QTextEdit ---
    def append(self, s: str) -> None: self.text.append(s)
    def clear(self) -> None: self.text.clear()
    def setPlainText(self, s: str) -> None: self.text.setPlainText(s)
    def toPlainText(self) -> str: return self.text.toPlainText()


class FolderList(QWidget):
    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        lay.addWidget(self.list)
        row = QHBoxLayout()
        self.add_btn = QPushButton("Добавить папку…")
        self.del_btn = QPushButton("Удалить выбранное")
        row.addWidget(self.add_btn)
        row.addWidget(self.del_btn)
        lay.addLayout(row)
        self.add_btn.clicked.connect(self._add)
        self.del_btn.clicked.connect(self._del)

    def _add(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Выберите папку")
        if not d:
            return
        existing = {self.list.item(i).text() for i in range(self.list.count())}
        if d not in existing:
            self.list.addItem(d)

    def _del(self) -> None:
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))

    def folders(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]


def make_scroll_splitter(top_widget: QWidget, log_widget: QWidget) -> QSplitter:
    """Верхняя часть — в скролле, журнал — внизу, разделитель перетаскивается."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(top_widget)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setMinimumHeight(180)

    splitter = QSplitter(Qt.Orientation.Vertical)
    splitter.setChildrenCollapsible(False)
    splitter.addWidget(scroll)
    splitter.addWidget(log_widget)
    splitter.setStretchFactor(0, 3)
    splitter.setStretchFactor(1, 1)
    splitter.setSizes([600, 220])
    return splitter
