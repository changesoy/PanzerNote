# -*- coding: utf-8 -*-
"""
编辑器组件
基于QPlainTextEdit的文本编辑器
支持Pygments语法高亮、自动缩进、行宽模式切换、代码缩略图（Minimap）

v1.5.4 改动：
  - 修复 toggle_minimap / set_minimap_visible 传 None 给 resizeEvent 导致卡死的严重 Bug
  - 新增 auto_minimap 支持：仅代码文件自动显示缩略图（.txt / .md 不显示）

v1.6 改动：
  - 新增括号/引号自动配对功能（可在设置中开关）
  - 新增行操作快捷键：Ctrl+Shift+K 删除行、Alt+Up/Down 移动行、Ctrl+Shift+D 复制行
  - 新增大小写转换功能：Ctrl+Shift+U 切换大小写，右键菜单支持转大写/小写/首字母大写
  - 新增转到行功能：goto_line 方法
  - 新增JSON/XML格式化功能：右键菜单"格式化文档"
"""

import os
import json
import xml.dom.minidom as minidom
from contextlib import contextmanager
from typing import Generator, Optional, Set, cast
from PyQt6.QtWidgets import (
    QPlainTextEdit, QWidget, QTextEdit, QVBoxLayout,
    QMenu, QMessageBox, QPlainTextDocumentLayout
)
from PyQt6.QtCore import Qt, QRect, QSize, QTimer, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QTextFormat, QTextCharFormat, QPolygonF,
    QSyntaxHighlighter, QTextDocument, QTextCursor, QKeyEvent, QAction,
    QHideEvent, QFocusEvent,
)

from ..core.config import Config
from ..core.shared_document import SharedDocument
from .syntax_highlighter import get_highlighter_for_file
from .editor_actions import EditorActionsMixin
from .auto_pair_handler import AutoPairHandlerMixin
from .virtual_scroll import LazyHighlightManager
from .extra_selection_manager import ExtraSelectionManager
from .indentation import get_indent_width, get_indent_unit
from .completion import CompletionPopup, CompletionProvider
from .text_stats import count_mixed_words
from .bracket_matcher import find_matching_bracket
from ..utils.perf_probe import measure as _perf_measure
from .completion import CompletionProvider, CompletionPopup
from .folding import FoldingManager
from ..themes.theme_aware_mixin import ThemeAwareMixin


class LineNumberArea(QWidget):
    """行号区域"""

    def __init__(self, editor: 'Editor'):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)

    def mousePressEvent(self, event) -> None:
        """检测折叠标记点击。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.editor._handle_fold_marker_click(event.pos().y())
            return
        super().mousePressEvent(event)


class Editor(ThemeAwareMixin, AutoPairHandlerMixin, EditorActionsMixin, QPlainTextEdit):
    """文本编辑器"""

    word_count_recomputed = pyqtSignal()
    # 3.5.8（批次 5）：有效折叠管理器的状态变化转发信号（attach 共享 Document 后
    # 转发 Document 级 FoldingManager 的 fold_state_changed；独立时转发本地）。
    # MarkdownPreviewWidget 与重绘统一监听本信号，避免 attach 前后连接对象漂移。
    fold_state_changed = pyqtSignal()

    # 需要自动增加缩进的行尾字符（按语言）
    INDENT_TRIGGERS = {
        'Python': [':'],
        'C': ['{'], 'C++': ['{'], 'Java': ['{'],
        'JavaScript': ['{'], 'TypeScript': ['{'],
        'CSS': ['{'], 'Go': ['{'], 'Rust': ['{'],
        'Swift': ['{'], 'Kotlin': ['{'],
        'Lua': ['then', 'do', 'function'],
        'Ruby': ['do', 'then'],
    }

    # 需要自动减少缩进的行首字符
    DEDENT_TRIGGERS = {
        'C': ['}'], 'C++': ['}'], 'Java': ['}'],
        'JavaScript': ['}'], 'TypeScript': ['}'],
        'CSS': ['}'], 'Go': ['}'], 'Rust': ['}'],
        'Swift': ['}'], 'Kotlin': ['}'],
    }

    # 不显示缩略图的文件类型
    _NO_MINIMAP_TYPES = {'纯文本', 'Markdown'}

    # 支持折叠的文件类型
    _FOLD_SUPPORTED_TYPES = frozenset({'Markdown', 'Python', 'YAML'})

    # 括号/引号自动配对映射（英文 + 中文）
    AUTO_PAIR_CHARS = {
        # 英文括号
        '(': ')',
        '[': ']',
        '{': '}',
        # 英文引号
        '"': '"',
        "'": "'",
        # 中文括号
        '\uff08': '\uff09',  # （）
        '\u3010': '\u3011',  # 【】
        '\u300c': '\u300d',  # 「」
        '\u300e': '\u300f',  # 『』
        # 中文引号
        '\u201c': '\u201d',  # ""
        '\u2018': '\u2019',  # ''
        # 中文书名号
        '\u300a': '\u300b',  # 《》
        '\u3008': '\u3009',  # 〈〉
    }

    def __init__(self, config: Config, theme_engine, parent=None):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("Editor 必须传入 theme_engine，不允许为 None")
        self.config = config
        self._theme_engine = theme_engine
        self.tab_id: Optional[int] = None
        self._highlighter: Optional[QSyntaxHighlighter] = None
        self._file_type = "纯文本"
        self._filepath_or_ext: str = ""
        self._wrap_mode = "no_wrap"
        self._programmatic_modify = False
        self._is_pasting = False
        self._composing = False  # IME 输入法组字中

        # 自动补全（timer 须在 _init_ui 前创建，因 textChanged 信号会引用它）
        self._completion_timer = QTimer(self)
        self._completion_timer.setSingleShot(True)
        self._completion_timer.setInterval(500)
        self._completion_timer.timeout.connect(self._rebuild_completion_words)

        self._fold_timer = QTimer(self)
        self._fold_timer.setSingleShot(True)
        self._fold_timer.setInterval(300)
        self._fold_timer.timeout.connect(self._refresh_folding)

        self._completion_provider = CompletionProvider()
        self._completion_popup = CompletionPopup(None)  # type: ignore[arg-type]
        self._completion_popup.item_selected.connect(self._apply_completion)

        self._selection_manager = ExtraSelectionManager(self)

        self._init_ui()
        self._init_minimap_attrs()
        self._init_line_numbers()
        self._init_minimap()
        self._lazy_highlight = LazyHighlightManager(self)
        self._local_bookmarks: Set[int] = set()
        # 3.5.8（批次 5）：本地折叠管理器（独立编辑时使用）。attach 共享 Document
        # 后 _folding 属性委托到 Document 级单实例（规格 2.10），本地实例闲置。
        self._local_folding = FoldingManager(cast(QTextDocument, self.document()), parent=self)
        self._local_folding.fold_state_changed.connect(self._forward_fold_state_changed)

        self._cached_word_count: int = 0
        self._word_count_dirty: bool = True
        self._word_count_timer = QTimer(self)
        self._word_count_timer.setSingleShot(True)
        self._word_count_timer.setInterval(800)
        self._word_count_timer.timeout.connect(self._recompute_word_count)
        # 3.5.8 共享 Document：attach 后本 View 使用 Document 级统计/内容
        self._shared_doc: Optional[SharedDocument] = None

        # 自动补全
        self.cursorPositionChanged.connect(self._trigger_completion)

    @property
    def is_programmatic_modify(self) -> bool:
        return self._programmatic_modify

    @contextmanager
    def programmatic_modify(self) -> Generator[None, None, None]:
        self._programmatic_modify = True
        try:
            yield
        finally:
            self._programmatic_modify = False

    def _init_ui(self):
        """初始化UI"""
        # 设置字体
        font_family = self.config.get_editor_setting("font_family", "Microsoft YaHei")
        font_size = self.config.get_editor_setting("font_size", 12)
        font = QFont(font_family, font_size)
        self.setFont(font)

        # 设置Tab宽度（按缩进配置）
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * get_indent_width(self.config))

        # 设置换行模式
        wrap_mode = self.config.get_editor_setting("wrap_mode", "no_wrap")
        self.set_wrap_mode(wrap_mode)

        # 设置样式（由 _apply_theme_colors 管理）
        self._init_theme(self._theme_engine)

        # 高亮当前行
        if self.config.get_editor_setting("highlight_current_line", True):
            self.cursorPositionChanged.connect(self._highlight_current_line)
            self._highlight_current_line()

        # 括号匹配高亮
        self.cursorPositionChanged.connect(self._highlight_bracket_match)

        # 文本变更时触发补全词集刷新（500ms 防抖）
        self.textChanged.connect(self._completion_timer.start)
        self.textChanged.connect(self._fold_timer.start)

        # 禁用默认右键菜单，使用自定义的
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _apply_theme_colors(self, colors):
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                border: none;
                background-color: {colors.editor_bg};
                selection-background-color: {colors.primary_light};
                color: {colors.text_primary};
            }}
        """)
        # 更新高亮器的主题（3.5.8：两种高亮器均实现 set_dark_mode——Pygments
        # 走 set_dark_mode 重建 formats，不经过 set_file_type，避免摘除共享高亮）
        if self._highlighter and self._filepath_or_ext:
            is_dark = self._theme_engine.get_active_theme().is_dark
            if hasattr(self._highlighter, 'set_dark_mode'):
                self._highlighter.set_dark_mode(is_dark)
            else:
                # 旧式高亮器回退：重新设置文件类型以切换主题
                self.set_file_type(self._filepath_or_ext)
        self._highlight_current_line()

        # 更新无父顶层补全弹窗的主题
        if hasattr(self, "_completion_popup") and self._completion_popup is not None:
            self._completion_popup.apply_theme_colors(colors)
            font_family = self.config.get_editor_setting("font_family", "Microsoft YaHei")
            font_size = self.config.get_editor_setting("font_size", 12)
            self._completion_popup.apply_font(font_family, font_size)

    def _show_context_menu(self, position):
        """显示中文右键菜单"""
        menu = QMenu(self)
        doc = self.document()
        assert doc is not None

        undo_action = QAction("撤销", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.setEnabled(doc.isUndoAvailable())
        undo_action.triggered.connect(self.undo)
        menu.addAction(undo_action)

        redo_action = QAction("重做", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.setEnabled(doc.isRedoAvailable())
        redo_action.triggered.connect(self.redo)
        menu.addAction(redo_action)

        menu.addSeparator()

        cut_action = QAction("剪切", self)
        cut_action.setShortcut("Ctrl+X")
        cut_action.setEnabled(self.textCursor().hasSelection())
        cut_action.triggered.connect(self.cut)
        menu.addAction(cut_action)

        copy_action = QAction("复制", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.setEnabled(self.textCursor().hasSelection())
        copy_action.triggered.connect(self.copy)
        menu.addAction(copy_action)

        paste_action = QAction("粘贴", self)
        paste_action.setShortcut("Ctrl+V")
        paste_action.triggered.connect(self.paste)
        menu.addAction(paste_action)

        delete_action = QAction("删除", self)
        delete_action.setEnabled(self.textCursor().hasSelection())
        delete_action.triggered.connect(lambda: self.textCursor().removeSelectedText())
        menu.addAction(delete_action)

        menu.addSeparator()

        select_all_action = QAction("全选", self)
        select_all_action.setShortcut("Ctrl+A")
        select_all_action.triggered.connect(self.selectAll)
        menu.addAction(select_all_action)

        menu.addSeparator()

        # 大小写转换子菜单
        case_menu = menu.addMenu("大小写转换")
        if case_menu:
            upper_action = QAction("转为大写", self)
            upper_action.setEnabled(self.textCursor().hasSelection())
            upper_action.triggered.connect(self.to_uppercase)
            case_menu.addAction(upper_action)

            lower_action = QAction("转为小写", self)
            lower_action.setEnabled(self.textCursor().hasSelection())
            lower_action.triggered.connect(self.to_lowercase)
            case_menu.addAction(lower_action)

            title_action = QAction("首字母大写", self)
            title_action.setEnabled(self.textCursor().hasSelection())
            title_action.triggered.connect(self.to_titlecase)
            case_menu.addAction(title_action)

            toggle_case_action = QAction("切换大小写", self)
            toggle_case_action.setShortcut("Ctrl+Shift+U")
            toggle_case_action.setEnabled(self.textCursor().hasSelection())
            toggle_case_action.triggered.connect(self.toggle_case)
            case_menu.addAction(toggle_case_action)

        # JSON/XML格式化（仅对应文件类型显示）
        if self._file_type in ('JSON', 'XML', 'HTML', 'YAML', 'TOML', 'CSS'):
            menu.addSeparator()
            format_action = QAction("格式化文档", self)
            format_action.triggered.connect(self.format_document)
            menu.addAction(format_action)

        menu.exec(self.mapToGlobal(position))

    # ═══════════════════ 行号 ═══════════════════

    def _init_line_numbers(self):
        """初始化行号显示"""
        self.line_number_area = LineNumberArea(self)

        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)

        self._update_line_number_area_width(0)

        show_line_numbers = self.config.get_editor_setting("show_line_numbers", True)
        self.line_number_area.setVisible(show_line_numbers)

    def line_number_area_width(self) -> int:
        """计算行号区域宽度（含折叠标记列）"""
        if not self.line_number_area.isVisible():
            return 0

        digits = 1
        max_num = max(1, self.blockCount())
        while max_num >= 10:
            max_num //= 10
            digits += 1

        space = 10 + self.fontMetrics().horizontalAdvance('9') * digits
        # 为折叠标记预留空间（支持折叠的文件类型）
        if self._file_type in self._FOLD_SUPPORTED_TYPES:
            space += self._folding.fold_marker_width
        return int(space)

    def _update_line_number_area_width(self, _):
        """更新行号区域宽度"""
        right_margin = self._minimap_width() if self._minimap_visible else 0
        self.setViewportMargins(self.line_number_area_width(), 0, right_margin, 0)

    def _update_line_number_area(self, rect, dy):
        """更新行号区域"""
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())

        viewport = self.viewport()
        if viewport is not None and rect.contains(viewport.rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event):
        """调整大小事件"""
        super().resizeEvent(event)
        self._update_child_geometries()

    def _update_child_geometries(self):
        """更新行号区域和缩略图的几何位置（从 resizeEvent 中提取，可安全独立调用）"""
        cr = self.contentsRect()

        # 行号区域
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

        # 缩略图
        if self._minimap_visible and self.minimap is not None:
            mw = self._minimap_width()
            self.minimap.setGeometry(
                cr.right() - mw + 1, cr.top(),
                mw, cr.height()
            )

    def showEvent(self, event):
        """显示事件：重新计算行号区域宽度，修复首次显示时文字被遮挡"""
        super().showEvent(event)
        self._update_line_number_area_width(0)

    def line_number_area_paint_event(self, event):
        """绘制行号 + 折叠标记"""
        painter = QPainter(self.line_number_area)
        bg_color = self._theme_engine.get_active_theme().colors.sidebar_bg
        text_color = self._theme_engine.get_active_theme().colors.editor_line_number
        bookmark_bg_color = self._theme_engine.get_active_theme().colors.editor_bookmark_bg
        bookmark_fg_color = self._theme_engine.get_active_theme().colors.editor_bookmark_fg
        painter.fillRect(event.rect(), QColor(bg_color))

        supports_fold = self._file_type in self._FOLD_SUPPORTED_TYPES
        marker_width = self._folding.fold_marker_width if supports_fold else 0
        area_width = self.line_number_area.width()

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                # 书签背景
                if block_number in self._bookmarks:
                    painter.fillRect(
                        0, top,
                        area_width,
                        self.fontMetrics().height(),
                        QColor(bookmark_bg_color)
                    )
                    painter.setPen(QColor(bookmark_fg_color))
                else:
                    painter.setPen(QColor(text_color))

                # 行号右对齐（留出折叠标记空间）
                number_width = area_width - marker_width - 5
                painter.drawText(
                    0, top,
                    number_width,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, str(block_number + 1)
                )

                # 折叠标记 — 手绘三角（大小一致，不受行高影响）
                if supports_fold and self._folding.is_foldable(block_number):
                    collapsed = (block_number + 1) in self._folding._collapsed_blocks
                    fold_color_expanded_name = self._theme_engine.get_active_theme().colors.editor_fold_marker
                    fold_color_collapsed_name = self._theme_engine.get_active_theme().colors.editor_fold_marker_collapsed
                    painter.setBrush(QColor(fold_color_collapsed_name if collapsed else fold_color_expanded_name))
                    painter.setPen(Qt.PenStyle.NoPen)
                    tri_size = 8  # 三角边长 px
                    cx = float(area_width - marker_width // 2 - 2)  # 三角中心 x
                    cy = float(top + self.fontMetrics().height() // 2)  # 三角中心 y
                    if collapsed:
                        # 向右三角 ▶
                        points = QPolygonF([
                            QPointF(cx - tri_size // 2, cy - tri_size // 2),
                            QPointF(cx - tri_size // 2, cy + tri_size // 2),
                            QPointF(cx + tri_size // 2, cy),
                        ])
                    else:
                        # 向下三角 ▼
                        points = QPolygonF([
                            QPointF(cx - tri_size // 2, cy - tri_size // 2),
                            QPointF(cx + tri_size // 2, cy - tri_size // 2),
                            QPointF(cx, cy + tri_size // 2),
                        ])
                    painter.drawPolygon(points)
                    painter.setPen(Qt.PenStyle.SolidLine)
                    painter.setBrush(Qt.BrushStyle.NoBrush)

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def _highlight_current_line(self):
        """高亮当前行"""
        if self.isReadOnly():
            self._selection_manager.clear_layer("current_line")
        else:
            selection = QTextEdit.ExtraSelection()
            line_color_name = self._theme_engine.get_active_theme().colors.editor_current_line
            line_color = QColor(line_color_name)
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            self._selection_manager.set_layer("current_line", [selection])
        self._selection_manager.refresh()

    def _highlight_bracket_match(self):
        """高亮光标位置的配对括号"""
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()

        self._selection_manager.clear_layer("bracket_match")

        bracket_pos, match_pos = find_matching_bracket(text, pos)
        if bracket_pos is None:
            self._selection_manager.refresh()
            return

        colors = self._theme_engine.get_active_theme().colors
        match_bg = colors.editor_bracket_match_bg
        match_fg = colors.editor_bracket_match_fg
        unmatched = colors.editor_bracket_unmatched

        selections: list[QTextEdit.ExtraSelection] = []

        if match_pos is None:
            # 未匹配：仅高亮 bracket 本身，用红色下划线
            fmt = QTextCharFormat()
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
            fmt.setUnderlineColor(QColor(unmatched))
            sel = QTextEdit.ExtraSelection()
            sel.format = fmt
            sel.cursor = QTextCursor(cursor)
            sel.cursor.setPosition(bracket_pos)
            sel.cursor.setPosition(bracket_pos + 1, QTextCursor.MoveMode.KeepAnchor)
            selections.append(sel)
            self._selection_manager.set_layer("bracket_match", selections)
            self._selection_manager.refresh()
            return

        # 已匹配 → 同时高亮 bracket 本身与配对括号
        _bracket_pos: int = bracket_pos
        _match_pos: int = match_pos

        bracket_sel = QTextEdit.ExtraSelection()
        bracket_fmt = QTextCharFormat()
        bracket_fmt.setBackground(QColor(match_bg))
        bracket_sel.format = bracket_fmt
        bracket_sel.cursor = QTextCursor(cursor)
        bracket_sel.cursor.setPosition(_bracket_pos)
        bracket_sel.cursor.setPosition(_bracket_pos + 1, QTextCursor.MoveMode.KeepAnchor)
        selections.append(bracket_sel)

        match_sel = QTextEdit.ExtraSelection()
        match_fmt = QTextCharFormat()
        match_fmt.setBackground(QColor(match_bg))
        match_fmt.setForeground(QColor(match_fg))
        match_sel.format = match_fmt
        match_sel.cursor = QTextCursor(cursor)
        match_sel.cursor.setPosition(_match_pos)
        match_sel.cursor.setPosition(_match_pos + 1, QTextCursor.MoveMode.KeepAnchor)
        selections.append(match_sel)

        self._selection_manager.set_layer("bracket_match", selections)
        self._selection_manager.refresh()

    # ═══════════════════ 缩略图（Minimap） ═══════════════════

    def _init_minimap_attrs(self):
        """预初始化缩略图属性（在行号初始化之前调用）"""
        self._minimap_visible = self.config.get_editor_setting("show_minimap", True)
        self.minimap = None

    def _init_minimap(self):
        """初始化代码缩略图"""
        from .minimap import MinimapWidget

        self.minimap = MinimapWidget(self, theme_engine=self._theme_engine)
        self.minimap.setVisible(self._minimap_visible)
        # 初始布局
        self._update_line_number_area_width(0)

    def _minimap_width(self) -> int:
        """缩略图宽度"""
        if self.minimap:
            return int(self.minimap.MINIMAP_WIDTH)
        return 80

    def toggle_minimap(self):
        """切换缩略图显示/隐藏

        v1.5.4: 不再调用 self.resizeEvent(None)，改用 _update_child_geometries()
        修复传 None 给 super().resizeEvent() 导致程序卡死 / 崩溃的 Bug。
        """
        self._minimap_visible = not self._minimap_visible
        if self.minimap:
            self.minimap.setVisible(self._minimap_visible)
        self._update_line_number_area_width(0)
        self._update_child_geometries()

    def set_minimap_visible(self, visible: bool):
        """设置缩略图可见性

        v1.5.4: 同上修复。
        """
        self._minimap_visible = visible
        if self.minimap:
            self.minimap.setVisible(visible)
        self._update_line_number_area_width(0)
        self._update_child_geometries()

    def apply_auto_minimap(self):
        """根据 auto_minimap 设置和当前文件类型自动决定缩略图是否显示

        规则：
        - auto_minimap 关闭时：使用全局 show_minimap 设置
        - auto_minimap 开启时：仅代码文件（非 .txt / .md）显示缩略图
        """
        auto = self.config.get_editor_setting("auto_minimap", False)
        if auto:
            should_show = self._file_type not in self._NO_MINIMAP_TYPES
        else:
            should_show = self.config.get_editor_setting("show_minimap", True)
        self.set_minimap_visible(should_show)

    # ═══════════════════ 语法高亮 ═══════════════════

    def set_file_type(self, filepath_or_ext: str):
        """根据文件类型设置语法高亮

        3.5.8（R1 收敛）：共享 Document 只建一次 highlighter——同一 qdocument
        若有多个 View，后续 View 直接复用（避免多个 QSyntaxHighlighter 反复
        重排同一 document，高亮重叠/性能浪费）。
        """
        if self._highlighter:
            shared = self._shared_doc
            # 3.5.8（批次 5 修复）：共享高亮属于 Document（R1 收敛），不能被摘除——
            # 主题刷新走 set_dark_mode 不经过这里；仅本地/独立高亮才摘除重建，
            # 否则会把 Document 级高亮从共享文档上摘掉导致渲染永久失效。
            if shared is None or self._highlighter is not getattr(
                shared, "_highlighter", None
            ):
                self._highlighter.setDocument(None)
                self._highlighter = None

        self._filepath_or_ext = filepath_or_ext
        doc = self.document()
        assert doc is not None
        shared = self._shared_doc
        if shared is not None:
            existing = shared._highlighter
            if existing is not None:
                self._highlighter = cast(QSyntaxHighlighter, existing)
                self._file_type = shared._highlighter_file_type
                self._lazy_highlight.set_highlighter(self._highlighter)
                self.apply_auto_minimap()
                return
        is_dark = self._theme_engine.get_active_theme().is_dark
        self._highlighter, self._file_type = get_highlighter_for_file(
            doc, filepath_or_ext, theme_engine=self._theme_engine, is_dark=is_dark
        )
        if shared is not None:
            shared._highlighter = self._highlighter
            shared._highlighter_file_type = self._file_type

        self._lazy_highlight.set_highlighter(self._highlighter)
        self.apply_auto_minimap()

    # ═══════════════════ 行宽模式 ═══════════════════

    def set_wrap_mode(self, mode: str):
        """设置行宽模式"""
        self._wrap_mode = mode
        if mode == "limit_width":
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        else:
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def get_wrap_mode(self) -> str:
        return self._wrap_mode

    # ═══════════════════ 键盘事件处理 ═══════════════════

    def keyPressEvent(self, event: QKeyEvent | None):
        """键盘事件 - 自动缩进、自动配对、IME 等编辑器行为。

        编辑器操作快捷键（删除行/复制行/移行/转大小写）由 ShortcutManager
        统一管理，可在命令面板搜索、在快捷键面板自定义。
        """
        if event is None:
            return

        # 自动补全弹框键盘导航
        if self._completion_popup.visible:
            if self._completion_popup.key_press_event(event):
                return

        modifiers = event.modifiers()
        key = event.key()

        # Backspace: 删除成对的括号/引号
        if key == Qt.Key.Key_Backspace and not modifiers:
            if self.config.get_editor_setting("auto_pair_brackets", True):
                cursor = self.textCursor()
                if not cursor.hasSelection():
                    pos = cursor.position()
                    char_before = self._doc_char_at(pos - 1)
                    char_after = self._doc_char_at(pos)
                    if char_before in self.AUTO_PAIR_CHARS and self.AUTO_PAIR_CHARS[char_before] == char_after:
                        cursor.deleteChar()
                        cursor.deletePreviousChar()
                        return
            # 不满足条件时，交给默认处理
            super().keyPressEvent(event)
            return

        # 回车键: 自动缩进
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._handle_enter()
            return

        # Tab键: 插入缩进
        if key == Qt.Key.Key_Tab and not modifiers:
            cursor = self.textCursor()
            if cursor.hasSelection():
                self._indent_selection(cursor, indent=True)
            else:
                cursor.insertText(get_indent_unit(self.config))
            return

        # Shift+Tab: 减少缩进
        if key == Qt.Key.Key_Backtab:
            cursor = self.textCursor()
            self._indent_selection(cursor, indent=False)
            return

        # 输入 } 时自动减少缩进（C系语言）
        if event.text() == '}' and self._file_type in self.DEDENT_TRIGGERS:
            self._handle_closing_brace()
            return

        # ═══════════ 括号/引号智能处理 ═══════════
        if self._handle_auto_pair_keypress(event):
            return

        super().keyPressEvent(event)

    def hideEvent(self, event: QHideEvent | None) -> None:
        """编辑器隐藏时隐藏补全弹窗。"""
        self._completion_popup.hide()
        super().hideEvent(event)

    def focusOutEvent(self, event: QFocusEvent | None) -> None:
        """编辑器失焦时隐藏补全弹窗。"""
        self._completion_popup.hide()
        super().focusOutEvent(event)

    def inputMethodEvent(self, event):
        """IME 输入事件：修复中文输入法提交字符时的自动配对

        说明：
        - 英文键盘直接输入通常会走 keyPressEvent
        - 中文输入法（含中文标点）往往通过 inputMethodEvent 提交 commitString
        """
        # 跟踪 IME 组字状态
        preedit = event.preeditString()
        self._composing = bool(preedit)

        if self._handle_auto_pair_ime(event):
            return None

        super().inputMethodEvent(event)
        return None

    def insertFromMimeData(self, source):
        self._is_pasting = True
        try:
            super().insertFromMimeData(source)
        finally:
            self._is_pasting = False

    # === 拖放：本地文件 URL 放行给窗口级打开（3.5.7） ===
    #
    # QPlainTextEdit 默认接受 text/uri-list 拖放（把文件内容/路径插入为文本），
    # 会吞掉从文件树/资源管理器拖入的文件，导致「拖文件到编辑区打开」失效。
    # 仅拦截"本地文件"URL 拖放并 event.ignore() 冒泡给 MainWindow 打开文件；
    # 文本/纯链接拖放（如浏览器拖 URL 粘贴）保留默认行为。

    def _has_local_file_urls(self, mime) -> bool:
        if not mime.hasUrls():
            return False
        return any(url.isLocalFile() for url in mime.urls())

    def dragEnterEvent(self, event):
        if self._has_local_file_urls(event.mimeData()):
            event.ignore()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._has_local_file_urls(event.mimeData()):
            event.ignore()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        if self._has_local_file_urls(event.mimeData()):
            event.ignore()
            return
        super().dropEvent(event)

    def _handle_enter(self):
        """处理回车键 - 自动缩进、Python 关键词 dedent"""
        cursor = self.textCursor()
        block = cursor.block()
        text = block.text()

        # 获取当前行的前导空白
        indent = ""
        for char in text:
            if char in (' ', '\t'):
                indent += char
            else:
                break

        # 检查是否需要增加缩进
        stripped = text.rstrip()
        extra_indent = ""

        triggers = self.INDENT_TRIGGERS.get(self._file_type, [])
        for trigger in triggers:
            if stripped.endswith(trigger):
                extra_indent = get_indent_unit(self.config)
                break

        # Python 关键词触发 dedent（return / pass / break / continue / raise）
        # 条件：Python 文件 && 没有额外缩进触发（如行尾有冒号）
        if self._file_type == 'Python' and not extra_indent:
            content = stripped.lstrip()
            if content.split(maxsplit=1)[0] in ('return', 'pass', 'break', 'continue', 'raise'):
                indent_unit = get_indent_unit(self.config)
                if len(indent) >= len(indent_unit):
                    indent = indent[:len(indent) - len(indent_unit)]

        cursor.beginEditBlock()
        cursor.insertBlock()
        cursor.insertText(indent + extra_indent)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def _handle_closing_brace(self):
        """处理输入 } 时自动减少缩进"""
        cursor = self.textCursor()
        block = cursor.block()
        text = block.text()

        if text.strip() == '':
            indent_unit = get_indent_unit(self.config)
            if text.startswith(indent_unit):
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.MoveAnchor)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                new_text = text[len(indent_unit):] + '}'
                cursor.insertText(new_text)
                self.setTextCursor(cursor)
                return

        cursor.insertText('}')
        self.setTextCursor(cursor)

    def _indent_selection(self, cursor, indent: bool = True):
        """缩进/反缩进选中的行"""
        indent_unit = get_indent_unit(self.config)

        if not cursor.hasSelection():
            block = cursor.block()
            text = block.text()

            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.MoveAnchor)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)

            if indent:
                cursor.insertText(indent_unit + text)
            else:
                if text.startswith(indent_unit):
                    cursor.insertText(text[len(indent_unit):])
                elif text.startswith("\t"):
                    cursor.insertText(text[1:])
            return

        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        cursor.setPosition(start)
        start_block = cursor.blockNumber()
        cursor.setPosition(end)
        end_block = cursor.blockNumber()

        cursor.beginEditBlock()

        doc = self.document()
        assert doc is not None
        for block_num in range(start_block, end_block + 1):
            block = doc.findBlockByNumber(block_num)
            cursor.setPosition(block.position())

            if indent:
                cursor.insertText(indent_unit)
            else:
                text = block.text()
                if text.startswith(indent_unit):
                    cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, len(indent_unit))
                    cursor.removeSelectedText()
                elif text.startswith("\t"):
                    cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
                    cursor.removeSelectedText()

        cursor.endEditBlock()

    # ═══════════════════ 动态设置 ═══════════════════

    def set_show_line_numbers(self, show: bool):
        """动态切换行号显示"""
        self.line_number_area.setVisible(show)
        self._update_line_number_area_width(0)
        self._update_child_geometries()

    def set_highlight_current_line(self, enabled: bool):
        """动态切换高亮当前行"""
        try:
            self.cursorPositionChanged.disconnect(self._highlight_current_line)
        except TypeError:
            pass

        if enabled:
            self.cursorPositionChanged.connect(self._highlight_current_line)
            self._highlight_current_line()
        else:
            self._selection_manager.clear_layer("current_line")
            self._selection_manager.refresh()

    def set_editor_font(self, family: str, size: int):
        """动态设置编辑器字体和大小"""
        font = QFont(family, size)
        self.setFont(font)
        # 更新 Tab 宽度
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * get_indent_width(self.config))
        # 更新行号区域宽度（字体变化后数字宽度可能不同）
        self._update_line_number_area_width(0)
        self._update_child_geometries()

    # ═══════════════════ 辅助方法 ═══════════════════
    def get_char_count(self) -> int:
        return len(self.toPlainText())

    def get_fast_char_count(self) -> int:
        doc = self.document()
        if doc is None:
            return 0
        return int(max(0, doc.characterCount() - 1))

    def get_word_count(self) -> int:
        shared = self._shared_doc
        if shared is not None:
            return shared.word_count  # Document 级单一统计（共享后只算一次）
        return count_mixed_words(self.toPlainText())

    def get_debounced_word_count(self) -> int:
        if self._word_count_dirty:
            self._word_count_timer.start(800)
        return self._cached_word_count

    def invalidate_word_count(self):
        self._word_count_dirty = True
        self._word_count_timer.start(800)

    def _recompute_word_count(self):
        shared = self._shared_doc
        if shared is not None:
            self._cached_word_count = shared.word_count
        else:
            self._cached_word_count = count_mixed_words(self.toPlainText())
        self._word_count_dirty = False
        self.word_count_recomputed.emit()

    # ═══════════════ 3.5.8 共享 Document attach/detach ═══════════════

    @property
    def shared_doc(self) -> Optional[SharedDocument]:
        """当前 attach 的共享 Document（未 attach 时为 None）。"""
        return self._shared_doc

    def attach_shared_document(self, shared_doc: SharedDocument) -> None:
        """attach 外部共享 QTextDocument（3.5.8）。

        Editor 只 attach，不取得所有权（SharedDocument 拥有 qdocument）；
        注册 Document 级字数统计函数（只算一次，两个 View 共享缓存）；
        folding 收敛 Document 级：首次 attach 创建 Document 单实例并订阅其信号。
        """
        self._shared_doc = shared_doc
        self.setDocument(shared_doc.qdocument)
        if getattr(shared_doc, '_word_count_fn', None) is None:
            shared_doc.set_word_count_fn(count_mixed_words)
        if getattr(shared_doc, "_folding", None) is None:
            shared_doc._folding = FoldingManager(
                shared_doc.qdocument, parent=shared_doc
            )
        shared_folding = cast(FoldingManager, shared_doc._folding)
        try:
            shared_folding.fold_state_changed.connect(self._forward_fold_state_changed)
        except (TypeError, RuntimeError):
            pass
        try:
            shared_doc.bookmarksChanged.connect(self._repaint_bookmarks)
        except (TypeError, RuntimeError):
            pass
        self.invalidate_word_count()

    def detach_shared_document(self) -> None:
        """detach：恢复独立编辑器 document。

        新建的默认 QTextDocument 必须显式设置 QPlainTextDocumentLayout，
        否则 setDocument 静默不绑定（规格 2.3 契约：layout 不兼容会被 Qt 拒绝）。
        未 attach 过时直接返回——否则会新建空文档清掉独立编辑中的内容。
        """
        if self._shared_doc is None:
            return
        shared_hl = getattr(self._shared_doc, "_highlighter", None)
        shared_folding = cast(FoldingManager, self._shared_doc._folding)
        try:
            shared_folding.fold_state_changed.disconnect(self._forward_fold_state_changed)
        except (TypeError, RuntimeError):
            pass
        try:
            self._shared_doc.bookmarksChanged.disconnect(self._repaint_bookmarks)
        except (TypeError, RuntimeError):
            pass
        self._shared_doc = None
        new_doc = QTextDocument(self)
        new_doc.setDocumentLayout(QPlainTextDocumentLayout(new_doc))
        self.setDocument(new_doc)
        # 3.5.8（批次 5 修复）：detach 后 Editor 用全新 document，原共享高亮仍
        # 挂在旧 Document 上——必须重建本地高亮，否则旧 Document 销毁后
        # self._highlighter 悬垂（切主题时报 PygmentsHighlighter has been deleted）。
        if self._highlighter is not None and self._highlighter is shared_hl:
            self._highlighter = None
            if self._filepath_or_ext:
                self.set_file_type(self._filepath_or_ext)
        self._local_folding = FoldingManager(new_doc, parent=self)
        self._local_folding.fold_state_changed.connect(self._forward_fold_state_changed)
        self.invalidate_word_count()  # 清掉共享 Document 的缓存词数，下次按独立内容重算

    def get_current_line(self) -> int:
        return int(self.textCursor().blockNumber() + 1)

    def get_current_column(self) -> int:
        return int(self.textCursor().columnNumber() + 1)

    def get_file_type(self) -> str:
        return self._file_type

    @property
    def selection_manager(self) -> ExtraSelectionManager:
        return self._selection_manager

    def load_content(self, content: str):
        """加载文本内容，大文件自动启用延迟高亮"""
        # 停止补全相关状态，避免加载过程中弹窗
        self._completion_timer.stop()
        self._completion_popup.hide()

        with self.programmatic_modify():
            # E1 profiling：大文件 lazy 加载耗时（≥LARGE_FILE_THRESHOLD 行才走此路径）
            if not _perf_measure(
                "editor.load_content.lazy",
                lambda: self._lazy_highlight.load_content(content),
            ):
                self.setPlainText(content)

        # 重建补全词集
        self._completion_provider.rebuild_from_text(self.toPlainText())
        # 重建折叠区间
        self._refresh_folding()
        # 再次确保补全弹窗已隐藏
        self._completion_popup.hide()

    def goto_line(self, line: int):
        """跳转到指定行（如果行在折叠区域内则自动展开）"""
        self._folding.ensure_visible(line)
        doc = self.document()
        assert doc is not None
        block = doc.findBlockByNumber(line - 1)
        if block.isValid():
            cursor = self.textCursor()
            cursor.setPosition(block.position())
            self.setTextCursor(cursor)
            self.centerCursor()
            if self._lazy_highlight.is_active():
                self._lazy_highlight.goto_line(line)

    @property
    def _bookmarks(self) -> Set[int]:
        """有效书签集合：attach 共享 Document 时用 Document 级书签，否则本地集合。

        3.5.8（批次 5，规格 2.12）：书签标记文档位置 → Document 级，两个 View
        看同一份；A 切换书签经 bookmarksChanged 信号驱动 B 重绘行号区。
        """
        shared = self._shared_doc
        if shared is not None:
            return shared.bookmarks
        return self._local_bookmarks

    def _repaint_bookmarks(self) -> None:
        """书签集合变化后刷新行号区（含书签图标）。"""
        self.line_number_area.update()

    def toggle_bookmark(self):
        line = self.textCursor().blockNumber()
        bookmarks = self._bookmarks
        if line in bookmarks:
            bookmarks.discard(line)
        else:
            bookmarks.add(line)
        if self._shared_doc is not None:
            self._shared_doc.bookmarksChanged.emit()
        else:
            self._repaint_bookmarks()

    def next_bookmark(self):
        current = self.textCursor().blockNumber()
        bookmarks = sorted(self._bookmarks)
        for b in bookmarks:
            if b > current:
                self.goto_line(b + 1)
                return
        if bookmarks:
            self.goto_line(bookmarks[0] + 1)

    def prev_bookmark(self):
        current = self.textCursor().blockNumber()
        bookmarks = sorted(self._bookmarks, reverse=True)
        for b in bookmarks:
            if b < current:
                self.goto_line(b + 1)
                return
        if bookmarks:
            self.goto_line(bookmarks[-1] + 1)

    def get_bookmarks(self) -> Set[int]:
        return self._bookmarks.copy()

    def set_bookmarks(self, bookmarks: Set[int]):
        shared = self._shared_doc
        if shared is not None:
            shared._bookmarks.clear()
            shared._bookmarks.update(bookmarks)
            shared.bookmarksChanged.emit()
        else:
            self._local_bookmarks = bookmarks.copy()
            self._repaint_bookmarks()

    # === 折叠 ===

    @property
    def _folding(self) -> FoldingManager:
        """有效折叠管理器：attach 共享 Document 时用 Document 级单实例，否则本地实例。

        3.5.8（批次 5，规格 2.10）：折叠可见性落在共享 QTextDocument 的 block 上，
        同 Document 的所有 View 必须共享同一 FoldingManager，A 折叠 B 同步。
        """
        shared = self._shared_doc
        if shared is not None:
            shared_folding = getattr(shared, "_folding", None)
            if shared_folding is not None:
                return cast(FoldingManager, shared_folding)
        return self._local_folding

    def _forward_fold_state_changed(self) -> None:
        """有效折叠管理器状态变化 → 本 View 重绘 + 转发给监听方（预览等）。"""
        self.fold_state_changed.emit()
        viewport = self.viewport()
        if viewport is not None:
            viewport.update()
        if hasattr(self, "line_number_area"):
            self.line_number_area.update()

    def _handle_fold_marker_click(self, y: int) -> None:
        """检测点击的折叠标记并切换折叠。"""
        if self._file_type not in self._FOLD_SUPPORTED_TYPES:
            return

        area_width = self.line_number_area.width()
        marker_width = self._folding.fold_marker_width

        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid():
            if block.isVisible() and top <= y <= bottom:
                break
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())

        if block.isValid() and self._folding.is_foldable(block.blockNumber()):
            self._folding.toggle_fold(block.blockNumber())
            self._update_line_number_area_width(0)

    def toggle_fold_all(self) -> None:
        """折叠全部 / 展开全部（toggle）。"""
        if self._file_type not in self._FOLD_SUPPORTED_TYPES:
            return
        self._folding.toggle_fold_all()
        self._update_line_number_area_width(0)

    def _refresh_folding(self) -> None:
        """文本变化后重建折叠区间。"""
        if self._file_type not in self._FOLD_SUPPORTED_TYPES:
            return
        try:
            text = self.toPlainText()
        except (RuntimeError, AttributeError):
            return
        if self._file_type == 'Markdown':
            self._folding.rebuild_from_text(text)
        else:
            indent_size = get_indent_width(self.config)
            self._folding.rebuild_from_indent(text, indent_size)
            if self._file_type == 'Python':
                self._folding.fold_imports(text)

    # === 自动补全 ===

    def _trigger_completion(self) -> None:
        """光标位置改变时触发补全检查。"""
        # 编辑器不可见/无焦点/程序化修改/粘贴/IME 组字中直接隐藏并返回
        if self._programmatic_modify or self._is_pasting or self._composing:
            self._completion_popup.hide()
            return

        if not self.hasFocus() or not self.isVisible():
            self._completion_popup.hide()
            return

        if not self.config.get_editor_setting("enable_completion", False):
            return

        if self._completion_popup.visible:
            self._completion_popup.hide()

        prefix = self._completion_prefix()
        min_chars = self.config.get_editor_setting("completion_min_chars", 2)
        if len(prefix) < min_chars:
            return

        candidates = self._completion_provider.candidates_for_prefix(prefix)
        if not candidates:
            return

        self._completion_popup.set_candidates(candidates)
        # 弹框定位到光标下方
        cr = self.cursorRect()
        pos = self.viewport().mapToGlobal(cr.bottomLeft())  # type: ignore[union-attr]
        self._completion_popup.show_at(pos)

    def _rebuild_completion_words(self) -> None:
        """从文档全文重建补全词集。"""
        if self.config.get_editor_setting("enable_completion", False):
            self._completion_provider.rebuild_from_text(self.toPlainText())

    def _completion_prefix(self) -> str:
        """获取光标前的词语前缀（字母/数字/下划线/中文）。"""
        cursor = self.textCursor()
        block = cursor.block()
        line = block.text()
        col = cursor.positionInBlock()
        line_prefix = line[:col]
        import re
        match = re.search(r'[a-zA-Z0-9_\u4e00-\u9fff]+$', line_prefix)
        return match.group() if match else ''

    def _apply_completion(self, text: str) -> None:
        """用补全候选替换光标前缀。"""
        cursor = self.textCursor()
        prefix = self._completion_prefix()
        suffix = text[len(prefix):]
        cursor.insertText(suffix)

    def set_completion_enabled(self, enabled: bool) -> None:
        """动态开关自动补全。"""
        # 开关在 cursorPositionChanged slot 中读取，无需额外操作
        if not enabled:
            self._completion_popup.hide()

    def hide_completion(self) -> None:
        """隐藏补全弹框。"""
        self._completion_popup.hide()
