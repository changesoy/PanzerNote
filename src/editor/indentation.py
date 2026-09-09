# -*- coding: utf-8 -*-
"""
编辑器缩进统一入口

提供缩进宽度和缩进文本单元的唯一获取方式。
所有缩进相关逻辑（Tab 插入、回车自动缩进、选区缩进/反缩进、
格式化缩进、TabStopDistance）必须从此模块读取，禁止局部硬编码。
"""

from .editor_actions import EditorActionsMixin  # noqa: F401  # 供类型标注引用


def get_indent_width(config) -> int:
    """获取一级缩进的视觉宽度（字符数）

    返回缩进级别对应的空格数。当 use_tabs=True 时，
    返回的是制表符的显示宽度，而非文本长度。
    """
    try:
        return int(config.get_editor_setting("indent_size", 4))
    except (ValueError, TypeError):
        return 4


def get_indent_unit(config) -> str:
    """获取一级缩进的文本单元

    use_tabs=False 时返回 indent_size 个空格；
    use_tabs=True  时返回单个制表符 \\t。
    """
    try:
        if config.get_editor_setting("use_tabs", False):
            return "\t"
    except Exception:
        pass
    return " " * get_indent_width(config)
