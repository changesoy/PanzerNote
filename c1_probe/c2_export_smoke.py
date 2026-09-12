# -*- coding: utf-8 -*-
"""导出端到端冒烟（C 路径：ExportService.export_pdf → WebView2 适配器）。

为什么不在 pytest 内跑：WebView2 适配器要求 qasync 把 asyncio 与 Qt 循环合并到
同一线程，而 pytest 套件不建立 asyncio 事件循环，且真实 WebView2 会另起原生子
进程，不适合放进共享测试进程。故分工如下：

- 确定性部分（打印设置 should_print_backgrounds、产物校验、HTML 写盘）
  → tests/test_export_webview2.py（pytest 内，无运行时依赖）
- 真实运行时端到端（离屏适配器真跑 print_to_pdf_async）
  → 本探针

断言：回调类型 / %PDF- 字节头 / 体积 / 可解析页数 / 第 1 页正文文本 /
pn_preview_*.pdf 临时文件中转无残留。

历史：本文件原为 C2 时期的 QWebEngineView 版（AA_ShareOpenGLContexts +
printToPdf），C3-D 摘除 WebEngine 后已失效，C4 改写为 WebView2 版。

用法：
  .venv\\Scripts\\python.exe c1_probe/c2_export_smoke.py
全程 30s 看门狗兜底，不会无限无响应。
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QWidget
from qasync import QEventLoop

TIMEOUT_MS = 30_000
MD = "# 标题\n\n中文正文与 `code`。\n\n```python\nprint('hello')\n```\n"

PASSED: list[str] = []
FAILED: list[str] = []


def report(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}", flush=True)
    (PASSED if ok else FAILED).append(name)


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


def leftover_preview_pdfs() -> set[str]:
    """导出用的临时文件中转（pn_preview_*.pdf）现状。"""
    return {p.name for p in Path(tempfile.gettempdir()).glob("pn_preview_*.pdf")}


def inspect_pdf(data: bytes) -> tuple[int, str]:
    """QPdfDocument 解析产物：返回（页数，第 1 页文本）。解析失败返回 (0, "")。

    经 QBuffer 在内存里加载：不落临时文件（QPdfDocument 会持有文件句柄，
    Windows 下随即 unlink 会报 WinError 32）。
    """
    from PyQt6.QtCore import QByteArray, QBuffer, QIODevice
    from PyQt6.QtPdf import QPdfDocument

    buffer = QBuffer()
    buffer.setData(QByteArray(data))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    doc = QPdfDocument(None)
    try:
        doc.load(buffer)
        if doc.error() != QPdfDocument.Error.None_:
            return 0, ""
        pages = doc.pageCount()
        if pages < 1:
            return 0, ""
        return pages, doc.getAllText(0).text()
    finally:
        doc.close()
        buffer.close()


def main() -> int:
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    parent = QWidget()  # 真实父控件：离屏适配器生命周期与生产一致
    engine = build_theme_engine()

    from src.editor.export_service import ExportService
    from src.themes.theme_v2.consumer import v2_export_colors

    colors = v2_export_colors(engine)
    before = leftover_preview_pdfs()
    box: dict[str, object] = {}

    def on_done(pdf_data) -> None:
        box["data"] = pdf_data
        loop.stop()

    returned = ExportService.export_pdf(
        MD, True, parent, on_done, colors, engine, "C4 冒烟"
    )
    print(f"[smoke] export_pdf 返回类型: {type(returned).__name__}", flush=True)

    QTimer.singleShot(TIMEOUT_MS, loop.stop)
    loop.run_forever()

    if "data" not in box:
        print(f"[FAIL] {TIMEOUT_MS}ms 内未收到回调", flush=True)
        loop.close()
        return 1

    data = box["data"]
    ok_type = isinstance(data, bytes)
    report("回调为 bytes", ok_type, type(data).__name__)
    if not ok_type:
        loop.close()
        return 1

    report("PDF 字节头 %PDF-", data.startswith(b"%PDF-"), f"长度={len(data)}")
    report("体积 > 500", len(data) > 500)

    pages, text = inspect_pdf(data)
    report("PDF 可解析且页数 >= 1", pages >= 1, f"页数={pages}")
    report(
        "第 1 页正文可抽取（内容真正渲染）",
        "标题" in text,
        f"文本长度={len(text)}",
    )

    residue = sorted(leftover_preview_pdfs() - before)
    report("临时文件中转已清理", not residue, ",".join(residue))

    loop.close()
    print(f"\n[smoke] 通过 {len(PASSED)} 项，失败 {len(FAILED)} 项", flush=True)
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
