# -*- coding: utf-8 -*-
"""
增强型查找替换栏
支持正则表达式搜索、大小写敏感、全词匹配、匹配计数

v1.5.4 新增
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLineEdit,
    QPushButton, QLabel, QCheckBox, QToolButton, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import (
    QColor, QTextCursor
)

from ..themes.theme_aware_mixin import ThemeAwareMixin
from ..utils.logger import get_logger
from .search_service import SearchService




# 高亮颜色
_MATCH_BG = QColor("#FFEE58")       # 所有匹配：淡黄色
_CURRENT_BG = QColor("#FF9800")     # 当前匹配：橙色
_CURRENT_FG = QColor("#FFFFFF")


class FindReplaceBar(ThemeAwareMixin, QWidget):
    """嵌入式查找替换栏

    嵌入在编辑器容器顶部，Ctrl+F 打开查找模式，Ctrl+H 打开替换模式。
    """

    closed = pyqtSignal()

    def __init__(self, theme_engine=None, parent=None):
        super().__init__(parent)
        self._editor = None
        self._matches = []
        self._current_idx = -1
        self._replace_visible = False

        self._init_ui()
        self._connect_signals()
        if theme_engine:
            self._init_theme(theme_engine)
        self.hide()

    # ────────────────── UI 初始化 ──────────────────

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 4, 8, 4)
        main_layout.setSpacing(3)

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
        self.match_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
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

        service = SearchService(self._editor)
        use_regex = self.regex_cb.isChecked()
        success = service.replace_current(
            start, end, replacement,
            use_regex=use_regex,
            query=self.search_input.text() if use_regex else "",
            case_sensitive=self.case_cb.isChecked(),
        )
        if not success:
            return

        self._update_matches()
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

        query = self.search_input.text()
        if not query:
            return

        replacement = self.replace_input.text()
        service = SearchService(self._editor)
        service.replace_all(
            query, replacement,
            case_sensitive=self.case_cb.isChecked(),
            whole_word=self.word_cb.isChecked(),
            use_regex=self.regex_cb.isChecked(),
        )

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

    def _update_matches(self):
        """重新搜索并更新匹配列表和高亮"""
        self._clear_highlights()
        self._matches.clear()

        if not self._editor:
            return

        query = self.search_input.text()
        if not query or len(query) > 500:
            self._update_match_label()
            return

        service = SearchService(self._editor)
        self._matches = service.find_all(
            query,
            case_sensitive=self.case_cb.isChecked(),
            whole_word=self.word_cb.isChecked(),
            use_regex=self.regex_cb.isChecked(),
        )

        self._update_match_label()
        self._apply_highlights()

    def _apply_theme_colors(self, colors):
        self.setStyleSheet(f"""
            FindReplaceBar {{
                background-color: {colors.surface};
                border-bottom: 1px solid {colors.border};
            }}
            QLineEdit {{
                padding: 3px 6px;
                border: 1px solid {colors.border};
                border-radius: 3px;
                background: {colors.card};
                color: {colors.text_primary};
                font-size: 12px;
            }}
            QLineEdit:focus {{ border-color: {colors.primary}; }}
            QPushButton, QToolButton {{
                padding: 3px 8px;
                border: 1px solid {colors.border};
                border-radius: 3px;
                background: {colors.card};
                color: {colors.text_primary};
                font-size: 12px;
            }}
            QPushButton:hover, QToolButton:hover {{ background: {colors.primary_light}; }}
            QPushButton:pressed, QToolButton:pressed {{ background: {colors.border}; }}
            QCheckBox {{ font-size: 12px; margin-left: 4px; color: {colors.text_primary}; }}
            QLabel {{ font-size: 12px; color: {colors.text_primary}; }}
        """)
        self._update_match_label()

    def _update_match_label(self):
        """更新匹配计数标签"""
        total = len(self._matches)
        if not hasattr(self, '_theme_engine') or self._theme_engine is None:
            error_color = "#D32F2F"
            text_color = "#333"
        else:
            colors = self._theme_engine.get_active_theme().colors
            error_color = colors.error
            text_color = colors.text_primary
        if total == 0:
            query = self.search_input.text()
            if query:
                self.match_label.setText("无匹配")
                self.match_label.setStyleSheet(f"color: {error_color};")
            else:
                self.match_label.setText("")
                self.match_label.setStyleSheet("")
        else:
            idx = self._current_idx + 1 if self._current_idx >= 0 else 0
            self.match_label.setText(f"第 {idx}/{total} 个匹配")
            self.match_label.setStyleSheet(f"color: {text_color};")

    # ────────────────── 高亮管理 ──────────────────

    def _apply_highlights(self):
        """用 ExtraSelections 高亮所有匹配"""
        if not self._editor:
            return

        selections = []
        for i, (start, end) in enumerate(self._matches):
            from PyQt6.QtWidgets import QTextEdit
            extra = QTextEdit.ExtraSelection()

            if i == self._current_idx:
                extra.format.setBackground(_CURRENT_BG)
                extra.format.setForeground(_CURRENT_FG)
            else:
                extra.format.setBackground(_MATCH_BG)

            cursor = self._editor.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            extra.cursor = cursor
            selections.append(extra)

        self._editor.selection_manager.set_layer("search_matches", selections)
        self._editor.selection_manager.refresh()

    def _clear_highlights(self):
        """清除搜索高亮，保留当前行高亮"""
        if not self._editor:
            return
        self._editor.selection_manager.clear_layer("search_matches")
        self._editor.selection_manager.refresh()

    def _navigate_to_current(self):
        """将编辑器光标移动到当前匹配"""
        if not self._editor or not self._matches or self._current_idx < 0:
            return

        start, end = self._matches[self._current_idx]
        cursor = self._editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
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
        if event.key() == Qt.Key.Key_Escape:
            self.close_bar()
            return

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.find_previous()
            else:
                self.find_next()
            return

        super().keyPressEvent(event)
