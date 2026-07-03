# -*- coding: utf-8 -*-
"""
主题感知混入
组件继承此混入后可自动订阅 theme_changed 信号并更新样式
"""

import sys
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QFrame, QWidget

from ..themes.theme_engine import ThemeEngine

if TYPE_CHECKING:
    pass


def _update_title_bar_theme(widget: QWidget, is_dark: bool):
    """Windows 下通过 DWM API 设置窗口标题栏暗色模式"""
    if sys.platform != "win32" or not widget.isWindow():
        return
    try:
        import ctypes
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        hwnd = int(widget.winId())
        value = ctypes.c_int(1 if is_dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception:
        pass


def _fix_separator_lines(widget: QWidget, border_color: str):
    """递归修复 widget 及其子控件中所有 QFrame 分隔线的颜色

    QFrame.HLine / QFrame.VLine 使用 Sunken 效果时依赖系统调色板，
    暗色模式下显示为白色。此函数将它们改为 NoFrame + 背景色样式。
    """
    for child in widget.findChildren(QFrame):
        shape = child.frameShape()
        if shape == QFrame.Shape.HLine:
            child.setFrameShape(QFrame.Shape.NoFrame)
            child.setFixedHeight(1)
            child.setStyleSheet(f"background-color: {border_color};")
        elif shape == QFrame.Shape.VLine:
            child.setFrameShape(QFrame.Shape.NoFrame)
            child.setFixedWidth(1)
            child.setStyleSheet(f"background-color: {border_color};")


class ThemeAwareMixin:
    """主题感知混入

    使用方式：
    1. 组件继承 ThemeAwareMixin
    2. 在 __init__ 中调用 _init_theme(theme_engine)
    3. 实现 _apply_theme_colors(colors) 方法，用主题颜色更新组件样式
    """

    def _init_theme(self, theme_engine: ThemeEngine):
        self._theme_engine = theme_engine
        theme_engine.theme_changed.connect(self._on_theme_changed)
        theme = theme_engine.get_active_theme()
        self._apply_theme_colors(theme.colors)
        self._apply_common_theme(theme)

    def _on_theme_changed(self, theme_id: str):
        theme = self._theme_engine.get_theme(theme_id)
        if theme:
            self._apply_theme_colors(theme.colors)
            self._apply_common_theme(theme)

    def _apply_theme_colors(self, colors):
        raise NotImplementedError("子类必须实现 _apply_theme_colors 方法")

    def _apply_common_theme(self, theme):
        """应用通用主题效果（DWM 标题栏 + 分隔线修复）

        子类可重写此方法以自定义行为。
        """
        if isinstance(self, QWidget):
            _fix_separator_lines(self, theme.colors.border)
            _update_title_bar_theme(self, theme.is_dark)
