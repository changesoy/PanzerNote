# -*- coding: utf-8 -*-
"""WebView2 Runtime 可用性检测与安装指引。

C3-D 后 WebView2 是**唯一**预览 / 导出后端，运行时缺失必须可见：
- 启动时检测并记录明确错误（供日志与可见提示使用）；
- 预览初始化失败时预览区给出同一份指引，而不是留空白。

本模块只读注册表、只依赖标准库 `winreg`：
不导入 PyWinRT，因此即使 winrt 绑定本身损坏也能完成检测并报出原因。
"""

from __future__ import annotations

import winreg

from ..utils.logger import get_logger

_log = get_logger(__name__)

# WebView2 Runtime 的固定产品标识（Microsoft Edge Update 客户端 GUID）
_RUNTIME_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

# 可能的安装位置：64 位视图 / 32 位视图 / 当前用户
_REG_PATHS: tuple[tuple[int, str], ...] = (
    (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{_RUNTIME_GUID}"),
    (
        winreg.HKEY_LOCAL_MACHINE,
        rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{_RUNTIME_GUID}",
    ),
    (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{_RUNTIME_GUID}"),
)

# 缺失时的用户可读指引（预览占位与启动提示共用同一文案）
INSTALL_HINT = (
    "未检测到 WebView2 Runtime，Markdown 预览与 PDF 导出不可用。\n\n"
    "WebView2 Runtime 是 Windows 系统组件（Windows 11 与多数 Windows 10 已预装）。\n"
    "如缺失，请安装 Microsoft Edge WebView2 Runtime 后重启 PanzerNote。\n\n"
    "下载地址：https://developer.microsoft.com/microsoft-edge/webview2/"
)


def runtime_version() -> str | None:
    """返回已安装的 WebView2 Runtime 版本号；未安装返回 None。"""
    for hive, subkey in _REG_PATHS:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                value, _ = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def is_available() -> bool:
    """WebView2 Runtime 是否可用。"""
    return runtime_version() is not None


def log_availability() -> bool:
    """启动时调用：记录检测结果，返回是否可用。

    不可用属**阻断预览能力**的故障，故以 error 级别记录（而非 warning）。
    """
    version = runtime_version()
    if version is None:
        _log.error("未检测到 WebView2 Runtime：Markdown 预览与 PDF 导出不可用")
        return False
    _log.info("WebView2 Runtime 版本 %s", version)
    return True
