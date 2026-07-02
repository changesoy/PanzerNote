# -*- coding: utf-8 -*-
"""Markdown 标题折叠 —— 折叠区间计算、可见性切换、自动展开"""

from __future__ import annotations

from typing import List, Set, Dict, Tuple

from PyQt6.QtCore import pyqtSignal, QObject
from PyQt6.QtWidgets import QPlainTextEdit

from src.editor.outline_parser import parse_headings, Heading


class FoldingManager(QObject):
    """管理 Markdown 标题折叠。

    职责：
    - 根据标题列表计算折叠区间（标题行 → 下一同级/高级标题之前）
    - 切换折叠（setVisible）
    - 确保某行可见（自动展开包含它的折叠）
    - 提供折叠标记绘制所需的数据
    """

    fold_state_changed = pyqtSignal()
    _FOLD_MARKER_WIDTH = 16  # 折叠标记列的宽度（px）

    def __init__(self, editor: QPlainTextEdit):
        super().__init__(editor)
        self._editor = editor
        self._collapsed_blocks: Set[int] = set()  # 被折叠的标题行 blockNumber
        self._headings: List[Heading] = []  # (level, line_num, title)
        self._fold_ranges: Dict[int, Tuple[int, int]] = {}  # heading_line → (first_child, last_child)

    # ========== 折叠标记列宽度 ==========

    @property
    def fold_marker_width(self) -> int:
        return self._FOLD_MARKER_WIDTH

    # ========== 区间计算 ==========

    def rebuild_from_text(self, text: str) -> None:
        """从文档文本重建折叠区间（标题切换后调用）。"""
        self._headings = parse_headings(text)
        self._fold_ranges.clear()

        for i, (level, line_num, _) in enumerate(self._headings):
            # 找到下一个 ≤ 当前层级的标题
            child_end = None
            for j in range(i + 1, len(self._headings)):
                next_level, next_line, _ = self._headings[j]
                if next_level <= level:
                    child_end = next_line - 1  # 到下一同级/高级标题前一行
                    break
            if child_end is None:
                # 没有后续同级或更高级标题 → 到文档末尾
                doc = self._editor.document()
                if doc is not None:
                    child_end = doc.blockCount()
                else:
                    continue

            first_child = line_num + 1
            if first_child <= child_end:
                self._fold_ranges[line_num] = (first_child, child_end)

        # 清理不再有效的折叠状态
        valid = set(self._fold_ranges.keys())
        self._collapsed_blocks &= valid

    def get_foldable_headings(self) -> List[Tuple[int, bool]]:
        """返回 [(line_num, is_collapsed)] — 所有可折叠标题行及其折叠状态。"""
        result: List[Tuple[int, bool]] = []
        for heading_line in sorted(self._fold_ranges.keys()):
            result.append((heading_line, heading_line in self._collapsed_blocks))
        return result

    def is_foldable(self, block_number: int) -> bool:
        """该 block 是否为可折叠标题行。"""
        return (block_number + 1) in self._fold_ranges

    @property
    def all_collapsed(self) -> bool:
        """是否所有可折叠区域都已折叠。"""
        if not self._fold_ranges:
            return False
        return self._collapsed_blocks == set(self._fold_ranges.keys())

    # ========== 折叠/展开 ==========

    def toggle_fold(self, block_number: int) -> None:
        """切换指定标题行的折叠状态。"""
        heading_line = block_number + 1
        if heading_line not in self._fold_ranges:
            return

        doc = self._editor.document()
        if doc is None:
            return

        first_child, last_child = self._fold_ranges[heading_line]
        if heading_line in self._collapsed_blocks:
            # 展开
            self._collapsed_blocks.discard(heading_line)
            for line in range(first_child, last_child + 1):
                block = doc.findBlockByNumber(line - 1)
                if block.isValid():
                    block.setVisible(True)
            # 恢复嵌套子折叠
            self._restore_nested_folds(heading_line)
        else:
            # 折叠
            self._collapsed_blocks.add(heading_line)
            for line in range(first_child, last_child + 1):
                block = doc.findBlockByNumber(line - 1)
                if block.isValid():
                    block.setVisible(False)

        self._editor.viewport().update()
        self._editor.line_number_area.update()
        self.fold_state_changed.emit()

    def toggle_fold_all(self) -> None:
        """全部折叠或全部展开（toggle）。"""
        if self.all_collapsed:
            self._expand_all()
        else:
            self._collapse_all()

    def _collapse_all(self) -> None:
        """折叠所有可折叠区域。"""
        doc = self._editor.document()
        if doc is None:
            return

        for heading_line, (first_child, last_child) in self._fold_ranges.items():
            if heading_line in self._collapsed_blocks:
                continue
            self._collapsed_blocks.add(heading_line)
            for line in range(first_child, last_child + 1):
                block = doc.findBlockByNumber(line - 1)
                if block.isValid():
                    block.setVisible(False)

        self._editor.viewport().update()
        self._editor.line_number_area.update()
        self.fold_state_changed.emit()

    def _expand_all(self) -> None:
        """展开所有折叠区域。"""
        doc = self._editor.document()
        if doc is None:
            return

        # 先全部展开（setVisible + 清空 collapsed）
        all_collapsed = list(self._collapsed_blocks)
        self._collapsed_blocks.clear()
        for heading_line in all_collapsed:
            _, (first_child, last_child) = heading_line, self._fold_ranges[heading_line]
            for line in range(first_child, last_child + 1):
                block = doc.findBlockByNumber(line - 1)
                if block.isValid():
                    block.setVisible(True)

        self._editor.viewport().update()
        self._editor.line_number_area.update()
        self.fold_state_changed.emit()

    def _restore_nested_folds(self, parent_heading_line: int) -> None:
        """展开父标题后，恢复其子标题的折叠状态。

        遍历父标题子区间内所有已折叠的子标题，重新隐藏它们的子内容。
        """
        if parent_heading_line not in self._fold_ranges:
            return
        doc = self._editor.document()
        if doc is None:
            return

        parent_first, parent_last = self._fold_ranges[parent_heading_line]
        nested: List[int] = []
        for heading_line in self._collapsed_blocks:
            if parent_first <= heading_line <= parent_last:
                nested.append(heading_line)

        for heading_line in nested:
            if heading_line not in self._fold_ranges:
                continue
            first_child, last_child = self._fold_ranges[heading_line]
            for line in range(first_child, last_child + 1):
                block = doc.findBlockByNumber(line - 1)
                if block.isValid():
                    block.setVisible(False)

    # ========== 自动展开 ==========

    def ensure_visible(self, line: int) -> None:
        """确保第 line 行（1-based）可见——展开所有包含该行的折叠。

        无副作用返回（不影响已展开区域）。
        """
        to_expand: List[int] = []
        for heading_line, (first_child, last_child) in self._fold_ranges.items():
            if heading_line in self._collapsed_blocks:
                if first_child <= line <= last_child:
                    to_expand.append(heading_line)

        if not to_expand:
            return

        doc = self._editor.document()
        if doc is None:
            return

        for heading_line in to_expand:
            self._collapsed_blocks.discard(heading_line)
            _, (first_child, last_child) = heading_line, self._fold_ranges[heading_line]
            for l in range(first_child, last_child + 1):
                block = doc.findBlockByNumber(l - 1)
                if block.isValid():
                    block.setVisible(True)
            # 恢复嵌套子折叠
            self._restore_nested_folds(heading_line)

        if to_expand:
            self._editor.viewport().update()
            self._editor.line_number_area.update()

    def is_line_visible(self, line: int) -> bool:
        """第 line 行（1-based）是否可见。"""
        doc = self._editor.document()
        if doc is None:
            return True
        block = doc.findBlockByNumber(line - 1)
        return bool(block.isValid() and block.isVisible())

    # ========== 持久化 ==========

    def get_collapsed_lines(self) -> List[int]:
        """返回所有被折叠标题的行号列表（1-based），用于持久化。"""
        return sorted(self._collapsed_blocks)

    def set_collapsed_lines(self, lines: List[int]) -> None:
        """从持久化数据恢复折叠状态（1-based 行号列表）。

        调用方需在 rebuild_from_text 之后调用。
        """
        doc = self._editor.document()
        if doc is None:
            return

        valid = set(self._fold_ranges.keys())
        for line in lines:
            if line not in valid:
                continue
            self._collapsed_blocks.add(line)
            first_child, last_child = self._fold_ranges[line]
            for l in range(first_child, last_child + 1):
                block = doc.findBlockByNumber(l - 1)
                if block.isValid():
                    block.setVisible(False)

        if self._collapsed_blocks:
            self._editor.viewport().update()
            self._editor.line_number_area.update()

    @property
    def visible_block_count(self) -> int:
        """返回可见 block 数（供 minimap 使用）。"""
        doc = self._editor.document()
        if doc is None:
            return 0
        count = 0
        block = doc.begin()
        while block.isValid():
            if block.isVisible():
                count += 1
            block = block.next()
        return count
