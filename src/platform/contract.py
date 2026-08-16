# -*- coding: utf-8 -*-
"""Window Chrome 契约类型与后端抽象（Wave 8 B1）。

降级链（B1 文档 4.10 / 九节）：C2 → C1（若支持）→ C0；C1 → C0；
C0 customization failure → OS native default。themed opaque 不是通用 fallback。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

from PyQt6.QtWidgets import QWidget


class ChromeMode(Enum):
    """window_chrome.mode 枚举（与 theme.json 字段值一一对应）。"""

    NATIVE = "native"
    EXTENDED_NATIVE = "extended-native"  # 预留 C1
    CUSTOM = "custom"                    # 预留 C2


class ChromeAppearance(Enum):
    """明暗等视觉意图。B1 仅 dark/light。"""

    LIGHT = "light"
    DARK = "dark"


class ChromeCapability(Enum):
    """Window Chrome 能力等级 C0/C1/C2（能力等级，不归属主题）。"""

    C0 = "C0"
    C1 = "C1"
    C2 = "C2"


class ChromeStatus(Enum):
    """apply 结果状态。"""

    APPLIED = "applied"
    FALLBACK = "fallback"
    FAILED = "failed"


@dataclass(frozen=True)
class ChromeApplyResult:
    """一次 Window Chrome apply 的结果（含可读原因，不静默吞错）。"""

    capability: ChromeCapability
    status: ChromeStatus
    reason: str | None = None


@dataclass(frozen=True)
class WindowChromeProfile:
    """Window Chrome 应用档案（mode + 明暗视觉意图）。"""

    mode: ChromeMode
    appearance: ChromeAppearance


class WindowChromeBackend(ABC):
    """平台 Window Chrome 后端抽象（Win32 细节封在 src/platform/windows/）。"""

    @abstractmethod
    def apply(self, widget: QWidget | None, profile: WindowChromeProfile) -> ChromeApplyResult:
        """应用 profile。不得抛异常：任何失败返回 FALLBACK/FAILED + reason。"""
        raise NotImplementedError
