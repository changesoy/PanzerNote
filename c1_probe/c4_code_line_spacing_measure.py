# -*- coding: utf-8 -*-
"""代码块行距一致性探针（预览 vs 导出）。

背景：设置项「代码块行间距」在预览与导出两侧表现不一致（用户真机报告导出更小）。
静态读 CSS 得不到定论 —— 两侧的 DOM 结构不同：

- 预览：`.code-container > .code-pre > .code-block > .code-line`（每行一个块级 span，
  带 min-height: calc(var(--code-line-spacing) * 1em)）
- 导出：`<pre><code>` 纯文本，行盒由 `pre, pre code { line-height: var(...) }` 决定

且两侧的**字号基准**可能不同（预览 .code-block 显式 14px；导出 body 未设 font-size）。
line-height 是倍数时，pitch = 倍数 × 自身 font-size，所以字号基准必须一致，否则
同一倍数会渲染出不同的绝对行距。

本探针在同一进程内用真实 WebView2 分别加载「真预览文档」与「真导出文档」，
读取计算样式（font-size / line-height / 解析出的变量值）与**实测行距**
（相邻行盒 top 之差），把差异钉成数字。

用法：
  .venv\\Scripts\\python.exe c1_probe/c4_code_line_spacing_measure.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from unittest.mock import MagicMock

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QWidget
from qasync import QEventLoop

TIMEOUT_MS = 40_000

# 两段正文 + 三行代码：既量代码块行距，也量正文行距作对照
MD = (
    "第一段正文，用于测量正文行距。\n\n"
    "第二段正文，用于测量正文行距。\n\n"
    "```python\nline_one = 1\nline_two = 2\nline_three = 3\n```\n"
)

MEASURE_PREVIEW_JS = """(function(){
  const lines = document.querySelectorAll('.code-line');
  const blk = document.querySelector('.code-block');
  if (!lines.length) return JSON.stringify({error: 'no .code-line'});
  const cs = getComputedStyle(lines[0]);
  const r = [lines[0].getBoundingClientRect(), lines[1].getBoundingClientRect()];
  const root = getComputedStyle(document.documentElement);
  const body = getComputedStyle(document.body);
  const ps = document.querySelectorAll('#content p');
  let bodyPitch = null;
  if (ps.length >= 2) {
    bodyPitch = Math.round((ps[1].getBoundingClientRect().top
                            - ps[0].getBoundingClientRect().top) * 100) / 100;
  }
  const describe = (n) => n.nodeType === 3
      ? 'TEXT:' + JSON.stringify(n.data)
      : n.nodeName + (n.className ? '.' + n.className : '');
  return JSON.stringify({
    count: lines.length,
    code_font: cs.fontSize,
    code_lineHeight: cs.lineHeight,
    pitch: Math.round((r[1].top - r[0].top) * 100) / 100,
    line_h: Math.round(r[0].height * 100) / 100,
    block_font: blk ? getComputedStyle(blk).fontSize : null,
    block_lineHeight: blk ? getComputedStyle(blk).lineHeight : null,
    block_whiteSpace: blk ? getComputedStyle(blk).whiteSpace : null,
    block_children: blk ? Array.from(blk.childNodes).map(describe) : null,
    body_font: body.fontSize,
    body_lineHeight: body.lineHeight,
    body_pitch: bodyPitch,
    var_code_ls: root.getPropertyValue('--code-line-spacing').trim(),
    var_css_code_ls: root.getPropertyValue('--css-code-line-spacing').trim(),
    var_line_ls: root.getPropertyValue('--line-spacing').trim()
  });
})()"""

MEASURE_EXPORT_JS = """(function(){
  const pre = document.querySelector('pre');
  const code = pre ? pre.querySelector('code') : null;
  if (!code) return JSON.stringify({error: 'no pre code'});
  const range = document.createRange();
  range.selectNodeContents(code);
  const rects = Array.from(range.getClientRects()).map(
    x => [Math.round(x.top * 100) / 100, Math.round(x.height * 100) / 100]
  );
  const cs = getComputedStyle(code);
  const ps = getComputedStyle(pre);
  const root = getComputedStyle(document.documentElement);
  const body = getComputedStyle(document.body);
  const bps = document.querySelectorAll('body > p');
  let bodyPitch = null;
  if (bps.length >= 2) {
    bodyPitch = Math.round((bps[1].getBoundingClientRect().top
                            - bps[0].getBoundingClientRect().top) * 100) / 100;
  }
  const tops = Array.from(new Set(rects.map(x => x[0])));
  return JSON.stringify({
    line_tops: tops,
    pitch: tops.length > 1 ? Math.round((tops[1] - tops[0]) * 100) / 100 : null,
    pre_font: ps.fontSize,
    pre_lineHeight: ps.lineHeight,
    code_font: cs.fontSize,
    code_lineHeight: cs.lineHeight,
    body_font: body.fontSize,
    body_lineHeight: body.lineHeight,
    body_pitch: bodyPitch,
    var_code_ls: root.getPropertyValue('--code-line-spacing').trim(),
    var_line_ls: root.getPropertyValue('--line-spacing').trim()
  });
})()"""

PASSED: list[str] = []
FAILED: list[str] = []


def report(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}", flush=True)
    (PASSED if ok else FAILED).append(name)


def build_theme_engine():
    from src.themes.theme_engine import ThemeEngine

    cfg = MagicMock()
    cfg.get_app_dir = MagicMock(return_value=".")
    cfg.get_view_setting = MagicMock(
        side_effect=lambda key, default=None: "light" if key == "theme" else default
    )
    engine = ThemeEngine(cfg)
    engine.initialize_active_theme()
    return engine


def build_config():
    """按生产默认值建模排版设置读取入口（与 tests/conftest.py 同口径）。"""
    from src.core.settings_store import (
        DEFAULT_CODE_FONT_FAMILY,
        DEFAULT_CODE_LINE_SPACING,
        DEFAULT_LINE_SPACING,
    )

    cfg = MagicMock()
    cfg.get_app_dir = MagicMock(return_value=".")
    cfg.get_view_setting = MagicMock(side_effect=lambda key, default=None: default)
    cfg.get_editor_setting = MagicMock(side_effect=lambda key, default=None: default)
    cfg.get_code_font_family = MagicMock(return_value=DEFAULT_CODE_FONT_FAMILY)
    cfg.get_line_spacing = MagicMock(return_value=DEFAULT_LINE_SPACING)
    cfg.get_code_line_spacing = MagicMock(return_value=DEFAULT_CODE_LINE_SPACING)
    return cfg


async def _eval(adapter, expr: str):
    """读取 WebView 求值结果。

    JS 侧用 JSON.stringify 返回字符串时，ExecuteScript 会再套一层 JSON 编码，
    故这里允许「解一层还是字符串」时再解一层。
    """
    try:
        raw = await adapter._webview.execute_script_async(expr)
    except Exception:  # noqa: BLE001
        return None
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            pass
    return value


async def measure_preview(host: QWidget, engine) -> dict:
    from src.editor.markdown_preview import MarkdownPreviewWidget

    widget = MarkdownPreviewWidget(build_config(), engine, parent=host)
    widget.editor.setPlainText(MD)
    widget._update_preview()
    widget._preview_timer.stop()

    data = None
    for _ in range(400):
        data = await _eval(widget.preview, MEASURE_PREVIEW_JS)
        if isinstance(data, dict) and data.get("count"):
            break
        await asyncio.sleep(0.05)

    # 假设验证：.code-line 之间的换行文本节点在 white-space: pre 下形成匿名行盒，
    # 使实测行距 = 2 × line-height。注入覆盖把 .code-block 的 white-space 改成
    # normal（.code-line 自身仍是 pre，缩进不受影响）后再量一次。
    if isinstance(data, dict) and data.get("block_whiteSpace") == "pre":
        await _eval(
            widget.preview,
            "(function(){const s=document.createElement('style');"
            "s.id='pn-probe-override';"
            "s.textContent='.code-block{white-space:normal !important}';"
            "document.head.appendChild(s);return JSON.stringify(1);})()",
        )
        await asyncio.sleep(0.1)
        overridden = await _eval(widget.preview, MEASURE_PREVIEW_JS)
        if isinstance(overridden, dict):
            data["pitch_after_ws_normal"] = overridden.get("pitch")
    widget.close()
    return data or {}


async def measure_export(host: QWidget, engine) -> dict:
    from src.editor.secure_markdown_renderer import (
        build_export_html_document,
        render_markdown_to_safe_html,
    )
    from src.editor.web_preview import create_preview_adapter
    from src.themes.theme_v2.consumer import v2_export_colors
    from src.core.settings_store import DEFAULT_CODE_LINE_SPACING, DEFAULT_LINE_SPACING

    html = build_export_html_document(
        render_markdown_to_safe_html(MD),
        v2_export_colors(engine),
        "行距探针",
        line_spacing=DEFAULT_LINE_SPACING,
        code_line_spacing=DEFAULT_CODE_LINE_SPACING,
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
    data = await _eval(adapter, MEASURE_EXPORT_JS)
    adapter.set_visible(False)
    return data or {}


def main() -> int:
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    host = QWidget()
    engine = build_theme_engine()

    preview = loop.run_until_complete(measure_preview(host, engine))
    export = loop.run_until_complete(measure_export(host, engine))

    print("\n=== 预览侧（WebView2 真文档）===")
    for k in ("count", "code_font", "code_lineHeight", "pitch", "line_h", "block_font",
              "block_lineHeight", "block_whiteSpace", "pitch_after_ws_normal",
              "body_font", "body_lineHeight", "body_pitch",
              "var_code_ls", "var_css_code_ls", "var_line_ls", "error"):
        if k in preview:
            print(f"  {k:22} = {preview[k]}")
    print(f"  {'block_children':22} = {preview.get('block_children')}")

    print("\n=== 导出侧（WebView2 真文档）===")
    for k in ("pre_font", "pre_lineHeight", "code_font", "code_lineHeight", "pitch",
              "body_font", "body_lineHeight", "body_pitch", "var_code_ls", "var_line_ls",
              "error"):
        if k in export:
            print(f"  {k:22} = {export[k]}")
    print(f"  {'line_tops':22} = {export.get('line_tops')}")

    print("\n=== 对比 ===")
    p_pitch, e_pitch = preview.get("pitch"), export.get("pitch")
    p_font, e_font = preview.get("code_font"), export.get("code_font")
    print(f"  代码块实测行距(pitch): 预览 {p_pitch} / 导出 {e_pitch}")
    print(f"  -> 覆盖 white-space 后预览: {preview.get('pitch_after_ws_normal')}")
    print(f"  代码字号:              预览 {p_font} / 导出 {e_font}")
    report("两侧代码块行距一致", bool(p_pitch and e_pitch and abs(p_pitch - e_pitch) < 0.5),
           f"preview={p_pitch} export={e_pitch}")
    report("两侧代码字号一致", bool(p_font and e_font and p_font == e_font),
           f"preview={p_font} export={e_font}")

    QTimer.singleShot(TIMEOUT_MS, loop.stop)
    loop.close()
    print(f"\n[probe] 通过 {len(PASSED)} 项，失败 {len(FAILED)} 项", flush=True)
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
