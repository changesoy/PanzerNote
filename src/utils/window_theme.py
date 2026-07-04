# -*- coding: utf-8 -*-
"""
Windows 原生窗口标题栏主题辅助。

只处理非客户区标题栏颜色，不处理 Qt 内容区 QSS。
"""

from __future__ import annotations

import sys
import ctypes
from ctypes import wintypes
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QEvent, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QWidget


def apply_native_dark_titlebar(widget: QWidget | None, is_dark: bool) -> None:
    """在 Windows 上为一个顶层窗口设置原生标题栏深/浅色。

    非 Windows、无效窗口、无 hwnd、DWM 调用失败时静默返回。
    """
    if sys.platform != "win32" or widget is None:
        return

    try:
        hwnd = int(widget.winId())
        if hwnd == 0:
            return

        value = ctypes.c_int(1 if is_dark else 0)

        # Windows 11 官方值通常是 20；部分 Windows 10 构建需要 19。
        # 先试 20，再 fallback 19。
        for attr in (20, 19):
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(attr),
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
            if result == 0:
                break
    except Exception:
        # 这里必须静默，不能让主题修复影响应用启动/弹窗显示。
        return


class NativeTitleBarThemeFilter(QObject):
    """为所有后续显示的顶层窗口补设原生标题栏主题。"""

    def __init__(self, is_dark_getter: Callable[[], bool], parent: QObject | None = None):
        super().__init__(parent)
        self._is_dark_getter = is_dark_getter

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if obj is None or event is None:
            return bool(super().eventFilter(obj, event))
        if event.type() == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow():
            # 跳过无边框窗口（如 CompletionPopup），它们没有原生标题栏
            if obj.windowFlags() & Qt.WindowType.FramelessWindowHint:
                return bool(super().eventFilter(obj, event))

            widget = obj

            def apply_later() -> None:
                try:
                    apply_native_dark_titlebar(widget, bool(self._is_dark_getter()))
                except Exception:
                    pass

            # 延迟到 native handle/窗口实现稳定后再设。
            QTimer.singleShot(0, apply_later)

        return bool(super().eventFilter(obj, event))


def install_native_titlebar_theme_filter(
    app: QApplication | None,
    is_dark_getter: Callable[[], bool],
    parent: QObject | None = None,
) -> Optional[NativeTitleBarThemeFilter]:
    """安装应用级事件过滤器，并返回过滤器对象。

    调用方必须保存返回对象引用，避免被 GC。
    """
    if sys.platform != "win32" or app is None:
        return None

    titlebar_filter = NativeTitleBarThemeFilter(is_dark_getter, parent)
    app.installEventFilter(titlebar_filter)
    return titlebar_filter
