# -*- coding: utf-8 -*-
"""
自动配对处理模块
将括号/引号自动配对逻辑从 Editor 的 keyPressEvent / inputMethodEvent 中抽离

采用 Mixin 模式，Editor 通过多继承获得这些能力。
"""

from typing import Any

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeyEvent, QTextCursor

from ..utils.logger import get_logger


class AutoPairHandlerMixin:
    """括号/引号自动配对 Mixin

    要求宿主类提供以下属性/方法：
    - textCursor() -> QTextCursor
    - setTextCursor(cursor)
    - toPlainText() -> str
    - config: Config 实例
    - AUTO_PAIR_CHARS: dict
    """

    def _handle_auto_pair_keypress(self, event: QKeyEvent) -> bool:
        """处理 keyPressEvent 中的自动配对逻辑

        Returns:
            True 表示事件已处理，调用方应 return
            False 表示事件未处理，调用方应继续默认处理
        """
        if not self.config.get_editor_setting("auto_pair_brackets", True):
            return False

        char = event.text()
        if not char:
            return False

        cursor: QTextCursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()

        if self._handle_right_bracket_keypress(char, cursor, pos, text):
            return True

        if self._handle_left_bracket_keypress(char, cursor, pos, text):
            return True

        return False

    def _handle_right_bracket_keypress(
        self, char: str, cursor: QTextCursor, pos: int, text: str
    ) -> bool:
        """处理输入右括号/引号的情况"""
        if char not in self.AUTO_PAIR_CHARS.values():
            return False

        if pos < len(text) and text[pos] == char:
            cursor.movePosition(cursor.Right)
            self.setTextCursor(cursor)
            return True

        close_to_open: dict[str, str] = {v: k for k, v in self.AUTO_PAIR_CHARS.items()}
        if char in close_to_open:
            expected_open = close_to_open[char]
            if pos > 0 and text[pos - 1] == expected_open:
                cursor.insertText(char)
                cursor.movePosition(cursor.Left)
                self.setTextCursor(cursor)
                return True

        return False

    def _handle_left_bracket_keypress(
        self, char: str, cursor: QTextCursor, pos: int, text: str
    ) -> bool:
        """处理输入左括号/引号的情况"""
        if char not in self.AUTO_PAIR_CHARS:
            return False

        closing = self.AUTO_PAIR_CHARS[char]

        if cursor.hasSelection():
            selected = cursor.selectedText()
            cursor.insertText(char + selected + closing)
            self.setTextCursor(cursor)
            return True

        char_before = text[pos - 1] if pos > 0 else ''
        char_after = text[pos] if pos < len(text) else ''

        between_existing_pair = (
            char_before in self.AUTO_PAIR_CHARS and
            self.AUTO_PAIR_CHARS.get(char_before) == char_after
        )

        should_skip_pair = (
            char_before and not char_before.isspace() and
            char_after and not char_after.isspace() and
            not between_existing_pair
        )

        if should_skip_pair:
            if char in ("\u201c", "\u201d", "\u2018", "\u2019", "\u300c", "\u300d", "\u300e", "\u300f"):
                cursor.insertText(self._pick_single_cjk_quote(char, pos))
                self.setTextCursor(cursor)
                return True
            return False

        cursor.insertText(char + closing)
        cursor.movePosition(cursor.Left)
        self.setTextCursor(cursor)
        return True

    def _handle_auto_pair_ime(self, event: Any) -> bool:
        """处理 inputMethodEvent 中的自动配对逻辑

        Returns:
            True 表示事件已处理
            False 表示事件未处理
        """
        if not self.config.get_editor_setting("auto_pair_brackets", True):
            return False

        commit = event.commitString()
        if not commit or len(commit) != 1:
            return False

        char: str = commit
        cursor: QTextCursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()

        if self._handle_right_bracket_ime(char, cursor, pos, text, event):
            return True

        if self._handle_left_bracket_ime(char, cursor, pos, text, event):
            return True

        return False

    def _handle_right_bracket_ime(
        self, char: str, cursor: QTextCursor, pos: int, text: str, event: Any
    ) -> bool:
        """处理 IME 输入右括号/引号"""
        if char not in self.AUTO_PAIR_CHARS.values():
            return False

        if pos < len(text) and text[pos] == char:
            try:
                event.setCommitString("", 0, 0)
            except Exception as _e:
                get_logger(__name__).debug("IME setCommitString 失败: %s", _e)
            super(self.__class__, self).inputMethodEvent(event)
            cursor = self.textCursor()
            cursor.movePosition(cursor.Right)
            self.setTextCursor(cursor)
            return True

        close_to_open: dict[str, str] = {v: k for k, v in self.AUTO_PAIR_CHARS.items()}
        if char in close_to_open:
            expected_open = close_to_open[char]
            if pos > 0 and text[pos - 1] == expected_open:
                cursor.insertText(char)
                cursor.movePosition(cursor.Left)
                self.setTextCursor(cursor)
                return True

        if char in ("\u201d", "\u2019"):
            open_char = "\u201c" if char == "\u201d" else "\u2018"
            block = cursor.block()
            line_prefix = text[block.position():pos]

            _cb = text[pos - 1] if pos > 0 else ''
            _ca = text[pos] if pos < len(text) else ''
            _between_existing_pair = (
                _cb in self.AUTO_PAIR_CHARS and
                self.AUTO_PAIR_CHARS.get(_cb) == _ca
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

            if line_prefix.count(open_char) <= line_prefix.count(char):
                try:
                    event.setCommitString("", 0, 0)
                except Exception as _e:
                    get_logger(__name__).debug("IME setCommitString 失败: %s", _e)
                super(self.__class__, self).inputMethodEvent(event)
                cursor = self.textCursor()
                if cursor.hasSelection():
                    selected = cursor.selectedText()
                    cursor.insertText(open_char + selected + char)
                else:
                    cursor.insertText(open_char + char)
                    cursor.movePosition(cursor.Left)
                self.setTextCursor(cursor)
                return True

        return False

    def _handle_left_bracket_ime(
        self, char: str, cursor: QTextCursor, pos: int, text: str, event: Any
    ) -> bool:
        """处理 IME 输入左括号/引号"""
        if char not in self.AUTO_PAIR_CHARS:
            return False

        closing = self.AUTO_PAIR_CHARS[char]

        if cursor.hasSelection():
            selected = cursor.selectedText()
            try:
                event.setCommitString("", 0, 0)
            except Exception as _e:
                get_logger(__name__).debug("IME setCommitString 失败: %s", _e)
            super(self.__class__, self).inputMethodEvent(event)
            cursor = self.textCursor()
            cursor.insertText(char + selected + closing)
            self.setTextCursor(cursor)
            return True

        char_before = text[pos - 1] if pos > 0 else ''
        char_after = text[pos] if pos < len(text) else ''

        between_existing_pair = (
            char_before in self.AUTO_PAIR_CHARS and
            self.AUTO_PAIR_CHARS.get(char_before) == char_after
        )

        should_skip_pair = (
            char_before and not char_before.isspace() and
            char_after and not char_after.isspace() and
            not between_existing_pair
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
        cursor.movePosition(cursor.Left)
        self.setTextCursor(cursor)
        return True
