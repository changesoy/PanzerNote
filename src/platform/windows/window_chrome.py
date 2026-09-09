# -*- coding: utf-8 -*-
"""Windows Window Chrome 后端（Wave 8 B1）。

B1 只落地 C0（native 模式 dark/light）；C1/C2 仅预留枚举。
Backend fail softly：任何失败返回 FALLBACK/FAILED + reason，绝不抛异常。
"""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QWidget

from ..contract import (
    ChromeAppearance,
    ChromeApplyResult,
    ChromeCapability,
    ChromeMode,
    ChromeStatus,
    WindowChromeBackend,
    WindowChromeProfile,
)
from .dwm import apply_dwm_dark_titlebar


class WindowsChromeBackend(WindowChromeBackend):
    """Windows 原生标题栏 C0 实现（DWM API）。"""

    def apply(
        self, widget: QWidget | None, profile: WindowChromeProfile
    ) -> ChromeApplyResult:
        if sys.platform != "win32":
            return ChromeApplyResult(
                ChromeCapability.C0, ChromeStatus.FALLBACK, "非 Windows 平台"
            )
        if profile.mode is not ChromeMode.NATIVE:
            return ChromeApplyResult(
                ChromeCapability.C0,
                ChromeStatus.FALLBACK,
                f"B1 仅支持 C0 native，忽略 {profile.mode.value}",
            )
        if widget is None:
            return ChromeApplyResult(
                ChromeCapability.C0, ChromeStatus.FALLBACK, "widget 为空"
            )

        try:
            hwnd = int(widget.winId())
        except Exception as exc:
            return ChromeApplyResult(
                ChromeCapability.C0,
                ChromeStatus.FALLBACK,
                f"获取窗口句柄失败: {exc}",
            )
        if hwnd == 0:
            return ChromeApplyResult(
                ChromeCapability.C0,
                ChromeStatus.FALLBACK,
                "窗口尚无原生句柄",
            )

        is_dark = profile.appearance is ChromeAppearance.DARK
        if apply_dwm_dark_titlebar(hwnd, is_dark):
            return ChromeApplyResult(ChromeCapability.C0, ChromeStatus.APPLIED)

        return ChromeApplyResult(
            ChromeCapability.C0,
            ChromeStatus.FAILED,
            "DwmSetWindowAttribute 失败，保留 OS 原生默认标题栏",
        )
