# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

import pytest
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QKeyEvent, QTextCursor
from PyQt5.QtWidgets import QPlainTextEdit

from src.editor.auto_pair_handler import AutoPairHandlerMixin


AUTO_PAIR_CHARS = {
    '(': ')',
    '[': ']',
    '{': '}',
    '"': '"',
    "'": "'",
    '\uff08': '\uff09',
    '\u3010': '\u3011',
    '\u300c': '\u300d',
    '\u300e': '\u300f',
    '\u201c': '\u201d',
    '\u2018': '\u2019',
    '\u300a': '\u300b',
    '\u3008': '\u3009',
}


class TestEditor(AutoPairHandlerMixin, QPlainTextEdit):
    AUTO_PAIR_CHARS = AUTO_PAIR_CHARS

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = MagicMock()
        self.config.get_editor_setting = MagicMock(return_value=True)


@pytest.fixture
def editor(qtbot):
    e = TestEditor()
    qtbot.addWidget(e)
    return e


class TestAutoPairKeypress:
    def test_left_bracket_inserts_pair(self, editor):
        editor.setPlainText("")
        event = QKeyEvent(QEvent.KeyPress, Qt.Key_ParenLeft, Qt.NoModifier, "(")
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.toPlainText() == "()"

    def test_left_square_bracket(self, editor):
        editor.setPlainText("")
        event = QKeyEvent(QEvent.KeyPress, Qt.Key_BracketLeft, Qt.NoModifier, "[")
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.toPlainText() == "[]"

    def test_left_curly_bracket(self, editor):
        editor.setPlainText("")
        event = QKeyEvent(QEvent.KeyPress, Qt.Key_BraceLeft, Qt.NoModifier, "{")
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.toPlainText() == "{}"

    def test_right_bracket_skips_over(self, editor):
        editor.setPlainText("()")
        cursor = editor.textCursor()
        cursor.movePosition(cursor.Start)
        cursor.movePosition(cursor.Right)
        editor.setTextCursor(cursor)

        event = QKeyEvent(QEvent.KeyPress, Qt.Key_ParenRight, Qt.NoModifier, ")")
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.textCursor().position() == 2

    def test_right_bracket_normal_insert(self, editor):
        editor.setPlainText("ab")
        cursor = editor.textCursor()
        cursor.movePosition(cursor.Start)
        cursor.movePosition(cursor.Right)
        editor.setTextCursor(cursor)

        event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_ParenRight, Qt.NoModifier, ")")
        result = editor._handle_auto_pair_keypress(event)
        assert result is False

    def test_auto_pair_disabled(self, editor):
        editor.config.get_editor_setting = MagicMock(return_value=False)
        editor.setPlainText("")
        event = QKeyEvent(QEvent.KeyPress, Qt.Key_ParenLeft, Qt.NoModifier, "(")
        result = editor._handle_auto_pair_keypress(event)
        assert result is False

    def test_no_text_event(self, editor):
        editor.setPlainText("")
        event = QKeyEvent(QEvent.KeyPress, Qt.Key_Shift, Qt.ShiftModifier, "")
        result = editor._handle_auto_pair_keypress(event)
        assert result is False

    def test_selection_wrapping(self, editor):
        editor.setPlainText("hello")
        cursor = editor.textCursor()
        cursor.select(QTextCursor.Document)
        editor.setTextCursor(cursor)

        event = QKeyEvent(QEvent.KeyPress, Qt.Key_ParenLeft, Qt.NoModifier, "(")
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.toPlainText() == "(hello)"

    def test_single_quote_pair(self, editor):
        editor.setPlainText("")
        event = QKeyEvent(QEvent.KeyPress, Qt.Key_Apostrophe, Qt.NoModifier, "'")
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.toPlainText() == "''"

    def test_double_quote_pair(self, editor):
        editor.setPlainText("")
        event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_QuoteDbl, Qt.NoModifier, '"')
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.toPlainText() == '""'

    def test_skip_pair_between_letters(self, editor):
        editor.setPlainText("ab")
        cursor = editor.textCursor()
        cursor.movePosition(cursor.Start)
        cursor.movePosition(cursor.Right)
        editor.setTextCursor(cursor)

        event = QKeyEvent(QEvent.KeyPress, Qt.Key_ParenLeft, Qt.NoModifier, "(")
        result = editor._handle_auto_pair_keypress(event)
        assert result is False


class TestRightBracketKeypress:
    def test_right_bracket_after_left(self, editor):
        editor.setPlainText("()")
        cursor = editor.textCursor()
        cursor.movePosition(cursor.Start)
        cursor.movePosition(cursor.Right)
        editor.setTextCursor(cursor)

        event = QKeyEvent(QEvent.KeyPress, Qt.Key_ParenRight, Qt.NoModifier, ")")
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.textCursor().position() == 2

    def test_right_bracket_between_pair(self, editor):
        editor.setPlainText("()")
        cursor = editor.textCursor()
        cursor.movePosition(cursor.Start)
        cursor.movePosition(cursor.Right)
        editor.setTextCursor(cursor)

        event = QKeyEvent(QEvent.KeyPress, Qt.Key_ParenRight, Qt.NoModifier, ")")
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.textCursor().position() == 2
