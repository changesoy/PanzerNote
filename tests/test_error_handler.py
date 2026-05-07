# -*- coding: utf-8 -*-
import pytest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

from src.utils.error_handler import (
    ErrorHandler, ErrorCategory, _sanitize_message,
    _CATEGORY_LABELS, _SUGGESTION_MAP, _ErrorDialog
)


class TestSanitizeMessage:
    def test_windows_path_filtered(self):
        result = _sanitize_message("Error in C:\\Users\\test\\file.txt")
        assert "C:\\Users\\test\\file.txt" not in result
        assert "[已过滤]" in result

    def test_unix_path_filtered(self):
        result = _sanitize_message("Error in /home/user/file.txt")
        assert "/home/user/file.txt" not in result
        assert "[已过滤]" in result

    def test_mac_path_filtered(self):
        result = _sanitize_message("Error in /Users/test/file.txt")
        assert "/Users/test/file.txt" not in result

    def test_tmp_path_filtered(self):
        result = _sanitize_message("Error in /tmp/cache.txt")
        assert "/tmp/cache.txt" not in result

    def test_traceback_filtered(self):
        result = _sanitize_message('Traceback (most recent call last):\n  File "test.py"')
        assert "Traceback" not in result

    def test_file_line_filtered(self):
        result = _sanitize_message('File "src/main.py", line 42')
        assert 'File "src/main.py"' not in result

    def test_ip_address_filtered(self):
        result = _sanitize_message("Connect to 192.168.1.100")
        assert "192.168.1.100" not in result

    def test_password_filtered(self):
        result = _sanitize_message("password=secret123")
        assert "secret123" not in result

    def test_token_filtered(self):
        result = _sanitize_message("token=abc123xyz")
        assert "abc123xyz" not in result

    def test_normal_text_preserved(self):
        result = _sanitize_message("文件保存失败")
        assert result == "文件保存失败"

    def test_empty_string(self):
        result = _sanitize_message("")
        assert result == ""

    def test_key_filtered(self):
        result = _sanitize_message("key=mysecret")
        assert "mysecret" not in result


class TestErrorCategory:
    def test_all_categories_have_labels(self):
        for cat in ErrorCategory:
            assert cat in _CATEGORY_LABELS

    def test_all_categories_have_suggestions(self):
        for cat in ErrorCategory:
            assert cat in _SUGGESTION_MAP

    def test_category_values(self):
        assert ErrorCategory.FILE.value == 1
        assert ErrorCategory.NETWORK.value == 2
        assert ErrorCategory.CONFIG.value == 3
        assert ErrorCategory.GENERAL.value == 8


class TestErrorHandler:
    def test_sanitize_public_interface(self):
        result = ErrorHandler.sanitize("C:\\secret\\path")
        assert "secret" not in result

    def test_register_handler(self):
        called = []

        def handler(category, title, message, suggestion, detail):
            called.append((category, title))

        ErrorHandler.register_handler(ErrorCategory.NETWORK, handler)
        ErrorHandler.show_error(
            category=ErrorCategory.NETWORK,
            title="网络错误",
            message="连接超时",
        )
        assert len(called) == 1
        assert called[0][0] == ErrorCategory.NETWORK
        assert called[0][1] == "网络错误"
        ErrorHandler.unregister_handler(ErrorCategory.NETWORK)

    def test_unregister_handler(self):
        called = []

        def handler(category, title, message, suggestion, detail):
            called.append(title)

        ErrorHandler.register_handler(ErrorCategory.GAME, handler)
        ErrorHandler.unregister_handler(ErrorCategory.GAME)
        ErrorHandler.show_error(
            category=ErrorCategory.GAME,
            title="游戏错误",
            message="数据损坏",
        )
        assert len(called) == 0

    def test_show_from_exception(self):
        called = []

        def handler(category, title, message, suggestion, detail):
            called.append((category, title, message))

        ErrorHandler.register_handler(ErrorCategory.FILE, handler)
        exc = IOError("disk full")
        ErrorHandler.show_from_exception(
            exception=exc,
            category=ErrorCategory.FILE,
            title="保存失败",
        )
        assert len(called) == 1
        assert called[0][0] == ErrorCategory.FILE
        assert called[0][1] == "保存失败"
        ErrorHandler.unregister_handler(ErrorCategory.FILE)

    def test_show_from_exception_sanitizes(self):
        called = []

        def handler(category, title, message, suggestion, detail):
            called.append(message)

        ErrorHandler.register_handler(ErrorCategory.CONFIG, handler)
        exc = IOError("C:\\Users\\admin\\.ssh\\id_rsa")
        ErrorHandler.show_from_exception(
            exception=exc,
            category=ErrorCategory.CONFIG,
        )
        assert len(called) == 1
        assert ".ssh" not in called[0]
        ErrorHandler.unregister_handler(ErrorCategory.CONFIG)

    def test_default_suggestion_provided(self):
        called = []

        def handler(category, title, message, suggestion, detail):
            called.append(suggestion)

        ErrorHandler.register_handler(ErrorCategory.MEMORY, handler)
        ErrorHandler.show_error(
            category=ErrorCategory.MEMORY,
            title="内存不足",
            message="可用内存不足",
        )
        assert len(called) == 1
        assert called[0] != ""
        ErrorHandler.unregister_handler(ErrorCategory.MEMORY)

    def test_custom_suggestion_overrides_default(self):
        called = []

        def handler(category, title, message, suggestion, detail):
            called.append(suggestion)

        ErrorHandler.register_handler(ErrorCategory.PERMISSION, handler)
        ErrorHandler.show_error(
            category=ErrorCategory.PERMISSION,
            title="权限不足",
            message="无法写入文件",
            suggestion="请以管理员身份运行程序。",
        )
        assert len(called) == 1
        assert called[0] == "请以管理员身份运行程序。"
        ErrorHandler.unregister_handler(ErrorCategory.PERMISSION)

    def test_handler_exception_falls_back(self):
        def bad_handler(category, title, message, suggestion, detail):
            raise RuntimeError("handler crashed")

        ErrorHandler.register_handler(ErrorCategory.EDITOR, bad_handler)
        ErrorHandler.show_error(
            category=ErrorCategory.EDITOR,
            title="编辑器错误",
            message="无法打开文件",
        )
        ErrorHandler.unregister_handler(ErrorCategory.EDITOR)


class TestErrorDialog:
    def test_dialog_show_with_suggestion(self, qtbot):
        app = QApplication.instance()
        if app is None:
            pytest.skip("No QApplication available")

        def close_dialog():
            for widget in app.topLevelWidgets():
                if widget.__class__.__name__ == "QMessageBox":
                    widget.accept()

        QTimer.singleShot(100, close_dialog)

        _ErrorDialog.show(
            category=ErrorCategory.FILE,
            title="文件错误",
            message="无法读取文件",
            suggestion="请检查文件是否存在",
        )

    def test_dialog_show_with_detail(self, qtbot):
        app = QApplication.instance()
        if app is None:
            pytest.skip("No QApplication available")

        def close_dialog():
            for widget in app.topLevelWidgets():
                if widget.__class__.__name__ == "QMessageBox":
                    widget.accept()

        QTimer.singleShot(100, close_dialog)

        _ErrorDialog.show(
            category=ErrorCategory.NETWORK,
            title="网络错误",
            message="连接超时",
            detail="Connection refused at 192.168.1.1:8080",
        )

    def test_dialog_show_minimal(self, qtbot):
        app = QApplication.instance()
        if app is None:
            pytest.skip("No QApplication available")

        def close_dialog():
            for widget in app.topLevelWidgets():
                if widget.__class__.__name__ == "QMessageBox":
                    widget.accept()

        QTimer.singleShot(100, close_dialog)

        _ErrorDialog.show(
            category=ErrorCategory.GENERAL,
            title="提示",
            message="操作失败",
        )

    def test_dialog_show_sanitizes_path(self, qtbot):
        app = QApplication.instance()
        if app is None:
            pytest.skip("No QApplication available")

        def close_dialog():
            for widget in app.topLevelWidgets():
                if widget.__class__.__name__ == "QMessageBox":
                    widget.accept()

        QTimer.singleShot(100, close_dialog)

        _ErrorDialog.show(
            category=ErrorCategory.FILE,
            title="路径错误",
            message="无法访问 C:\\Users\\admin\\secret.txt",
            detail="File not found: /home/user/.ssh/config",
        )

    def test_show_error_default_dialog(self, qtbot):
        app = QApplication.instance()
        if app is None:
            pytest.skip("No QApplication available")

        def close_dialog():
            for widget in app.topLevelWidgets():
                if widget.__class__.__name__ == "QMessageBox":
                    widget.accept()

        QTimer.singleShot(100, close_dialog)

        ErrorHandler.show_error(
            category=ErrorCategory.CONFIG,
            title="配置错误",
            message="配置文件损坏",
        )
