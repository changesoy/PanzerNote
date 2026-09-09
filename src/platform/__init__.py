# -*- coding: utf-8 -*-
"""Window Chrome 契约（Wave 8 B1）。

Window Chrome 是平台能力层，不属于主题；主题只表达视觉意图
（Theme Intent → Capability → Platform Backend）。
"""
from .contract import (
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
    "WindowChromeBackend",
    "WindowChromeProfile",
]
