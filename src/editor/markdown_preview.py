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
import html as html_module
from typing import Optional, Union

from PyQt6.QtWidgets import (
    QWidget, QSplitter, QVBoxLayout, QTextBrowser, QApplication, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, QUrl, QPoint, QEvent
from PyQt6.QtGui import QFont, QDesktopServices, QCursor, QTextCursor

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

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
    _WEBENGINE_IMPORT_ERROR = ""
except ImportError as _exc:
    # 常见原因并非"未安装"，而是导入时机过晚：QtWebEngineWidgets 必须在
    # QApplication 创建前导入，或在创建前设置 AA_ShareOpenGLContexts（见 main.py）。
    HAS_WEBENGINE = False
    _WEBENGINE_IMPORT_ERROR = str(_exc)

from ..core.config import Config
from ..editor.editor import Editor
from ..utils.logger import get_logger
from ..utils.feature_flags import is_enabled
from ..security.path_validator import PathValidator
from ..themes.theme_aware_mixin import ThemeAwareMixin
from .highlight_themes import highlight_code_html
from .webengine_runtime import WebEngineRuntime

# ════════════════════════════════════════════════════════
#  正则 / 常量
# ════════════════════════════════════════════════════════

# 匹配 fenced_code 输出的 <pre><code> 块（支持 pre 标签上的属性）
_CODEBLOCK_RE = re.compile(
    r'<pre(?P<pre_attrs>[^>]*)>\s*'
    r'<code(?P<code_attrs>[^>]*)>'
    r'(?P<body>.*?)'
    r'</code>\s*</pre>',
    re.DOTALL | re.IGNORECASE,
)

# 匹配 <img src="..."> 标签中的 src 属性
_IMG_SRC_RE = re.compile(
    r'(<img\s[^>]*?)src="([^"]*)"',
    re.IGNORECASE,
)

# 用于在 QTextDocument 中标记代码块起止位置的 Unicode 角括号
_MK_S1 = "\u231C"  # ⌜
_MK_S2 = "\u231D"  # ⌝
_MK_E1 = "\u231E"  # ⌞
_MK_E2 = "\u231F"  # ⌟

from .secure_markdown_renderer import strip_dangerous_html as _strip_dangerous_html


def _extract_language_from_code_attrs(attrs: str) -> str:
    """从 code 标签的属性串中提取语言名称。"""
    m = re.search(r'class="([^"]*)"', attrs or "")
    if not m:
        return ""
    classes = m.group(1).split()
    for cls in classes:
        if cls.startswith("language-"):
            return cls.removeprefix("language-")
        if cls.startswith("lang-"):
            return cls.removeprefix("lang-")
    return ""

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
}}

/* ========== 基础 ========== */
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei UI",
                 "Microsoft YaHei", Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.7;
    color: var(--text-primary);
    padding: 12px 20px 40px 20px;
    margin: 0;
    max-width: 100%;
    background: var(--bg-card);
    word-wrap: break-word;
    overflow-wrap: break-word;
}}

/* ========== 标题 ========== */
h1, h2, h3, h4, h5, h6 {{
    color: var(--text-primary);
    font-weight: bold;
    margin-top: 24px;
    margin-bottom: 12px;
    line-height: 1.3;
}}
h1 {{
    font-size: 1.85em;
    border-bottom: 1px solid var(--border);
    padding-bottom: 6px;
}}
h2 {{
    font-size: 1.5em;
    border-bottom: 1px solid var(--border-soft);
    padding-bottom: 5px;
}}
h3 {{ font-size: 1.3em; }}
h4 {{ font-size: 1.15em; }}
h5 {{ font-size: 1.05em; }}
h6 {{ font-size: 1em; color: var(--text-muted); }}

/* ========== 段落 / 文本 ========== */
p {{ margin: 8px 0; }}
strong {{ font-weight: 700; }}
em {{ font-style: italic; }}

/* ========== 行内代码 ========== */
:not(pre) > code {{
    font-family: "JetBrains Mono", Consolas, "Courier New", "Microsoft YaHei", monospace;
    background: var(--surface);
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 0.92em;
    color: var(--text-primary);
    border: 1px solid var(--divider);
}}

/* ========== 引用 ========== */
blockquote {{
    border-left: 3px solid var(--scrollbar-thumb-hover);
    padding: 4px 16px;
    margin: 10px 0;
    background: var(--surface-soft);
    color: var(--text-secondary);
}}
blockquote p {{ margin: 4px 0; }}

/* ========== 表格 ========== */
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 12px 0;
}}
th, td {{
    border: 1px solid var(--border);
    padding: 6px 12px;
    text-align: left;
}}
th {{
    background: var(--surface);
    font-weight: 600;
}}
tr:nth-child(even) {{ background: var(--surface-hover); }}

/* ========== 链接 ========== */
a {{ color: var(--primary); text-decoration: none; }}
a:hover {{ text-decoration: underline; color: var(--primary-hover); }}

/* ========== 图片 ========== */
img {{ max-width: 100%; border-radius: 3px; }}

/* ========== 分割线 ========== */
hr {{ border: none; border-top: 1px solid var(--border); margin: 20px 0; }}

/* ========== 列表 ========== */
ul, ol {{ padding-left: 26px; margin: 6px 0; }}
li {{ margin: 3px 0; }}

/* ========== 任务列表 ========== */
li input[type="checkbox"] {{
    margin-right: 6px;
    vertical-align: middle;
}}

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
    font-family: Consolas, "Courier New", monospace;
    font-size: 14px;
    line-height: 1.55;
    white-space: pre;
    color: var(--text-primary);
}}
.code-line {{
    display: block;
    min-height: 1.55em;
    white-space: pre;
    background: transparent !important;
}}
.code-marker {{
    font-size: 1px;
    color: transparent;
    user-select: none;
    pointer-events: none;
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

/* ========== 滚动条（与编辑器样式一致，暗色模式下自适应） ========== */
::-webkit-scrollbar {{
    width: 12px;
    height: 12px;
}}
::-webkit-scrollbar-track {{
    background: var(--scrollbar-track);
}}
::-webkit-scrollbar-thumb {{
    background: var(--scrollbar-thumb);
    border-radius: 6px;
    border: 2px solid var(--scrollbar-track);
}}
::-webkit-scrollbar-thumb:hover {{
    background: var(--scrollbar-thumb-hover);
}}
::-webkit-scrollbar-corner {{
    background: var(--scrollbar-track);
}}
</style>
</head>
<body>
<div id="content">
{content}
</div>
<script>
// ========== 锚点缓存：layout 变化(内容/高度/宽度)即重建 ==========
var _nodesVersion = null;
var _cachedNodes = null;

// 编辑器→预览 驱动滚动时的回声锁：在此时间戳前，预览自身的 scroll 事件
// 视为回声，不回传给编辑器，避免双向同步形成回授环。
var _previewScrollLock = 0;
var _previewSyncNonce = 0;
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

// 预览滚动时把顶部源码行经 document.title 轻量回传给 Python(无需 QWebChannel)。
// performance.now() 早于 _previewScrollLock 说明是编辑器驱动的回声，跳过。
function _reportPreviewScroll() {{
    if (performance.now() < _previewScrollLock) {{ return; }}
    var line = _previewTopToLine();
    if (line == null) {{ return; }}
    document.title = "__pzsync__:" + line.toFixed(3) + ":" + (_previewSyncNonce++);
}}
function _schedulePreviewScrollReport() {{
    if (_pvScrollTimer) {{ return; }}
    _pvScrollTimer = setTimeout(function() {{
        _pvScrollTimer = null;
        _reportPreviewScroll();
    }}, 60);
}}
window.addEventListener("scroll", _schedulePreviewScrollReport, {{ passive: true }});

window.resyncAfterImagesLoaded = function() {{
    document.querySelectorAll("img").forEach(function(img) {{
        if (img.__panzerNoteSyncBound) {{ return; }}
        img.__panzerNoteSyncBound = true;

        var resync = function() {{
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

        img.addEventListener("load", resync);
        img.addEventListener("error", resync);
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
        var btn = e.target.closest('.code-copy-btn');
        if (!btn) return;
        e.stopPropagation();
        var idx = btn.getAttribute('data-code-index');
        if (idx == null) return;
        document.title = '__pncopy__:' + idx;
        btn.textContent = '\\u2714';
        setTimeout(function() {{ btn.textContent = '\\ud83d\\udccb'; }}, 800);
    }});
}})();
</script>
</body>
</html>"""


# ════════════════════════════════════════════════════════
#  预览模板 CSS 变量注入（替代旧的正则颜色替换）
# ════════════════════════════════════════════════════════

def _build_preview_css_vars(theme_engine) -> str:
    """根据主题引擎构造 :root CSS 变量覆盖块。

    theme_engine 必须传入，不允许为 None。
    """
    c = theme_engine.get_active_theme().colors

    # 颜色语义映射：CSS 变量名 → 主题 token 值
    # light/dark 主题 token 已各自配置正确色值，无需再做明暗判断
    vars_map = {
        "bg-card": c.background,
        "text-primary": c.text_primary,
        "text-secondary": c.text_secondary,
        "text-muted": c.text_disabled,
        "border": c.border,
        "border-soft": c.divider,
        "divider": c.divider,
        "surface": c.surface,
        "surface-soft": c.surface,
        "surface-hover": c.sidebar_bg,
        "primary": c.primary,
        "primary-hover": c.primary_dark,
        "bg-codeblock": c.bg_codeblock,
        "codeblock-border": c.codeblock_border,
        "toc-bg": c.sidebar_bg,
        "scrollbar-track": c.surface,
        "scrollbar-thumb": c.border,
        "scrollbar-thumb-hover": c.text_disabled,
    }
    lines = [":root {"]
    for k, v in vars_map.items():
        lines.append(f"    --css-{k}: {v};")
    lines.append("}")
    return "\n".join(lines)


# ════════════════════════════════════════════════════════
#  PreviewBrowser —— 带浮动复制按钮的 QTextBrowser
# ════════════════════════════════════════════════════════

class PreviewBrowser(QTextBrowser):
    """QTextBrowser 子类：鼠标悬停代码块时在右上角显示浮动复制按钮。

    原理：
      1. 在每个代码块 HTML 的首尾嵌入不可见 Unicode 标记（⌜N⌝ / ⌞N⌟）
      2. setHtml 后，用 QTextDocument.find() 缓存标记对应的 QTextCursor
      3. mouseMoveEvent 中，通过 cursorRect() 判断鼠标是否在某个代码块的
         垂直范围内，是则在右上角显示浮动 QPushButton
    """

    def __init__(self, theme_engine, parent=None):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("PreviewBrowser 必须传入 theme_engine，不允许为 None")
        self._theme_engine = theme_engine
        self.setMouseTracking(True)
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._on_anchor_clicked)

        # 存储每个代码块的原始文本（用于复制）
        self._code_blocks = []
        # 缓存的 (start_cursor, end_cursor, index) 列表
        self._code_cursors = []
        # 当前悬停的代码块索引
        self._hover_idx = -1
        # 鼠标是否在复制按钮上
        self._btn_hovered = False

        # ── 浮动复制按钮（挂在 viewport 上，随内容滚动） ──
        self._copy_btn = QPushButton("\U0001f4cb", self.viewport())
        self._copy_btn.setFixedSize(26, 20)
        self._copy_btn.setToolTip("复制到剪贴板")
        self._copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._copy_btn.hide()
        colors = theme_engine.get_active_theme().colors
        self._apply_copy_btn_style(colors)
        self._copy_btn.clicked.connect(self._copy_current)
        self._copy_btn.installEventFilter(self)

        # ── 悬停检测防抖定时器 ──
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(30)
        self._hover_timer.timeout.connect(self._check_hover)
        self._mouse_pos = QPoint()

    def _apply_copy_btn_style(self, colors) -> None:
        """使用主题色更新浮动复制按钮样式。"""
        self._copy_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: {colors.card};"
            f"  border: 1px solid {colors.border};"
            f"  border-radius: 3px;"
            f"  font-size: 12px;"
            f"  padding: 0;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background: {colors.surface};"
            f"  border-color: {colors.text_disabled};"
            f"}}"
        )

    # ──────────── 公开方法 ────────────

    def set_code_blocks(self, blocks: list):
        """设置代码块原始文本列表（与 HTML 中的标记索引对应）"""
        self._code_blocks = list(blocks)

    def setHtml(self, html_str):
        super().setHtml(html_str)
        self._cache_cursors()

    # ──────────── 标记位置缓存 ────────────

    def _cache_cursors(self):
        """在 QTextDocument 中查找所有代码块标记并缓存 cursor"""
        doc = self.document()
        if doc is None:
            return
        self._code_cursors = []
        for i in range(len(self._code_blocks)):
            s_marker = f"{_MK_S1}{i}{_MK_S2}"
            e_marker = f"{_MK_E1}{i}{_MK_E2}"
            sc = doc.find(s_marker)
            ec = doc.find(e_marker)
            if not sc.isNull() and not ec.isNull():
                self._code_cursors.append((sc, ec, i))

    # ──────────── 鼠标悬停检测 ────────────

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self._mouse_pos = event.pos()
        self._hover_timer.start()

    def _check_hover(self):
        """检查鼠标当前位置是否在某个代码块的垂直范围内"""
        y = self._mouse_pos.y()
        for sc, ec, idx in self._code_cursors:
            sr = self.cursorRect(sc)
            er = self.cursorRect(ec)
            top = min(sr.top(), sr.bottom())
            bot = max(er.top(), er.bottom())
            if top <= y <= bot:
                self._show_btn(top, idx)
                return
        self._hide_btn()

    def _show_btn(self, top_y, idx):
        self._hover_idx = idx
        vp = self.viewport()
        if vp is None:
            return
        x = vp.width() - self._copy_btn.width() - 6
        y = max(2, top_y + 3)
        self._copy_btn.move(x, y)
        self._copy_btn.show()
        self._copy_btn.raise_()

    def _hide_btn(self):
        self._copy_btn.hide()
        self._hover_idx = -1

    # ──────────── 复制按钮的 enter/leave 处理 ────────────

    def eventFilter(self, obj, event):
        """拦截复制按钮的 Enter/Leave 事件，防止按钮在点击前消失"""
        if obj is self._copy_btn:
            if event.type() == QEvent.Type.Enter:
                self._btn_hovered = True
            elif event.type() == QEvent.Type.Leave:
                self._btn_hovered = False
                QTimer.singleShot(80, self._after_btn_leave)
        return super().eventFilter(obj, event)

    def _after_btn_leave(self):
        vp = self.viewport()
        if vp is None:
            self._hide_btn()
            return
        local = vp.mapFromGlobal(QCursor.pos())
        if vp.rect().contains(local):
            self._mouse_pos = local
            self._check_hover()
        else:
            self._hide_btn()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        QTimer.singleShot(80, self._maybe_hide)

    def _maybe_hide(self):
        if not self._btn_hovered:
            self._hide_btn()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        if self._copy_btn.isVisible():
            self._check_hover()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._copy_btn.isVisible():
            self._check_hover()

    # ──────────── 复制 / 链接处理 ────────────

    def _copy_current(self):
        if 0 <= self._hover_idx < len(self._code_blocks):
            cb = QApplication.clipboard()
            if cb is not None:
                cb.setText(self._code_blocks[self._hover_idx])

    def _on_anchor_clicked(self, url: QUrl):
        url_str = url.toString()
        if url_str.startswith("copy-code:"):
            try:
                idx = int(url_str.split(":")[1])
                if 0 <= idx < len(self._code_blocks):
                    cb = QApplication.clipboard()
                    if cb is not None:
                        cb.setText(self._code_blocks[idx])
            except (ValueError, IndexError):
                get_logger(__name__).debug("代码块复制链接解析失败: %s", url_str)
        else:
            QDesktopServices.openUrl(url)


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
        webengine_runtime: WebEngineRuntime | None = None,
        parent=None,
    ):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("MarkdownPreviewWidget 必须传入 theme_engine，不允许为 None")
        self.config = config
        self._theme_engine = theme_engine
        self._webengine_runtime = webengine_runtime
        self.tab_id = None

        self._code_blocks: list[str] = []
        self._base_path = ""
        self._async_renderer = None
        self._pending_async_task: Optional[str] = None
        self._render_cache = None
        self._md_parser = self._create_md_parser()
        self._html_template_loaded = False
        self._preview_dirty = True
        self._initial_preview_rendered = False
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
            self._async_renderer.result_ready.connect(self._on_async_highlight_ready)

        if is_enabled("markdown_incremental"):
            from .incremental_renderer import RenderCache
            self._render_cache = RenderCache(
                self._render_markdown_with_source_map, cache_size=50
            )

        self._init_ui()
        self._connect_signals()

    def set_base_path(self, path: str):
        """设置基础路径（文件所在目录），用于解析本地相对图片路径

        v1.5.4 新增
        """
        if path != self._base_path:
            self._html_template_loaded = False
        self._base_path = path

    def _on_load_finished(self, ok):
        if ok:
            self._html_template_loaded = True

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧编辑器
        self.editor = Editor(self.config, theme_engine=self._theme_engine)
        self.splitter.addWidget(self.editor)

        # 右侧预览
        self.preview: Union[QWebEngineView, PreviewBrowser]
        if HAS_WEBENGINE:
            self.preview = QWebEngineView()
        else:
            self.preview = PreviewBrowser(self._theme_engine, self)
            self.preview.setFont(QFont("Microsoft YaHei", 11))
            get_logger(__name__).warning(
                "QWebEngineView 导入失败，预览回退到 QTextBrowser（源码行号同步不可用）。"
                " 真实原因: %s",
                _WEBENGINE_IMPORT_ERROR or "未知（HAS_WEBENGINE=False 但无异常信息）",
            )

        self.splitter.addWidget(self.preview)
        self.splitter.setSizes([500, 500])
        layout.addWidget(self.splitter)

        if (
            HAS_WEBENGINE
            and isinstance(self.preview, QWebEngineView)
            and self._webengine_runtime is not None
        ):
            self._webengine_runtime.notify_real_view_attached()

        # 防抖定时器
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._update_preview)

        self._preview_visible = True

        if HAS_WEBENGINE and isinstance(self.preview, QWebEngineView):
            self.preview.loadFinished.connect(self._on_load_finished)
            page = self.preview.page()
            if page is not None:
                # 预览 -> 编辑器：JS 经 document.title 回传顶部源码行
                page.titleChanged.connect(self._on_preview_title)

        # 拖动分隔条改变预览宽度后，锚点像素位置整体变化，需重新同步
        self.splitter.splitterMoved.connect(lambda *_: self._schedule_resync())

        self._init_theme(self._theme_engine)

    def _apply_theme_colors(self, colors):
        if isinstance(self.preview, PreviewBrowser):
            self.preview._apply_copy_btn_style(colors)
        # 主题变更时重建预览以应用新 CSS（重置标志让 _push_to_preview 走 setHtml 路径）
        self._html_template_loaded = False
        if getattr(self, 'editor', None) is not None:
            self._update_preview()

    def _connect_signals(self) -> None:
        self.editor.textChanged.connect(self._on_text_changed)
        vbar = self.editor.verticalScrollBar()
        if vbar is not None:
            vbar.valueChanged.connect(self._sync_scroll)
        # 折叠状态变更 → 同步预览
        folding = getattr(self.editor, '_folding', None)
        if folding is not None:
            folding.fold_state_changed.connect(self._sync_folds_to_preview)

    def refresh_preview_now(self) -> None:
        """文件装载/主题重建后强制刷新预览，不依赖 textChanged 防抖。"""
        if hasattr(self, "_preview_timer"):
            self._preview_timer.stop()
        self._update_preview()
        self._initial_preview_rendered = True

    def invalidate_preview(self) -> None:
        self._preview_dirty = True

    def ensure_preview_rendered(self) -> None:
        if not self._preview_dirty:
            return

        self._preview_dirty = False
        self._initial_preview_rendered = True
        self.refresh_preview_now()

    def _on_text_changed(self):
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

        if self._render_cache and is_enabled("markdown_incremental"):
            html_content = self._render_cache.render(text)
        elif HAS_MARKDOWN_IT or HAS_MARKDOWN:
            html_content = self._render_markdown_with_source_map(text)
        else:
            html_content = self._basic_md_to_html(text)

        if self._async_renderer and is_enabled("async_highlight"):
            html_content = self._process_code_blocks_async(html_content)
        else:
            html_content = self._process_code_blocks(html_content)

        html_content = self._resolve_local_images(html_content)

        # 包裹折叠 section（编辑器的折叠状态同步到预览）
        html_content = self._wrap_fold_sections(html_content, text)

        self._push_to_preview(html_content)

    def _push_to_preview(self, html_content: str):
        """把渲染好的 HTML 推送到预览，供 _update_preview / _on_async_highlight_done 共用。

        - QWebEngine 且模板已加载：仅更新 #content 的 innerHTML 并重同步(不重建整页 DOM，
          因此保留滚动位置)；
        - 否则：整页 setHtml(首次加载 / QTextBrowser)。
        """
        if isinstance(self.preview, PreviewBrowser):
            self.preview.set_code_blocks(self._code_blocks)

        if HAS_WEBENGINE and isinstance(self.preview, QWebEngineView) and self._html_template_loaded:
            import json
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
            page = self.preview.page()
            if page is not None:
                page.runJavaScript(js)
        else:
            css_vars = _build_preview_css_vars(self._theme_engine)
            template = PREVIEW_HTML_TEMPLATE
            try:
                full_html = template.format(content=html_content).replace(
                    "</style>", css_vars + "\n</style>", 1
                )
            except Exception as exc:
                get_logger(__name__).error(
                    "Markdown preview template format failed: %s",
                    exc,
                    exc_info=True,
                )

                colors = self._theme_engine.get_active_theme().colors
                fallback_bg = colors.background
                fallback_text = colors.text_primary
                fallback_code_bg = colors.bg_codeblock
                fallback_border = colors.codeblock_border
                fallback_link = colors.primary

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
            if HAS_WEBENGINE and isinstance(self.preview, QWebEngineView):
                if self._base_path:
                    base_url = QUrl.fromLocalFile(self._base_path + '/')
                    self.preview.setHtml(full_html, base_url)
                else:
                    self.preview.setHtml(full_html)
            elif isinstance(self.preview, PreviewBrowser):
                self.preview.setHtml(full_html)

        # 同步当前折叠状态到预览
        self._sync_folds_to_preview()

    def _create_md_parser(self):
        if not HAS_MARKDOWN_IT:
            return None
        md = _MarkdownIt("commonmark", {"html": False})
        md.enable(["table", "strikethrough"])
        try:
            from mdit_py_plugins.deflist import deflist_plugin
            deflist_plugin(md)
        except ImportError:
            get_logger(__name__).debug("mdit_py_plugins 未安装，定义列表语法不可用")
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

    def _wrap_fold_sections(self, html: str, text: str) -> str:
        """在 Markdown 标题的 DOM 节点外包裹 <section data-fold-heading="N">。

        折叠区间计算与 FoldingManager 一致，确保编辑器和预览折叠对应。
        在 _process_code_blocks 之后、_push_to_preview 之前调用。
        """
        import re
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
        if not HAS_WEBENGINE or not isinstance(self.preview, QWebEngineView):
            return
        if not self._html_template_loaded:
            return

        import json
        collapsed = folding.get_collapsed_lines()
        js = f"window.updateFoldVisibility('{json.dumps(collapsed)}');"
        page = self.preview.page()
        if page is not None:
            page.runJavaScript(js)

    # ──────────── 代码块后处理 ────────────

    def _get_code_highlight_theme(self):
        """获取代码高亮用的 ThemeEngine 实例。

        兼容旧配置：
        - 空值 / auto / default / none / null 视为自动，使用当前主题；
        - 其它显式主题名保留但对旧用户透明——始终使用当前主题引擎。
        """
        return self._theme_engine

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

        self._code_blocks = []
        block_idx = [0]

        def _replace_sync(m):
            code_attrs = m.group("code_attrs") or ""
            lang = _extract_language_from_code_attrs(code_attrs)
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

    def _on_async_highlight_ready(self, task_id: str, html: str, language: str):
        pass

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
        """构建代码块 HTML 容器：浅蓝背景 + 首尾不可见标记 + 逐行锚点。

        标记用于 PreviewBrowser 在 QTextDocument 中定位代码块的
        垂直范围，从而在正确位置显示浮动复制按钮。
        """
        sm = f"{_MK_S1}{index}{_MK_S2}"
        em = f"{_MK_E1}{index}{_MK_E2}"
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
            f'<span class="code-marker">{sm}</span>'
            f'<pre class="code-pre"><code class="code-block">{code_html}</code></pre>'
            f'<span class="code-marker">{em}</span>'
            f'</div>'
        )

    # ──────────── 基础渲染（无 markdown 库回退） ────────────

    def _basic_md_to_html(self, text: str) -> str:
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
                p = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', p)
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
        at_bottom = (bar is not None and bar.maximum() > 0
                     and bar.value() >= bar.maximum())

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
            or (bar.maximum() > 0 and bar.value() >= bar.maximum())
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

        if HAS_WEBENGINE and isinstance(self.preview, QWebEngineView):
            page = self.preview.page()
            if page is None:
                return
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
            page.runJavaScript(js)
            return

        # QTextBrowser fallback：按源码行号比例滚动
        if total_lines > 0:
            line_ratio = min(frac_line / total_lines, 1.0)
            try:
                assert isinstance(self.preview, PreviewBrowser)
                pb = self.preview.verticalScrollBar()
                if pb is not None:
                    pb.setValue(int(line_ratio * pb.maximum()))
            except Exception:
                get_logger(__name__).debug("QTextBrowser 同步失败", exc_info=True)

    # ──────────── 预览 -> 编辑器 反向同步 ────────────

    def _on_preview_title(self, title: str):
        """JS 经 document.title 回传消息，据此滚动编辑器或执行复制。"""
        if not title:
            return
        if title.startswith("__pncopy__:"):
            try:
                idx = int(title.split(":")[1])
                if 0 <= idx < len(self._code_blocks):
                    cb = QApplication.clipboard()
                    if cb is not None:
                        cb.setText(self._code_blocks[idx])
            except (ValueError, IndexError):
                pass
            return
        if not title.startswith("__pzsync__:"):
            return
        parts = title.split(":")
        if len(parts) < 2:
            return
        try:
            frac_line = float(parts[1])
        except ValueError:
            return
        self._scroll_editor_to_line(frac_line)

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

    def debug_sync_state(self) -> None:
        """打印运行时同步调试信息到日志。"""
        if HAS_WEBENGINE and isinstance(self.preview, QWebEngineView):
            page = self.preview.page()
            if page is not None:
                page.runJavaScript(
                    "var nodes = document.querySelectorAll('[data-source-line]'); "
                    "var sample = Array.from(nodes).slice(0, 15).map(function(el) {"
                    "  return { line: el.getAttribute('data-source-line'), tag: el.tagName, cls: el.className };"
                    "});"
                    "JSON.stringify({ nodeCount: nodes.length, sample: sample, debug: window.__panzerSyncDebug || {} })",
                    lambda result: get_logger(__name__).debug(
                        "Markdown sync debug: %s", result
                    ),
                )

    def toggle_preview(self):
        self._preview_visible = not self._preview_visible
        self.preview.setVisible(self._preview_visible)
        if self._preview_visible:
            self._update_preview()

    def set_preview_visible(self, visible: bool):
        self._preview_visible = visible
        self.preview.setVisible(visible)
        if visible:
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
