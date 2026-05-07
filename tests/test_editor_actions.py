# -*- coding: utf-8 -*-
import sys

import pytest
from PyQt5.QtWidgets import QApplication, QPlainTextEdit
from PyQt5.QtGui import QTextCursor

from src.editor.editor_actions import EditorActionsMixin


class TestEditor(EditorActionsMixin, QPlainTextEdit):
    _file_type = "Text"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = MagicMock()


from unittest.mock import MagicMock


@pytest.fixture
def app(qtbot):
    editor = TestEditor()
    qtbot.addWidget(editor)
    return editor


class TestDeleteCurrentLine:
    def test_delete_single_line(self, app):
        app.setPlainText("line1\nline2\nline3")
        cursor = app.textCursor()
        cursor.movePosition(cursor.Start)
        cursor.movePosition(cursor.Down)
        app.setTextCursor(cursor)

        app.delete_current_line()
        assert app.toPlainText() == "line1\nline3"

    def test_delete_last_line(self, app):
        app.setPlainText("line1\nline2\nline3")
        cursor = app.textCursor()
        cursor.movePosition(cursor.Start)
        cursor.movePosition(cursor.Down, cursor.MoveAnchor, 2)
        app.setTextCursor(cursor)
        assert cursor.blockNumber() == 2

        app.delete_current_line()
        result = app.toPlainText()
        assert "line3" not in result
        assert "line1" in result

    def test_delete_only_line(self, app):
        app.setPlainText("only line")
        app.delete_current_line()
        assert app.toPlainText() == ""


class TestDuplicateLine:
    def test_duplicate_line(self, app):
        app.setPlainText("line1\nline2\nline3")
        cursor = app.textCursor()
        cursor.movePosition(cursor.Start)
        cursor.movePosition(cursor.Down)
        app.setTextCursor(cursor)

        app.duplicate_line()
        assert app.toPlainText() == "line1\nline2\nline2\nline3"


class TestMoveLineUp:
    def test_move_line_up(self, app):
        app.setPlainText("line1\nline2\nline3")
        cursor = app.textCursor()
        cursor.movePosition(cursor.Start)
        cursor.movePosition(cursor.Down)
        app.setTextCursor(cursor)

        app.move_line_up()
        assert app.toPlainText() == "line2\nline1\nline3"

    def test_cannot_move_first_line_up(self, app):
        app.setPlainText("line1\nline2")
        cursor = app.textCursor()
        cursor.movePosition(cursor.Start)
        app.setTextCursor(cursor)

        app.move_line_up()
        assert app.toPlainText() == "line1\nline2"


class TestMoveLineDown:
    def test_move_line_down(self, app):
        app.setPlainText("line1\nline2\nline3")
        cursor = app.textCursor()
        cursor.movePosition(cursor.Start)
        app.setTextCursor(cursor)

        app.move_line_down()
        assert app.toPlainText() == "line2\nline1\nline3"

    def test_cannot_move_last_line_down(self, app):
        app.setPlainText("line1\nline2")
        cursor = app.textCursor()
        cursor.movePosition(cursor.Start)
        cursor.movePosition(cursor.Down)
        app.setTextCursor(cursor)

        app.move_line_down()
        assert app.toPlainText() == "line1\nline2"


class TestCaseConversion:
    def test_to_uppercase(self, app):
        app.setPlainText("hello world")
        cursor = app.textCursor()
        cursor.select(QTextCursor.Document)
        app.setTextCursor(cursor)

        app.to_uppercase()
        assert app.toPlainText() == "HELLO WORLD"

    def test_to_lowercase(self, app):
        app.setPlainText("HELLO WORLD")
        cursor = app.textCursor()
        cursor.select(QTextCursor.Document)
        app.setTextCursor(cursor)

        app.to_lowercase()
        assert app.toPlainText() == "hello world"

    def test_to_titlecase(self, app):
        app.setPlainText("hello world")
        cursor = app.textCursor()
        cursor.select(QTextCursor.Document)
        app.setTextCursor(cursor)

        app.to_titlecase()
        assert app.toPlainText() == "Hello World"

    def test_toggle_case_upper_to_lower(self, app):
        app.setPlainText("HELLO")
        cursor = app.textCursor()
        cursor.select(QTextCursor.Document)
        app.setTextCursor(cursor)

        app.toggle_case()
        assert app.toPlainText() == "hello"

    def test_toggle_case_lower_to_upper(self, app):
        app.setPlainText("hello")
        cursor = app.textCursor()
        cursor.select(QTextCursor.Document)
        app.setTextCursor(cursor)

        app.toggle_case()
        assert app.toPlainText() == "HELLO"

    def test_no_selection_does_nothing(self, app):
        app.setPlainText("hello")
        app.to_uppercase()
        assert app.toPlainText() == "hello"


class TestGotoLine:
    def test_goto_line(self, app):
        app.setPlainText("line1\nline2\nline3\nline4\nline5")
        app.goto_line(3)
        cursor = app.textCursor()
        assert cursor.blockNumber() == 2

    def test_goto_line_out_of_range(self, app):
        app.setPlainText("line1\nline2")
        app.goto_line(999)
        cursor = app.textCursor()
        assert cursor.blockNumber() == 1

    def test_goto_line_zero(self, app):
        app.setPlainText("line1\nline2")
        app.goto_line(0)
        cursor = app.textCursor()
        assert cursor.blockNumber() == 0


class TestFormatDocument:
    def test_format_json(self, app):
        app._file_type = "JSON"
        app.setPlainText('{"b":2,"a":1}')
        app.format_document()
        result = app.toPlainText()
        assert '"b"' in result
        assert '"a"' in result

    def test_format_json_invalid(self, app):
        app._file_type = "JSON"
        app.setPlainText("not json")
        app.format_document()
        assert app.toPlainText() == "not json"
