# -*- coding: utf-8 -*-
"""C2 E2 功能冒烟：ExportService.export_pdf 经 Web Preview Adapter 的真实导出路径。

背景：tests/test_export_service.py 中的 TestExportPdf 带 @a_only 门控
（A 实现 4 参签名），在 B 分支被跳过 → 导出路径当前无自动化覆盖。
本脚本以真实 QWebEngineView（离屏）跑通完整路径并断言产物。

用法：
  python c2_export_smoke.py
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QWidget

# 必须在创建 QApplication 之前设置（WebEngine 前置条件）
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

TIMEOUT_MS = 30_000
MD = "# 标题\n\n中文正文与 `code`。\n\n```python\nprint('hello')\n```\n"


def build_theme_engine():
    """复刻 tests/conftest.py 的 theme_engine fixture。"""
    from src.themes.theme_engine import ThemeEngine

    cfg = MagicMock()
    cfg.get_app_dir = MagicMock(return_value=".")

    def _view_setting(key, default=None):
        return "light" if key == "theme" else default

    cfg.get_view_setting = MagicMock(side_effect=_view_setting)
    engine = ThemeEngine(cfg)
    engine.initialize_active_theme()
    return engine


def main() -> int:
    app = QApplication(sys.argv)
    parent = QWidget()  # 真实父控件：保证离屏适配器生命周期与生产一致
    engine = build_theme_engine()

    from src.editor.export_service import ExportService
    from src.themes.theme_v2.consumer import v2_export_colors

    colors = v2_export_colors(engine)
    box: dict[str, object] = {}

    def on_done(pdf_data) -> None:
        box["data"] = pdf_data
        box["type"] = type(pdf_data).__name__
        app.quit()

    returned = ExportService.export_pdf(
        MD, True, parent, on_done, colors, engine, "C2 冒烟"
    )
    print(f"[smoke] export_pdf 返回类型: {type(returned).__name__}", flush=True)

    QTimer.singleShot(TIMEOUT_MS, app.quit)
    app.exec()

    if "data" not in box:
        print(f"[FAIL] {TIMEOUT_MS}ms 内未收到回调", flush=True)
        return 1

    data = box["data"]
    ok_type = isinstance(data, bytes)
    ok_head = ok_type and data.startswith(b"%PDF-")
    ok_size = ok_type and len(data) > 500
    print(
        f"[smoke] 回调类型={box['type']} 长度={len(data) if ok_type else 'N/A'}",
        flush=True,
    )
    print(f"[{'PASS' if ok_type else 'FAIL'}] 回调为 bytes", flush=True)
    print(f"[{'PASS' if ok_head else 'FAIL'}] PDF 头部 %PDF-", flush=True)
    print(f"[{'PASS' if ok_size else 'FAIL'}] 长度 > 500", flush=True)

    return 0 if (ok_type and ok_head and ok_size) else 1


if __name__ == "__main__":
    sys.exit(main())
