# -*- coding: utf-8 -*-
"""Window Chrome 能力层（Wave 8 B1）。

由 `bool is_dark` 升级为 `WindowChromeProfile(mode, appearance)`：
backend fail softly → fallback OS native default → 记录 diagnostic（不静默吞错）。

降级链：C2 → C1（若支持）→ C0；C1 → C0；C0 customization failure → OS native default。
themed opaque 不是通用 fallback（仅未来 Aero profile 的视觉 fallback）。

对外保留 `apply_native_dark_titlebar` / `install_native_titlebar_theme_filter` 兼容入口，
内部统一走 WindowChromeManager。
"""

from __future__ import annotations

import sys
from typing import Callable, Optional

from PyQt6.QtCore import QEvent, QObject, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QWidget

from ..utils.logger import get_logger
from ..platform import (
    ChromeAppearance,
    ChromeApplyResult,
    ChromeCapability,
    ChromeMode,
    ChromeStatus,
    WindowChromeBackend,
    WindowChromeProfile,
)

__all__ = [
    "ChromeAppearance",
    "ChromeApplyResult",
    "ChromeCapability",
    "ChromeMode",
    "ChromeStatus",
    "WindowChromeProfile",
    "WindowChromeManager",
    "apply_native_dark_titlebar",
    "install_native_titlebar_theme_filter",
]


class WindowChromeManager:
    """Window Chrome 能力层入口：按 mode 选择平台 backend，记录降级诊断。"""

    def __init__(self) -> None:
        self._logger = get_logger(__name__)
        self._backends: dict[ChromeMode, WindowChromeBackend] = {}
        if sys.platform == "win32":
            from ..platform.windows.window_chrome import WindowsChromeBackend

            self._backends[ChromeMode.NATIVE] = WindowsChromeBackend()

    def apply(self, widget: QWidget | None, profile: WindowChromeProfile) -> ChromeApplyResult:
        backend = self._backends.get(profile.mode)
        if backend is None:
            result = ChromeApplyResult(
                ChromeCapability.C0,
                ChromeStatus.FALLBACK,
                f"mode {profile.mode.value} 无可用 backend",
            )
        else:
            try:
                result = backend.apply(widget, profile)
            except Exception as exc:  # backend 自身不应抛异常，防御性兜底
                result = ChromeApplyResult(
                    ChromeCapability.C0, ChromeStatus.FAILED, f"backend 异常: {exc}"
                )

        if result.status is not ChromeStatus.APPLIED:
            self._logger.warning(
                "Window Chrome 未应用（%s）: %s", profile.mode.value, result.reason
            )
        return result


_manager: WindowChromeManager | None = None


def _get_manager() -> WindowChromeManager:
    global _manager
    if _manager is None:
        _manager = WindowChromeManager()
    return _manager


def apply_native_dark_titlebar(widget: QWidget | None, is_dark: bool) -> None:
    """在 Windows 上为一个顶层窗口设置原生标题栏深/浅色（兼容入口）。

    非 Windows、无效窗口、无 hwnd、DWM 调用失败时走降级链并记录 diagnostic。
    """
    if sys.platform != "win32" or widget is None:
        return
    profile = WindowChromeProfile(
        mode=ChromeMode.NATIVE,
        appearance=ChromeAppearance.DARK if is_dark else ChromeAppearance.LIGHT,
    )
    _get_manager().apply(widget, profile)


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
