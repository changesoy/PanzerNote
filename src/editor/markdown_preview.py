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
from typing import Optional

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

from ..core.config import Config
from ..editor.editor import Editor
from ..utils.logger import get_logger
from ..utils.feature_flags import is_enabled
from ..themes.theme_aware_mixin import ThemeAwareMixin
from ..themes.theme_v2.consumer import v2_color, v2_token
from .highlight_themes import highlight_code_html

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

# 匹配折叠 section 的开闭标签（方案 A：QTextDocument 无法用 CSS 隐藏折叠区段）
_SECTION_TAG_RE = re.compile(r'<section data-fold-heading="(\d+)">|</section>')

# 源码行锚点标记：QTextDocument 无法读取 HTML 自定义属性，故在块首嵌入
# 不可见标记（⌈N⌉），setHtml 后按块扫描还原"源码行 → 文档像素 y"锚点表。
_SRC_MARK_OPEN = "\u2308"  # ⌈
_SRC_MARK_CLOSE = "\u2309"  # ⌉
_SRC_MARK_RE = re.compile(r"\u2308(\d+)\u2309")

# 可安全嵌入块首标记的标签（容器类标签如 table/tr/div 内直接插内联节点会破坏结构）
_SRC_MARK_TAGS = frozenset({
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "li", "blockquote", "td", "th", "span",
})

# 匹配携带 data-source-line 的开标签
_SRC_LINE_TAG_RE = re.compile(
    r'<(?P<tag>[a-zA-Z][\w-]*)\b[^>]*?\bdata-source-line="(?P<line>\d+)"[^>]*>'
)

# 复制时剔除所有预览内部标记（源码行锚点 + 代码块起止标记）
_PREVIEW_MARK_STRIP_RE = re.compile(r"[\u2308\u231C\u231E]\d+[\u2309\u231D\u231F]")

from .secure_markdown_renderer import (
    convert_layout_css_for_qtext,
    strip_dangerous_html as _strip_dangerous_html,
)
from .document_render_cache import _DOC_RENDER_CACHE, clear_document_render_cache


def strip_preview_markers(text: str) -> str:
    """剔除预览内部锚点/标记字符，供剪贴板复制使用。"""
    if not text:
        return text
    return _PREVIEW_MARK_STRIP_RE.sub("", text)


def _inject_source_line_marks(html: str) -> str:
    """在带 data-source-line 的块级标签首部注入不可见源码行标记（⌈N⌉）。

    QTextDocument 不保留 HTML 自定义属性，锚点标记是唯一可靠的行定位手段：
    setHtml 后按块扫描标记，即可建立"源码行 → 文档像素 y"锚点表，
    供编辑器↔预览双向滚动同步使用。标记在复制时由 strip_preview_markers 剔除。
    """
    def _replace(match: re.Match[str]) -> str:
        if match.group("tag").lower() not in _SRC_MARK_TAGS:
            return match.group(0)
        line = match.group("line")
        return (
            f'{match.group(0)}<span class="src-mark" '
            f'style="font-size:1px;color:transparent;">'
            f'{_SRC_MARK_OPEN}{line}{_SRC_MARK_CLOSE}</span>'
        )

    return _SRC_LINE_TAG_RE.sub(_replace, html)


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
        # 源码行锚点表 [(源码行, 文档像素 y)] 与脏标记（布局变化后惰性重建）
        self._line_anchors: list[tuple[float, float]] = []
        self._line_anchors_dirty = True

        # ── 浮动复制按钮（挂在 viewport 上，随内容滚动） ──
        self._copy_btn = QPushButton("\U0001f4cb", self.viewport())
        self._copy_btn.setFixedSize(26, 20)
        self._copy_btn.setToolTip("复制到剪贴板")
        self._copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._copy_btn.hide()
        self._apply_copy_btn_style()
        self._copy_btn.clicked.connect(self._copy_current)
        self._copy_btn.installEventFilter(self)

        # ── 悬停检测防抖定时器 ──
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(30)
        self._hover_timer.timeout.connect(self._check_hover)
        self._mouse_pos = QPoint()

    def _apply_copy_btn_style(self) -> None:
        """使用主题 token 更新浮动复制按钮样式（B2：纯 v2，无 v1 回退）。"""
        btn_bg = v2_token(self._theme_engine, "surface_raised", "#FFFFFF")
        btn_border = v2_token(self._theme_engine, "border_muted", "#E0E0E0")
        btn_hover_bg = v2_token(self._theme_engine, "surface_secondary", "#F5F5F5")
        btn_hover_border = v2_token(self._theme_engine, "text_muted", "#BDBDBD")
        self._copy_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: {btn_bg};"
            f"  border: 1px solid {btn_border};"
            f"  border-radius: 3px;"
            f"  font-size: 12px;"
            f"  padding: 0;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background: {btn_hover_bg};"
            f"  border-color: {btn_hover_border};"
            f"}}"
        )

    # ──────────── 公开方法 ────────────

    def set_code_blocks(self, blocks: list):
        """设置代码块原始文本列表（与 HTML 中的标记索引对应）"""
        self._code_blocks = list(blocks)

    def setHtml(self, html_str):
        super().setHtml(html_str)
        self._cache_cursors()
        self._line_anchors_dirty = True

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

    # ──────────── 源码行锚点表（滚动同步） ────────────

    def line_anchors(self) -> list[tuple[float, float]]:
        """返回 [(源码行, 文档像素 y)] 锚点表，按 y 升序。

        布局变化（resize / setHtml）后惰性重建：QTextDocument 不保留 HTML
        自定义属性，锚点由 _inject_source_line_marks 嵌入的不可见标记还原。
        """
        if self._line_anchors_dirty:
            self._rebuild_line_anchors()
        return self._line_anchors

    def _rebuild_line_anchors(self) -> None:
        doc = self.document()
        anchors: list[tuple[float, float]] = []
        layout = doc.documentLayout() if doc is not None else None
        if doc is not None and layout is not None:
            block = doc.begin()
            while block.isValid():
                match = _SRC_MARK_RE.match(block.text())
                if match:
                    top = layout.blockBoundingRect(block).top()
                    anchors.append((float(match.group(1)), float(top)))
                block = block.next()
        anchors.sort(key=lambda item: (item[1], item[0]))
        self._line_anchors = anchors
        self._line_anchors_dirty = False

    def scroll_to_source_line(
        self, frac_line: float, at_top: bool = False, at_bottom: bool = False
    ) -> None:
        """把源码行 frac_line 对齐到预览视口顶部。

        锚点间线性插值；无锚点时由调用方（widget）回退到整体比例滚动。
        文档坐标 y 与竖直滚动条取值范围同源，可直接 setValue。
        """
        bar = self.verticalScrollBar()
        if bar is None:
            return
        if at_top:
            bar.setValue(bar.minimum())
            return
        if at_bottom:
            bar.setValue(bar.maximum())
            return

        anchors = self.line_anchors()
        if len(anchors) < 2:
            return
        target = self._interpolate_line_to_y(anchors, frac_line)
        bar.setValue(int(max(float(bar.minimum()), min(target, float(bar.maximum())))))

    @staticmethod
    def _interpolate_line_to_y(anchors: list[tuple[float, float]], frac_line: float) -> float:
        """源码行（可含小数）→ 文档像素 y，锚点间线性插值。"""
        first_line, first_y = anchors[0]
        if frac_line <= first_line:
            return first_y
        for (line0, y0), (line1, y1) in zip(anchors, anchors[1:]):
            if line0 <= frac_line < line1:
                if line1 <= line0:
                    return y0
                ratio = (frac_line - line0) / (line1 - line0)
                return y0 + (y1 - y0) * ratio
        return anchors[-1][1]

    def source_line_at_viewport_top(self) -> float | None:
        """预览视口顶部对应的源码行（可含小数）；锚点不足时返回 None。"""
        bar = self.verticalScrollBar()
        anchors = self.line_anchors()
        if bar is None or len(anchors) < 2:
            return None
        y = float(bar.value())
        first_line, first_y = anchors[0]
        if y <= first_y:
            return first_line
        for (line0, y0), (line1, y1) in zip(anchors, anchors[1:]):
            if y0 <= y < y1:
                if y1 <= y0:
                    return line0
                ratio = (y - y0) / (y1 - y0)
                return line0 + (line1 - line0) * ratio
        return anchors[-1][0]

    def createMimeDataFromSelection(self):
        """复制时剔除预览内部锚点/标记字符，避免剪贴板出现不可见噪声。"""
        mime = super().createMimeDataFromSelection()
        if mime is None:
            return mime
        text = mime.text()
        if text and _PREVIEW_MARK_STRIP_RE.search(text):
            mime.setText(strip_preview_markers(text))
        return mime

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
        # 换行宽度变化会改变块高度 → 锚点像素位置失效，标记待重建
        self._line_anchors_dirty = True
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
        self._preview_dirty = True
        self._last_sync_frac: float = 1.0
        self._last_at_top: bool = True
        self._last_at_bottom: bool = False
        self._last_sync_time: float = 0.0
        self._sync_trailing_timer = QTimer(self)
        self._sync_trailing_timer.setSingleShot(True)
        self._sync_trailing_timer.timeout.connect(self._on_sync_trailing)
        self._suppress_editor_sync: bool = False
        self._suppress_preview_sync: bool = False
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
        self._base_path = path

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧编辑器
        self.editor = Editor(self.config, theme_engine=self._theme_engine)
        self.splitter.addWidget(self.editor)

        # 右侧预览：QTextBrowser（QTextDocument 唯一渲染路径，方案 A）
        self.preview = PreviewBrowser(self._theme_engine, self)
        self.preview.setFont(QFont("Microsoft YaHei", 11))

        self.splitter.addWidget(self.preview)
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
        self.preview._apply_copy_btn_style()
        # 主题变更时清空 Document 级渲染缓存（高亮颜色/折叠样式依赖主题）
        clear_document_render_cache()
        # 主题变更时重建预览以应用新 CSS（QTextBrowser 走整页 setHtml）
        if getattr(self, 'editor', None) is not None:
            self._update_preview()

    def _connect_signals(self) -> None:
        self.editor.textChanged.connect(self._on_text_changed)
        vbar = self.editor.verticalScrollBar()
        if vbar is not None:
            vbar.valueChanged.connect(self._sync_scroll)
        # 预览滚动 → 反向同步编辑器（锚点表映射，替代原 JS 回传桥）
        pbar = self.preview.verticalScrollBar()
        if pbar is not None:
            pbar.valueChanged.connect(self._on_preview_scroll)
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

        if self._async_renderer and is_enabled("async_highlight"):
            html_content = self._process_code_blocks_async(html_content)
        else:
            html_content = self._process_code_blocks(html_content)

        html_content = self._resolve_local_images(html_content)

        # 注入源码行锚点标记（滚动同步用，复制时剔除）
        html_content = _inject_source_line_marks(html_content)

        # 包裹折叠 section（编辑器的折叠状态同步到预览；产物仅依赖 text）
        html_content = self._wrap_fold_sections(html_content, text)

        self._last_render_text = text
        self._last_render_html = html_content
        return html_content

    def _push_to_preview(self, html_content: str):
        """把渲染好的 HTML 推送到预览，供 _update_preview / _on_async_highlight_done 共用。

        方案 A：唯一渲染路径为 QTextBrowser（QTextDocument CSS 子集），整页 setHtml。
        折叠区段在推送前按当前折叠状态剔除（QTextDocument 无法用 CSS 隐藏）。
        """
        self.preview.set_code_blocks(self._code_blocks)

        html_content = self._apply_fold_visibility(
            html_content, self._collapsed_fold_lines()
        )

        try:
            full_html = self._build_qtext_full_html(html_content)
        except Exception as exc:
            get_logger(__name__).error(
                "Markdown preview QTextDocument HTML 构建失败: %s",
                exc,
                exc_info=True,
            )
            full_html = self._build_qtext_full_html_fallback(html_content)

        # setHtml 会把预览滚动条归零。该"程序性归零"必须与用户滚动区分开：
        # 否则会经 _on_preview_scroll 反向把编辑器拖回文档开头
        # （点折叠标记/改文本/切主题触发的重渲染都会命中）。
        # 先抑制反向同步，再在下一轮事件循环把预览重新对齐编辑器顶部行。
        self._suppress_preview_sync = True
        self.preview.setHtml(full_html)
        QTimer.singleShot(0, self._restore_preview_scroll)

    def _restore_preview_scroll(self) -> None:
        """重渲染后把预览重新对齐到编辑器当前顶部行，并解除反向同步抑制。"""
        self._suppress_preview_sync = True
        try:
            frac_line, at_top, at_bottom = self._editor_top_fractional_line()
            self.preview.scroll_to_source_line(frac_line, at_top, at_bottom)
        except Exception:
            get_logger(__name__).debug("预览滚动位置恢复失败", exc_info=True)
        finally:
            self._suppress_preview_sync = False

    def _qtext_theme_colors(self) -> dict[str, str]:
        """构建 QTextDocument 子集 CSS 的变量色值。

        键与 MARKDOWN_LAYOUT_CSS 的 CSS 变量一致（无 -- 前缀），
        经 convert_layout_css_for_qtext 注入为具体色值。
        """
        te = self._theme_engine
        return {
            "text-primary": v2_token(te, "text_primary", "#212121"),
            "text-secondary": v2_token(te, "text_secondary", "#757575"),
            "text-muted": v2_token(te, "text_muted", "#BDBDBD"),
            "border": v2_token(te, "border_muted", "#E0E0E0"),
            "border-soft": v2_token(te, "border_muted", "#EEEEEE"),
            "divider": v2_token(te, "border_muted", "#EEEEEE"),
            "surface": v2_token(te, "surface_secondary", "#F5F5F5"),
            "surface-soft": v2_token(te, "surface_secondary", "#F5F5F5"),
            "surface-hover": v2_token(te, "surface_raised", "#FAFAFA"),
            "primary": v2_token(te, "accent", "#2196F3"),
            "primary-hover": v2_token(te, "focus", "#1976D2"),
            "bg-codeblock": v2_token(te, "md_preview_code_block_bg", "#EDF3FA"),
            "scrollbar-thumb-hover": v2_color(te, "scrollbar", "handle_hover", "#BDBDBD"),
        }

    def _build_qtext_full_html(self, html_content: str) -> str:
        """构建 QTextDocument 渲染的完整 HTML：布局 CSS 子集 + body 具体色值。"""
        layout_css = convert_layout_css_for_qtext(self._qtext_theme_colors())
        bg = v2_token(self._theme_engine, "surface_primary", "#FFFFFF")
        fg = v2_token(self._theme_engine, "text_primary", "#212121")
        return (
            "<html><head><style>\n"
            "body { font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
            " font-size: 14px; line-height: 1.7; }\n"
            f"{layout_css}"
            "</style></head>"
            f'<body style="background-color:{bg};color:{fg};">'
            f"{html_content}</body></html>"
        )

    def _build_qtext_full_html_fallback(self, html_content: str) -> str:
        """CSS 构建失败时的降级 HTML（字面量 = v1 light 值，B8 语义）。"""
        return (
            "<html><head><style>\n"
            "body { font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
            " font-size: 14px; line-height: 1.7; }\n"
            "</style></head>"
            '<body style="background-color:#FFFFFF;color:#212121;">'
            f"{html_content}</body></html>"
        )

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

    @staticmethod
    def _apply_fold_visibility(html: str, collapsed: set[int]) -> str:
        """剔除被折叠 section 的整段内容。

        QTextDocument 既不支持 JS 也无 display:none，因此折叠只能通过
        "不把该段内容放进文档"来实现：在已包裹 section 的 HTML 上按折叠行号
        做深度感知的区间删除（支持标题层级嵌套产生的嵌套 section）。
        标签不配对时原样返回，避免半截 HTML。
        """
        if not collapsed:
            return html

        out: list[str] = []
        pos = 0
        skip_depth = 0
        for match in _SECTION_TAG_RE.finditer(html):
            token = match.group(0)
            is_open = token.startswith("<section")
            if skip_depth:
                skip_depth += 1 if is_open else -1
                if skip_depth == 0:
                    pos = match.end()
                continue
            if is_open and int(match.group(1)) in collapsed:
                out.append(html[pos:match.start()])
                skip_depth = 1
                pos = match.end()

        if skip_depth:
            get_logger(__name__).debug("折叠 section 标签不配对，跳过折叠过滤")
            return html

        out.append(html[pos:])
        return "".join(out)

    def _collapsed_fold_lines(self) -> set[int]:
        """读取编辑器 FoldingManager 当前折叠的标题行号集合。"""
        editor = getattr(self, "editor", None)
        folding = getattr(editor, "_folding", None) if editor is not None else None
        if folding is None:
            return set()
        try:
            return {int(line) for line in folding.get_collapsed_lines()}
        except Exception:
            get_logger(__name__).debug("读取折叠状态失败", exc_info=True)
            return set()

    def _sync_folds_to_preview(self) -> None:
        """编辑器折叠状态变化 → 重新推送预览（按折叠剔除被隐藏区段）。

        经预览防抖定时器复用 textChanged 的刷新路径，避免连续折叠时抖动。
        """
        timer = getattr(self, "_preview_timer", None)
        if timer is not None:
            timer.start()

    # ──────────── 代码块后处理 ────────────

    def _qtext_code_container_style(self) -> str:
        """构建 QTextDocument 代码块 <pre> 容器的 inline style（当前主题色值）。

        QTextDocument 的 class 选择器支持有限，代码块容器直接用
        inline style，与 _build_container 的 container_style 参数配套。
        """
        bg = v2_token(self._theme_engine, "md_preview_code_block_bg", "#EDF3FA")
        border = v2_token(self._theme_engine, "border_muted", "#D8DEE9")
        fg = v2_token(self._theme_engine, "text_primary", "#212121")
        return (
            f"background-color:{bg};border:1px solid {border};padding:10px;"
            f"color:{fg};font-family:Consolas,'Courier New',monospace;"
            f"font-size:14px;line-height:1.55;"
        )

    def _process_code_blocks(self, html: str) -> str:
        """替换所有 <pre><code> 块：语法高亮 + 容器 + 嵌入位置标记"""
        self._code_blocks = []
        container_style = self._qtext_code_container_style()

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
            return self._build_container(idx, highlighted, source_line, container_style)

        return _CODEBLOCK_RE.sub(_replace, html)

    def _process_code_blocks_async(self, html: str) -> str:
        """异步版本的代码块处理：先渲染占位符，再异步替换高亮结果"""
        self._code_blocks = []
        container_style = self._qtext_code_container_style()

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
            return self._build_container(idx, escaped, source_line, container_style)

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
        container_style = self._qtext_code_container_style()

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
                return self._build_container(idx, highlighted_blocks[idx], source_line, container_style)
            return self._build_container(idx, html_module.escape(raw), source_line, container_style)

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
    def _build_container(
        index: int,
        code_html: str,
        source_line: Optional[int] = None,
        container_style: str = "",
    ) -> str:
        """构建代码块 HTML 容器：背景容器 + 首尾不可见标记 + 逐行锚点。

        标记用于 PreviewBrowser 在 QTextDocument 中定位代码块的
        垂直范围，从而在正确位置显示浮动复制按钮（Qt 原生浮层，
        无 HTML button——QTextDocument 不认识 button 标签）。

        container_style：<pre> 容器的 inline style（QTextDocument CSS 子集），
        由调用方按当前主题构建，默认空字符串。
        """
        sm = f"{_MK_S1}{index}{_MK_S2}"
        em = f"{_MK_E1}{index}{_MK_E2}"
        line_attr = ""
        if source_line is not None:
            line_attr = f' data-source-line="{source_line}"'

        code_html = MarkdownPreviewWidget._wrap_code_lines_with_source_map(
            code_html, source_line
        )

        style_attr = f' style="{container_style}"' if container_style else ""
        return (
            f'<div class="code-container src-line"{line_attr}>'
            f'<span class="code-marker" style="font-size:1px;color:transparent;">{sm}</span>'
            f'<pre class="code-pre"{style_attr}><code class="code-block">{code_html}</code></pre>'
            f'<span class="code-marker" style="font-size:1px;color:transparent;">{em}</span>'
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

        # 锚点表定位：源码行 → 文档像素 y（锚点不足时回退到整体比例）
        self._suppress_preview_sync = True
        try:
            self.preview.scroll_to_source_line(frac_line, at_top, at_bottom)
            if not self.preview.line_anchors() and total_lines > 0:
                line_ratio = min(frac_line / total_lines, 1.0)
                bar = self.preview.verticalScrollBar()
                if bar is not None:
                    bar.setValue(int(line_ratio * bar.maximum()))
        except Exception:
            get_logger(__name__).debug("预览滚动同步失败", exc_info=True)
        finally:
            # setValue 同步触发的 valueChanged 已被抑制，下一轮事件循环再解除
            QTimer.singleShot(0, self._clear_preview_suppress)

    def _clear_preview_suppress(self):
        self._suppress_preview_sync = False

    def _on_preview_scroll(self, value):
        """预览滚动 → 反向同步编辑器（方案 A：原 JS 回传桥由锚点表替代）。"""
        if not self._preview_visible or self._suppress_preview_sync:
            return
        frac_line = self.preview.source_line_at_viewport_top()
        if frac_line is None:
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
        self.preview.setVisible(self._preview_visible)
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
