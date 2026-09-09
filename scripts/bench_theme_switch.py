# -*- coding: utf-8 -*-
"""Theme v2 切换性能基准（Wave 8 B9 performance 审计，B1-1）。

offscreen 运行，不创建窗口。测量四段：
1. cold load      —— ThemeV2Service.load_default()（启动期包加载 + 全量校验）
2. L0 prepare     —— ThemeManager.prepare（同包变体切换，数据解析/兼容性计算）
3. L0 commit      —— ThemeManager.commit（激活事务，无 QWidget 副作用）
4. QSS rebuild    —— ThemeComponentLibrary.all_qss（全局 QSS 生成，_apply_theme 主体）

生产路径 L0 恒成立（产品注册 0 个 RendererHost）；L1 仅在 B7 测试
fixture renderer 下验证，不在本基准范围。

用法：
    .venv\\Scripts\\python.exe scripts/bench_theme_switch.py [--iter N]
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.themes.theme_v2.library import ThemeComponentLibrary  # noqa: E402
from src.themes.theme_v2.manager import ThemeManager  # noqa: E402
from src.themes.theme_v2.service import ThemeV2Service  # noqa: E402
from src.themes.theme_v2.transition import CommitResult  # noqa: E402


def _ms(fn) -> float:
    start = time.perf_counter()
    fn()
    return (time.perf_counter() - start) * 1000.0


def _report(name: str, times: list[float]) -> None:
    times.sort()
    p95 = times[int(len(times) * 0.95) - 1]
    print(
        f"{name:<16} median {statistics.median(times):8.2f} ms"
        f"  p95 {p95:8.2f} ms  max {max(times):8.2f} ms  n={len(times)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iter", type=int, default=20)
    args = parser.parse_args()

    app = QApplication.instance() or QApplication([])
    themes_dir = Path(__file__).resolve().parents[1] / "themes"

    # 1. cold load（单次：启动期只发生一次）
    svc = ThemeV2Service(themes_dir)
    cold = _ms(lambda: svc.load_default())
    if svc.snapshot() is None:
        print("ERROR: 默认主题加载失败")
        sys.exit(1)
    print(f"{'cold load':<16} single   {cold:8.2f} ms")

    lib = ThemeComponentLibrary(svc)
    mgr = ThemeManager(themes_dir, svc)
    # 首次 request 作为 warmup（含 palette 目录扫描等一次性成本）
    warm = mgr.request("default", "light")
    assert warm is CommitResult.COMMITTED, warm

    # 2/3. L0 变体切换 prepare + commit（light ↔ dark）
    prepare_light = [_ms(lambda: mgr.prepare("default", "light")) for _ in range(args.iter)]
    prepare_dark = [_ms(lambda: mgr.prepare("default", "dark")) for _ in range(args.iter)]
    commit_light = []
    for _ in range(args.iter):
        mgr.prepare("default", "light")
        commit_light.append(_ms(lambda: mgr.commit()))
    commit_dark = []
    for _ in range(args.iter):
        mgr.prepare("default", "dark")
        commit_dark.append(_ms(lambda: mgr.commit()))

    # 4. 全局 QSS 重建
    qss_light = [_ms(lambda: lib.all_qss("light")) for _ in range(args.iter)]
    qss_dark = [_ms(lambda: lib.all_qss("dark")) for _ in range(args.iter)]

    print("---")
    _report("prepare L0→light", prepare_light)
    _report("prepare L0→dark", prepare_dark)
    _report("commit L0→light", commit_light)
    _report("commit L0→dark", commit_dark)
    _report("qss rebuild light", qss_light)
    _report("qss rebuild dark", qss_dark)

    total = statistics.median(prepare_light) + statistics.median(commit_light) + statistics.median(qss_light)
    print(f"---")
    print(f"单次 L0 切换合计（prepare+commit+qss rebuild，light）：{total:.2f} ms")


if __name__ == "__main__":
    main()
