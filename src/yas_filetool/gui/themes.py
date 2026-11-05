"""Темы оформления: auto / light / dark."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication


def _light_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(240, 240, 240))
    p.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.black)
    p.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(245, 245, 245))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 220))
    p.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.black)
    p.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.black)
    p.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
    p.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.black)
    p.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    p.setColor(QPalette.ColorRole.Link, QColor(0, 102, 204))
    p.setColor(QPalette.ColorRole.Highlight, QColor(51, 153, 255))
    p.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorGroup.Disabled,
               QPalette.ColorRole.Text, QColor(160, 160, 160))
    p.setColor(QPalette.ColorGroup.Disabled,
               QPalette.ColorRole.ButtonText, QColor(160, 160, 160))
    return p


def _dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    p.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(25, 25, 25))
    p.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    p.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    p.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    p.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    p.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    p.setColor(QPalette.ColorGroup.Disabled,
               QPalette.ColorRole.Text, QColor(127, 127, 127))
    p.setColor(QPalette.ColorGroup.Disabled,
               QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
    return p


def apply_theme(app: QApplication, mode: str) -> None:
    """mode ∈ {'auto', 'light', 'dark'}."""
    app.setStyle("Fusion")   # одинаковый вид на Windows/Linux
    if mode == "dark":
        app.setPalette(_dark_palette())
        return
    if mode == "light":
        app.setPalette(_light_palette())
        return
    # auto — читаем системную схему (Qt 6.5+)
    hints = app.styleHints()
    if hasattr(hints, "colorScheme") and \
            hints.colorScheme() == Qt.ColorScheme.Dark:
        app.setPalette(_dark_palette())
    else:
        app.setPalette(_light_palette())
