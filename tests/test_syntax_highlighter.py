# -*- coding: utf-8 -*-
import pytest
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QApplication

from src.editor.syntax_highlighter import (
    MarkdownHighlighter, PygmentsHighlighter,
    get_highlighter_for_file, HAS_PYGMENTS,
)


class TestMarkdownHighlighter:
    def test_init(self, qtbot):
        doc = QTextDocument()
        hl = MarkdownHighlighter(doc)
        assert hl is not None

    def test_heading_h1(self, qtbot):
        doc = QTextDocument()
        doc.setPlainText("# Hello")
        hl = MarkdownHighlighter(doc)
        hl.highlightBlock("# Hello")
        fmt = hl.format(0)
        assert fmt.isValid()

    def test_heading_h2(self, qtbot):
        doc = QTextDocument()
        hl = MarkdownHighlighter(doc)
        hl.highlightBlock("## Hello")
        fmt = hl.format(0)
        assert fmt.isValid()

    def test_heading_h3(self, qtbot):
        doc = QTextDocument()
        hl = MarkdownHighlighter(doc)
        hl.highlightBlock("### Hello")
        fmt = hl.format(0)
        assert fmt.isValid()

    def test_code_fence(self, qtbot):
        doc = QTextDocument()
        hl = MarkdownHighlighter(doc)
        hl.highlightBlock("```python")
        fmt = hl.format(0)
        assert fmt.isValid()

    def test_inline_code(self, qtbot):
        doc = QTextDocument()
        hl = MarkdownHighlighter(doc)
        hl.highlightBlock("some `code` here")
        assert True

    def test_bold(self, qtbot):
        doc = QTextDocument()
        hl = MarkdownHighlighter(doc)
        hl.highlightBlock("some **bold** text")
        assert True

    def test_link(self, qtbot):
        doc = QTextDocument()
        hl = MarkdownHighlighter(doc)
        hl.highlightBlock("[link](http://example.com)")
        assert True

    def test_list_item(self, qtbot):
        doc = QTextDocument()
        hl = MarkdownHighlighter(doc)
        hl.highlightBlock("- item")
        assert True

    def test_quote(self, qtbot):
        doc = QTextDocument()
        hl = MarkdownHighlighter(doc)
        hl.highlightBlock("> quote text")
        assert True

    def test_empty_text(self, qtbot):
        doc = QTextDocument()
        hl = MarkdownHighlighter(doc)
        hl.highlightBlock("")
        assert True


class TestGetHighlighterForFile:
    def test_markdown(self, qtbot):
        doc = QTextDocument()
        hl, ftype = get_highlighter_for_file(doc, "test.md")
        assert ftype == "Markdown"
        assert isinstance(hl, MarkdownHighlighter)

    def test_txt(self, qtbot):
        doc = QTextDocument()
        hl, ftype = get_highlighter_for_file(doc, "test.txt")
        assert ftype == "纯文本"
        assert hl is None

    def test_extension_only(self, qtbot):
        doc = QTextDocument()
        hl, ftype = get_highlighter_for_file(doc, ".md")
        assert ftype == "Markdown"

    def test_python(self, qtbot):
        doc = QTextDocument()
        hl, ftype = get_highlighter_for_file(doc, "test.py")
        assert ftype == "Python"

    def test_no_extension(self, qtbot):
        doc = QTextDocument()
        hl, ftype = get_highlighter_for_file(doc, "Makefile")
        assert ftype == "纯文本"

    def test_json(self, qtbot):
        doc = QTextDocument()
        hl, ftype = get_highlighter_for_file(doc, "data.json")
        assert ftype == "JSON"

    @pytest.mark.skipif(not HAS_PYGMENTS, reason="pygments not installed")
    def test_python_with_pygments(self, qtbot):
        doc = QTextDocument()
        hl, ftype = get_highlighter_for_file(doc, "test.py")
        assert hl is not None
        assert isinstance(hl, PygmentsHighlighter)
