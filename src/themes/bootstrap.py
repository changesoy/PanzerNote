# -*- coding: utf-8 -*-
"""Layer 0 Bootstrap / Pre-Main 外观（Wave 8 D31）。

MainWindow 创建前的启动期 UI（FirstRunDialog 等）经 BootstrapAppearance 覆盖：
font（由 app 级 QFont 承担）+ light/dark + basic controls + window chrome（C0 native titlebar）。

刻意自足：
- 不解析 Theme v2、不依赖主题文件——主题损坏时仍保证首帧基础观感（no white flash）；
- 色板常量与 themes/default（design.json + variants/light.json / dark.json + recipes.json）
  对齐；默认主题视觉更新时需同步本文件；
- 当前明暗固定为浅色（与主程序默认主题 default/light 一致，避免启动首帧与主界面割裂）；
  dark 色板保留，供未来按需启用。
"""

from __future__ import annotations

import sys
from typing import Final

from PyQt6.QtCore import QEvent, QObject, QTimer
from PyQt6.QtWidgets import QDialog, QWidget

from ..utils.window_theme import apply_native_dark_titlebar

__all__ = ["BootstrapAppearance"]

#: Bootstrap 色板。值取自 themes/default（默认主题为唯一真相源，此处为轻量快照，
#: 不随主题文件加载，保证主题损坏时启动期仍可渲染基础观感）。
_PALETTES: Final[dict[str, dict[str, str]]] = {
    "light": {
        "surface_primary": "#FFFFFF",
        "surface_raised": "#FFFFFF",
        "text_primary": "#212121",
        "text_secondary": "#757575",
        "border_muted": "#E0E0E0",
        "accent": "#2196F3",
        "button_hover": "#1E88E5",
        "button_pressed": "#1976D2",
        "on_accent": "#FFFFFF",
    },
    "dark": {
        "surface_primary": "#181818",
        "surface_raised": "#2B2B2B",
        "text_primary": "#E0E0E0",
        "text_secondary": "#A0A0A0",
        "border_muted": "#3C3C3C",
        "accent": "#0078D4",
        "button_hover": "#1989DC",
        "button_pressed": "#2B8FD8",
        "on_accent": "#FFFFFF",
    },
}

#: 基础控件 QSS（QDialog/QLabel/QLineEdit/QPushButton——FirstRunDialog 实际控件集）。
#: 半径/间距与 design.json（radius_sm=3 / radius_md=6 / space_2=4 / space_3=8）对齐。
_QSS_TEMPLATE: Final[str] = """
QDialog {{
    background-color: {surface_primary};
}}
QLabel {{
    color: {text_primary};
}}
QLineEdit {{
    background-color: {surface_raised};
    border: 1px solid {border_muted};
    border-radius: 3px;
    padding: 4px 8px;
    color: {text_primary};
    selection-background-color: {accent};
    selection-color: {on_accent};
}}
QLineEdit:focus {{
    border-color: {accent};
}}
QPushButton {{
    background-color: {accent};
    color: {on_accent};
    border: 1px solid {accent};
    border-radius: 6px;
    padding: 8px 16px;
}}
QPushButton:hover {{
    background-color: {button_hover};
}}
QPushButton:pressed {{
    background-color: {button_pressed};
}}
QPushButton:focus {{
    border-color: {accent};
}}
"""


def _build_qss(dark: bool) -> str:
    palette = _PALETTES["dark" if dark else "light"]
    return _QSS_TEMPLATE.format(**palette)


class _TitleBarShowFilter(QObject):
    """窗口 Show 后延迟应用 C0 native titlebar（winId 稳定后再设 DWM 属性）。

    parent 绑定到目标窗口：窗口销毁时过滤器一并销毁，不污染全局事件链。
    """

    def __init__(self, widget: QWidget, dark: bool, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._widget = widget
        self._dark = dark

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if (
            obj is self._widget
            and event is not None
            and event.type() == QEvent.Type.Show
            and isinstance(obj, QWidget)
            and obj.isWindow()
        ):
            widget = obj

            def apply_later() -> None:
                try:
                    apply_native_dark_titlebar(widget, self._dark)
                except Exception:
                    pass

            # 延迟到 native handle / 窗口实现稳定后再设（与全局 EventFilter 同策略）。
            QTimer.singleShot(0, apply_later)
        return bool(super().eventFilter(obj, event))


class BootstrapAppearance:
    """Layer 0 启动期外观：基础控件 QSS + C0 titlebar 钩子。"""

    def __init__(self, dark: bool = False) -> None:
        self._dark = dark
        self._qss = _build_qss(dark)

    @property
    def dark(self) -> bool:
        return self._dark

    def qss(self) -> str:
        return self._qss

    @classmethod
    def apply_to_dialog(cls, dialog: QDialog, dark: bool = False) -> "BootstrapAppearance":
        """给启动期 dialog 应用 Bootstrap 外观（局部 QSS + Windows C0 titlebar 钩子）。"""
        appearance = cls(dark=dark)
        dialog.setStyleSheet(appearance.qss())
        if sys.platform == "win32":
            # parent=dialog：dialog 销毁时过滤器随同销毁，引用由 Qt 对象树持有。
            title_filter = _TitleBarShowFilter(dialog, dark, parent=dialog)
            dialog.installEventFilter(title_filter)
        return appearance
