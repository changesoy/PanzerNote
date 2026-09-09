# -*- coding: utf-8 -*-
"""DWM 低层封装（Wave 8 B1）。

原生标题栏深/浅色设置。失败返回 False，不抛异常（调用方负责降级链与诊断）。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes


def apply_dwm_dark_titlebar(hwnd: int, is_dark: bool) -> bool:
    """为窗口设置原生标题栏深/浅色，返回是否成功。

    成功 = 属性 20 或 19 任一设置成功（Windows 11 用 20，部分 Windows 10 用 19）。
    """
    if hwnd <= 0:
        return False
    try:
        value = ctypes.c_int(1 if is_dark else 0)
        for attr in (20, 19):
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(attr),
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
            if result == 0:
                return True
        return False
    except Exception:
        return False
