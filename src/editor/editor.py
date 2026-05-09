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
from typing import Generator, Set
from PyQt5.QtWidgets import (
    QPlainTextEdit, QWidget, QTextEdit, QVBoxLayout,
    QMenu, QAction, QMessageBox
)
from PyQt5.QtCore import Qt, QRect, QSize
from PyQt5.QtGui import (
    QFont, QColor, QPainter, QTextFormat, QTextCharFormat,
    QSyntaxHighlighter, QTextDocument, QKeyEvent
)

from ..core.config import Config
from .syntax_highlighter import get_highlighter_for_file
from .editor_actions import EditorActionsMixin
from .auto_pair_handler import AutoPairHandlerMixin
from .virtual_scroll import LazyHighlightManager
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


class Editor(ThemeAwareMixin, AutoPairHandlerMixin, EditorActionsMixin, QPlainTextEdit):
    """文本编辑器"""

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

    def __init__(self, config: Config, theme_engine=None, parent=None):
        super().__init__(parent)
        self.config = config
        self._theme_engine = theme_engine
        self.tab_id = None
        self._highlighter = None
        self._file_type = "纯文本"
        self._wrap_mode = "no_wrap"
        self._programmatic_modify = False
        self._is_pasting = False

        self._init_ui()
        self._init_minimap_attrs()
        self._init_line_numbers()
        self._init_minimap()
        self._lazy_highlight = LazyHighlightManager(self)
        self._bookmarks: Set[int] = set()

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

        # 设置Tab宽度（4个空格）
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)

        # 设置换行模式
        wrap_mode = self.config.get_editor_setting("wrap_mode", "no_wrap")
        self.set_wrap_mode(wrap_mode)

        # 设置样式（由 _apply_theme_colors 管理）
        if self._theme_engine:
            self._init_theme(self._theme_engine)
        else:
            self.setStyleSheet("""
                QPlainTextEdit {
                    border: none;
                    background-color: white;
                    selection-background-color: #bbdefb;
                }
            """)

        # 高亮当前行
        if self.config.get_editor_setting("highlight_current_line", True):
            self.cursorPositionChanged.connect(self._highlight_current_line)
            self._highlight_current_line()

        # 禁用默认右键菜单，使用自定义的
        self.setContextMenuPolicy(Qt.CustomContextMenu)
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
        self._highlight_current_line()

    def _show_context_menu(self, position):
        """显示中文右键菜单"""
        menu = QMenu(self)

        undo_action = QAction("撤销", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.setEnabled(self.document().isUndoAvailable())
        undo_action.triggered.connect(self.undo)
        menu.addAction(undo_action)

        redo_action = QAction("重做", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.setEnabled(self.document().isRedoAvailable())
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

        menu.exec_(self.mapToGlobal(position))

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
        """计算行号区域宽度"""
        if not self.line_number_area.isVisible():
            return 0

        digits = 1
        max_num = max(1, self.blockCount())
        while max_num >= 10:
            max_num //= 10
            digits += 1

        space = 10 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

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

        if rect.contains(self.viewport().rect()):
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
        """绘制行号"""
        painter = QPainter(self.line_number_area)
        bg_color = self._theme_engine.get_active_theme().colors.sidebar_bg if self._theme_engine else "#f5f5f5"
        text_color = self._theme_engine.get_active_theme().colors.editor_line_number if self._theme_engine else "#999999"
        bookmark_color = QColor("#FF9800") if not self._theme_engine else QColor(self._theme_engine.get_active_theme().colors.accent if hasattr(self._theme_engine.get_active_theme().colors, 'accent') else "#FF9800")
        painter.fillRect(event.rect(), QColor(bg_color))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                if block_number in self._bookmarks:
                    painter.fillRect(
                        0, top,
                        self.line_number_area.width(),
                        self.fontMetrics().height(),
                        bookmark_color
                    )
                    painter.setPen(QColor("#FFFFFF"))
                else:
                    painter.setPen(QColor(text_color))
                number = str(block_number + 1)
                painter.drawText(
                    0, top,
                    self.line_number_area.width() - 5,
                    self.fontMetrics().height(),
                    Qt.AlignRight, number
                )

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def _highlight_current_line(self):
        """高亮当前行"""
        extra_selections = []

        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color_name = self._theme_engine.get_active_theme().colors.editor_current_line if self._theme_engine else "#FFFDE7"
            line_color = QColor(line_color_name)
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)

        self.setExtraSelections(extra_selections)

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
            return self.minimap.MINIMAP_WIDTH
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
        """根据文件类型设置语法高亮"""
        if self._highlighter:
            self._highlighter.setDocument(None)
            self._highlighter = None

        self._highlighter, self._file_type = get_highlighter_for_file(
            self.document(), filepath_or_ext
        )

        self._lazy_highlight.set_highlighter(self._highlighter)
        self.apply_auto_minimap()

    # ═══════════════════ 行宽模式 ═══════════════════

    def set_wrap_mode(self, mode: str):
        """设置行宽模式"""
        self._wrap_mode = mode
        if mode == "limit_width":
            self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        else:
            self.setLineWrapMode(QPlainTextEdit.NoWrap)

    def get_wrap_mode(self) -> str:
        return self._wrap_mode

    # ═══════════════════ 键盘事件处理 ═══════════════════

    def keyPressEvent(self, event: QKeyEvent):
        """键盘事件 - 自动缩进、行操作、大小写转换等"""
        modifiers = event.modifiers()
        key = event.key()

        # Ctrl+Shift+K: 删除当前行
        if modifiers == (Qt.ControlModifier | Qt.ShiftModifier) and key == Qt.Key_K:
            self.delete_current_line()
            return

        # Ctrl+Shift+D: 复制当前行
        if modifiers == (Qt.ControlModifier | Qt.ShiftModifier) and key == Qt.Key_D:
            self.duplicate_line()
            return

        # Alt+Up: 上移当前行
        if modifiers == Qt.AltModifier and key == Qt.Key_Up:
            self.move_line_up()
            return

        # Alt+Down: 下移当前行
        if modifiers == Qt.AltModifier and key == Qt.Key_Down:
            self.move_line_down()
            return

        # Ctrl+Shift+U: 切换大小写
        if modifiers == (Qt.ControlModifier | Qt.ShiftModifier) and key == Qt.Key_U:
            self.toggle_case()
            return

        # Backspace: 删除成对的括号/引号
        if key == Qt.Key_Backspace and not modifiers:
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
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._handle_enter()
            return

        # Tab键: 插入4个空格（而非真Tab）
        if key == Qt.Key_Tab and not modifiers:
            cursor = self.textCursor()
            if cursor.hasSelection():
                self._indent_selection(cursor, indent=True)
            else:
                cursor.insertText("    ")
            return

        # Shift+Tab: 减少缩进
        if key == Qt.Key_Backtab:
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

    def inputMethodEvent(self, event):
        """IME 输入事件：修复中文输入法提交字符时的自动配对

        说明：
        - 英文键盘直接输入通常会走 keyPressEvent
        - 中文输入法（含中文标点）往往通过 inputMethodEvent 提交 commitString
        """
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

    def _handle_enter(self):
        """处理回车键 - 自动缩进"""
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
                extra_indent = "    "
                break

        cursor.insertText('\n' + indent + extra_indent)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def _handle_closing_brace(self):
        """处理输入 } 时自动减少缩进"""
        cursor = self.textCursor()
        block = cursor.block()
        text = block.text()

        if text.strip() == '':
            if text.startswith("    "):
                cursor.movePosition(cursor.StartOfBlock, cursor.MoveAnchor)
                cursor.movePosition(cursor.EndOfBlock, cursor.KeepAnchor)
                new_text = text[4:] + '}'
                cursor.insertText(new_text)
                self.setTextCursor(cursor)
                return

        cursor.insertText('}')
        self.setTextCursor(cursor)

    def _indent_selection(self, cursor, indent: bool = True):
        """缩进/反缩进选中的行"""
        if not cursor.hasSelection():
            block = cursor.block()
            text = block.text()

            cursor.movePosition(cursor.StartOfBlock, cursor.MoveAnchor)
            cursor.movePosition(cursor.EndOfBlock, cursor.KeepAnchor)

            if indent:
                cursor.insertText("    " + text)
            else:
                if text.startswith("    "):
                    cursor.insertText(text[4:])
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

        for block_num in range(start_block, end_block + 1):
            block = self.document().findBlockByNumber(block_num)
            cursor.setPosition(block.position())

            if indent:
                cursor.insertText("    ")
            else:
                text = block.text()
                if text.startswith("    "):
                    cursor.movePosition(cursor.Right, cursor.KeepAnchor, 4)
                    cursor.removeSelectedText()
                elif text.startswith("\t"):
                    cursor.movePosition(cursor.Right, cursor.KeepAnchor, 1)
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
            pass  # 尚未连接，忽略

        if enabled:
            self.cursorPositionChanged.connect(self._highlight_current_line)
            self._highlight_current_line()
        else:
            # 清除已有的高亮
            self.setExtraSelections([])

    def set_editor_font(self, family: str, size: int):
        """动态设置编辑器字体和大小"""
        font = QFont(family, size)
        self.setFont(font)
        # 更新 Tab 宽度
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)
        # 更新行号区域宽度（字体变化后数字宽度可能不同）
        self._update_line_number_area_width(0)
        self._update_child_geometries()

    # ═══════════════════ 辅助方法 ═══════════════════
    def get_char_count(self) -> int:
        return len(self.toPlainText())

    def get_word_count(self) -> int:
        import re
        text = self.toPlainText()
        if not text.strip():
            return 0
        return len(re.findall(r'\b\w+\b', text))

    def get_current_line(self) -> int:
        return self.textCursor().blockNumber() + 1

    def get_current_column(self) -> int:
        return self.textCursor().columnNumber() + 1

    def get_file_type(self) -> str:
        return self._file_type

    def load_content(self, content: str):
        """加载文本内容，大文件自动启用延迟高亮"""
        if not self._lazy_highlight.load_content(content):
            self.setPlainText(content)

    def goto_line(self, line: int):
        """跳转到指定行"""
        block = self.document().findBlockByNumber(line - 1)
        if block.isValid():
            cursor = self.textCursor()
            cursor.setPosition(block.position())
            self.setTextCursor(cursor)
            self.centerCursor()
            if self._lazy_highlight.is_active():
                self._lazy_highlight.goto_line(line)

    def toggle_bookmark(self):
        line = self.textCursor().blockNumber()
        if line in self._bookmarks:
            self._bookmarks.discard(line)
        else:
            self._bookmarks.add(line)
        self.line_number_area.update()

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
        self._bookmarks = bookmarks.copy()
        self.line_number_area.update()
