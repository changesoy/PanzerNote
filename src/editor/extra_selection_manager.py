# -*- coding: utf-8 -*-
"""
额外选区管理器

统一管理编辑器的所有高亮层，避免各模块直接调用 setExtraSelections()
导致互相覆盖。支持按层名注册/清除选区，最终合并后一次性设置。
"""

from typing import Dict, List, Optional

from PyQt6.QtWidgets import QTextEdit
from PyQt6.QtGui import QColor, QTextCursor, QTextFormat


class ExtraSelectionManager:
    """管理编辑器多层级 ExtraSelection

    使用方式：
        mgr = ExtraSelectionManager(editor)
        mgr.set_layer("current_line", [current_line_sel])
        mgr.set_layer("search_matches", match_sels)
        mgr.clear_layer("search_matches")
        mgr.refresh()
    """

    def __init__(self, editor):
        self._editor = editor
        self._layers: Dict[str, List[QTextEdit.ExtraSelection]] = {}

    def set_layer(self, name: str, selections: List[QTextEdit.ExtraSelection]):
        """设置或更新一个高亮层"""
        self._layers[name] = list(selections)

    def clear_layer(self, name: str):
        """清除一个高亮层"""
        self._layers.pop(name, None)

    def clear_all(self):
        """清除所有层"""
        self._layers.clear()

    def refresh(self):
        """合并所有层并应用到编辑器"""
        merged = []
        for name in ("current_line", "bookmarks", "diagnostics",
                     "search_matches", "current_search_match", "temporary_marks"):
            layer = self._layers.get(name)
            if layer:
                merged.extend(layer)
        self._editor.setExtraSelections(merged)
