# -*- coding: utf-8 -*-
import pytest
from PyQt6.QtWidgets import QApplication

from src.editor.status_bar import StatusBarWidget


@pytest.fixture
def app(qtbot):
    sb = StatusBarWidget()
    qtbot.addWidget(sb)
    return sb


class TestStatusBarWidget:
    def test_init(self, app):
        assert app is not None

    def test_default_labels(self, app):
        assert app.position_label.text() == "行 1, 列 1"
        assert app.char_count_label.text() == "0 个字符"
        assert app.encoding_label.text() == "UTF-8"
        assert app.file_type_label.text() == "纯文本"

    def test_update_stats(self, app):
        app.update_stats(100, 5, 10, "gbk", "Python")
        assert app.position_label.text() == "行 5, 列 10"
        assert app.char_count_label.text() == "100 个字符"
        assert app.encoding_label.text() == "GBK"
        assert app.file_type_label.text() == "Python"

    def test_set_encoding(self, app):
        app.set_encoding("utf-8")
        assert app.encoding_label.text() == "UTF-8"

    def test_set_file_type(self, app):
        app.set_file_type("Markdown")
        assert app.file_type_label.text() == "Markdown"
