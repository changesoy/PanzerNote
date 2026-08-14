# -*- coding: utf-8 -*-
"""折叠管理器 —— Markdown 标题折叠 + 代码缩进折叠，统一管理折叠区间、可见性切换、自动展开"""

from __future__ import annotations

from typing import List, Optional, Set, Dict, Tuple

from PyQt6.QtCore import pyqtSignal, QObject
from PyQt6.QtGui import QTextDocument

from src.editor.outline_parser import parse_headings, Heading


class FoldingManager(QObject):
    """管理 Markdown 标题折叠 + 代码缩进折叠。

    职责：
    - Markdown：根据标题列表计算折叠区间（标题行 → 下一同级/高级标题之前）
    - 代码文件：根据缩进级别计算折叠区间（缩进增加的行可折叠其后内容）
    - 切换折叠（setVisible）
    - 确保某行可见（自动展开包含它的折叠）
    - 提供折叠标记绘制所需的数据
    """

    fold_state_changed = pyqtSignal()
    _FOLD_MARKER_WIDTH = 16  # 折叠标记列的宽度（px）

    def __init__(self, document: QTextDocument, parent: Optional[QObject] = None):
        """document：折叠作用的目标 QTextDocument（共享后为 Document 级单实例）。

        折叠可见性（QTextBlock.setVisible）落在 document 的 block 上；各 View 的
        重绘与预览同步由 fold_state_changed 信号驱动，本管理器不直接触碰 Editor。
        """
        super().__init__(parent)
        self._document = document
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
                doc = self._document
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

    def rebuild_from_indent(self, text: str, indent_size: int) -> None:
        """从文本基于缩进级别重建折叠区间（用于 Python / YAML 等代码文件）。

        算法：
        - 对每行非空非注释行，计算缩进级别 = 前导空白 / indent_size
        - 若紧邻下一非空非注释行缩进更深，则该行可折叠
        - 折叠区间 = [当前行+1, 下一缩进级别 ≤ 当前级别的行-1]
        - 空行和注释行归属到其上方最近的折叠区间
        """
        self._headings = []
        self._fold_ranges.clear()

        lines = text.split('\n')
        n = len(lines)
        if n == 0:
            return

        if indent_size < 1:
            indent_size = 4

        # 逐行计算缩进级别（跳过空行和纯注释行）
        indent_levels: Dict[int, int] = {}
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            leading = len(line) - len(line.lstrip())
            tab_count = line[:leading].count('\t')
            spaces = leading - tab_count
            level = (tab_count * indent_size + spaces) // indent_size
            indent_levels[i + 1] = level  # 1-based 行号

        # 构建折叠区间：仅当紧邻下一非空行缩进更深时，当前行可折叠
        for line_num, level in indent_levels.items():
            # 找到紧邻的下一非空非注释行
            next_meaningful: Optional[int] = None
            for scan in range(line_num + 1, n + 1):
                if scan in indent_levels:
                    next_meaningful = scan
                    break

            if next_meaningful is None:
                continue

            if indent_levels[next_meaningful] <= level:
                continue  # 下一行没更深，不可折叠

            # 可折叠：计算区间终点（到下一缩进级别 ≤ 当前的行之前）
            first_child = line_num + 1
            section_end = n + 1  # 默认到文件末尾
            for scan in range(next_meaningful + 1, n + 1):
                if scan in indent_levels and indent_levels[scan] <= level:
                    section_end = scan
                    break

            self._fold_ranges[line_num] = (first_child, section_end - 1)

        # 清理不再有效的折叠状态
        valid = set(self._fold_ranges.keys())
        self._collapsed_blocks &= valid

    def fold_imports(self, text: str) -> None:
        """为 Python 文件追加 import 折叠区间。

        两层策略：
        1. AST — 多行 import（如 from X import (\\n...\\n)）
        2. 分组 — ≥2 行连续的 import/from 单行，首行可折叠整组
        在 rebuild_from_indent 之后调用。仅 Python 文件使用。
        """
        import ast
        import re

        # ── 1. AST：多行 import ──
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None

        if tree is not None:
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                if node.end_lineno is None or node.end_lineno <= node.lineno:
                    continue
                self._fold_ranges[node.lineno] = (node.lineno + 1, node.end_lineno)

        # ── 2. 分组：连续 import/from 单行，容忍 ≤4 行非 import 间隔 ──
        lines = text.split('\n')
        n = len(lines)
        IMPORT_RE = re.compile(r'^(import\s|from\s)')
        i = 0
        while i < n:
            stripped = lines[i].strip()
            if not IMPORT_RE.match(stripped):
                i += 1
                continue

            group_start = i
            consecutive_non = 0
            first_non_pos = -1
            i += 1
            while i < n:
                stripped = lines[i].strip()
                if IMPORT_RE.match(stripped):
                    i += 1
                    consecutive_non = 0
                    first_non_pos = -1
                else:
                    if consecutive_non == 0:
                        first_non_pos = i
                    consecutive_non += 1
                    if consecutive_non >= 5:
                        break
                    i += 1

            if consecutive_non >= 5 and first_non_pos >= 0:
                group_end = first_non_pos - 1
            else:
                group_end = i - 1

            if group_end > group_start:
                start_line = group_start + 1
                end_line = group_end + 1
                if start_line not in self._fold_ranges:
                    self._fold_ranges[start_line] = (start_line + 1, end_line)

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

        doc = self._document
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

        self.fold_state_changed.emit()

    def toggle_fold_all(self) -> None:
        """全部折叠或全部展开（toggle）。"""
        if self.all_collapsed:
            self._expand_all()
        else:
            self._collapse_all()

    def _collapse_all(self) -> None:
        """折叠所有可折叠区域。"""
        doc = self._document
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

        self.fold_state_changed.emit()

    def _expand_all(self) -> None:
        """展开所有折叠区域。"""
        doc = self._document
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

        self.fold_state_changed.emit()

    def _restore_nested_folds(self, parent_heading_line: int) -> None:
        """展开父标题后，恢复其子标题的折叠状态。

        遍历父标题子区间内所有已折叠的子标题，重新隐藏它们的子内容。
        """
        if parent_heading_line not in self._fold_ranges:
            return
        doc = self._document
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

        doc = self._document
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
            self.fold_state_changed.emit()

    def is_line_visible(self, line: int) -> bool:
        """第 line 行（1-based）是否可见。"""
        doc = self._document
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
        doc = self._document
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
            self.fold_state_changed.emit()

    @property
    def visible_block_count(self) -> int:
        """返回可见 block 数（供 minimap 使用）。"""
        doc = self._document
        if doc is None:
            return 0
        count = 0
        block = doc.begin()
        while block.isValid():
            if block.isVisible():
                count += 1
            block = block.next()
        return count
