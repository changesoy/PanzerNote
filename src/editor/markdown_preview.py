# -*- coding: utf-8 -*-
"""
Markdown分屏预览组件
左侧为原始Markdown编辑器，右侧为渲染预览

v1.5.2 改动：
  - 代码块浅蓝色背景（#EDF3FA），无左侧竖条
  - 浮动复制按钮：鼠标悬停代码块时出现，移到按钮上显示 tooltip
  - 代码块语法高亮（Pygments 内联样式，配色与编辑器一致）
  - 修复代码块末尾多余空行
  - TOC 目录浅蓝色背景样式

v1.5.4 改动：
  - Markdown 预览中支持本地图片：自动将相对路径 ![](./img.png) 解析为 file:// 绝对路径

v1.6.2 改动：
  - 渲染引擎优先使用 markdown-it-py（CommonMark 兼容），修复列表无法打断段落的 bug
  - 回退兼容：未安装 markdown-it-py 时仍使用 python-markdown
"""

import os
import re
import time
import json
import html as html_module
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QSplitter, QVBoxLayout, QApplication
)
from PyQt6.QtCore import Qt, QTimer, QUrl, QPoint
from PyQt6.QtGui import QDesktopServices, QTextCursor

from .web_preview import create_preview_adapter

try:
    from markdown_it import MarkdownIt as _MarkdownIt
    HAS_MARKDOWN_IT = True
except ImportError:
    HAS_MARKDOWN_IT = False

try:
    import markdown as md_lib
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

from ..core.config import Config
from ..core.settings_store import DEFAULT_CODE_LINE_SPACING, DEFAULT_LINE_SPACING
from ..editor.editor import Editor
from ..utils.logger import get_logger
from ..utils.feature_flags import is_enabled
from ..themes.theme_aware_mixin import ThemeAwareMixin
from ..themes.theme_v2.consumer import (
    v2_active_variant,
    v2_color,
    v2_style_value,
    v2_token,
)
from .highlight_themes import highlight_code_html

# ════════════════════════════════════════════════════════
#  正则 / 常量
# ════════════════════════════════════════════════════════

# 匹配 <img src="..."> 标签中的 src 属性
_IMG_SRC_RE = re.compile(
    r'(<img\s[^>]*?)src="([^"]*)"',
    re.IGNORECASE,
)

from .secure_markdown_renderer import (
    CODEBLOCK_RE as _CODEBLOCK_RE,
    MARKDOWN_LAYOUT_CSS as _MARKDOWN_LAYOUT_CSS,
    code_font_css_stack as _code_font_css_stack,
    extract_language_from_code_attrs as _extract_language_from_code_attrs,
    extract_mermaid_blocks as _extract_mermaid_blocks,
    strip_dangerous_html as _strip_dangerous_html,
)
from .document_render_cache import _DOC_RENDER_CACHE, clear_document_render_cache
from . import math_render as _math_render
from . import mermaid_render as _mermaid_render

# ════════════════════════════════════════════════════════
#  HTML 模板
# ════════════════════════════════════════════════════════

PREVIEW_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
:root {{
    --bg-card: var(--css-bg-card);
    --text-primary: var(--css-text-primary);
    --text-secondary: var(--css-text-secondary);
    --text-muted: var(--css-text-muted);
    --border: var(--css-border);
    --border-soft: var(--css-border-soft);
    --divider: var(--css-divider);
    --surface: var(--css-surface);
    --surface-soft: var(--css-surface-soft);
    --surface-hover: var(--css-surface-hover);
    --primary: var(--css-primary);
    --primary-hover: var(--css-primary-hover);
    --bg-codeblock: var(--css-bg-codeblock);
    --codeblock-border: var(--css-codeblock-border);
    --toc-bg: var(--css-toc-bg);
    --scrollbar-track: var(--css-scrollbar-track);
    --scrollbar-thumb: var(--css-scrollbar-thumb);
    --scrollbar-thumb-hover: var(--css-scrollbar-thumb-hover);
    --code-font: var(--css-code-font);
    --line-spacing: var(--css-line-spacing);
    --code-line-spacing: var(--css-code-line-spacing);
    --sb-width: var(--css-sb-width);
    --sb-radius: var(--css-sb-radius);
    --sb-margin: var(--css-sb-margin);
}}

/* ========== 基础 ========== */
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei UI",
                 "Microsoft YaHei", Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: var(--line-spacing);
    color: var(--text-primary);
    padding: 12px 20px 40px 20px;
    margin: 0;
    max-width: 100%;
    background: var(--bg-card);
    word-wrap: break-word;
    overflow-wrap: break-word;
}}

/* ========== Markdown 内容排版（共享单一来源，Wave 1.5） ========== */
{layout_css}

/* ========== TOC 目录 ========== */
.toc {{
    background: var(--toc-bg);
    border-radius: 4px;
    padding: 10px 16px;
    margin: 10px 0 20px 0;
    font-size: 0.92em;
    line-height: 1.8;
}}
.toc ul {{
    list-style: none;
    padding-left: 18px;
    margin: 4px 0;
}}
.toc > ul {{ padding-left: 0; }}
.toc li {{ margin: 2px 0; }}
.toc a {{ color: var(--primary); text-decoration: none; }}
.toc a:hover {{ text-decoration: underline; color: var(--primary-hover); }}

/* ========== 代码块容器 ========== */
.code-container {{
    position: relative;
    margin: 16px 0;
    padding: 0;
    border-radius: 6px;
    background: var(--bg-codeblock);
    border: 1px solid var(--codeblock-border);
    overflow: auto;
}}
.code-pre {{
    margin: 0;
    padding: 12px 14px;
    background: transparent;
    overflow-x: auto;
    white-space: pre;
}}
.code-block {{
    display: block;
    margin: 0;
    padding: 0 !important;
    background: transparent !important;
    border-radius: 0 !important;
    font-family: var(--code-font);
    font-size: 14px;
    line-height: var(--code-line-spacing);
    white-space: pre;
    color: var(--text-primary);
}}
.code-line {{
    display: block;
    min-height: calc(var(--code-line-spacing) * 1em);
    white-space: pre;
    background: transparent !important;
}}
.code-copy-btn {{
    display: none;
    position: absolute;
    top: 4px;
    right: 4px;
    width: 26px;
    height: 22px;
    border: 1px solid rgba(128, 128, 128, 0.35);
    border-radius: 3px;
    background: rgba(128, 128, 128, 0.12);
    font-size: 12px;
    line-height: 20px;
    padding: 0;
    cursor: pointer;
    z-index: 10;
}}
.code-copy-btn:hover {{
    background: rgba(128, 128, 128, 0.25);
    border-color: rgba(128, 128, 128, 0.55);
}}
.code-container:hover .code-copy-btn {{
    display: block;
}}

pre code,
.code-block,
.code-block code,
.code-line {{
    background: transparent !important;
    padding: 0 !important;
    border-radius: 0 !important;
    border: none !important;
}}

/* ========== 折叠区块（预览折叠对标编辑器折叠） ========== */
section[data-fold-heading] {{
    display: block;
    margin: 0;
}}
section[data-fold-heading].folded {{
    display: none;
}}

/* ========== 滚动条（与编辑器样式一致：同一 scrollbar recipe 供值） ========== */
::-webkit-scrollbar {{
    width: var(--sb-width);
    height: var(--sb-width);
}}
::-webkit-scrollbar-track {{
    background: var(--scrollbar-track);
}}
::-webkit-scrollbar-thumb {{
    background: var(--scrollbar-thumb);
    border-radius: var(--sb-radius);
    border: var(--sb-margin) solid var(--scrollbar-track);
}}
::-webkit-scrollbar-thumb:hover {{
    background: var(--scrollbar-thumb-hover);
}}
::-webkit-scrollbar-corner {{
    background: var(--scrollbar-track);
}}
</style>
{math_style}
</head>
<body>
<div id="content">
{content}
</div>
<script>
// ========== 预览 → Python 消息通道（WebView2 官方 postMessage） ==========
// 协议：`<前缀>:<载荷>`；前缀由 Python 侧 _on_preview_message 消费
// （__pzsync__ 滚动同步 / __pnopen__ 外开链接 / __pncopy__ 复制代码块）。
// 无宿主的场合（导出文档被普通浏览器打开）静默跳过，不抛错。
window.pnPostMessage = function (message) {{
    try {{
        if (window.chrome && window.chrome.webview) {{
            window.chrome.webview.postMessage(String(message));
            return true;
        }}
    }} catch (e) {{}}
    return false;
}};

// ========== 锚点缓存：layout 变化(内容/高度/宽度)即重建 ==========
var _nodesVersion = null;
var _cachedNodes = null;

// 编辑器→预览 驱动滚动时的回声锁：在此时间戳前，预览自身的 scroll 事件
// 视为回声，不回传给编辑器，避免双向同步形成回授环。
var _previewScrollLock = 0;
var _pvScrollTimer = null;

// 收集 [data-source-line] 锚点：{{line, top}}(相对文档顶部的绝对像素)。
// 缓存键含 scrollHeight + innerWidth：任何重排(改宽度/缩放/图片加载/内容变更)
// 都会改变其一从而自动失效，避免拖动分隔条后锚点 top 变陈旧。
function _collectAnchors() {{
    var contentEl = document.getElementById("content");
    var ver = (contentEl ? contentEl.childElementCount : 0) + "|"
            + document.documentElement.scrollHeight + "|" + window.innerWidth;
    if (_nodesVersion === ver && _cachedNodes) {{ return _cachedNodes; }}
    _nodesVersion = ver;
    var scrollTop = window.pageYOffset || document.documentElement.scrollTop || 0;
    _cachedNodes = Array.prototype.slice
        .call(document.querySelectorAll("[data-source-line]"))
        .map(function(el) {{
            var r = el.getBoundingClientRect();
            return {{ line: Number(el.getAttribute("data-source-line")),
                     top: r.top + scrollTop }};
        }})
        .filter(function(x) {{ return !Number.isNaN(x.line); }})
        .sort(function(a, b) {{ return (a.line - b.line) || (a.top - b.top); }});
    return _cachedNodes;
}}

// 末尾追加 EOF 哨兵锚点，使末块很高时也能插值到底。
function _anchorsWithSentinel(nodes, totalLines) {{
    var docH = document.documentElement.scrollHeight;
    var lastReal = nodes[nodes.length - 1];
    var sentinelLine = (typeof totalLines === "number" && totalLines > lastReal.line)
        ? (totalLines + 1) : (lastReal.line + 1);
    return nodes.concat([{{ line: sentinelLine, top: docH }}]);
}}

// === 编辑器 -> 预览 ===
// 把"编辑器顶部源码行(可带小数)"对齐到"预览视口顶部"(top-to-top)。
//   · 顶行对齐：与两侧高度比无关，窄预览同样成立(VSCode markdown 预览模型)。
//   · EOF 哨兵：末块很高(窄预览下长表格/长段落)也能按源码行比例平滑滚到底。
//   · 硬端点：编辑器真正到顶/到底时，预览直接赋值贴 0 / maxScroll。
window.scrollToSourceLine = function(fracLine, totalLines, atTop, atBottom) {{
    try {{
        if (typeof fracLine !== "number" || !isFinite(fracLine)) {{ fracLine = 1; }}

        var maxScroll = Math.max(0,
            document.documentElement.scrollHeight - window.innerHeight);
        if (maxScroll <= 0) {{
            window.__panzerSyncDebug = {{ fracLine: fracLine, boundary: "too-short" }};
            return;
        }}

        // 本次是编辑器驱动的滚动，给预览自身 scroll 事件上回声锁
        _previewScrollLock = performance.now() + 220;

        if (atTop === true) {{
            document.documentElement.scrollTop = 0;
            document.body.scrollTop = 0;
            window.__panzerSyncDebug = {{ fracLine: fracLine, boundary: "top-snap" }};
            return;
        }}
        if (atBottom === true) {{
            document.documentElement.scrollTop = maxScroll;
            document.body.scrollTop = maxScroll;
            window.__panzerSyncDebug = {{ fracLine: fracLine, boundary: "bottom-snap" }};
            return;
        }}

        var nodes = _collectAnchors();

        if (!nodes.length) {{
            if (typeof totalLines === "number" && totalLines > 0) {{
                var fr = Math.max(0, Math.min(1, fracLine / totalLines));
                window.scrollTo({{ top: fr * maxScroll, behavior: "auto" }});
            }}
            window.__panzerSyncDebug = {{ fracLine: fracLine, error: "no anchors" }};
            return;
        }}

        var anchors = _anchorsWithSentinel(nodes, totalLines);

        if (fracLine <= anchors[0].line) {{
            window.scrollTo({{ top: 0, behavior: "auto" }});
            window.__panzerSyncDebug = {{ fracLine: fracLine, boundary: "before-first" }};
            return;
        }}

        var prev = anchors[0], next = anchors[anchors.length - 1];
        for (var i = 0; i < anchors.length - 1; i++) {{
            if (anchors[i].line <= fracLine && fracLine < anchors[i + 1].line) {{
                prev = anchors[i];
                next = anchors[i + 1];
                break;
            }}
        }}

        var targetTop = prev.top;
        if (next.line > prev.line) {{
            var t = (fracLine - prev.line) / (next.line - prev.line);
            t = Math.max(0, Math.min(1, t));
            targetTop = prev.top + (next.top - prev.top) * t;
        }}

        var finalTop = Math.max(0, Math.min(targetTop, maxScroll));
        window.scrollTo({{ top: finalTop, behavior: "auto" }});

        window.__panzerSyncDebug = {{
            fracLine: fracLine, prevLine: prev.line, nextLine: next.line,
            targetTop: targetTop, finalTop: finalTop, maxScroll: maxScroll,
            nodeCount: nodes.length
        }};
    }} catch (e) {{
        console.error('[SYNC-JS] scrollToSourceLine error:', e);
        window.__panzerSyncDebug = {{ error: e.message, stack: e.stack }};
    }}
}};

// === 预览 -> 编辑器 ===
// 预览视口顶部像素 -> 源码行(可带小数)，是 scrollToSourceLine 的逆映射。
function _previewTopToLine() {{
    var nodes = _collectAnchors();
    if (!nodes.length) {{ return null; }}
    var anchors = _anchorsWithSentinel(nodes, window.__lastTotalLines || 0);
    var top = window.pageYOffset || document.documentElement.scrollTop || 0;
    if (top <= anchors[0].top) {{ return anchors[0].line; }}
    var prev = anchors[0], next = anchors[anchors.length - 1];
    for (var i = 0; i < anchors.length - 1; i++) {{
        if (anchors[i].top <= top && top < anchors[i + 1].top) {{
            prev = anchors[i];
            next = anchors[i + 1];
            break;
        }}
    }}
    var line = prev.line;
    if (next.top > prev.top) {{
        var t = (top - prev.top) / (next.top - prev.top);
        line = prev.line + (next.line - prev.line) * t;
    }}
    return line;
}}

// 预览滚动时把顶部源码行经消息通道回传给 Python。
// performance.now() 早于 _previewScrollLock 说明是编辑器驱动的回声，跳过。
function _reportPreviewScroll() {{
    if (performance.now() < _previewScrollLock) {{ return; }}
    var line = _previewTopToLine();
    if (line == null) {{ return; }}
    window.pnPostMessage("__pzsync__:" + line.toFixed(3));
}}
function _schedulePreviewScrollReport() {{
    if (_pvScrollTimer) {{ return; }}
    _pvScrollTimer = setTimeout(function() {{
        _pvScrollTimer = null;
        _reportPreviewScroll();
    }}, 60);
}}
window.addEventListener("scroll", _schedulePreviewScrollReport, {{ passive: true }});

// 页面尺寸在渲染后变化（图片加载完成 / 图表渲染出 SVG）时，锚点缓存与滚动
// 位置都已过期，需要按上次的同步状态重算一次。
window.resyncAfterLayout = function() {{
    _nodesVersion = null;
    _cachedNodes = null;
    if (window.scrollToSourceLine) {{
        window.scrollToSourceLine(
            typeof window.__lastFracLine === "number" ? window.__lastFracLine : 1,
            window.__lastTotalLines || 0,
            window.__lastAtTop === true,
            window.__lastAtBottom === true
        );
    }}
}};

window.resyncAfterImagesLoaded = function() {{
    document.querySelectorAll("img").forEach(function(img) {{
        if (img.__panzerNoteSyncBound) {{ return; }}
        img.__panzerNoteSyncBound = true;

        img.addEventListener("load", window.resyncAfterLayout);
        img.addEventListener("error", window.resyncAfterLayout);
    }});
}};

// ========== 折叠区块可见性同步 ==========
window.updateFoldVisibility = function(collapsedLinesJson) {{
    try {{
        _previewScrollLock = performance.now() + 220;
        var collapsedLines = JSON.parse(collapsedLinesJson);
        var collapsedSet = new Set(collapsedLines.map(String));
        var sections = document.querySelectorAll('section[data-fold-heading]');
        for (var i = 0; i < sections.length; i++) {{
            var line = sections[i].getAttribute('data-fold-heading');
            if (collapsedSet.has(line)) {{
                sections[i].classList.add('folded');
            }} else {{
                sections[i].classList.remove('folded');
            }}
        }}
    }} catch(e) {{}}
}};

(function() {{
    document.addEventListener('click', function(e) {{
        // 链接点击 → 外部浏览器打开（经消息通道回传，阻止预览内部导航）
        var a = e.target.closest('a');
        if (a) {{
            var href = a.getAttribute('href');
            if (href != null && href.charAt(0) !== '#') {{
                e.preventDefault();
                window.pnPostMessage('__pnopen__:' + href);
                return;
            }}
        }}
        var btn = e.target.closest('.code-copy-btn');
        if (!btn) return;
        e.stopPropagation();
        var idx = btn.getAttribute('data-code-index');
        if (idx == null) return;
        window.pnPostMessage('__pncopy__:' + idx);
        btn.textContent = '\\u2714';
        setTimeout(function() {{ btn.textContent = '\\ud83d\\udccb'; }}, 800);
    }});
}})();
</script>
{math_script}
</body>
</html>"""


# ════════════════════════════════════════════════════════
#  预览模板 CSS 变量注入（替代旧的正则颜色替换）
# ════════════════════════════════════════════════════════

def _preview_css_vars(
    theme_engine,
    code_font_family: str | None = None,
    line_spacing: float | None = None,
    code_line_spacing: float | None = None,
) -> dict[str, str]:
    """预览 CSS 变量表（键为 CSS 变量短名，值为实际值）。

    单一真相源：首屏模板注入块（_build_preview_css_vars）与主题切换/设置变更时的
    运行时更新（_css_vars_update_js）都从本表取值，避免两处漂移。

    覆盖范围 = 预览中**全部随主题或设置变化的样式**：颜色 token + 代码字体 +
    行距 + 滚动条尺寸。滚动条尺寸也纳入变量，主题切换才能不重载页面
    （否则只能整页 set_html 重新灌入模板里的字面量）。
    """
    sb_width = int(v2_style_value(theme_engine, "scrollbar", "width", 12))
    sb_margin = int(v2_style_value(theme_engine, "scrollbar", "margin", 2))
    # 行距是倍数，必须写成无单位数字（与 px 项同理：变量替换是纯文本替换，
    # 带了单位会污染 line-height 与 calc()）
    spacing = DEFAULT_LINE_SPACING if line_spacing is None else float(line_spacing)
    code_spacing = (
        DEFAULT_CODE_LINE_SPACING if code_line_spacing is None else float(code_line_spacing)
    )
    # 颜色语义映射：CSS 变量名 → v2 token / recipe 值（B8：字面量 fallback = v1 light 值）
    return {
        "code-font": _code_font_css_stack(code_font_family),
        "line-spacing": f"{spacing:g}",
        "code-line-spacing": f"{code_spacing:g}",
        "bg-card": v2_token(theme_engine, "surface_primary", "#FFFFFF"),
        "text-primary": v2_token(theme_engine, "text_primary", "#212121"),
        "text-secondary": v2_token(theme_engine, "text_secondary", "#757575"),
        "text-muted": v2_token(theme_engine, "text_muted", "#BDBDBD"),
        "border": v2_token(theme_engine, "border_muted", "#E0E0E0"),
        "border-soft": v2_token(theme_engine, "border_muted", "#EEEEEE"),
        "divider": v2_token(theme_engine, "border_muted", "#EEEEEE"),
        "surface": v2_token(theme_engine, "surface_secondary", "#F5F5F5"),
        "surface-soft": v2_token(theme_engine, "surface_secondary", "#F5F5F5"),
        "surface-hover": v2_token(theme_engine, "surface_raised", "#FAFAFA"),
        "primary": v2_token(theme_engine, "accent", "#2196F3"),
        "primary-hover": v2_token(theme_engine, "focus", "#1976D2"),
        "bg-codeblock": v2_color(theme_engine, "markdown", "code_block_bg", "#EDF3FA"),
        "codeblock-border": v2_token(theme_engine, "border_muted", "#D8DEE9"),
        "toc-bg": v2_token(theme_engine, "surface_secondary", "#FAFAFA"),
        "scrollbar-track": v2_color(theme_engine, "scrollbar", "track", "#F5F5F5"),
        "scrollbar-thumb": v2_color(theme_engine, "scrollbar", "handle", "#E0E0E0"),
        "scrollbar-thumb-hover": v2_color(theme_engine, "scrollbar", "handle_hover", "#BDBDBD"),
        # 滚动条尺寸（与 Qt 侧同一 scrollbar recipe；radius 取宽度一半）
        # 必须带 px 单位：CSS 变量替换是纯文本替换，写成裸数字会让
        # `width: var(--sb-width)` 解析为 `width: 10`（无效）致整条规则被丢弃。
        "sb-width": f"{sb_width}px",
        "sb-radius": f"{sb_width // 2}px",
        "sb-margin": f"{sb_margin}px",
    }


def _build_preview_css_vars(
    theme_engine,
    code_font_family: str | None = None,
    line_spacing: float | None = None,
    code_line_spacing: float | None = None,
) -> str:
    """根据主题引擎构造 :root CSS 变量覆盖块（首屏整页模板注入用）。

    B2：纯消费 Theme v2（semantic token + markdown/scrollbar recipe），无 v1 回退。
    theme_engine 必须传入，不允许为 None。
    code_font_family / line_spacing / code_line_spacing：设置项「代码字体 /
    正文行距 / 代码块行距」，缺省回退各自默认值。
    """
    lines = [":root {"]
    for k, v in _preview_css_vars(
        theme_engine, code_font_family, line_spacing, code_line_spacing
    ).items():
        lines.append(f"    --css-{k}: {v};")
    lines.append("}")
    return "\n".join(lines)


def _css_vars_update_js(vars_map: dict[str, str]) -> str:
    """生成「就地更新预览 CSS 变量」的 JS。

    写进 documentElement 的内联样式，优先级高于样式表里的 :root 块，
    因此无需重新导航即可让新主题立即生效 —— 这是主题切换不闪烁的关键：
    整页 set_html 会拆掉旧文档、新文档首帧前出现空档，切深色时最显眼。
    """
    pairs = ",".join(
        f"[{json.dumps('--css-' + k)},{json.dumps(v)}]" for k, v in vars_map.items()
    )
    return (
        f"var _pnVars=[{pairs}];"
        "for (var i=0;i<_pnVars.length;i++){"
        "document.documentElement.style.setProperty(_pnVars[i][0],_pnVars[i][1]);"
        "}"
    )


# ════════════════════════════════════════════════════════
#  MarkdownPreviewWidget
# ════════════════════════════════════════════════════════

class MarkdownPreviewWidget(ThemeAwareMixin, QWidget):
    """Markdown分屏预览组件

    包含左侧编辑器和右侧预览，提供与Editor相同的接口
    """

    def __init__(
        self,
        config: Config,
        theme_engine,
        parent=None,
    ):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("MarkdownPreviewWidget 必须传入 theme_engine，不允许为 None")
        self.config = config
        self._theme_engine = theme_engine
        self.tab_id = None

        self._code_blocks: list[str] = []
        self._base_path = ""
        self._async_renderer = None
        self._pending_async_task: Optional[str] = None
        self._last_render_text: str = ""
        self._last_render_html: str = ""
        self._md_parser = self._create_md_parser()
        self._reset_template_state()
        self._preview_dirty = True
        self._last_sync_frac: float = 1.0
        self._last_at_top: bool = True
        self._last_at_bottom: bool = False
        self._last_sync_time: float = 0.0
        self._sync_trailing_timer = QTimer(self)
        self._sync_trailing_timer.setSingleShot(True)
        self._sync_trailing_timer.timeout.connect(self._on_sync_trailing)
        self._suppress_editor_sync: bool = False
        self._resync_timer = QTimer(self)
        self._resync_timer.setSingleShot(True)
        self._resync_timer.setInterval(120)
        self._resync_timer.timeout.connect(self._do_sync)

        if is_enabled("async_highlight"):
            from .async_highlight import AsyncHighlightRenderer
            self._async_renderer = AsyncHighlightRenderer(self)

        self._init_ui()
        self._connect_signals()

    @property
    def shared_doc(self):
        """当前 attach 的共享 Document（代理编辑器，未 attach 时为 None）。"""
        return self.editor.shared_doc

    def set_base_path(self, path: str):
        """设置基础路径（文件所在目录），用于解析本地相对图片路径

        v1.5.4 新增
        """
        if path != self._base_path:
            self._reset_template_state()
        self._base_path = path

    def _on_load_finished(self, ok):
        if not ok:
            return
        self._html_template_loaded = True
        # 整页灌入这条路（见 _push_to_preview 的 else 分支）不注入图表库，而
        # 「首次推送就带着图表」恰好走它：会话恢复时内容在模板加载完成前就推了进来，
        # 之后没有内容更新，图表便一直以源码文本留在页面上。故「模板已加载」这一
        # 事实本身就要补齐一次能力 —— 注入载荷自带当前 #content 的渲染，
        # 不需要再推一次内容（_mermaid_loaded 保证同一 JS 上下文只注入一次）。
        self._ensure_mermaid_capability(self._last_render_html)

    def _reset_template_state(self) -> None:
        """整页（重新）加载前作废「模板已加载」与「图表库已注入」两项状态。

        两者都只在同一个 JS 上下文内成立：重新导航会重置页面上下文，任何
        「已注入」记忆都会失真。故集中在一处作废，避免将来只改一处留下静默失效。
        """
        self._html_template_loaded = False
        self._mermaid_loaded = False

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧编辑器
        self.editor = Editor(self.config, theme_engine=self._theme_engine)
        self.splitter.addWidget(self.editor)

        # 右侧预览（经 Web Preview Adapter，后端由 create_preview_adapter 选择）
        self.preview = create_preview_adapter()

        self.splitter.addWidget(self.preview.widget())
        # 恢复编辑区/预览分栏占比（与侧栏分栏的 view_setting 模式一致）
        editor_w = self.config.get_view_setting("preview_editor_width", 500)
        preview_w = self.config.get_view_setting("preview_width", 500)
        self.splitter.setSizes([editor_w, preview_w])
        layout.addWidget(self.splitter)

        # 防抖定时器
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._update_preview)

        self._preview_visible = True

        self.preview.load_finished.connect(self._on_load_finished)
        # 预览 -> 编辑器：页面经官方消息通道回传顶部源码行
        self.preview.message_received.connect(self._on_preview_message)

        # 拖动分隔条改变预览宽度后，锚点像素位置整体变化，需重新同步；
        # 同时保存编辑区/预览分栏占比
        self.splitter.splitterMoved.connect(self._on_splitter_moved)

        self._init_theme(self._theme_engine)

    def _on_splitter_moved(self, *args):
        """保存编辑区/预览分栏占比，并重新同步预览锚点"""
        sizes = self.splitter.sizes()
        if len(sizes) >= 2:
            self.config.set_view_setting("preview_editor_width", sizes[0])
            self.config.set_view_setting("preview_width", sizes[1])
        self._schedule_resync()

    def _apply_theme_colors(self):
        # 主题变更时清空渲染缓存（高亮颜色/折叠样式依赖主题）。
        # Document 级缓存之外还要清 widget 级渲染记忆：_render_full 对「文本未变」
        # 会直接返回上次产物，而高亮颜色由主题决定 —— 只清 Document 缓存时，
        # 文本未改动的情况下切主题会沿用旧主题的 token 颜色。
        clear_document_render_cache()
        self._last_render_text = ""
        self._last_render_html = ""
        # 已加载的页面就地更新 CSS 变量（含代码字体/滚动条尺寸）；未加载则首屏整页灌入。
        # 不再强制整页重载：重载会拆掉旧文档，新文档首帧前出现空档 → 切深色时明显闪烁。
        self._apply_preview_css_vars()
        if getattr(self, 'editor', None) is not None:
            self._update_preview()

    def _apply_preview_css_vars(self) -> None:
        """把当前主题的 CSS 变量就地写入已加载页面（不重新导航）。

        模板尚未加载时不做任何事：此时变量会随首屏整页 set_html 一起灌入。
        """
        if not self._html_template_loaded:
            return
        vars_map = _preview_css_vars(
            self._theme_engine,
            self.config.get_code_font_family(),
            self.config.get_line_spacing(),
            self.config.get_code_line_spacing(),
        )
        self.preview.run_javascript(_css_vars_update_js(vars_map))

    def _is_dark_theme(self) -> bool:
        """当前激活主题是否为深色（与 editor.py 同一判据）。"""
        return v2_active_variant(self._theme_engine) == "dark"

    def _ensure_mermaid_capability(self, html_content: str) -> None:
        """首次出现图表时把 Mermaid vendor 懒注入页面（每个 JS 上下文一次）。

        模板只在首屏加载一次，且不内联图表库（约 5.58 MB，绝大多数文稿用不到），
        故首次真正需要时才经 run_javascript 注入。注入载荷自身会渲染当前
        #content，与紧随其后的内容更新脚本互为幂等（见 mermaid_render 中
        data-pn-graph 的说明），两者执行顺序不影响结果。
        """
        if self._mermaid_loaded or not _mermaid_render.has_mermaid(html_content):
            return
        payload = _mermaid_render.lazy_load_js(self._is_dark_theme())
        if not payload:
            return  # vendor 缺失：不置位，资产补齐后同一次会话内仍会尝试
        self._mermaid_loaded = True
        self.preview.run_javascript(payload)

    def refresh_typography_settings(self) -> None:
        """「代码字体 / 正文行距 / 代码块行距」变更后应用新 CSS。

        三项都只存在于 CSS（渲染产物不含排版信息），与主题变更同一路径：
        已加载则就地更新变量，未加载则由首屏整页灌入，故无需清 Document 渲染缓存。
        """
        self._apply_preview_css_vars()
        self._update_preview()

    def _connect_signals(self) -> None:
        self.editor.textChanged.connect(self._on_text_changed)
        vbar = self.editor.verticalScrollBar()
        if vbar is not None:
            vbar.valueChanged.connect(self._sync_scroll)
        # 折叠状态变更 → 同步预览（3.5.8 批次 5：监听编辑器转发的有效折叠信号，
        # attach 共享 Document 后仍指向 Document 级 FoldingManager，连接不漂移）
        self.editor.fold_state_changed.connect(self._sync_folds_to_preview)

    def refresh_preview_now(self) -> None:
        """文件装载/主题重建后强制刷新预览，不依赖 textChanged 防抖。"""
        if hasattr(self, "_preview_timer"):
            self._preview_timer.stop()
        self._update_preview()

    def invalidate_preview(self) -> None:
        self._preview_dirty = True

    def ensure_preview_rendered(self) -> None:
        if not self._preview_dirty:
            return

        self._preview_dirty = False
        self.refresh_preview_now()

    def _on_text_changed(self):
        # Wave 4 E3：大文件模式暂停自动刷新（大文件 md 全量渲染高成本），
        # 保留 refresh_preview_now() 手动刷新入口。
        editor = getattr(self, "editor", None)
        if editor is not None and editor.is_large_file_mode():
            return
        self._preview_timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 窗口/分栏尺寸变化 -> 预览重排 -> 锚点位置变化 -> 防抖后重新同步
        self._schedule_resync()

    def _schedule_resync(self):
        # 防御：resizeEvent 可能在 _init_ui 完成前(属性尚未就绪)触发
        if getattr(self, "_preview_visible", False) and hasattr(self, "_resync_timer"):
            self._resync_timer.start(120)

    # ──────────── 核心渲染 ────────────

    def _update_preview(self):
        text = self.editor.toPlainText()
        doc = self.editor.document()
        if doc is not None and is_enabled("markdown_incremental"):
            # Document 级缓存：同一 SharedDocument 多 View 共用，内容未变跳过渲染
            html_content = _DOC_RENDER_CACHE.get_or_render(
                doc, doc.revision(), lambda: self._render_full(text)
            )
        else:
            html_content = self._render_full(text)
        self._push_to_preview(html_content)

    def _render_full(self, text: str) -> str:
        """完整渲染流程（渲染 → 高亮 → 图片 → 折叠），最终产物整体可被 Document 缓存复用。"""
        # widget 层快路径：同一 widget 连续相同文本秒回（同 revision 已由 Document 缓存覆盖）
        if text == self._last_render_text:
            return self._last_render_html

        if HAS_MARKDOWN_IT or HAS_MARKDOWN:
            html_content = self._render_markdown_with_source_map(text)
        else:
            html_content = self._basic_md_to_html(text)

        # 图表围栏 → 图表容器 div，必须在代码块处理之前：否则它会占掉
        # 代码块序号（复制按钮索引）并被当成代码高亮
        html_content = _extract_mermaid_blocks(html_content)

        if self._async_renderer and is_enabled("async_highlight"):
            html_content = self._process_code_blocks_async(html_content)
        else:
            html_content = self._process_code_blocks(html_content)

        html_content = self._resolve_local_images(html_content)

        # 包裹折叠 section（编辑器的折叠状态同步到预览；产物仅依赖 text）
        html_content = self._wrap_fold_sections(html_content, text)

        self._last_render_text = text
        self._last_render_html = html_content
        return html_content

    def _push_to_preview(self, html_content: str):
        """把渲染好的 HTML 推送到预览，供 _update_preview / _on_async_highlight_done 共用。

        - 模板已加载：仅更新 #content 的 innerHTML 并重同步(不重建整页 DOM，
          因此保留滚动位置)；
        - 否则：整页 setHtml(首次加载)。
        """
        if self._html_template_loaded:
            self._ensure_mermaid_capability(html_content)
            escaped = json.dumps(html_content)
            doc = self.editor.document()
            assert doc is not None
            total_lines = doc.blockCount()
            frac = getattr(self, '_last_sync_frac', 1.0)
            at = "true" if getattr(self, '_last_at_top', True) else "false"
            ab = "true" if getattr(self, '_last_at_bottom', False) else "false"
            js = (
                f"document.getElementById('content').innerHTML = {escaped};"
                "_nodesVersion = null; _cachedNodes = null;"
                # 公式与图表都是客户端展开（不经 Python），内容变换后各自重跑
                f"{_math_render.content_update_js()}"
                f"{_mermaid_render.content_update_js(self._is_dark_theme())}"
                f"window.__lastFracLine={frac:.4f};"
                f"window.__lastTotalLines={total_lines};"
                f"window.__lastAtTop={at};"
                f"window.__lastAtBottom={ab};"
                "if (window.resyncAfterImagesLoaded) { window.resyncAfterImagesLoaded(); }"
                "requestAnimationFrame(function() {"
                "  if (window.scrollToSourceLine) {"
                f"    window.scrollToSourceLine({frac:.4f}, {total_lines}, {at}, {ab});"
                "  }"
                "});"
            )
            self.preview.run_javascript(js)
        else:
            css_vars = _build_preview_css_vars(
                self._theme_engine,
                self.config.get_code_font_family(),
                self.config.get_line_spacing(),
                self.config.get_code_line_spacing(),
            )
            template = PREVIEW_HTML_TEMPLATE
            try:
                full_html = template.format(
                    content=html_content,
                    layout_css=_MARKDOWN_LAYOUT_CSS,
                    # 模板只加载一次，之后仅换 #content 内容，故公式库始终内联一次
                    math_style=_math_render.style_fragment(),
                    math_script=_math_render.script_fragment(
                        "document.getElementById('content')"
                    ),
                ).replace(
                    "</style>", css_vars + "\n</style>", 1
                )
            except Exception as exc:
                get_logger(__name__).error(
                    "Markdown preview template format failed: %s",
                    exc,
                    exc_info=True,
                )

                # B2：模板格式失败时的降级 HTML（B8：字面量 = v1 light 值，无 v1 回退）
                fallback_bg = "#FFFFFF"
                fallback_text = "#212121"
                fallback_code_bg = "#EDF3FA"
                fallback_border = "#D8DEE9"
                fallback_link = "#2196F3"

                full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                 "Microsoft YaHei UI", "Microsoft YaHei", Arial, sans-serif;
    font-size: 14px;
    line-height: 1.7;
    margin: 0;
    padding: 12px 20px 40px 20px;
    background: {fallback_bg};
    color: {fallback_text};
    word-wrap: break-word;
}}
pre {{
    background: {fallback_code_bg};
    color: {fallback_text};
    border: 1px solid {fallback_border};
    border-radius: 6px;
    padding: 12px 14px;
    overflow: auto;
}}
code {{
    font-family: Consolas, "Courier New", monospace;
}}
a {{
    color: {fallback_link};
}}
</style>
</head>
<body>
{html_content}
</body>
</html>"""
            self.preview.set_resource_root(self._base_path or None)
            self.preview.set_html(full_html)

        # 同步当前折叠状态到预览
        self._sync_folds_to_preview()

    @staticmethod
    def _create_md_parser():
        if not HAS_MARKDOWN_IT:
            return None
        md = _MarkdownIt("commonmark", {"html": False})
        md.enable(["table", "strikethrough"])
        try:
            from mdit_py_plugins.deflist import deflist_plugin
            from mdit_py_plugins.tasklists import tasklists_plugin
            deflist_plugin(md)
            tasklists_plugin(md)
        except ImportError:
            get_logger(__name__).debug("mdit_py_plugins 未安装，扩展语法（定义列表/任务列表）不可用")
        _math_render.register(md)
        return md

    def _render_markdown(self, text: str) -> str:
        if self._md_parser is not None:
            try:
                result = self._md_parser.render(text)
                return _strip_dangerous_html(result)
            except Exception:
                get_logger(__name__).debug("markdown-it 渲染失败，回退到 python-markdown")

        from .secure_markdown_renderer import render_markdown_to_safe_html
        return render_markdown_to_safe_html(text)

    # ──────────── 源码行号注入渲染 ────────────

    _SOURCE_LINE_TOKEN_TYPES = frozenset({
        "heading_open",
        "paragraph_open",
        "blockquote_open",
        "bullet_list_open",
        "ordered_list_open",
        "list_item_open",
        "table_open",
        "thead_open",
        "tbody_open",
        "tr_open",
        "hr",
        "fence",
        "code_block",
    })

    def _render_markdown_with_source_map(self, text: str) -> str:
        """使用 markdown-it-py 渲染 Markdown，并给主要块级节点注入 data-source-line。

        用于实现编辑器源码行与预览 DOM 节点的同步。
        """
        if self._md_parser is None:
            return self._render_markdown(text)

        try:
            tokens = self._md_parser.parse(text)

            self._code_block_source_lines: list[int] = []
            injected_count = 0

            for token in tokens:
                if token.type in ("fence", "code_block") and token.map:
                    # 图表围栏稍后转成图表容器 div，不占代码块序号：
                    # 否则 _code_block_source_lines 与真实代码块索引错位
                    if token.type == "fence" and _mermaid_render.is_mermaid_fence(
                        getattr(token, "info", "") or ""
                    ):
                        continue
                    self._code_block_source_lines.append(token.map[0] + 1)

                if not token.map:
                    continue

                if token.nesting == -1:
                    continue

                if token.type in self._SOURCE_LINE_TOKEN_TYPES:
                    line_no = token.map[0] + 1
                    token.attrSet("data-source-line", str(line_no))
                    token.attrJoin("class", "src-line")
                    injected_count += 1

            html = self._md_parser.renderer.render(
                tokens,
                self._md_parser.options,
                {},
            )

            get_logger(__name__).debug(
                "Markdown source map: injected %d data-source-line attrs", injected_count
            )
            return _strip_dangerous_html(html)

        except Exception as e:
            get_logger(__name__).error(
                "Markdown source map render failed: %s, fallback to normal render",
                str(e),
                exc_info=True,
            )
            return self._render_markdown(text)

    # ──────────── 本地图片路径解析 ────────────

    def _resolve_local_images(self, html: str) -> str:
        """将 HTML 中的相对图片路径转换为 file:// 绝对路径

        处理 <img src="./img.png"> 和 <img src="img.png"> 等形式。
        绝对路径、http(s):// 链接不受影响。

        v1.5.4 新增
        """
        if not self._base_path:
            return html

        def _resolve_src(m):
            prefix = m.group(1)
            src = m.group(2)

            if src.startswith(('http://', 'https://', 'file://', 'data:')):
                return m.group(0)

            if os.path.isabs(src):
                return m.group(0)

            abs_path = os.path.normpath(os.path.join(self._base_path, src))
            try:
                real_base = os.path.realpath(self._base_path)
                real_abs = os.path.realpath(abs_path)
                if not (real_abs == real_base or real_abs.startswith(real_base + os.sep)):
                    return m.group(0)
            except (OSError, ValueError):
                return m.group(0)

            if os.path.exists(abs_path):
                file_url = QUrl.fromLocalFile(abs_path).toString()
                return f'{prefix}src="{file_url}"'

            return m.group(0)

        return _IMG_SRC_RE.sub(_resolve_src, html)

    # ──────────── 折叠 section 包裹 ────────────

    @staticmethod
    def _wrap_fold_sections(html: str, text: str) -> str:
        """在 Markdown 标题的 DOM 节点外包裹 <section data-fold-heading="N">。

        折叠区间计算与 FoldingManager 一致，确保编辑器和预览折叠对应。
        在 _process_code_blocks 之后、_push_to_preview 之前调用。
        """
        from src.editor.outline_parser import parse_headings

        headings = parse_headings(text)
        if not headings:
            return html

        # 找到 HTML 中所有含 data-source-line 的标题标签及其位置
        heading_pattern = re.compile(
            r'(<h([1-6])((?:\s[^>]*)?)data-source-line="(\d+)"[^>]*>.*?</h\2>)',
            re.DOTALL | re.IGNORECASE
        )
        matches = list(heading_pattern.finditer(html))
        if not matches:
            return html

        # line_no → (level, tag_text, start_pos, end_pos)
        heading_info: dict[int, tuple[int, str, int, int]] = {}
        for m in matches:
            level = int(m.group(2))
            line_no = int(m.group(4))
            heading_info[line_no] = (level, m.group(1), m.start(), m.end())

        # 计算可折叠区间 → {heading_line: (content_start_pos, section_end_pos)}
        foldable: dict[int, tuple[int, int]] = {}
        for i, (h_level, line_no, _title) in enumerate(headings):
            if line_no not in heading_info:
                continue
            # 找到下一个 ≤ 同级标题的起始位置
            section_end = len(html)
            for j in range(i + 1, len(headings)):
                next_level, next_line, _ = headings[j]
                if next_level <= h_level and next_line in heading_info:
                    section_end = heading_info[next_line][2]  # 下一标题的 start
                    break
            content_start = heading_info[line_no][3]  # 当前标题 tag 结束位置
            if content_start < section_end:
                foldable[line_no] = (content_start, section_end)

        if not foldable:
            return html

        ops: list[tuple[int, int, str]] = []
        for line_no, (content_start, section_end) in foldable.items():
            section_open = f'<section data-fold-heading="{line_no}">'
            section_close = '</section>'
            ops.append((content_start, 0, section_open))
            ops.append((section_end, -line_no, section_close))

        ops.sort(key=lambda x: (x[0], x[1]), reverse=True)

        result = html
        for pos, _tiebreaker, tag in ops:
            result = result[:pos] + tag + result[pos:]

        return result

    # ──────────── 折叠同步 ────────────

    def _sync_folds_to_preview(self) -> None:
        """将编辑器 FoldingManager 的折叠状态同步到预览 DOM。"""
        if not self.editor:
            return
        folding = getattr(self.editor, '_folding', None)
        if folding is None:
            return
        if not self._html_template_loaded:
            return

        collapsed = folding.get_collapsed_lines()
        js = f"window.updateFoldVisibility('{json.dumps(collapsed)}');"
        self.preview.run_javascript(js)

    # ──────────── 代码块后处理 ────────────

    def _process_code_blocks(self, html: str) -> str:
        """替换所有 <pre><code> 块：语法高亮 + 浅蓝容器 + 嵌入位置标记"""
        self._code_blocks = []

        def _replace(m):
            code_attrs = m.group("code_attrs") or ""
            lang = _extract_language_from_code_attrs(code_attrs)
            raw = html_module.unescape(m.group("body"))
            if raw.endswith("\n"):
                raw = raw[:-1]

            idx = len(self._code_blocks)
            self._code_blocks.append(raw)

            source_line = None
            if hasattr(self, "_code_block_source_lines"):
                if idx < len(self._code_block_source_lines):
                    source_line = self._code_block_source_lines[idx]

            highlighted = highlight_code_html(raw, lang, self._theme_engine)
            return self._build_container(idx, highlighted, source_line)

        return _CODEBLOCK_RE.sub(_replace, html)

    def _process_code_blocks_async(self, html: str) -> str:
        """异步版本的代码块处理：先渲染占位符，再异步替换高亮结果"""
        self._code_blocks = []

        if self._pending_async_task:
            if self._async_renderer is not None:
                self._async_renderer.cancel(self._pending_async_task)
            self._pending_async_task = None

        def _replace(m):
            raw = html_module.unescape(m.group("body"))
            if raw.endswith("\n"):
                raw = raw[:-1]

            idx = len(self._code_blocks)
            self._code_blocks.append(raw)

            source_line = None
            if hasattr(self, "_code_block_source_lines"):
                if idx < len(self._code_block_source_lines):
                    source_line = self._code_block_source_lines[idx]

            escaped = html_module.escape(raw)
            return self._build_container(idx, escaped, source_line)

        result = _CODEBLOCK_RE.sub(_replace, html)

        if self._code_blocks and self._async_renderer:
            task_id = self._async_renderer.render(
                "\n---SEPARATOR---\n".join(self._code_blocks),
                "auto",
                self._theme_engine,
                callback=self._on_async_highlight_done,
            )
            self._pending_async_task = task_id

        return result

    def _on_async_highlight_done(self, task_id: str, html_result: str, language: str):
        self._pending_async_task = None
        if not html_result or not self._code_blocks:
            return

        highlighted_blocks = html_result.split("\n---SEPARATOR---\n")
        if len(highlighted_blocks) != len(self._code_blocks):
            return

        text = self.editor.toPlainText()
        if HAS_MARKDOWN_IT or HAS_MARKDOWN:
            html_content = self._render_markdown_with_source_map(text)
        else:
            html_content = self._basic_md_to_html(text)

        # 与 _render_full 同一步骤：图表围栏先转成容器 div。否则下面这轮重渲染会把
        # 它当普通代码块（转义后的源码文本），图表退化成文字。
        html_content = _extract_mermaid_blocks(html_content)

        self._code_blocks = []
        block_idx = [0]

        def _replace_sync(m):
            raw = html_module.unescape(m.group("body"))
            if raw.endswith("\n"):
                raw = raw[:-1]

            idx = block_idx[0]
            self._code_blocks.append(raw)

            source_line = None
            if hasattr(self, "_code_block_source_lines"):
                if idx < len(self._code_block_source_lines):
                    source_line = self._code_block_source_lines[idx]

            if idx < len(highlighted_blocks):
                return self._build_container(idx, highlighted_blocks[idx], source_line)
            return self._build_container(idx, html_module.escape(raw), source_line)

        block_idx_ref = block_idx

        def _replace_and_count(m):
            result = _replace_sync(m)
            block_idx_ref[0] += 1
            return result

        html_content = _CODEBLOCK_RE.sub(_replace_and_count, html_content)
        html_content = self._resolve_local_images(html_content)
        html_content = self._wrap_fold_sections(html_content, text)
        self._push_to_preview(html_content)

    @staticmethod
    def _wrap_code_lines_with_source_map(
        code_html: str,
        source_line: Optional[int],
    ) -> str:
        """给代码块内部每一行 HTML 增加 data-source-line 锚点。

        code_html 应为高亮后的代码内部片段（不含外层 <pre>/<code>）。
        """
        if source_line is None:
            return code_html

        lines = code_html.split("\n")
        wrapped: list[str] = []

        for offset, line_html in enumerate(lines):
            line_no = source_line + offset
            if line_html == "":
                line_html = " "
            wrapped.append(
                f'<span class="code-line src-line" data-source-line="{line_no}">{line_html}</span>'
            )

        return "\n".join(wrapped)

    @staticmethod
    def _build_container(index: int, code_html: str, source_line: Optional[int] = None) -> str:
        """构建代码块 HTML 容器：浅蓝背景 + 逐行锚点 + 悬停复制按钮。
        """
        line_attr = ""
        if source_line is not None:
            line_attr = f' data-source-line="{source_line}"'

        code_html = MarkdownPreviewWidget._wrap_code_lines_with_source_map(
            code_html, source_line
        )

        return (
            f'<div class="code-container src-line"{line_attr}>'
            f'<button class="code-copy-btn" data-code-index="{index}"'
            f' title="复制到剪贴板">\U0001f4cb</button>'
            f'<pre class="code-pre"><code class="code-block">{code_html}</code></pre>'
            f'</div>'
        )

    # ──────────── 基础渲染（无 markdown 库回退） ────────────

    @staticmethod
    def _basic_md_to_html(text: str) -> str:
        lines = text.split('\n')
        html_lines = []
        in_code = False

        for line in lines:
            if line.strip().startswith('```'):
                if in_code:
                    html_lines.append('</code></pre>')
                    in_code = False
                else:
                    html_lines.append('<pre><code>')
                    in_code = True
                continue
            if in_code:
                html_lines.append(line.replace('<', '&lt;').replace('>', '&gt;'))
                continue
            if line.startswith('######'):
                html_lines.append(f'<h6>{line[6:].strip()}</h6>')
            elif line.startswith('#####'):
                html_lines.append(f'<h5>{line[5:].strip()}</h5>')
            elif line.startswith('####'):
                html_lines.append(f'<h4>{line[4:].strip()}</h4>')
            elif line.startswith('###'):
                html_lines.append(f'<h3>{line[3:].strip()}</h3>')
            elif line.startswith('##'):
                html_lines.append(f'<h2>{line[2:].strip()}</h2>')
            elif line.startswith('#'):
                html_lines.append(f'<h1>{line[1:].strip()}</h1>')
            elif line.startswith('>'):
                html_lines.append(f'<blockquote>{line[1:].strip()}</blockquote>')
            elif re.match(r'^[-*_]{3,}\s*$', line):
                html_lines.append('<hr>')
            elif line.strip():
                p = line
                p = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', p)
                p = re.sub(r'\*(.+?)\*', r'<em>\1</em>', p)
                p = re.sub(r'`(.+?)`', r'<code>\1</code>', p)
                p = re.sub(r'\[(.+?)]\((.+?)\)', r'<a href="\2">\1</a>', p)
                html_lines.append(f'<p>{p}</p>')
            else:
                html_lines.append('<br>')

        if in_code:
            html_lines.append('</code></pre>')
        return '\n'.join(html_lines)

    # ──────────── 同步滚动 ────────────

    def _editor_top_fractional_line(self) -> tuple[float, bool, bool]:
        """返回 (顶部源码行(可含小数), 编辑器是否到顶, 编辑器是否到底)。

        顶部行 = 编辑器视口最上方那一行；小数部分表示该行已被向上滚出视口的比例，
        用于子行级平滑。两侧统一采用"顶行对齐"模型，不再有视口比例偏移。
        端点 (到顶/到底) 单独返回，交由预览侧硬贴 0 / maxScroll。
        """
        ed = self.editor
        bar = ed.verticalScrollBar()
        at_top = bar is None or bar.value() <= bar.minimum()
        at_bottom = (bar is not None and 0 < bar.maximum() <= bar.value())

        frac_line = 1.0
        try:
            cursor = ed.cursorForPosition(QPoint(0, 0))
            block = cursor.block()
            line = int(block.blockNumber()) + 1
            # 用块的起始/结束两处 cursorRect 求块的完整高度(含软换行的多显示行)，
            # 使长段落/换行块内滚动也能得到 [0,1) 平滑子行偏移，而非很快饱和到 0.999。
            start_cur = QTextCursor(block)
            end_cur = QTextCursor(block)
            end_cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            top = ed.cursorRect(start_cur).top()
            bottom = ed.cursorRect(end_cur).bottom()
            block_h = bottom - top
            if block_h <= 0:
                block_h = ed.cursorRect(cursor).height() or ed.fontMetrics().height()
            sub = 0.0
            if block_h > 0:
                # top <= 0：该块已被向上滚出视口的比例
                sub = min(max(-top / block_h, 0.0), 0.999)
            frac_line = line + sub
        except Exception:
            get_logger(__name__).debug("顶部参考行计算失败，回退到光标行", exc_info=True)
            cursor = ed.textCursor()
            frac_line = float(int(cursor.block().blockNumber()) + 1)

        return max(1.0, frac_line), at_top, at_bottom

    def _sync_scroll(self, value):
        if not self._preview_visible:
            return
        # 若本次编辑器滚动由"预览->编辑器"反向同步触发，跳过，避免回授环
        if self._suppress_editor_sync:
            return

        bar = self.editor.verticalScrollBar()
        at_edge = bar is not None and (
            bar.value() <= bar.minimum()
            or (0 < bar.maximum() <= bar.value())
        )

        # 带后沿的节流：50ms 内最多一次 leading 同步，避免高频 runJavaScript；
        # 端点(到顶/到底)绕过节流立即同步，确保 value=0 / value=max 的收尾事件
        # 不被丢弃；其余收尾事件由 trailing 定时器补发。
        now = time.monotonic()
        elapsed = now - self._last_sync_time
        if at_edge or elapsed >= 0.05:
            self._last_sync_time = now
            self._do_sync()
        elif not self._sync_trailing_timer.isActive():
            self._sync_trailing_timer.start(int((0.05 - elapsed) * 1000) + 1)

    def _on_sync_trailing(self):
        """节流窗口结束后补一次同步，确保收尾位置不被丢弃。"""
        self._last_sync_time = time.monotonic()
        self._do_sync()

    def _do_sync(self):
        frac_line, at_top, at_bottom = self._editor_top_fractional_line()
        doc = self.editor.document()
        assert doc is not None
        total_lines = doc.blockCount()
        self._last_sync_frac = frac_line
        self._last_at_top = at_top
        self._last_at_bottom = at_bottom

        at = "true" if at_top else "false"
        ab = "true" if at_bottom else "false"
        js = (
            f"window.__lastFracLine={frac_line:.4f};"
            f"window.__lastTotalLines={total_lines};"
            f"window.__lastAtTop={at};"
            f"window.__lastAtBottom={ab};"
            f"if(window.scrollToSourceLine){{"
            f"window.scrollToSourceLine({frac_line:.4f},{total_lines},{at},{ab});}}"
        )
        self.preview.run_javascript(js)

    # ──────────── 预览 -> 编辑器 反向同步 ────────────

    def _on_preview_message(self, message: str):
        """页面经 WebView2 官方消息通道回传，据此滚动编辑器、复制或打开链接。

        协议：``<前缀>:<载荷>``，前缀见预览模板里的 window.pnPostMessage。
        """
        if not message:
            return
        if message.startswith("__pnopen__:"):
            self._open_external_link(message[len("__pnopen__:"):])
            return
        if message.startswith("__pncopy__:"):
            try:
                idx = int(message.split(":")[1])
                if 0 <= idx < len(self._code_blocks):
                    cb = QApplication.clipboard()
                    if cb is not None:
                        cb.setText(self._code_blocks[idx])
            except (ValueError, IndexError):
                pass
            return
        if not message.startswith("__pzsync__:"):
            return
        parts = message.split(":")
        if len(parts) < 2:
            return
        try:
            frac_line = float(parts[1])
        except ValueError:
            return
        self._scroll_editor_to_line(frac_line)

    @staticmethod
    def _open_external_link(url: str) -> None:
        """预览链接点击 → 系统外部浏览器打开（与 QTextBrowser 回退路径一致）。"""
        if not url:
            return
        QDesktopServices.openUrl(QUrl(url))

    def _scroll_editor_to_line(self, frac_line: float):
        """把源码行 frac_line 滚到编辑器视口顶部(不移动光标)。

        QPlainTextEdit 的竖直滚动条在"不换行"模式下以源码行(block)为步进，
        value == 顶部 block 序号，可直接 setValue(line-1)；"限制行宽"模式下滚动条
        按显示行计数，无法 1:1 映射，退化为按行号比例近似。
        全程置 _suppress_editor_sync，避免触发反向回授。
        """
        ed = self.editor
        bar = ed.verticalScrollBar()
        if bar is None:
            return
        doc = ed.document()
        assert doc is not None
        total = doc.blockCount()
        line = max(1, min(int(round(frac_line)), total))

        self._suppress_editor_sync = True
        try:
            if ed.get_wrap_mode() == "no_wrap":
                bar.setValue(line - 1)
            elif total > 1:
                bar.setValue(int((line - 1) / (total - 1) * bar.maximum()))
        finally:
            # setValue 同步触发的 valueChanged 已被抑制，下一轮事件循环再解除
            QTimer.singleShot(0, self._clear_suppress)

    def _clear_suppress(self):
        self._suppress_editor_sync = False

    # ──────────── 预览显隐 ────────────

    def toggle_preview(self):
        self._preview_visible = not self._preview_visible
        self.preview.set_visible(self._preview_visible)
        if self._preview_visible:
            self._update_preview()

    # ══════════════════════════════════════════════════
    #  代理 Editor 接口（EditorTabWidget 统一调用）
    # ══════════════════════════════════════════════════

    def toPlainText(self) -> str:
        return str(self.editor.toPlainText())

    def setPlainText(self, text: str):
        self.editor.setPlainText(text)
        self._update_preview()

    def document(self):
        return self.editor.document()

    def textCursor(self):
        return self.editor.textCursor()

    def setTextCursor(self, cursor):
        self.editor.setTextCursor(cursor)

    def verticalScrollBar(self):
        return self.editor.verticalScrollBar()

    def undo(self):
        self.editor.undo()

    def redo(self):
        self.editor.redo()

    def cut(self):
        self.editor.cut()

    def copy(self):
        self.editor.copy()

    def paste(self):
        self.editor.paste()

    def selectAll(self):
        self.editor.selectAll()

    def zoomIn(self, n=1):
        self.editor.zoomIn(n)
        self._schedule_resync()

    def zoomOut(self, n=1):
        self.editor.zoomOut(n)
        self._schedule_resync()

    def font(self):
        return self.editor.font()

    def setFont(self, font):
        self.editor.setFont(font)

    def set_file_type(self, filepath_or_ext: str):
        self.editor.set_file_type(filepath_or_ext)

    def set_wrap_mode(self, mode: str):
        self.editor.set_wrap_mode(mode)

    def get_wrap_mode(self) -> str:
        return self.editor.get_wrap_mode()

    def get_char_count(self) -> int:
        return self.editor.get_char_count()

    def get_current_line(self) -> int:
        return self.editor.get_current_line()

    def get_current_column(self) -> int:
        return self.editor.get_current_column()

    def get_file_type(self) -> str:
        return self.editor.get_file_type()

    def toggle_minimap(self):
        self.editor.toggle_minimap()

    def set_minimap_visible(self, visible: bool):
        self.editor.set_minimap_visible(visible)

    @property
    def textChanged(self):
        return self.editor.textChanged
