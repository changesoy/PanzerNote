# -*- coding: utf-8 -*-
"""
模块懒加载管理器
实现非核心模块的按需加载，优化应用启动性能

核心设计：
1. 延迟导入：非核心模块在首次使用时才加载
2. 并行初始化：利用 QTimer.singleShot 将非关键初始化推迟到事件循环空闲时
3. 启动进度跟踪：记录各阶段耗时
"""

import time
from typing import Dict, List, Optional, Callable, Any

from .logger import get_logger
from .feature_flags import is_enabled


class LazyLoader:
    """模块懒加载管理器"""

    def __init__(self):
        self._modules: Dict[str, Any] = {}
        self._loaders: Dict[str, Callable[[], Any]] = {}
        self._loaded: set = set()
        self._init_tasks: List[dict] = []

    def register(self, name: str, loader: Callable[[], Any]):
        self._loaders[name] = loader

    def get(self, name: str) -> Optional[Any]:
        if name in self._loaded:
            return self._modules.get(name)

        if name in self._loaders:
            t0 = time.perf_counter()
            self._modules[name] = self._loaders[name]()
            self._loaded.add(name)
            t1 = time.perf_counter()
            get_logger(__name__).debug("懒加载模块 %s: %.1fms", name, (t1 - t0) * 1000)
            return self._modules[name]

        return None

    def is_loaded(self, name: str) -> bool:
        return name in self._loaded

    def add_deferred_init(self, name: str, task: Callable[[], None], priority: int = 0):
        self._init_tasks.append({
            "name": name,
            "task": task,
            "priority": priority,
        })

    def run_deferred_inits(self, app: Any):
        from PyQt5.QtCore import QTimer

        sorted_tasks = sorted(self._init_tasks, key=lambda t: t["priority"])

        for i, task_info in enumerate(sorted_tasks):
            delay = (i + 1) * 100
            QTimer.singleShot(delay, task_info["task"])

        self._init_tasks.clear()


class StartupProfiler:
    """启动性能分析器"""

    def __init__(self):
        self._phases: List[dict] = []
        self._current_phase: Optional[str] = None
        self._phase_start: float = 0

    def begin_phase(self, name: str):
        if self._current_phase:
            self.end_phase()
        self._current_phase = name
        self._phase_start = time.perf_counter()

    def end_phase(self):
        if self._current_phase:
            elapsed = (time.perf_counter() - self._phase_start) * 1000
            self._phases.append({
                "name": self._current_phase,
                "elapsed_ms": round(elapsed, 2),
            })
            self._current_phase = None

    def get_report(self) -> str:
        lines: List[str] = ["启动性能报告:"]
        total: float = 0
        for phase in self._phases:
            ms: float = float(phase["elapsed_ms"])
            lines.append(f"  {phase['name']}: {ms:.1f}ms")
            total += ms
        lines.append(f"  总计: {total:.1f}ms")
        return "\n".join(lines)

    def get_total_ms(self) -> float:
        return float(sum(p["elapsed_ms"] for p in self._phases))


_profiler: Optional[StartupProfiler] = None


def get_startup_profiler() -> StartupProfiler:
    global _profiler
    if _profiler is None:
        _profiler = StartupProfiler()
    return _profiler
