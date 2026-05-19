# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QKeyEvent, QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit

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
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_ParenLeft, Qt.KeyboardModifier.NoModifier, "(")
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.toPlainText() == "()"

    def test_left_square_bracket(self, editor):
        editor.setPlainText("")
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_BracketLeft, Qt.KeyboardModifier.NoModifier, "[")
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.toPlainText() == "[]"

    def test_left_curly_bracket(self, editor):
        editor.setPlainText("")
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_BraceLeft, Qt.KeyboardModifier.NoModifier, "{")
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.toPlainText() == "{}"

    def test_right_bracket_skips_over(self, editor):
        editor.setPlainText("()")
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(QTextCursor.MoveOperation.Right)
        editor.setTextCursor(cursor)

        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_ParenRight, Qt.KeyboardModifier.NoModifier, ")")
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.textCursor().position() == 2

    def test_right_bracket_normal_insert(self, editor):
        editor.setPlainText("ab")
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(QTextCursor.MoveOperation.Right)
        editor.setTextCursor(cursor)

        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_ParenRight, Qt.KeyboardModifier.NoModifier, ")")
        result = editor._handle_auto_pair_keypress(event)
        assert result is False

    def test_auto_pair_disabled(self, editor):
        editor.config.get_editor_setting = MagicMock(return_value=False)
        editor.setPlainText("")
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_ParenLeft, Qt.KeyboardModifier.NoModifier, "(")
        result = editor._handle_auto_pair_keypress(event)
        assert result is False

    def test_no_text_event(self, editor):
        editor.setPlainText("")
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Shift, Qt.KeyboardModifier.ShiftModifier, "")
        result = editor._handle_auto_pair_keypress(event)
        assert result is False

    def test_selection_wrapping(self, editor):
        editor.setPlainText("hello")
        cursor = editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        editor.setTextCursor(cursor)

        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_ParenLeft, Qt.KeyboardModifier.NoModifier, "(")
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.toPlainText() == "(hello)"

    def test_single_quote_pair(self, editor):
        editor.setPlainText("")
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Apostrophe, Qt.KeyboardModifier.NoModifier, "'")
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.toPlainText() == "''"

    def test_double_quote_pair(self, editor):
        editor.setPlainText("")
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_QuoteDbl, Qt.KeyboardModifier.NoModifier, '"')
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.toPlainText() == '""'

    def test_skip_pair_between_letters(self, editor):
        editor.setPlainText("ab")
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(QTextCursor.MoveOperation.Right)
        editor.setTextCursor(cursor)

        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_ParenLeft, Qt.KeyboardModifier.NoModifier, "(")
        result = editor._handle_auto_pair_keypress(event)
        assert result is False


class TestRightBracketKeypress:
    def test_right_bracket_after_left(self, editor):
        editor.setPlainText("()")
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(QTextCursor.MoveOperation.Right)
        editor.setTextCursor(cursor)

        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_ParenRight, Qt.KeyboardModifier.NoModifier, ")")
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.textCursor().position() == 2

    def test_right_bracket_between_pair(self, editor):
        editor.setPlainText("()")
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(QTextCursor.MoveOperation.Right)
        editor.setTextCursor(cursor)

        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_ParenRight, Qt.KeyboardModifier.NoModifier, ")")
        result = editor._handle_auto_pair_keypress(event)
        assert result is True
        assert editor.textCursor().position() == 2
