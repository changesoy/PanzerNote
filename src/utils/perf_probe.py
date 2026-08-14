# -*- coding: utf-8 -*-
"""
运行时性能探针（Wave 4 批次 E1）

大文件打开 / 首屏高亮 / 滚动响应等热路径的轻量计时埋点：
- 仅记录超过 threshold_ms 的调用（默认 1ms），正常滚动/高频路径不产生日志
- 计时结果走 debug 级别日志（不侵入正常日志输出）
- set_enabled(False) 可整体关闭（measure 直接执行 fn，零计时开销）
- 独立于启动性能分析器（StartupProfiler，见 lazy_loader.py）：不污染启动报告
"""

import time
from typing import Callable, TypeVar

from .logger import get_logger

T = TypeVar("T")

_ENABLED = True


def set_enabled(enabled: bool) -> None:
    """全局开关：关闭后 measure 仅执行 fn 不计时。"""
    global _ENABLED
    _ENABLED = enabled


def is_enabled() -> bool:
    return _ENABLED


def measure(name: str, fn: Callable[[], T], threshold_ms: float = 1.0) -> T:
    """执行 fn 并记录耗时（ms，debug 日志）。

    仅当耗时超过 threshold_ms 时输出（默认 1ms），避免滚动等高频路径刷屏；
    超过阈值说明该次调用是潜在卡顿点，正是 profiling 目标。
    热路径专用：启用时仅比直接调用多一次 perf_counter 与一次条件判断。
    """
    if not _ENABLED:
        return fn()
    start = time.perf_counter()
    try:
        return fn()
    finally:
        elapsed = (time.perf_counter() - start) * 1000
        if elapsed >= threshold_ms:
            get_logger(__name__).debug("%s: %.1fms", name, elapsed)
