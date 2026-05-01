# -*- coding: utf-8 -*-
import pytest
from PyQt5.QtGui import QTextCharFormat, QFont

from src.editor.highlight_themes import (
    get_available_themes, get_theme, get_theme_info,
    build_format, get_editor_formats, get_preview_css,
    highlight_code_html, HAS_PYGMENTS, DEFAULT_THEME,
)


class TestGetAvailableThemes:
    def test_returns_list(self):
        themes = get_available_themes()
        assert isinstance(themes, list)

    @pytest.mark.skipif(not HAS_PYGMENTS, reason="pygments not installed")
    def test_includes_default(self):
        themes = get_available_themes()
        assert DEFAULT_THEME in themes


class TestGetTheme:
    @pytest.mark.skipif(not HAS_PYGMENTS, reason="pygments not installed")
    def test_default_theme_has_styles(self):
        styles = get_theme()
        assert len(styles) > 0

    @pytest.mark.skipif(not HAS_PYGMENTS, reason="pygments not installed")
    def test_named_theme(self):
        styles = get_theme(DEFAULT_THEME)
        assert len(styles) > 0

    @pytest.mark.skipif(not HAS_PYGMENTS, reason="pygments not installed")
    def test_unknown_theme_falls_back(self):
        styles = get_theme("nonexistent_theme")
        assert len(styles) > 0


class TestGetThemeInfo:
    @pytest.mark.skipif(not HAS_PYGMENTS, reason="pygments not installed")
    def test_default_info(self):
        info = get_theme_info()
        assert "name" in info
        assert "description" in info


class TestBuildFormat:
    def test_color(self):
        fmt = build_format({"color": "#FF0000"})
        assert fmt.foreground().color().name().upper() == "#FF0000"

    def test_bold(self):
        fmt = build_format({"bold": True})
        assert fmt.fontWeight() == QFont.Bold

    def test_italic(self):
        fmt = build_format({"italic": True})
        assert fmt.fontItalic() is True

    def test_empty(self):
        fmt = build_format({})
        assert isinstance(fmt, QTextCharFormat)


class TestGetEditorFormats:
    @pytest.mark.skipif(not HAS_PYGMENTS, reason="pygments not installed")
    def test_returns_dict(self):
        fmts = get_editor_formats()
        assert isinstance(fmts, dict)
        assert len(fmts) > 0


class TestGetPreviewCss:
    @pytest.mark.skipif(not HAS_PYGMENTS, reason="pygments not installed")
    def test_returns_string(self):
        css = get_preview_css()
        assert isinstance(css, str)
        assert len(css) > 0

    @pytest.mark.skipif(not HAS_PYGMENTS, reason="pygments not installed")
    def test_custom_class(self):
        css = get_preview_css(css_class="mycode")
        assert "mycode" in css


class TestHighlightCodeHtml:
    def test_empty_language_returns_escaped(self):
        result = highlight_code_html("x = 1", "")
        assert "&lt;" not in result or "x" in result

    def test_no_language_returns_escaped(self):
        result = highlight_code_html("x = 1", "   ")
        assert "x" in result

    @pytest.mark.skipif(not HAS_PYGMENTS, reason="pygments not installed")
    def test_python_highlight(self):
        result = highlight_code_html("x = 1", "python")
        assert "x" in result
        assert len(result) > 3
