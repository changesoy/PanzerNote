# -*- coding: utf-8 -*-
"""
统一错误提示系统

提供用户友好的错误提示机制，替代原始的异常堆栈展示。
所有错误提示必须包含：
  - 简明的错误描述（非技术语言）
  - 至少一项建议操作
  - 错误分类标识

安全要求：严格过滤错误信息，确保不泄露任何内部路径、堆栈跟踪或敏感信息。

用法:
    from src.utils.error_handler import ErrorHandler, ErrorCategory

    # 显示文件错误
    ErrorHandler.show_error(
        category=ErrorCategory.FILE,
        title="文件保存失败",
        message="无法保存当前文件",
        suggestion="请检查文件是否被其他程序占用，或尝试另存为新文件。"
    )

    # 从异常自动生成提示
    ErrorHandler.show_from_exception(
        exception=IOError("disk full"),
        category=ErrorCategory.FILE,
        title="文件保存失败"
    )

    # 注册自定义错误处理器
    ErrorHandler.register_handler(ErrorCategory.NETWORK, my_network_handler)
"""

import re
from enum import Enum, auto
from typing import Callable, Dict, Optional

from .logger import get_logger


class ErrorCategory(Enum):
    """错误分类"""
    FILE = auto()
    NETWORK = auto()
    CONFIG = auto()
    GAME = auto()
    EDITOR = auto()
    PERMISSION = auto()
    MEMORY = auto()
    GENERAL = auto()


_CATEGORY_LABELS = {
    ErrorCategory.FILE: "文件错误",
    ErrorCategory.NETWORK: "网络错误",
    ErrorCategory.CONFIG: "配置错误",
    ErrorCategory.GAME: "游戏错误",
    ErrorCategory.EDITOR: "编辑器错误",
    ErrorCategory.PERMISSION: "权限错误",
    ErrorCategory.MEMORY: "内存错误",
    ErrorCategory.GENERAL: "错误",
}

_SENSITIVE_PATTERNS = [
    re.compile(r'[A-Z]:\\\S*', re.IGNORECASE),
    re.compile(r'/home/\S*'),
    re.compile(r'/Users/\S*'),
    re.compile(r'/tmp/\S*'),
    re.compile(r'Traceback[\s\S]*'),
    re.compile(r'File\s+"[^"]*",\s*line\s+\d+'),
    re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'),
    re.compile(r'password\s*=\s*\S+', re.IGNORECASE),
    re.compile(r'token\s*=\s*\S+', re.IGNORECASE),
    re.compile(r'secret\s*=\s*\S+', re.IGNORECASE),
    re.compile(r'(?:api_?key|private_?key|access_?key)\s*=\s*\S+', re.IGNORECASE),
    re.compile(r'\bkey\s*=\s*\S+', re.IGNORECASE),
]

_SUGGESTION_MAP = {
    ErrorCategory.FILE: "请检查文件是否存在、是否被其他程序占用，或尝试重新打开文件。",
    ErrorCategory.NETWORK: "请检查网络连接是否正常，或稍后重试。",
    ErrorCategory.CONFIG: "请检查配置文件是否正确，或尝试恢复默认设置。",
    ErrorCategory.GAME: "游戏数据可能已损坏，请尝试重新启动应用。",
    ErrorCategory.EDITOR: "请尝试重新打开文件或重启应用。",
    ErrorCategory.PERMISSION: "请检查文件或目录的访问权限。",
    ErrorCategory.MEMORY: "请关闭不需要的标签页或重启应用以释放内存。",
    ErrorCategory.GENERAL: "请尝试重新操作，如问题持续请重启应用。",
}


def _sanitize_message(text: str) -> str:
    """过滤敏感信息

    移除路径、堆栈跟踪、IP 地址、密码等敏感内容。

    Args:
        text: 原始文本

    Returns:
        过滤后的安全文本
    """
    result = text
    for pattern in _SENSITIVE_PATTERNS:
        result = pattern.sub("[已过滤]", result)
    return result


class _ErrorDialog:
    """错误对话框（延迟导入以避免循环依赖）"""

    @staticmethod
    def show(
        category: ErrorCategory,
        title: str,
        message: str,
        suggestion: Optional[str] = None,
        detail: str = "",
    ) -> None:
        try:
            from PyQt6.QtWidgets import QMessageBox, QApplication

            app = QApplication.instance()
            if app is None:
                return

            safe_message = _sanitize_message(message)
            safe_detail = _sanitize_message(detail) if detail else ""

            category_label = _CATEGORY_LABELS.get(category, "错误")

            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle(f"PanzerNote - {category_label}")
            msg_box.setText(title)

            informative = safe_message
            if suggestion:
                informative += f"\n\n💡 建议：{suggestion}"
            msg_box.setInformativeText(informative)

            if safe_detail:
                msg_box.setDetailedText(safe_detail)

            msg_box.setStyleSheet("""
                QMessageBox {
                    font-family: "Microsoft YaHei";
                }
                QMessageBox QLabel {
                    font-size: 13px;
                    min-width: 300px;
                }
                QPushButton {
                    padding: 6px 20px;
                    min-width: 80px;
                }
            """)

            msg_box.exec()
        except Exception:
            get_logger(__name__).error("显示错误对话框失败")


class ErrorHandler:
    """统一错误提示处理器"""

    _handlers: Dict[ErrorCategory, Callable] = {}
    _dialog = _ErrorDialog()

    @classmethod
    def show_error(
        cls,
        category: ErrorCategory,
        title: str,
        message: str,
        suggestion: Optional[str] = None,
        detail: str = "",
    ) -> None:
        """显示用户友好的错误提示

        Args:
            category: 错误分类
            title: 错误标题（简明描述）
            message: 错误详情（非技术语言）
            suggestion: 建议操作
            detail: 技术详情（仅在详情按钮中展示，已过滤敏感信息）
        """
        logger = get_logger(__name__)
        logger.error("[%s] %s: %s", category.name, title, message)

        if suggestion is None:
            suggestion = _SUGGESTION_MAP.get(category, _SUGGESTION_MAP[ErrorCategory.GENERAL])

        handler = cls._handlers.get(category)
        if handler:
            try:
                handler(category, title, message, suggestion, detail)
                return
            except Exception:
                logger.warning("自定义错误处理器执行失败，回退到默认对话框")

        cls._dialog.show(category, title, message, suggestion, detail)

    @classmethod
    def show_from_exception(
        cls,
        exception: BaseException,
        category: ErrorCategory = ErrorCategory.GENERAL,
        title: Optional[str] = None,
        suggestion: Optional[str] = None,
    ) -> None:
        """从异常对象生成并显示错误提示

        自动将异常信息转换为用户友好的提示，
        原始异常信息仅在详情中展示（已过滤敏感信息）。

        Args:
            exception: 异常对象
            category: 错误分类
            title: 错误标题，默认使用异常类型名
            suggestion: 建议操作
        """
        if title is None:
            title = f"操作失败"

        safe_message = _sanitize_message(str(exception))

        cls.show_error(
            category=category,
            title=title,
            message=safe_message,
            suggestion=suggestion,
        )

    @classmethod
    def register_handler(cls, category: ErrorCategory, handler: Callable) -> None:
        """注册自定义错误处理器

        Args:
            category: 要处理的错误分类
            handler: 处理器函数，签名为 (category, title, message, suggestion, detail) -> None
        """
        cls._handlers[category] = handler

    @classmethod
    def unregister_handler(cls, category: ErrorCategory) -> None:
        """移除自定义错误处理器

        Args:
            category: 要移除处理器的错误分类
        """
        cls._handlers.pop(category, None)

    @classmethod
    def sanitize(cls, text: str) -> str:
        """过滤文本中的敏感信息（公开接口）

        Args:
            text: 原始文本

        Returns:
            过滤后的安全文本
        """
        return _sanitize_message(text)
