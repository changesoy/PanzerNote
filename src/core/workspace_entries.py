# -*- coding: utf-8 -*-
"""
workspace 序列化适配层（Wave 4 批次 D2）

SharedDocument / ViewState ↔ workspace.json open_files 条目的纯函数转换
（workspace schema 不动）：
- 具名文件条目：{path, cursor_position, scroll_position}
- 未命名条目：{is_new, untitled_number, display_name, content}
  （content 仅 dirty 时携带，恢复编辑现场）

本模块是 workspace 序列化的唯一出口（D4 删除 document_model.py 后）。
"""

from typing import Any, Dict, Optional


def named_entry(
    filepath: str,
    cursor_position: Optional[int],
    scroll_position: Optional[int],
) -> Dict[str, Any]:
    """具名文件 → workspace 条目（cursor/scroll 缺失按 0 导出）。"""
    return {
        "path": filepath,
        "cursor_position": cursor_position or 0,
        "scroll_position": scroll_position or 0,
    }


def untitled_entry(
    display_name: str,
    untitled_number: Optional[int],
    content: Optional[str],
) -> Dict[str, Any]:
    """未命名文件 → workspace 条目（编号缺省按 1，dirty 时带 content）。"""
    return {
        "is_new": True,
        "untitled_number": untitled_number or 1,
        "display_name": display_name,
        "content": content,
    }
