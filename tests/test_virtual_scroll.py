# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QPlainTextEdit

from src.editor.virtual_scroll import LazyHighlightManager, LARGE_FILE_THRESHOLD
from src.utils.feature_flags import set_enabled, is_enabled


@pytest.fixture
def editor(qtbot):
    e = QPlainTextEdit()
    qtbot.addWidget(e)
    return e


@pytest.fixture
def manager(editor):
    m = LazyHighlightManager(editor)
    return m


@pytest.fixture(autouse=True)
def enable_lazy_highlight():
    set_enabled("lazy_highlight", True)
    yield
    set_enabled("lazy_highlight", False)


class TestLoadContentNormal:
    def test_returns_false_when_disabled(self, manager):
        set_enabled("lazy_highlight", False)
        content = "\n".join(["line"] * (LARGE_FILE_THRESHOLD + 1))
        assert manager.load_content(content) is False

    def test_returns_false_for_small_file(self, manager):
        content = "\n".join(["line"] * 100)
        assert manager.load_content(content) is False

    def test_returns_true_for_large_file(self, manager):
        content = "\n".join(["line"] * (LARGE_FILE_THRESHOLD + 1))
        assert manager.load_content(content) is True

    def test_sets_is_large_file_true(self, manager):
        content = "\n".join(["line"] * (LARGE_FILE_THRESHOLD + 1))
        manager.load_content(content)
        assert manager.is_active() is True

    def test_content_loaded_in_editor(self, manager, editor):
        content = "\n".join(["line"] * (LARGE_FILE_THRESHOLD + 1))
        manager.load_content(content)
        assert editor.toPlainText() == content

    def test_exact_threshold_returns_true(self, manager):
        content = "\n".join(["line"] * LARGE_FILE_THRESHOLD)
        assert manager.load_content(content) is True

    def test_one_below_threshold_returns_false(self, manager):
        content = "\n".join(["line"] * (LARGE_FILE_THRESHOLD - 1))
        assert manager.load_content(content) is False


class TestLoadContentExceptionFallback:
    def test_setPlainText_exception_returns_false(self, manager, editor):
        content = "\n".join(["line"] * (LARGE_FILE_THRESHOLD + 1))
        with patch.object(QPlainTextEdit, 'setPlainText', side_effect=MemoryError("out of memory")):
            result = manager.load_content(content)
        assert result is False

    def test_setPlainText_exception_resets_is_large_file(self, manager, editor):
        content = "\n".join(["line"] * (LARGE_FILE_THRESHOLD + 1))
        with patch.object(QPlainTextEdit, 'setPlainText', side_effect=MemoryError("out of memory")):
            manager.load_content(content)
        assert manager._is_large_file is False

    def test_setPlainText_exception_is_active_false(self, manager, editor):
        content = "\n".join(["line"] * (LARGE_FILE_THRESHOLD + 1))
        with patch.object(QPlainTextEdit, 'setPlainText', side_effect=MemoryError("out of memory")):
            manager.load_content(content)
        assert manager.is_active() is False

    def test_setPlainText_exception_logs_error(self, manager, editor):
        content = "\n".join(["line"] * (LARGE_FILE_THRESHOLD + 1))
        with patch.object(QPlainTextEdit, 'setPlainText', side_effect=RuntimeError("test error")):
            with patch('src.editor.virtual_scroll.get_logger') as mock_logger:
                mock_log_instance = MagicMock()
                mock_logger.return_value = mock_log_instance
                manager.load_content(content)
                mock_log_instance.error.assert_called_once()
                call_args = mock_log_instance.error.call_args
                assert "延迟高亮加载失败" in call_args[0][0]
                assert call_args[1].get("exc_info") is True

    def test_setPlainText_exception_restores_highlighter_document(self, manager, editor):
        mock_highlighter = MagicMock()
        manager.set_highlighter(mock_highlighter)

        content = "\n".join(["line"] * (LARGE_FILE_THRESHOLD + 1))
        with patch.object(QPlainTextEdit, 'setPlainText', side_effect=MemoryError("out of memory")):
            manager.load_content(content)

        mock_highlighter.setDocument.assert_any_call(editor.document())

    def test_runtime_error_fallback(self, manager, editor):
        content = "\n".join(["line"] * (LARGE_FILE_THRESHOLD + 1))
        with patch.object(QPlainTextEdit, 'setPlainText', side_effect=RuntimeError("Qt internal error")):
            result = manager.load_content(content)
        assert result is False
        assert manager._is_large_file is False

    def test_value_error_fallback(self, manager, editor):
        content = "\n".join(["line"] * (LARGE_FILE_THRESHOLD + 1))
        with patch.object(QPlainTextEdit, 'setPlainText', side_effect=ValueError("bad content")):
            result = manager.load_content(content)
        assert result is False
        assert manager._is_large_file is False

    def test_fallback_without_highlighter(self, manager, editor):
        manager.set_highlighter(None)
        content = "\n".join(["line"] * (LARGE_FILE_THRESHOLD + 1))
        with patch.object(QPlainTextEdit, 'setPlainText', side_effect=MemoryError("out of memory")):
            result = manager.load_content(content)
        assert result is False
        assert manager._is_large_file is False

    def test_successful_load_after_previous_failure(self, manager, editor):
        content = "\n".join(["line"] * (LARGE_FILE_THRESHOLD + 1))
        with patch.object(QPlainTextEdit, 'setPlainText', side_effect=MemoryError("out of memory")):
            manager.load_content(content)
        assert manager._is_large_file is False

        result = manager.load_content(content)
        assert result is True
        assert manager._is_large_file is True


class TestLoadContentEdgeCases:
    def test_empty_content(self, manager):
        assert manager.load_content("") is False

    def test_single_line(self, manager):
        assert manager.load_content("single line") is False

    def test_content_with_only_newlines(self, manager):
        content = "\n" * (LARGE_FILE_THRESHOLD + 1)
        assert manager.load_content(content) is True

    def test_unicode_content(self, manager):
        content = "\n".join(["中文内容🎉"] * (LARGE_FILE_THRESHOLD + 1))
        assert manager.load_content(content) is True
