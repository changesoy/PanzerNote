# -*- coding: utf-8 -*-
"""
启动性能分析器
记录应用启动各阶段耗时，辅助性能优化
"""

import time
from typing import List, Optional


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
