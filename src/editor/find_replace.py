# -*- coding: utf-8 -*-
"""
增强型查找替换栏
支持正则表达式搜索、大小写敏感、全词匹配、匹配计数

v1.5.4 新增
"""

import re
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLineEdit,
    QPushButton, QLabel, QCheckBox, QToolButton, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import (
    QColor, QTextCharFormat, QTextCursor, QKeySequence, QTextDocument
)

from ..security.input_validator import InputValidator


# 高亮颜色
_MATCH_BG = QColor("#FFEE58")       # 所有匹配：淡黄色
_CURRENT_BG = QColor("#FF9800")     # 当前匹配：橙色
_CURRENT_FG = QColor("#FFFFFF")


class FindReplaceBar(QWidget):
    """嵌入式查找替换栏

    嵌入在编辑器容器顶部，Ctrl+F 打开查找模式，Ctrl+H 打开替换模式。
    """

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editor = None
        self._matches = []           # list of (start, end) positions
        self._current_idx = -1       # 当前高亮匹配索引
        self._replace_visible = False

        self._init_ui()
        self._connect_signals()
        self.hide()

    # ────────────────── UI 初始化 ──────────────────

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 4, 8, 4)
        main_layout.setSpacing(3)

        self.setStyleSheet("""
            FindReplaceBar {
                background-color: #F3F3F3;
                border-bottom: 1px solid #D0D0D0;
            }
            QLineEdit {
                padding: 3px 6px;
                border: 1px solid #CCC;
                border-radius: 3px;
                background: white;
                font-size: 12px;
            }
            QLineEdit:focus { border-color: #4A86C8; }
            QPushButton, QToolButton {
                padding: 3px 8px;
                border: 1px solid #CCC;
                border-radius: 3px;
                background: white;
                font-size: 12px;
            }
            QPushButton:hover, QToolButton:hover { background: #E8E8E8; }
            QPushButton:pressed, QToolButton:pressed { background: #D0D0D0; }
            QCheckBox { font-size: 12px; margin-left: 4px; }
            QLabel { font-size: 12px; }
        """)

        # ── 第一行：查找 ──
        find_row = QHBoxLayout()
        find_row.setSpacing(4)

        find_label = QLabel("查找")
        find_label.setFixedWidth(32)
        find_row.addWidget(find_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入搜索内容…")
        self.search_input.setMinimumWidth(180)
        find_row.addWidget(self.search_input, 1)

        self.match_label = QLabel("")
        self.match_label.setMinimumWidth(80)
        self.match_label.setAlignment(Qt.AlignCenter)
        find_row.addWidget(self.match_label)

        # 选项复选框
        self.case_cb = QCheckBox("Aa")
        self.case_cb.setToolTip("大小写敏感")
        find_row.addWidget(self.case_cb)

        self.word_cb = QCheckBox("W")
        self.word_cb.setToolTip("全词匹配")
        find_row.addWidget(self.word_cb)

        self.regex_cb = QCheckBox(".*")
        self.regex_cb.setToolTip("正则表达式")
        find_row.addWidget(self.regex_cb)

        self.prev_btn = QPushButton("▲")
        self.prev_btn.setFixedWidth(32)
        self.prev_btn.setToolTip("上一个 (Shift+Enter)")
        find_row.addWidget(self.prev_btn)

        self.next_btn = QPushButton("▼")
        self.next_btn.setFixedWidth(32)
        self.next_btn.setToolTip("下一个 (Enter)")
        find_row.addWidget(self.next_btn)

        self.close_btn = QToolButton()
        self.close_btn.setText("✕")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setToolTip("关闭 (Esc)")
        find_row.addWidget(self.close_btn)

        main_layout.addLayout(find_row)

        # ── 第二行：替换 ──
        self.replace_row_widget = QWidget()
        replace_row = QHBoxLayout(self.replace_row_widget)
        replace_row.setContentsMargins(0, 0, 0, 0)
        replace_row.setSpacing(4)

        replace_label = QLabel("替换")
        replace_label.setFixedWidth(32)
        replace_row.addWidget(replace_label)

        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("替换为…")
        self.replace_input.setMinimumWidth(180)
        replace_row.addWidget(self.replace_input, 1)

        self.replace_btn = QPushButton("替换")
        self.replace_btn.setToolTip("替换当前匹配")
        replace_row.addWidget(self.replace_btn)

        self.replace_all_btn = QPushButton("全部替换")
        self.replace_all_btn.setToolTip("替换所有匹配")
        replace_row.addWidget(self.replace_all_btn)

        # 占位与关闭按钮对齐
        replace_row.addSpacing(28)

        self.replace_row_widget.hide()
        main_layout.addWidget(self.replace_row_widget)

    def _connect_signals(self):
        self.search_input.textChanged.connect(self._on_search_changed)
        self.search_input.returnPressed.connect(self.find_next)

        self.case_cb.stateChanged.connect(self._on_option_changed)
        self.word_cb.stateChanged.connect(self._on_option_changed)
        self.regex_cb.stateChanged.connect(self._on_option_changed)

        self.prev_btn.clicked.connect(self.find_previous)
        self.next_btn.clicked.connect(self.find_next)
        self.close_btn.clicked.connect(self.close_bar)

        self.replace_btn.clicked.connect(self.replace_current)
        self.replace_all_btn.clicked.connect(self.replace_all)

    # ────────────────── 公开接口 ──────────────────

    def set_editor(self, editor):
        """设置当前关联的编辑器（QPlainTextEdit）"""
        self._editor = editor
        if self.isVisible():
            self._update_matches()

    def show_find(self):
        """打开查找模式"""
        self._replace_visible = False
        self.replace_row_widget.hide()
        self.show()
        self._focus_search()

    def show_replace(self):
        """打开查找+替换模式"""
        self._replace_visible = True
        self.replace_row_widget.show()
        self.show()
        self._focus_search()

    def close_bar(self):
        """关闭查找替换栏"""
        self._clear_highlights()
        self._matches.clear()
        self._current_idx = -1
        self.match_label.setText("")
        self.hide()
        if self._editor:
            self._editor.setFocus()
        self.closed.emit()

    def find_next(self):
        """查找下一个"""
        if not self._matches:
            return
        self._current_idx = (self._current_idx + 1) % len(self._matches)
        self._navigate_to_current()

    def find_previous(self):
        """查找上一个"""
        if not self._matches:
            return
        self._current_idx = (self._current_idx - 1) % len(self._matches)
        self._navigate_to_current()

    def replace_current(self):
        """替换当前匹配"""
        if not self._editor or not self._matches or self._current_idx < 0:
            return

        start, end = self._matches[self._current_idx]
        replacement = self.replace_input.text()

        # 如果使用正则表达式，支持反向引用（\1, \2 等）
        if self.regex_cb.isChecked():
            pattern = self._build_pattern()
            if pattern is None:
                return
            text = self._editor.toPlainText()
            original = text[start:end]
            try:
                replacement = pattern.sub(replacement, original, count=1)
            except re.error:
                pass

        cursor = self._editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.insertText(replacement)
        self._editor.setTextCursor(cursor)

        # 替换后重新搜索
        self._update_matches()
        # 调整索引，使下次 find_next 指向替换点之后
        if self._matches:
            new_pos = start + len(replacement)
            self._current_idx = -1
            for i, (s, e) in enumerate(self._matches):
                if s >= new_pos:
                    self._current_idx = i
                    break
            if self._current_idx < 0:
                self._current_idx = 0
            self._navigate_to_current()

    def replace_all(self):
        """替换所有匹配"""
        if not self._editor or not self._matches:
            return

        replacement = self.replace_input.text()
        pattern = self._build_pattern()
        if pattern is None and self.regex_cb.isChecked():
            return

        text = self._editor.toPlainText()
        cursor = self._editor.textCursor()
        cursor.beginEditBlock()

        if self.regex_cb.isChecked() and pattern:
            new_text = pattern.sub(replacement, text)
        else:
            # 从后往前替换以保持位置正确
            for start, end in reversed(self._matches):
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.KeepAnchor)
                cursor.insertText(replacement)
            cursor.endEditBlock()
            self._update_matches()
            self._update_match_label()
            return

        # 正则全局替换
        cursor.select(QTextCursor.Document)
        cursor.insertText(new_text)
        cursor.endEditBlock()

        self._update_matches()
        self._update_match_label()

    # ────────────────── 搜索逻辑 ──────────────────

    def _on_search_changed(self, text):
        self._update_matches()
        if self._matches:
            # 跳到编辑器光标附近的第一个匹配
            cursor_pos = self._editor.textCursor().position() if self._editor else 0
            self._current_idx = 0
            for i, (s, e) in enumerate(self._matches):
                if s >= cursor_pos:
                    self._current_idx = i
                    break
            self._navigate_to_current()
        else:
            self._current_idx = -1
            self._update_match_label()

    def _on_option_changed(self, _):
        self._update_matches()
        if self._matches:
            self._current_idx = 0
            self._navigate_to_current()
        else:
            self._current_idx = -1
            self._update_match_label()

    def _build_pattern(self):
        """根据选项构建正则表达式，失败返回 None"""
        query = self.search_input.text()
        if not query:
            return None

        validator = InputValidator()
        if not validator.validate_search(query):
            return None

        flags = 0
        if not self.case_cb.isChecked():
            flags |= re.IGNORECASE

        if self.regex_cb.isChecked():
            try:
                pattern = re.compile(query, flags)
            except re.error:
                return None
        else:
            escaped = re.escape(query)
            if self.word_cb.isChecked():
                escaped = r'\b' + escaped + r'\b'
            pattern = re.compile(escaped, flags)

        return pattern

    def _update_matches(self):
        """重新搜索并更新匹配列表和高亮"""
        self._clear_highlights()
        self._matches.clear()

        if not self._editor:
            return

        pattern = self._build_pattern()
        if pattern is None:
            self._update_match_label()
            return

        text = self._editor.toPlainText()
        for m in pattern.finditer(text):
            if m.start() != m.end():  # 忽略空匹配
                self._matches.append((m.start(), m.end()))

        self._update_match_label()
        self._apply_highlights()

    def _update_match_label(self):
        """更新匹配计数标签"""
        total = len(self._matches)
        if total == 0:
            query = self.search_input.text()
            if query:
                self.match_label.setText("无匹配")
                self.match_label.setStyleSheet("color: #D32F2F;")
            else:
                self.match_label.setText("")
                self.match_label.setStyleSheet("")
        else:
            idx = self._current_idx + 1 if self._current_idx >= 0 else 0
            self.match_label.setText(f"第 {idx}/{total} 个匹配")
            self.match_label.setStyleSheet("color: #333;")

    # ────────────────── 高亮管理 ──────────────────

    def _apply_highlights(self):
        """用 ExtraSelections 高亮所有匹配"""
        if not self._editor:
            return

        selections = []
        for i, (start, end) in enumerate(self._matches):
            sel = self._editor.__class__.__bases__[0]  # QPlainTextEdit
            # 使用 QTextEdit.ExtraSelection
            from PyQt5.QtWidgets import QTextEdit
            extra = QTextEdit.ExtraSelection()

            if i == self._current_idx:
                extra.format.setBackground(_CURRENT_BG)
                extra.format.setForeground(_CURRENT_FG)
            else:
                extra.format.setBackground(_MATCH_BG)

            cursor = self._editor.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            extra.cursor = cursor
            selections.append(extra)

        # 合并编辑器原有的当前行高亮
        current_line_sels = self._get_current_line_selection()
        self._editor.setExtraSelections(current_line_sels + selections)

    def _clear_highlights(self):
        """清除搜索高亮，保留当前行高亮"""
        if not self._editor:
            return
        current_line_sels = self._get_current_line_selection()
        self._editor.setExtraSelections(current_line_sels)

    def _get_current_line_selection(self):
        """获取当前行高亮的 ExtraSelection"""
        if not self._editor or self._editor.isReadOnly():
            return []
        from PyQt5.QtWidgets import QTextEdit
        from PyQt5.QtGui import QTextFormat
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(QColor("#FFFDE7"))
        sel.format.setProperty(QTextFormat.FullWidthSelection, True)
        sel.cursor = self._editor.textCursor()
        sel.cursor.clearSelection()
        return [sel]

    def _navigate_to_current(self):
        """将编辑器光标移动到当前匹配"""
        if not self._editor or not self._matches or self._current_idx < 0:
            return

        start, end = self._matches[self._current_idx]
        cursor = self._editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        self._editor.setTextCursor(cursor)
        self._editor.ensureCursorVisible()

        self._apply_highlights()
        self._update_match_label()

    # ────────────────── 辅助 ──────────────────

    def _focus_search(self):
        """将焦点设到搜索框，如果编辑器有选中文本则自动填入"""
        if self._editor:
            cursor = self._editor.textCursor()
            if cursor.hasSelection():
                selected = cursor.selectedText()
                if '\u2029' not in selected:  # 不跨行
                    self.search_input.setText(selected)
        self.search_input.selectAll()
        self.search_input.setFocus()
        self._update_matches()

    def keyPressEvent(self, event):
        """处理快捷键"""
        if event.key() == Qt.Key_Escape:
            self.close_bar()
            return

        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                self.find_previous()
            else:
                self.find_next()
            return

        super().keyPressEvent(event)
