# -*- coding: utf-8 -*-
"""
自动配对处理模块
将括号/引号自动配对逻辑从 Editor 的 keyPressEvent / inputMethodEvent 中抽离

采用 Mixin 模式，Editor 通过多继承获得这些能力。

v1.6.6 性能改造：
  - 引入 frozenset 快速过滤：非括号/引号字符 O(1) 返回，不读 cursor、不读全文
  - _doc_char_at 按需访问文档单字符，替代 toPlainText() 全文复制
  - _wrap_selection 用 cursor 操作包裹选区，避免 selectedText() 大字符串复制
  - _pick_single_cjk_quote 用 QTextCursor 读取前缀，替代 toPlainText() + 切片
  - 行内前缀改用 block.text() + str.count(start, end)，替代全文切片
"""

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent, QTextCursor

from ..utils.logger import get_logger


class AutoPairHandlerMixin:
    """括号/引号自动配对 Mixin

    要求宿主类提供以下属性/方法：
    - textCursor() -> QTextCursor
    - setTextCursor(cursor)
    - document() -> QTextDocument
    - config: Config 实例
    - AUTO_PAIR_CHARS: dict
    """

    def _ensure_auto_pair_cache(self):
        pairs = self.AUTO_PAIR_CHARS
        version = (id(pairs), tuple(pairs.items()))

        if getattr(self, "_auto_pair_cache_version", None) == version:
            return

        self._auto_pair_cache_version = version
        self._auto_pair_open_chars = frozenset(pairs.keys())
        self._auto_pair_close_to_open = {v: k for k, v in pairs.items()}
        self._auto_pair_close_chars = frozenset(self._auto_pair_close_to_open.keys())
        self._auto_pair_all_chars = (
            self._auto_pair_open_chars
            | self._auto_pair_close_chars
            | frozenset(("\u201c", "\u201d", "\u2018", "\u2019",
                         "\u300c", "\u300d", "\u300e", "\u300f"))
        )

    def _doc_char_at(self, pos: int) -> str:
        doc = self.document()
        if 0 <= pos < doc.characterCount() - 1:
            return doc.characterAt(pos)
        return ""

    def _handle_auto_pair_keypress(self, event: QKeyEvent) -> bool:
        if not self.config.get_editor_setting("auto_pair_brackets", True):
            return False

        char = event.text()
        if not char:
            return False

        self._ensure_auto_pair_cache()

        if char not in self._auto_pair_all_chars:
            return False

        cursor: QTextCursor = self.textCursor()
        pos = cursor.position()

        if self._handle_right_bracket_keypress(char, cursor, pos):
            return True

        if self._handle_left_bracket_keypress(char, cursor, pos):
            return True

        return False

    def _handle_right_bracket_keypress(
        self, char: str, cursor: QTextCursor, pos: int
    ) -> bool:
        if char not in self._auto_pair_close_chars:
            return False

        if self._doc_char_at(pos) == char:
            cursor.movePosition(QTextCursor.MoveOperation.Right)
            self.setTextCursor(cursor)
            return True

        if char in self._auto_pair_close_to_open:
            expected_open = self._auto_pair_close_to_open[char]
            if self._doc_char_at(pos - 1) == expected_open:
                cursor.insertText(char)
                cursor.movePosition(QTextCursor.MoveOperation.Left)
                self.setTextCursor(cursor)
                return True

        return False

    def _handle_left_bracket_keypress(
        self, char: str, cursor: QTextCursor, pos: int
    ) -> bool:
        if char not in self._auto_pair_open_chars:
            return False

        closing = self.AUTO_PAIR_CHARS[char]

        if cursor.hasSelection():
            self._wrap_selection(cursor, char, closing)
            return True

        char_before = self._doc_char_at(pos - 1)
        char_after = self._doc_char_at(pos)

        between_existing_pair = (
            char_before in self.AUTO_PAIR_CHARS
            and self.AUTO_PAIR_CHARS.get(char_before) == char_after
        )

        should_skip_pair = (
            char_before and not char_before.isspace()
            and char_after and not char_after.isspace()
            and not between_existing_pair
        )

        if should_skip_pair:
            if char in ("\u201c", "\u201d", "\u2018", "\u2019", "\u300c", "\u300d", "\u300e", "\u300f"):
                cursor.insertText(self._pick_single_cjk_quote(char, pos))
                self.setTextCursor(cursor)
                return True
            return False

        cursor.insertText(char + closing)
        cursor.movePosition(QTextCursor.MoveOperation.Left)
        self.setTextCursor(cursor)
        return True

    def _handle_auto_pair_ime(self, event: Any) -> bool:
        if not self.config.get_editor_setting("auto_pair_brackets", True):
            return False

        commit = event.commitString()
        if not commit or len(commit) != 1:
            return False

        char: str = commit
        self._ensure_auto_pair_cache()

        if char not in self._auto_pair_all_chars:
            return False

        cursor: QTextCursor = self.textCursor()
        pos = cursor.position()

        if self._handle_right_bracket_ime(char, cursor, pos, event):
            return True

        if self._handle_left_bracket_ime(char, cursor, pos, event):
            return True

        return False

    def _handle_right_bracket_ime(
        self, char: str, cursor: QTextCursor, pos: int, event: Any
    ) -> bool:
        if char not in self._auto_pair_close_chars:
            return False

        if self._doc_char_at(pos) == char:
            try:
                event.setCommitString("", 0, 0)
            except Exception as _e:
                get_logger(__name__).debug("IME setCommitString 失败: %s", _e)
            super(self.__class__, self).inputMethodEvent(event)
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Right)
            self.setTextCursor(cursor)
            return True

        if char in self._auto_pair_close_to_open:
            expected_open = self._auto_pair_close_to_open[char]
            if self._doc_char_at(pos - 1) == expected_open:
                cursor.insertText(char)
                cursor.movePosition(QTextCursor.MoveOperation.Left)
                self.setTextCursor(cursor)
                return True

        if char in ("\u201d", "\u2019"):
            open_char = "\u201c" if char == "\u201d" else "\u2018"
            block = cursor.block()
            rel_pos = pos - block.position()
            line_text = block.text()

            _cb = self._doc_char_at(pos - 1)
            _ca = self._doc_char_at(pos)
            _between_existing_pair = (
                _cb in self.AUTO_PAIR_CHARS
                and self.AUTO_PAIR_CHARS.get(_cb) == _ca
            )
            if _cb and not _cb.isspace() and _ca and not _ca.isspace() and not _between_existing_pair:
                try:
                    event.setCommitString("", 0, 0)
                except Exception as _e:
                    get_logger(__name__).debug("IME setCommitString 失败: %s", _e)
                super(self.__class__, self).inputMethodEvent(event)
                cursor = self.textCursor()
                cursor.insertText(self._pick_single_cjk_quote(char, pos))
                self.setTextCursor(cursor)
                return True

            if line_text.count(open_char, 0, rel_pos) <= line_text.count(char, 0, rel_pos):
                try:
                    event.setCommitString("", 0, 0)
                except Exception as _e:
                    get_logger(__name__).debug("IME setCommitString 失败: %s", _e)
                super(self.__class__, self).inputMethodEvent(event)
                cursor = self.textCursor()
                if cursor.hasSelection():
                    self._wrap_selection(cursor, open_char, char)
                else:
                    cursor.insertText(open_char + char)
                    cursor.movePosition(QTextCursor.MoveOperation.Left)
                self.setTextCursor(cursor)
                return True

        return False

    def _handle_left_bracket_ime(
        self, char: str, cursor: QTextCursor, pos: int, event: Any
    ) -> bool:
        if char not in self._auto_pair_open_chars:
            return False

        closing = self.AUTO_PAIR_CHARS[char]

        if cursor.hasSelection():
            try:
                event.setCommitString("", 0, 0)
            except Exception as _e:
                get_logger(__name__).debug("IME setCommitString 失败: %s", _e)
            super(self.__class__, self).inputMethodEvent(event)
            cursor = self.textCursor()
            self._wrap_selection(cursor, char, closing)
            return True

        char_before = self._doc_char_at(pos - 1)
        char_after = self._doc_char_at(pos)

        between_existing_pair = (
            char_before in self.AUTO_PAIR_CHARS
            and self.AUTO_PAIR_CHARS.get(char_before) == char_after
        )

        should_skip_pair = (
            char_before and not char_before.isspace()
            and char_after and not char_after.isspace()
            and not between_existing_pair
        )

        if should_skip_pair:
            if char in ("\u201c", "\u201d", "\u2018", "\u2019", "\u300c", "\u300d", "\u300e", "\u300f"):
                try:
                    event.setCommitString("", 0, 0)
                except Exception as _e:
                    get_logger(__name__).debug("IME setCommitString 失败: %s", _e)
                super(self.__class__, self).inputMethodEvent(event)
                cursor = self.textCursor()
                cursor.insertText(self._pick_single_cjk_quote(char, pos))
                self.setTextCursor(cursor)
                return True
            return False

        try:
            event.setCommitString("", 0, 0)
        except Exception as _e:
            get_logger(__name__).debug("IME setCommitString 失败: %s", _e)
        super(self.__class__, self).inputMethodEvent(event)
        cursor = self.textCursor()
        cursor.insertText(char + closing)
        cursor.movePosition(QTextCursor.MoveOperation.Left)
        self.setTextCursor(cursor)
        return True

    def _wrap_selection(self, cursor: QTextCursor, left: str, right: str) -> None:
        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        cursor.beginEditBlock()
        cursor.setPosition(end)
        cursor.insertText(right)
        cursor.setPosition(start)
        cursor.insertText(left)
        cursor.setPosition(end + len(left) + len(right))
        cursor.endEditBlock()

        self.setTextCursor(cursor)
