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
import html as html_module
from PyQt5.QtWidgets import (
    QWidget, QSplitter, QVBoxLayout, QTextBrowser, QApplication, QPushButton
)
from PyQt5.QtCore import Qt, QTimer, QUrl, QPoint, QEvent
from PyQt5.QtGui import QFont, QDesktopServices, QCursor

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
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False

from ..core.config import Config
from ..editor.editor import Editor
from ..utils.logger import get_logger
from ..utils.feature_flags import is_enabled
from .highlight_themes import highlight_code_html

# ════════════════════════════════════════════════════════
#  正则 / 常量
# ════════════════════════════════════════════════════════

# 匹配 fenced_code 输出的 <pre><code> 块
_CODEBLOCK_RE = re.compile(
    r'<pre><code(?:\s+class="language-([^"]*)")?>(.*?)</code>\s*</pre>',
    re.DOTALL,
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

# ════════════════════════════════════════════════════════
#  HTML 模板
# ════════════════════════════════════════════════════════

PREVIEW_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
/* ========== 基础 ========== */
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei UI",
                 "Microsoft YaHei", Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.7;
    color: #2b2b2b;
    padding: 12px 20px 40px 20px;
    margin: 0;
    max-width: 100%;
    background: #fff;
    word-wrap: break-word;
    overflow-wrap: break-word;
}}

/* ========== 标题 ========== */
h1, h2, h3, h4, h5, h6 {{
    color: #2b2b2b;
    font-weight: bold;
    margin-top: 24px;
    margin-bottom: 12px;
    line-height: 1.3;
}}
h1 {{
    font-size: 1.85em;
    border-bottom: 1px solid #d0d0d0;
    padding-bottom: 6px;
}}
h2 {{
    font-size: 1.5em;
    border-bottom: 1px solid #d9d9d9;
    padding-bottom: 5px;
}}
h3 {{ font-size: 1.3em; }}
h4 {{ font-size: 1.15em; }}
h5 {{ font-size: 1.05em; }}
h6 {{ font-size: 1em; color: #656565; }}

/* ========== 段落 / 文本 ========== */
p {{ margin: 8px 0; }}
strong {{ font-weight: 700; }}
em {{ font-style: italic; }}

/* ========== 行内代码 ========== */
code {{
    font-family: "JetBrains Mono", Consolas, "Courier New", "Microsoft YaHei", monospace;
    background: #f0f0f0;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 0.92em;
    color: #2b2b2b;
    border: 1px solid #e0e0e0;
}}

/* ========== 引用 ========== */
blockquote {{
    border-left: 3px solid #bababa;
    padding: 4px 16px;
    margin: 10px 0;
    background: #f9f9f9;
    color: #555;
}}
blockquote p {{ margin: 4px 0; }}

/* ========== 表格 ========== */
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 12px 0;
}}
th, td {{
    border: 1px solid #d0d0d0;
    padding: 6px 12px;
    text-align: left;
}}
th {{
    background: #f0f0f0;
    font-weight: 600;
}}
tr:nth-child(even) {{ background: #fafafa; }}

/* ========== 链接 ========== */
a {{ color: #2470B3; text-decoration: none; }}
a:hover {{ text-decoration: underline; color: #1a5a96; }}

/* ========== 图片 ========== */
img {{ max-width: 100%; border-radius: 3px; }}

/* ========== 分割线 ========== */
hr {{ border: none; border-top: 1px solid #d0d0d0; margin: 20px 0; }}

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
    background: #f2f6fc;
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
.toc a {{ color: #2470B3; text-decoration: none; }}
.toc a:hover {{ text-decoration: underline; color: #1a5a96; }}
</style>
</head>
<body>
{content}
</body>
</html>"""


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

    def __init__(self, parent=None):
        super().__init__(parent)
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
        self._copy_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._copy_btn.hide()
        self._copy_btn.setStyleSheet(
            "QPushButton {"
            "  background: rgba(255,255,255,0.92);"
            "  border: 1px solid #c0c0c0;"
            "  border-radius: 3px;"
            "  font-size: 12px;"
            "  padding: 0;"
            "}"
            "QPushButton:hover {"
            "  background: #e0e0e0;"
            "  border-color: #999;"
            "}"
        )
        self._copy_btn.clicked.connect(self._copy_current)
        self._copy_btn.installEventFilter(self)

        # ── 悬停检测防抖定时器 ──
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(30)
        self._hover_timer.timeout.connect(self._check_hover)
        self._mouse_pos = QPoint()

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
        x = self.viewport().width() - self._copy_btn.width() - 6
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
            if event.type() == QEvent.Enter:
                self._btn_hovered = True
            elif event.type() == QEvent.Leave:
                self._btn_hovered = False
                QTimer.singleShot(80, self._after_btn_leave)
        return super().eventFilter(obj, event)

    def _after_btn_leave(self):
        vp = self.viewport()
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
            QApplication.clipboard().setText(self._code_blocks[self._hover_idx])

    def _on_anchor_clicked(self, url: QUrl):
        url_str = url.toString()
        if url_str.startswith("copy-code:"):
            try:
                idx = int(url_str.split(":")[1])
                if 0 <= idx < len(self._code_blocks):
                    QApplication.clipboard().setText(self._code_blocks[idx])
            except (ValueError, IndexError):
                pass
        else:
            QDesktopServices.openUrl(url)


# ════════════════════════════════════════════════════════
#  MarkdownPreviewWidget
# ════════════════════════════════════════════════════════

class MarkdownPreviewWidget(QWidget):
    """Markdown分屏预览组件

    包含左侧编辑器和右侧预览，提供与Editor相同的接口
    """

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.tab_id = None

        self._code_blocks = []
        self._base_path = ""
        self._async_renderer = None
        self._pending_async_task = None
        self._incremental_renderer = None

        if is_enabled("async_highlight"):
            from .async_highlight import AsyncHighlightRenderer
            self._async_renderer = AsyncHighlightRenderer(self)
            self._async_renderer.result_ready.connect(self._on_async_highlight_ready)

        if is_enabled("markdown_incremental"):
            from .incremental_renderer import IncrementalRenderer
            self._incremental_renderer = IncrementalRenderer(
                self._render_markdown, cache_size=50
            )

        self._init_ui()
        self._connect_signals()

    def set_base_path(self, path: str):
        """设置基础路径（文件所在目录），用于解析本地相对图片路径

        v1.5.4 新增
        """
        self._base_path = path

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Horizontal)

        # 左侧编辑器
        self.editor = Editor(self.config)
        self.splitter.addWidget(self.editor)

        # 右侧预览
        if HAS_WEBENGINE:
            self.preview = QWebEngineView()
        else:
            self.preview = PreviewBrowser(self)
            self.preview.setFont(QFont("Microsoft YaHei", 11))

        self.splitter.addWidget(self.preview)
        self.splitter.setSizes([500, 500])
        layout.addWidget(self.splitter)

        # 防抖定时器
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._update_preview)

        self._preview_visible = True

    def _connect_signals(self):
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.verticalScrollBar().valueChanged.connect(self._sync_scroll)

    def _on_text_changed(self):
        self._preview_timer.start()

    # ──────────── 核心渲染 ────────────

    def _update_preview(self):
        text = self.editor.toPlainText()

        if self._incremental_renderer and is_enabled("markdown_incremental"):
            html_content = self._incremental_renderer.render(text)
        elif HAS_MARKDOWN_IT or HAS_MARKDOWN:
            html_content = self._render_markdown(text)
        else:
            html_content = self._basic_md_to_html(text)

        if self._async_renderer and is_enabled("async_highlight"):
            html_content = self._process_code_blocks_async(html_content)
        else:
            html_content = self._process_code_blocks(html_content)

        html_content = self._resolve_local_images(html_content)

        full_html = PREVIEW_HTML_TEMPLATE.format(content=html_content)

        if isinstance(self.preview, PreviewBrowser):
            self.preview.set_code_blocks(self._code_blocks)

        if HAS_WEBENGINE:
            if self._base_path:
                base_url = QUrl.fromLocalFile(self._base_path + '/')
                self.preview.setHtml(full_html, base_url)
            else:
                self.preview.setHtml(full_html)
        else:
            self.preview.setHtml(full_html)

    def _render_markdown(self, text: str) -> str:
        # 优先使用 markdown-it-py（CommonMark 兼容，列表可打断段落）
        if HAS_MARKDOWN_IT:
            try:
                md = _MarkdownIt("commonmark", {"html": True})
                md.enable(["table", "strikethrough"])
                try:
                    from mdit_py_plugins.deflist import deflist_plugin
                    deflist_plugin(md)
                except ImportError:
                    pass
                return md.render(text)
            except Exception:
                get_logger(__name__).debug("markdown-it 渲染失败，回退到 python-markdown")

        if HAS_MARKDOWN:
            extensions = [
                'tables', 'fenced_code', 'toc',
                'attr_list', 'def_list', 'sane_lists',
            ]
            try:
                return md_lib.markdown(text, extensions=extensions)
            except Exception:
                try:
                    return md_lib.markdown(text)
                except Exception:
                    get_logger(__name__).warning("python-markdown 渲染失败")

        return html_module.escape(text)

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

            # 跳过已经是绝对 URL 的
            if src.startswith(('http://', 'https://', 'file://', 'data:')):
                return m.group(0)

            # 将相对路径转为绝对路径
            abs_path = os.path.normpath(os.path.join(self._base_path, src))
            if os.path.exists(abs_path):
                # 转换为 file:// URL
                file_url = QUrl.fromLocalFile(abs_path).toString()
                return f'{prefix}src="{file_url}"'

            # 文件不存在，保持原样
            return m.group(0)

        return _IMG_SRC_RE.sub(_resolve_src, html)

    # ──────────── 代码块后处理 ────────────

    def _process_code_blocks(self, html: str) -> str:
        """替换所有 <pre><code> 块：语法高亮 + 浅蓝容器 + 嵌入位置标记"""
        self._code_blocks = []
        theme = self.config.get_editor_setting("code_highlight_theme", None)

        def _replace(m):
            lang = m.group(1) or ""
            raw = html_module.unescape(m.group(2))
            if raw.endswith("\n"):
                raw = raw[:-1]

            idx = len(self._code_blocks)
            self._code_blocks.append(raw)

            highlighted = highlight_code_html(raw, lang, theme)
            return self._build_container(idx, highlighted)

        return _CODEBLOCK_RE.sub(_replace, html)

    def _process_code_blocks_async(self, html: str) -> str:
        """异步版本的代码块处理：先渲染占位符，再异步替换高亮结果"""
        self._code_blocks = []
        theme = self.config.get_editor_setting("code_highlight_theme", None)

        if self._pending_async_task:
            self._async_renderer.cancel(self._pending_async_task)
            self._pending_async_task = None

        def _replace(m):
            lang = m.group(1) or ""
            raw = html_module.unescape(m.group(2))
            if raw.endswith("\n"):
                raw = raw[:-1]

            idx = len(self._code_blocks)
            self._code_blocks.append(raw)

            escaped = html_module.escape(raw)
            return self._build_container(idx, escaped)

        result = _CODEBLOCK_RE.sub(_replace, html)

        if self._code_blocks and self._async_renderer:
            task_id = self._async_renderer.render(
                "\n---SEPARATOR---\n".join(self._code_blocks),
                "auto",
                theme,
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
            html_content = self._render_markdown(text)
        else:
            html_content = self._basic_md_to_html(text)

        self._code_blocks = []
        block_idx = [0]

        def _replace_sync(m):
            lang = m.group(1) or ""
            raw = html_module.unescape(m.group(2))
            if raw.endswith("\n"):
                raw = raw[:-1]

            idx = block_idx[0]
            self._code_blocks.append(raw)

            if idx < len(highlighted_blocks):
                return self._build_container(idx, highlighted_blocks[idx])
            return self._build_container(idx, html_module.escape(raw))

        block_idx_ref = block_idx

        def _replace_and_count(m):
            result = _replace_sync(m)
            block_idx_ref[0] += 1
            return result

        html_content = _CODEBLOCK_RE.sub(_replace_and_count, html_content)
        html_content = self._resolve_local_images(html_content)
        full_html = PREVIEW_HTML_TEMPLATE.format(content=html_content)

        if isinstance(self.preview, PreviewBrowser):
            self.preview.set_code_blocks(self._code_blocks)

        if HAS_WEBENGINE:
            if self._base_path:
                base_url = QUrl.fromLocalFile(self._base_path + '/')
                self.preview.setHtml(full_html, base_url)
            else:
                self.preview.setHtml(full_html)
        else:
            self.preview.setHtml(full_html)

    def _on_async_highlight_ready(self, task_id: str, html: str, language: str):
        pass

    @staticmethod
    def _build_container(index: int, code_html: str) -> str:
        """构建代码块 HTML 容器：浅蓝背景 + 首尾不可见标记

        标记用于 PreviewBrowser 在 QTextDocument 中定位代码块的
        垂直范围，从而在正确位置显示浮动复制按钮。
        """
        sm = f"{_MK_S1}{index}{_MK_S2}"
        em = f"{_MK_E1}{index}{_MK_E2}"
        return (
            '<table cellpadding="0" cellspacing="0" border="0" width="100%"'
            ' style="margin-top:8px; margin-bottom:8px;">'
            '<tr>'
            '<td bgcolor="#EDF3FA" style="padding:4px 12px 6px 12px;">'
            # 起始标记（1px、同色，视觉不可见）
            f'<span style="font-size:1px; color:#EDF3FA;">{sm}</span>'
            # 代码区
            f'<pre id="code-block-{index}"'
            ' style="margin:0; padding:0;'
            ' background-color:transparent; background:transparent;'
            ' border:none;'
            " font-family:Consolas, 'Courier New', 'Microsoft YaHei', monospace;"
            ' font-size:12px; line-height:1.45; color:#2b2b2b;'
            f' white-space:pre; overflow-x:auto;">{code_html}</pre>'
            # 结束标记
            f'<span style="font-size:1px; color:#EDF3FA;">{em}</span>'
            '</td>'
            '</tr>'
            '</table>'
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

    def _sync_scroll(self, value):
        if not self._preview_visible:
            return
        bar = self.editor.verticalScrollBar()
        if bar.maximum() == 0:
            return
        ratio = value / bar.maximum() if bar.maximum() > 0 else 0
        if HAS_WEBENGINE:
            js = f"window.scrollTo(0, document.body.scrollHeight * {ratio});"
            self.preview.page().runJavaScript(js)
        else:
            pb = self.preview.verticalScrollBar()
            pb.setValue(int(ratio * pb.maximum()))

    # ──────────── 预览显隐 ────────────

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
        return self.editor.toPlainText()

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

    def zoomOut(self, n=1):
        self.editor.zoomOut(n)

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
