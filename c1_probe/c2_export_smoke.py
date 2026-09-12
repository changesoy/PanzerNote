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
pn_preview_*.pdf 临时文件中转无残留；随后在同一进程里把「含公式的导出文档」
灌进真实 WebView2，断言 KaTeX 确实把 .math 渲染成了 .katex DOM
（数学公式第一批的运行时证据）；再走一遍图表 PDF 导出，断言图表 SVG 文字
出现在 PDF 文本层而源码未泄漏（图表异步渲染就绪门的运行时证据 ——
PDF 是最终产物，这个断言比 DOM 层更贴近用户）；最后走一遍甘特图 PDF 导出，
断言图表横向铺开到纸面宽度（甘特图宽度取自容器宽度，离屏视口若不先调成纸面
尺寸就会被压成纸面左侧一小条）。

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
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication, QWidget
from qasync import QEventLoop

TIMEOUT_MS = 30_000
MD = "# 标题\n\n中文正文与 `code`。\n\n```python\nprint('hello')\n```\n"
MATH_MD = "行内 $E=mc^2$ 公式\n\n$$\n\\int_0^1 x\\,dx\n$$\n"
MERMAID_MD = "图表演示\n\n```mermaid\ngraph LR\n  A[Start] --> B[End]\n```\n"
# 甘特图节点文字保持英文：沙箱会拦截中文字体（MSYH.TTC）的加载
GANTT_MD = (
    "Gantt demo\n\n```mermaid\ngantt\n  title Plan\n  dateFormat YYYY-MM-DD\n"
    "  section Design\n    Spec :a1, 2026-09-01, 5d\n    Proto :a2, 2026-09-06, 4d\n"
    "  section Build\n    Code :a3, 2026-09-10, 10d\n```\n"
)

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


def build_config():
    """复刻 tests/conftest.py 的 mock_config（取值一律回落到默认值）。"""
    cfg = MagicMock()
    cfg.get_app_dir = MagicMock(return_value=".")
    cfg.get_view_setting = MagicMock(side_effect=lambda key, default=None: default)
    # code_font_family 必须给 str：H1 后 code_font_css_stack 对族名做 re.sub
    cfg.get_editor_setting = MagicMock(
        side_effect=lambda key, default=None:
            "" if key == "code_font_family" else default
    )
    # H1 后 code_font_css_stack 对族名做 re.sub，mock 必须给 str
    cfg.get_code_font_family = MagicMock(return_value="")
    return cfg


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


def page_ink_span(data: bytes) -> float:
    """第 1 页内容的横向跨度占比（0-1）。

    栅格化后取「已绘制且非白」像素的左右边界：甘特图铺开时约 0.84（纸面左右各留
    页边距），被压成左侧一小条时约 0.1。比读 SVG 属性的 DOM 断言更贴近用户看到
    的产物。

    注意必须排除 alpha=0：PDF 页面不绘制背景，未绘制区域经 QColor 读出来是黑色
    （曾因此得到恒为 1.00 的假阳性）。
    """
    from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QSize
    from PyQt6.QtPdf import QPdfDocument

    buffer = QBuffer()
    buffer.setData(QByteArray(data))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    doc = QPdfDocument(None)
    try:
        doc.load(buffer)
        if doc.error() != QPdfDocument.Error.None_:
            return 0.0
        image = doc.render(0, QSize(200, 283))
    finally:
        doc.close()
        buffer.close()

    if image.isNull():
        return 0.0
    width, height = image.width(), image.height()
    lo, hi = width, -1
    for y in range(height):
        for x in range(width):
            color = image.pixelColor(x, y)
            if color.alpha() > 0 and color.lightness() < 200:
                lo = min(lo, x)
                hi = max(hi, x)
    return 0.0 if hi < 0 else (hi - lo + 1) / width


async def preview_mermaid_phase(parent: QWidget, engine) -> None:
    """预览侧懒注入：内容先于模板加载到达时，图表库必须被补齐。

    会话恢复正是这个时序：整页灌入（_push_to_preview 的 else 分支）不注入图表库，
    而恢复后没有后续内容更新 —— 若不补，图表就一直以源码文本留在页面上（用户真机
    复现）。故本相位刻意「先推内容、再停掉防抖定时器」以复刻「之后不再推送」。
    """
    from src.editor.markdown_preview import MarkdownPreviewWidget

    widget = MarkdownPreviewWidget(build_config(), engine, parent=parent)
    adapter = widget.preview
    # 适配器尚未就绪就推内容：与恢复时序一致（内容先到，模板随后才加载完）
    widget.editor.setPlainText(MERMAID_MD)
    widget._update_preview()
    widget._preview_timer.stop()  # 复刻「之后没有内容更新」

    svg = 0
    for _ in range(400):
        svg = await _eval(adapter, "document.querySelectorAll('.pn-mermaid svg').length") or 0
        if svg:
            break
        await asyncio.sleep(0.05)
    report(
        "预览：内容早于模板加载到达仍渲染出图表（会话恢复路径）",
        svg == 1,
        f"svg={svg}",
    )
    widget.close()


async def _eval(adapter, expr: str) -> object:
    """仅探针使用的读取通道：直接取 WebView 求值（接口不提供返回值）。"""
    import json

    try:
        raw = await adapter._webview.execute_script_async(expr)
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        return None


async def math_phase(host: QWidget, colors) -> None:
    """含公式的导出文档在真实 WebView2 里的渲染结果。

    KaTeX 走同步渲染（页面脚本在 load 事件前跑完），故导航完成即可读 DOM：
    公式的最终证据是 .math 容器里出现 .katex 产物，而 KaTeX 若没加载出来
    容器只会保留原始 TeX 文本 —— 两种情况下 PDF 文本都拿不到定界符，
    所以必须在 DOM 层断言。
    """
    from src.editor.secure_markdown_renderer import (
        build_export_html_document,
        render_markdown_to_safe_html,
    )
    from src.editor.web_preview import create_preview_adapter

    html = build_export_html_document(
        render_markdown_to_safe_html(MATH_MD), colors, "公式冒烟"
    )
    adapter = create_preview_adapter(host)
    loads: list[bool] = []
    adapter.load_finished.connect(lambda ok: loads.append(ok))

    for _ in range(300):
        if getattr(adapter, "_ready", False):
            break
        await asyncio.sleep(0.05)
    adapter.set_html(html)
    for _ in range(200):
        if loads:
            break
        await asyncio.sleep(0.05)
    report("公式文档导航完成", bool(loads) and loads[0] is True, f"loads={loads}")

    containers = await _eval(adapter, "document.querySelectorAll('.math').length")
    report("公式容器（.math）两个：行内 + 块级", containers == 2, f"count={containers}")
    katex = await _eval(adapter, "document.querySelectorAll('.katex').length")
    report("KaTeX 渲染出 .katex DOM", katex == 2, f"count={katex}")
    glyphs = await _eval(
        adapter, "document.querySelectorAll('.katex .mord,.katex .mrel').length"
    )
    report(
        "公式内含排版字符节点",
        isinstance(glyphs, int) and glyphs > 0,
        f"nodes={glyphs}",
    )
    adapter.set_visible(False)


async def navigation_ownership_phase(parent: QWidget) -> None:
    """M5 真机时序证据：初始空白文档的导航完成不得 emit load_finished。

    监听器在适配器构造后立即连接（早于 controller 创建完成）。controller
    创建时会导航到初始空白文档，其 NavigationCompleted 可能晚于事件处理器
    注册到达 —— 若被无条件 emit，消费方会在模板尚未 set_html 时永久置位
    「模板已加载」，后续 innerHTML 分支找不到 #content，预览静默空白。
    修复后：只有 _navigate 发起的导航才 emit。
    """
    from src.editor.web_preview import create_preview_adapter

    adapter = create_preview_adapter(parent)
    loads: list[bool] = []
    adapter.load_finished.connect(lambda ok: loads.append(ok))

    for _ in range(300):
        if getattr(adapter, "_ready", False):
            break
        await asyncio.sleep(0.05)
    report(
        "适配器就绪前 load_finished 未 emit（初始空白文档不归属本适配器）",
        not loads,
        f"loads={loads}",
    )

    adapter.set_html("<html><body><div id='content'>m5</div></body></html>")
    for _ in range(200):
        if loads:
            break
        await asyncio.sleep(0.05)
    report(
        "set_html 发起的导航完成会 emit",
        bool(loads) and loads[0] is True,
        f"loads={loads}",
    )
    adapter.close()


async def resource_root_phase(parent: QWidget) -> None:
    """资源根（虚拟主机映射 + <base href>）路径的真机证据。

    本相位覆盖冒烟其余相位都没走的分支：set_resource_root 非空时适配器注入
    ``<base href="https://pnassets/">``，文档内的相对路径经虚拟主机映射解析。
    这是 L3（映射权限 ALLOW → DENY_CORS）唯一的作用面，必须真机确认收窄没有
    连带打掉「相对图片」这类常规子资源；同时断言 fetch() 确实被 CORS 拒绝
    （收窄的意图本身），以及 WinRT 回调的线程归属（_await_page_render 的
    轮询说明以「回调在创建 controller 的线程触发」为准）。
    """
    import threading

    from src.editor.web_preview import create_preview_adapter

    tmp = Path(tempfile.mkdtemp(prefix="pn_vhost_"))
    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(QColor("#336699"))
    png = tmp / "pic.png"
    image.save(str(png))
    html = (
        '<html><head><meta charset="utf-8"></head><body>'
        '<img id="pic" src="pic.png">'
        "<script>window.pnState={img:'pending',fetch:'pending'};"
        "var im=document.getElementById('pic');"
        "im.onload=function(){window.pnState.img='ok:'+im.naturalWidth;};"
        "im.onerror=function(){window.pnState.img='error';};"
        "fetch('https://pnassets/pic.png').then("
        "function(){window.pnState.fetch='ok';},"
        "function(){window.pnState.fetch='cors-denied';});"
        "</script></body></html>"
    )

    adapter = create_preview_adapter(parent)
    adapter.set_resource_root(str(tmp))
    for _ in range(300):
        if getattr(adapter, "_ready", False):
            break
        await asyncio.sleep(0.05)

    adapter.set_html(html)
    state: dict[str, str] = {}
    for _ in range(300):
        raw = await _eval(adapter, "window.pnState || null")
        if isinstance(raw, dict):
            state = raw
            if state.get("img", "pending") != "pending" and state.get("fetch") != "pending":
                break
        await asyncio.sleep(0.05)
    report(
        "资源根：相对路径 <img> 经虚拟主机加载成功（DENY_CORS 不打掉非 CORS 子资源）",
        str(state.get("img", "")).startswith("ok:"),
        str(state.get("img")),
    )
    report(
        "资源根：fetch() 被 CORS 拒绝（权限收窄生效）",
        state.get("fetch") == "cors-denied",
        str(state.get("fetch")),
    )

    main_ident = threading.get_ident()
    seen: list[int] = []
    nav_fn = adapter._on_navigation_completed

    def spy(sender, args):  # noqa: ANN001
        seen.append(threading.get_ident())
        return nav_fn(sender, args)

    adapter._webview.add_navigation_completed(spy)
    adapter.set_html("<html><body>thread-check</body></html>")
    for _ in range(200):
        if seen:
            break
        await asyncio.sleep(0.05)
    report(
        "NavigationCompleted 回调在创建 controller 的线程触发",
        bool(seen) and all(i == main_ident for i in seen),
        f"main={main_ident} callbacks={seen}",
    )
    adapter.close()


def mermaid_pdf_phase(loop, host: QWidget, colors, engine) -> None:
    """图表 PDF 导出：真机证据是图表渲染成 SVG 且源码未泄漏。

    就绪门的证据藏在 PDF 里：若适配器不等渲染完成就打印，图表位置会是源码
    文本（"graph LR ..."）或空白；若等了，PDF 文本层会出现 SVG 里的 "Start"/
    "End" 而源码 "graph LR" 不见。PDF 是最终产物，这个断言比 DOM 层更贴近用户。
    """
    from src.editor.export_service import ExportService

    box: dict[str, object] = {}

    def on_done(pdf_data) -> None:
        box["data"] = pdf_data
        loop.stop()

    ExportService.export_pdf(
        MERMAID_MD, True, host, on_done, colors, engine, "图表冒烟"
    )
    QTimer.singleShot(TIMEOUT_MS, loop.stop)
    loop.run_forever()

    data = box.get("data", b"")
    if not isinstance(data, bytes) or not data:
        report("图表 PDF 导出拿到产物", False, f"{type(data).__name__}/{len(data)}")
        return
    report("图表 PDF 导出拿到产物", True, f"长度={len(data)}")
    pages, text = inspect_pdf(data)
    report("图表 PDF 可解析", pages >= 1, f"页数={pages}")
    report(
        "图表 SVG 文字出现在 PDF（渲染完成才打印）",
        "Start" in text and "End" in text,
        f"文本长度={len(text)}",
    )
    report(
        "图表源码未以文本泄漏（就绪门生效）",
        "graph LR" not in text and "-->" not in text,
    )
    report("图表页正文仍在", "图表演示" in text)


def gantt_pdf_phase(loop, host: QWidget, colors, engine) -> None:
    """甘特图 PDF 导出：真机证据是图表横向铺开到纸面宽度。

    甘特图宽度取自容器宽度（mermaid 源码：以 parentElement.offsetWidth 作 SVG
    viewBox 宽度），而离屏容器从不进入布局、尺寸停留在 Qt 默认的袖珍值 —— 若不先
    把视口调成纸面尺寸，整张图会被压成纸面左侧一小条（用户真机复现过）。
    """
    from src.editor.export_service import ExportService

    box: dict[str, object] = {}

    def on_done(pdf_data) -> None:
        box["data"] = pdf_data
        loop.stop()

    ExportService.export_pdf(
        GANTT_MD, True, host, on_done, colors, engine, "甘特图冒烟"
    )
    QTimer.singleShot(TIMEOUT_MS, loop.stop)
    loop.run_forever()

    data = box.get("data", b"")
    if not isinstance(data, bytes) or not data:
        report("甘特图 PDF 导出拿到产物", False, f"{type(data).__name__}/{len(data)}")
        return
    report("甘特图 PDF 导出拿到产物", True, f"长度={len(data)}")

    pages, text = inspect_pdf(data)
    ratio = page_ink_span(data)
    report(
        "甘特图横向铺开到纸面宽度",
        pages >= 1 and ratio >= 0.5,
        f"页数={pages} 墨迹跨度={ratio:.2f}",
    )
    report("甘特图未以源码文本泄漏", "dateFormat" not in text and "section" not in text)


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

    loop.run_until_complete(math_phase(parent, colors))
    loop.run_until_complete(navigation_ownership_phase(parent))
    loop.run_until_complete(resource_root_phase(parent))
    loop.run_until_complete(preview_mermaid_phase(parent, engine))
    mermaid_pdf_phase(loop, parent, colors, engine)
    gantt_pdf_phase(loop, parent, colors, engine)

    loop.close()
    print(f"\n[smoke] 通过 {len(PASSED)} 项，失败 {len(FAILED)} 项", flush=True)
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
