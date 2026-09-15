# -*- coding: utf-8 -*-
"""
编辑器辅助操作模块
将行操作、大小写转换、文档格式化等辅助功能从 Editor 中抽离

采用 Mixin 模式，Editor 通过多继承获得这些能力。
"""

import json
import os
import re
import unicodedata
import xml.dom.minidom as minidom
from contextlib import contextmanager
from typing import Callable, Generator, Optional

from PyQt6.QtCore import QBuffer, QIODevice, QMimeData
from PyQt6.QtGui import QImage, QPixmap, QTextCursor
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from ..security.file_access_context import FileAccessContext
from ..utils.logger import get_logger
from .image_asset_service import SUPPORTED_EXTENSIONS, ImageAssetError, ImageAssetService


# 文件选择对话框的图片过滤器（从支持的扩展名派生，避免与落盘白名单漂移）
_IMAGE_FILE_FILTER = "图片 (" + " ".join(
    f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS)
) + ")"


def _to_qimage(image_data: object) -> Optional[QImage]:
    """把 mime 的 imageData 归一化为 QImage（可能是 QImage 或 QPixmap）。"""
    if isinstance(image_data, QPixmap):
        return image_data.toImage()
    if isinstance(image_data, QImage):
        return image_data
    return None


def _encode_png(image: QImage) -> bytes:
    """把 QImage 编码为 PNG 字节（剪贴板截图统一以 PNG 落盘）。"""
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise ImageAssetError("剪贴板图像编码失败")
    data = buffer.data().data()
    buffer.close()
    return data


# alt 文本中会破坏 ![...](...) 结构的字符，插入前需反斜杠转义
_ALT_ESCAPES = str.maketrans({ch: "\\" + ch for ch in "\\[]`"})


def _escape_markdown_alt(alt: str) -> str:
    """转义 alt 中的结构字符，保证插入的图片语法始终解析为标准图片。

    原始文件名可含 `[` `]`（Windows 允许），不转义会使 ![a]b](path) 退化为
    纯文本或普通链接；反斜杠转义是 CommonMark 规定的标准做法。
    """
    return alt.translate(_ALT_ESCAPES)


class EditorActionsMixin:
    """编辑器辅助操作 Mixin

    要求宿主类提供以下属性/方法：
    - textCursor() -> QTextCursor
    - setTextCursor(cursor)
    - toPlainText() -> str
    - setPlainText(text)
    - document() -> QTextDocument
    - ensureCursorVisible()
    - centerCursor()
    - _file_type: str
    """

    @contextmanager
    def programmatic_modify(self) -> Generator[None, None, None]:
        """标记程序化修改的上下文管理器

        Editor 类覆盖此方法以设置 _programmatic_modify 标志，
        防止语法高亮器在程序化修改期间重复触发生成。
        如果宿主类未提供，则默认为空操作。
        """
        yield

    def _get_config_indent(self) -> int:
        """获取编辑器缩进大小配置，使用默认值兜底"""
        from .indentation import get_indent_width
        if hasattr(self, 'config') and self.config is not None:
            return get_indent_width(self.config)
        return 4

    # ═══════════════════ 行操作 ═══════════════════

    def delete_current_line(self) -> None:
        """删除当前行"""
        cursor = self.textCursor()
        cursor.beginEditBlock()

        with self.programmatic_modify():
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)

            if cursor.block().next().isValid():
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
            elif cursor.block().blockNumber() > 0:
                anchor = cursor.position()
                cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter)
                cursor.setPosition(anchor, QTextCursor.MoveMode.KeepAnchor)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            else:
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)

            cursor.removeSelectedText()
        cursor.endEditBlock()

    def copy_line(self) -> None:
        """复制当前行到剪贴板（不删除，不换行）"""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)
        self.copy()
        # 恢复光标位置（copy() 不改变选区，但 QTextEdit.copy 会保持选区）
        # QPlainTextEdit.copy() 不会改变文本，只复制到剪贴板

    def paste_line(self) -> None:
        """粘贴剪贴板内容到当前行下方为新行"""
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        text = clipboard.text()
        if not text:
            return

        cursor = self.textCursor()
        cursor.beginEditBlock()

        with self.programmatic_modify():
            # 移到当前行末尾，插入新行 + 剪贴板内容
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            cursor.insertText('\n' + text)

        cursor.endEditBlock()

    def move_line_up(self) -> None:
        """上移当前行（与上一行交换内容），并让光标跟随到新位置"""
        cursor = self.textCursor()
        current_block = cursor.block()
        current_num = current_block.blockNumber()

        if current_num == 0:
            return

        prev_block = current_block.previous()
        col = cursor.columnNumber()

        current_text = current_block.text()
        prev_text = prev_block.text()

        start_pos = prev_block.position()
        end_pos = current_block.position() + current_block.length()

        cursor.beginEditBlock()

        with self.programmatic_modify():
            cursor.setPosition(start_pos)
            cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)

            trailing_newline = '\n' if current_block.next().isValid() else ''
            cursor.insertText(current_text + '\n' + prev_text + trailing_newline)

        cursor.endEditBlock()

        new_block = self.document().findBlockByNumber(current_num - 1)
        new_pos = new_block.position() + min(col, len(new_block.text()))
        cursor.setPosition(new_pos)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def move_line_down(self) -> None:
        """下移当前行（与下一行交换内容），并让光标跟随到新位置"""
        cursor = self.textCursor()
        current_block = cursor.block()
        current_num = current_block.blockNumber()
        next_block = current_block.next()

        if not next_block.isValid():
            return

        col = cursor.columnNumber()

        current_text = current_block.text()
        next_text = next_block.text()

        start_pos = current_block.position()
        end_pos = next_block.position() + next_block.length()

        cursor.beginEditBlock()

        with self.programmatic_modify():
            cursor.setPosition(start_pos)
            cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)

            trailing_newline = '\n' if next_block.next().isValid() else ''
            cursor.insertText(next_text + '\n' + current_text + trailing_newline)

        cursor.endEditBlock()

        new_block = self.document().findBlockByNumber(current_num + 1)
        new_pos = new_block.position() + min(col, len(new_block.text()))
        cursor.setPosition(new_pos)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    # ═══════════════════ 大小写转换 ═══════════════════

    def toggle_case(self) -> None:
        """切换选中文本的大小写（大写->小写->大写循环）"""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return

        text = cursor.selectedText()
        start = cursor.selectionStart()

        if text.isupper():
            new_text = text.lower()
        elif text.islower():
            new_text = text.upper()
        else:
            new_text = text.upper()

        with self.programmatic_modify():
            cursor.insertText(new_text)

        cursor.setPosition(start)
        cursor.setPosition(start + len(new_text), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)

    def to_uppercase(self) -> None:
        """转换为大写"""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return

        text = cursor.selectedText()
        start = cursor.selectionStart()
        new_text = text.upper()

        with self.programmatic_modify():
            cursor.insertText(new_text)

        cursor.setPosition(start)
        cursor.setPosition(start + len(new_text), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)

    def to_lowercase(self) -> None:
        """转换为小写"""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return

        text = cursor.selectedText()
        start = cursor.selectionStart()
        new_text = text.lower()

        with self.programmatic_modify():
            cursor.insertText(new_text)

        cursor.setPosition(start)
        cursor.setPosition(start + len(new_text), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)

    def to_titlecase(self) -> None:
        """转换为首字母大写"""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return

        text = cursor.selectedText()
        start = cursor.selectionStart()
        new_text = text.title()

        with self.programmatic_modify():
            cursor.insertText(new_text)

        cursor.setPosition(start)
        cursor.setPosition(start + len(new_text), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)

    # ═══════════════════ 转到行 ═══════════════════

    def goto_line(self, line_number: int) -> None:
        """跳转到指定行

        Args:
            line_number: 行号（从1开始）
        """
        max_line = self.document().blockCount()
        line_number = max(1, min(line_number, max_line))

        block = self.document().findBlockByLineNumber(line_number - 1)
        if block.isValid():
            cursor = self.textCursor()
            cursor.setPosition(block.position())
            self.setTextCursor(cursor)
            self.centerCursor()

    # ═══════════════════ 任务列表（阶段 2 F2） ═══════════════════

    _TASK_ROW_RE = re.compile(r"^(\s*[-*+]\s+)\[([ xX])\](.*)$")
    _TASK_BULLET_RE = re.compile(r"^(\s*[-*+]\s+)(?!\[)(.*)$")

    def toggle_task_checkbox(self) -> None:
        """切换当前行任务列表勾选状态（[ ] ⇄ [x]）。

        已有勾选框：空 ⇄ x（原为大写 X 时恢复为 x，避免无意义的大小写翻转）。
        普通列表项（- 内容）：补一个未勾选框 `- [ ] 内容`。
        非列表行 / 空列表项：不做任何事。
        """
        cursor = self.textCursor()
        line = cursor.block().text()

        m = self._TASK_ROW_RE.match(line)
        if m:
            new_line = f"{m.group(1)}[{' ' if m.group(2) != ' ' else 'x'}]{m.group(3)}"
        else:
            m = self._TASK_BULLET_RE.match(line)
            if not m or not m.group(2).strip():
                return
            new_line = f"{m.group(1)}[ ] {m.group(2)}"

        with self.programmatic_modify():
            row_cursor = self.textCursor()
            row_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            row_cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
            )
            row_cursor.insertText(new_line)

    # ═══════════════════ Markdown 表格（阶段 2 F3） ═══════════════════

    def _table_rows_at_cursor(self) -> Optional[list[str]]:
        """返回光标所在 Markdown 表格的各行文本（含分隔行）。

        表格 = 光标块向上/向下连续的以 `|` 开头（允许前导空白）的行；
        遇到空行或非表格行即停。光标不在表格内时返回 None。
        """
        doc = self.document()
        block = self.textCursor().block()
        if not block.text().lstrip().startswith("|"):
            return None

        rows: list[str] = []
        b = block
        while b.isValid() and b.text().lstrip().startswith("|"):
            rows.append(b.text())
            b = b.previous()
        rows.reverse()
        b = block.next()
        while b.isValid() and b.text().lstrip().startswith("|"):
            rows.append(b.text())
            b = b.next()
        return rows

    @staticmethod
    def _table_cells(row: str) -> list[str]:
        """拆分表格行为单元格（去掉首尾定界符；转义 `\\|` 暂不支持，见 docstring）。"""
        return row.strip().strip("|").split("|")

    @staticmethod
    def _table_render_row(cells: list[str]) -> str:
        return "|" + "|".join(cells) + "|"

    def _table_current_cell_index(self, row: str) -> int:
        """光标在当前行第几个单元格（0 起），行尾 clamp 到最后一个单元格。"""
        pos = self.textCursor().positionInBlock()
        delimiters = row.count("|", 0, pos)
        if row.lstrip().startswith("|"):
            delimiters -= 1
        cells = self._table_cells(row)
        return max(0, min(delimiters, len(cells) - 1))

    def _table_edit(self, rebuild: Callable[[list[str]], list[str]]) -> None:
        """表格编辑公共骨架：定位表格 → 逐行重建 → 替换原文本。"""
        rows = self._table_rows_at_cursor()
        if rows is None:
            return
        cursor = self.textCursor()
        start_block = cursor.block()
        while start_block.previous().isValid() and \
                start_block.previous().text().lstrip().startswith("|"):
            start_block = start_block.previous()

        with self.programmatic_modify():
            sel = self.textCursor()
            sel.setPosition(start_block.position())
            end = self.document().findBlockByNumber(
                start_block.blockNumber() + len(rows) - 1
            )
            sel.setPosition(end.position() + end.length() - 1,
                            QTextCursor.MoveMode.KeepAnchor)
            sel.insertText("\n".join(rebuild(rows)))

    def table_insert_row_below(self) -> None:
        """在光标行下方插入空行；若当前是表头则插到分隔行之后。"""
        def rebuild(rows: list[str]) -> list[str]:
            cols = len(self._table_cells(rows[0]))
            empty = self._table_render_row(["  "] * cols)
            # 表头行 → 空行插到分隔行之后，否则插到当前行之后
            idx = self._cursor_row_index(rows)
            if idx == 0 and len(rows) > 1 and self._is_table_separator(rows[1]):
                idx = 1
            out = list(rows)
            out.insert(idx + 1, empty)
            return out
        self._table_edit(rebuild)

    def table_insert_row_above(self) -> None:
        """在光标行上方插入空行；表头行上方不插（表格不允许顶到表头之上）。"""
        def rebuild(rows: list[str]) -> list[str]:
            cols = len(self._table_cells(rows[0]))
            empty = self._table_render_row(["  "] * cols)
            current_text = self.textCursor().block().text()
            idx = rows.index(current_text) if current_text in rows else 0
            if idx == 0:
                return rows  # 表头上方不插
            out = list(rows)
            out.insert(idx, empty)
            return out
        self._table_edit(rebuild)

    def table_delete_row(self) -> None:
        """删除光标所在行；表头与分隔行不可删。"""
        def rebuild(rows: list[str]) -> list[str]:
            current_text = self.textCursor().block().text()
            idx = rows.index(current_text) if current_text in rows else -1
            if idx <= (1 if len(rows) > 1 and self._is_table_separator(rows[1]) else 0):
                return rows  # 表头 / 分隔行不可删
            out = list(rows)
            del out[idx]
            return out
        self._table_edit(rebuild)

    def table_insert_column_left(self) -> None:
        """在光标所在单元格左侧插入一列（含分隔行补齐）。"""
        def rebuild(rows: list[str]) -> list[str]:
            idx = self._table_current_cell_index(rows[self._cursor_row_index(rows)])
            out = []
            for row in rows:
                cells = self._table_cells(row)
                if self._is_table_separator(row):
                    cells.insert(idx, " --- ")
                else:
                    cells.insert(idx, "  ")
                out.append(self._table_render_row(cells))
            return out
        self._table_edit(rebuild)

    def table_insert_column_right(self) -> None:
        """在光标所在单元格右侧插入一列（含分隔行补齐）。"""
        def rebuild(rows: list[str]) -> list[str]:
            idx = self._table_current_cell_index(rows[self._cursor_row_index(rows)])
            out = []
            for row in rows:
                cells = self._table_cells(row)
                if self._is_table_separator(row):
                    cells.insert(idx + 1, " --- ")
                else:
                    cells.insert(idx + 1, "  ")
                out.append(self._table_render_row(cells))
            return out
        self._table_edit(rebuild)

    def table_delete_column(self) -> None:
        """删除光标所在列（含分隔行对应段）；仅一列时不可删。"""
        def rebuild(rows: list[str]) -> list[str]:
            idx = self._table_current_cell_index(rows[self._cursor_row_index(rows)])
            if len(self._table_cells(rows[0])) <= 1:
                return rows
            out = []
            for row in rows:
                cells = self._table_cells(row)
                if idx < len(cells):
                    del cells[idx]
                out.append(self._table_render_row(cells))
            return out
        self._table_edit(rebuild)

    def _cursor_row_index(self, rows: list[str]) -> int:
        current_text = self.textCursor().block().text()
        return rows.index(current_text) if current_text in rows else 0

    @staticmethod
    def _is_table_separator(row: str) -> bool:
        cells = row.strip().strip("|").split("|")
        return bool(cells) and all(
            re.fullmatch(r"\s*:?-{1,}:?\s*", c) for c in cells
        )

    # ═══════════════════ 行内格式（阶段 2 G2） ═══════════════════

    def _wrap_inline(self, prefix: str, suffix: str,
                     link: bool = False,
                     strip_guard: Optional[Callable[[str], bool]] = None) -> None:
        """行内格式 toggle：选中且已被该标记包裹 → 剥掉标记；否则包裹。

        无选中 → 插入 `标记标记` 骨架，光标落在标记之间直接输入内容。
        link=True 时插入 `[文本]()` 并把光标移到括号内；选中 `[文本](url)`
        整体时还原为 `文本`。strip_guard 用于排除会误剥的相邻标记
        （如斜体不应剥掉 `**` 粗体的半个标记）。
        """
        cursor = self.textCursor()
        selected = cursor.selectedText()
        with self.programmatic_modify():
            if link:
                m = re.fullmatch(r"\[([^\]]*)\]\([^)]*\)", selected)
                if m is not None:
                    cursor.insertText(m.group(1))
                else:
                    cursor.insertText(f"[{selected}]()")
                    cursor.movePosition(QTextCursor.MoveOperation.Left)
            else:
                stripped = (
                    selected
                    and len(selected) >= len(prefix) + len(suffix)
                    and selected.startswith(prefix)
                    and selected.endswith(suffix)
                    and (strip_guard is None or strip_guard(selected))
                )
                if stripped:
                    cursor.insertText(
                        selected[len(prefix):len(selected) - len(suffix)])
                else:
                    cursor.insertText(f"{prefix}{selected}{suffix}")
                    if not selected:
                        # 无选中：光标移到标记之间，直接输入内容
                        cursor.movePosition(QTextCursor.MoveOperation.Left,
                                            QTextCursor.MoveMode.MoveAnchor,
                                            len(suffix))
            self.setTextCursor(cursor)

    def format_bold(self) -> None:
        self._wrap_inline("**", "**")

    def format_italic(self) -> None:
        # 斜体剥壳须排除 `**` 开头/结尾：`**粗体**` 按斜体应转粗斜体而非剥成 `*粗体*`；
        # 粗斜体 `***x***` 例外——剥一层斜体恰好还原为 `**x**`
        def guard(s: str) -> bool:
            if s.startswith("***") and s.endswith("***"):
                return True
            return not s.startswith("**") and not s.endswith("**")
        self._wrap_inline("*", "*", strip_guard=guard)

    def format_inline_code(self) -> None:
        self._wrap_inline("`", "`")

    def format_link(self) -> None:
        self._wrap_inline("", "", link=True)

    # ═══════════════════ 标题级别（阶段 2 G5） ═══════════════════

    _HEADING_RE = re.compile(r"^(#{1,6})(\s|$)")

    def set_heading_level(self, level: int) -> None:
        """把当前行设为 level 级标题（0 = 清除标题标记）。

        已是目标级别则清除（二次按同键 = 取消）；替换既有 `#` 前缀。
        """
        cursor = self.textCursor()
        line = cursor.block().text()
        m = self._HEADING_RE.match(line)
        stripped = line[m.end():] if m else line
        if m and len(m.group(1)) == level:
            new_line = stripped
        else:
            hashes = "#" * level + " " if level else ""
            new_line = f"{hashes}{stripped}"
        with self.programmatic_modify():
            row_cursor = self.textCursor()
            row_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            row_cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                                    QTextCursor.MoveMode.KeepAnchor)
            row_cursor.insertText(new_line)

    def _table_cell_cursor(self, row_no: int, row_text: str, col: int) -> bool:
        """把光标定位到指定行的第 col 个单元格内容起点（跳过前导空白）。"""
        pipes = [i for i, ch in enumerate(row_text) if ch == "|"]
        lead = 1 if row_text.lstrip().startswith("|") else 0
        p = col + lead
        if p >= len(pipes):
            return False
        block = self.document().findBlockByNumber(row_no)
        if not block.isValid():
            return False
        # 单元格内容位于 pipes[p-1] 与 pipes[p] 之间；无前导管道的首格从行首起
        pos = block.position() + (pipes[p - 1] + 1 if p > 0 else 0)
        doc = self.document()
        end = block.position() + block.length() - 1
        while pos < end and doc.characterAt(pos) == " ":
            pos += 1
        cursor = self.textCursor()
        cursor.setPosition(pos)
        self.setTextCursor(cursor)
        return True

    def _table_append_row(self, rows: list[str]) -> tuple[int, str]:
        """表尾追加空行（列数取表头），返回 (行号, 新行文本)。"""
        cols = len(self._table_cells(rows[0]))
        new_row = self._table_render_row(["  "] * cols)
        self._table_edit(lambda rs: rs + [new_row])
        return len(rows), new_row

    def _table_tab_next(self, backwards: bool = False) -> bool:
        """表格内 Tab 导航（阶段 2 G3）。

        跳到下一个 / 上一个可编辑单元格（自动跳过分隔行）；正向越过最后一格
        时在表尾新建一行并落到其首格；反向越过表头返回 False（回落减缩进）。
        返回是否处理了按键。
        """
        rows = self._table_rows_at_cursor()
        if not rows:
            return False
        block = self.textCursor().block()
        row_idx = rows.index(block.text())
        col_idx = self._table_current_cell_index(block.text())
        start_no = block.blockNumber() - row_idx

        editable_cells = [
            (r, c)
            for r, row in enumerate(rows)
            if not self._is_table_separator(row)
            for c in range(len(self._table_cells(row)))
        ]
        cur = (row_idx, col_idx)
        idx = editable_cells.index(cur) if cur in editable_cells else -1

        if backwards:
            if idx <= 0:
                return False
            r, c = editable_cells[idx - 1]
            return self._table_cell_cursor(start_no + r, rows[r], c)

        target = idx + 1
        if 0 <= target < len(editable_cells):
            r, c = editable_cells[target]
            return self._table_cell_cursor(start_no + r, rows[r], c)

        if idx == -1:
            # 光标在分隔行等位置：跳到其后最近的单元格
            nxt = [x for x in editable_cells if x > cur]
            if not nxt:
                return False
            r, c = nxt[0]
            return self._table_cell_cursor(start_no + r, rows[r], c)

        # 已在最后一格：表尾新建一行并落到首格
        r, new_row = self._table_append_row(rows)
        return self._table_cell_cursor(start_no + r, new_row, 0)

    # ═══════════════════ 表格对齐（阶段 2 G4） ═══════════════════

    @staticmethod
    def _display_width(text: str) -> int:
        """按终端显示宽计算（East Asian Wide/Fullwidth 记 2），保证中文对齐。"""
        return sum(
            2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
            for ch in text
        )

    def table_format_align(self) -> None:
        """按最宽单元格对齐管道符；分隔行按列宽生成 `---`。"""
        def rebuild(rows: list[str]) -> list[str]:
            grid = [self._table_cells(row) for row in rows]
            ncols = max(len(cells) for cells in grid)
            widths = [3] * ncols
            for r_i, row in enumerate(rows):
                if self._is_table_separator(row):
                    continue
                for c, cell in enumerate(grid[r_i]):
                    widths[c] = max(widths[c], self._display_width(cell.strip()))

            out = []
            for r_i, row in enumerate(rows):
                if self._is_table_separator(row):
                    cells = [" " + "-" * widths[c] + " " for c in range(ncols)]
                else:
                    cells = []
                    for c in range(ncols):
                        cell = grid[r_i][c].strip() if c < len(grid[r_i]) else ""
                        pad = widths[c] - self._display_width(cell)
                        cells.append(f" {cell}{' ' * (pad + 1)}")
                out.append(self._table_render_row(cells))
            return out
        self._table_edit(rebuild)

    # ═══════════════════ 插入图片 ═══════════════════

    def insert_image_from_file(self) -> None:
        """选择本地图片，落盘到文档同级 PanzerNote_assets/ 后插入 Markdown 图片语法。

        落盘与安全写入统一委托 ImageAssetService（经 FileGuard 原子写）。
        """
        if self._image_insert_document_path() is None:
            return

        source_path, _ = QFileDialog.getOpenFileName(
            self, "插入图片", "", _IMAGE_FILE_FILTER
        )
        if not source_path:
            return

        self.insert_images_from_paths([source_path])

    def insert_images_from_paths(self, paths: list[str]) -> None:
        """把本地图片文件按序落盘到文档同级 PanzerNote_assets/ 并插入 Markdown 图片语法。

        单个文件失败只告警并跳过，不阻断其余文件（拖入多图时保持其余可用）。
        """
        document_path = self._image_insert_document_path()
        if document_path is None:
            return

        file_guard = self.config.get_file_guard()
        service = ImageAssetService(file_guard)
        for source_path in paths:
            original_name = os.path.basename(source_path)
            try:
                data = file_guard.safe_read_bytes(
                    source_path, context=FileAccessContext.USER_DOCUMENT_READ
                )
                result = service.save_image(document_path, data, original_name)
            except ImageAssetError as exc:
                QMessageBox.warning(self, "插入图片", str(exc))
                continue
            except Exception as exc:
                QMessageBox.warning(self, "插入图片", f"插入图片失败: {exc}")
                continue

            alt = os.path.splitext(original_name)[0]
            self._insert_markdown_image(alt, result.relative_path)

    @staticmethod
    def _local_image_paths(mime: Optional[QMimeData]) -> list[str]:
        """mime 中「全部为受支持的本地图片文件」时返回路径列表，否则返回空列表。

        供拖入（E4）与剪贴板粘贴（E3）共用：任一 URL 非本地文件、或存在非图片
        扩展名时返回空列表，调用方据此回退默认行为（拖放=冒泡打开、粘贴=纯文本）。
        """
        if mime is None or not mime.hasUrls():
            return []
        paths = []
        for url in mime.urls():
            if not url.isLocalFile():
                return []
            path = url.toLocalFile()
            if not ImageAssetService.is_supported_image(path):
                return []
            paths.append(path)
        return paths

    def _is_markdown_document(self) -> bool:
        """当前共享文档是否为 Markdown（不弹窗，供插入/粘贴/拖放前置判断复用）。"""
        shared = getattr(self, "shared_doc", None)
        return shared is not None and bool(getattr(shared, "is_markdown", False))

    def _markdown_document_path(self) -> Optional[str]:
        """Markdown 共享文档的路径；非 Markdown 或文档未保存时返回 None（不弹窗）。"""
        shared = getattr(self, "shared_doc", None)
        if shared is None or not getattr(shared, "is_markdown", False):
            return None
        filepath = getattr(shared, "filepath", None)
        return str(filepath) if filepath else None

    def _image_insert_document_path(self) -> Optional[str]:
        """插入图片前置校验：返回可落盘的文档路径；不满足时提示并返回 None。"""
        if not self._is_markdown_document():
            QMessageBox.information(self, "插入图片", "仅 Markdown 文档支持插入图片。")
            return None
        document_path = self._markdown_document_path()
        if document_path is None:
            QMessageBox.information(self, "插入图片", "请先保存文档，再插入图片。")
            return None
        return document_path

    def _insert_markdown_image(self, alt: str, relative_path: str) -> None:
        """在当前光标插入 Markdown 图片语法（alt 经结构字符转义）。"""
        cursor = self.textCursor()
        cursor.beginEditBlock()
        with self.programmatic_modify():
            cursor.insertText(f"![{_escape_markdown_alt(alt)}]({relative_path})")
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def insert_image_from_mime(self, source: Optional[QMimeData]) -> bool:
        """剪贴板来源的 mime 含图像时，落盘到 PanzerNote_assets/ 并插入相对路径。

        支持两种剪贴板形态：图像数据（截图/位图）与图片文件 URL（文件管理器
        复制文件）。仅 Markdown 文档处理；其余情况返回 False，交由默认文本粘贴。
        未保存文档无落盘基准目录，提示后中止（不静默失败）。

        Returns:
            True 表示已按图片处理（调用方不应再走默认粘贴）；
            False 表示未处理，应回退默认行为。
        """
        if source is None:
            return False
        if not self._is_markdown_document():
            return False

        # 文件管理器复制的图片文件：剪贴板是 text/uri-list、没有图像数据，
        # 默认粘贴只会把文件路径当纯文本写进正文；此处与拖入（E4）保持一致。
        image_paths = self._local_image_paths(source)
        if image_paths:
            self.insert_images_from_paths(image_paths)
            return True

        if not source.hasImage():
            return False

        document_path = self._markdown_document_path()
        if document_path is None:
            QMessageBox.information(self, "插入图片", "请先保存文档，再粘贴图片。")
            return True

        image = _to_qimage(source.imageData())
        if image is None or image.isNull():
            return False

        try:
            png_bytes = _encode_png(image)
            file_guard = self.config.get_file_guard()
            result = ImageAssetService(file_guard).save_image(
                document_path, png_bytes, extension=".png"
            )
        except Exception as exc:
            QMessageBox.warning(self, "插入图片", f"粘贴图片失败: {exc}")
            return True

        # 剪贴板无原始文件名，alt 留空
        self._insert_markdown_image("", result.relative_path)
        return True

    # ═══════════════════ 文档格式化 ═══════════════════

    def format_document(self) -> None:
        """格式化JSON/XML/HTML/YAML/TOML/CSS文档"""
        content = self.toPlainText()

        if self._file_type == 'JSON':
            try:
                indent = self._get_config_indent()
                parsed = json.loads(content)
                formatted = json.dumps(parsed, ensure_ascii=False, indent=indent)
                with self.programmatic_modify():
                    self.setPlainText(formatted)
            except json.JSONDecodeError as e:
                get_logger(__name__).warning("JSON格式化失败: %s", e)
                QMessageBox.warning(
                    self, "格式化失败",
                    f"JSON格式错误:\n{str(e)}"
                )

        elif self._file_type == 'XML':
            try:
                dom = minidom.parseString(content.encode('utf-8'))
                formatted = dom.toprettyxml(indent="  ")

                lines = formatted.split('\n')
                result_lines = []

                has_declaration = content.strip().startswith('<?xml')

                for i, line in enumerate(lines):
                    if i == 0 and line.startswith('<?xml') and not has_declaration:
                        continue
                    if line.strip():
                        result_lines.append(line)

                with self.programmatic_modify():
                    self.setPlainText('\n'.join(result_lines))

            except Exception as e:
                get_logger(__name__).warning("XML格式化失败: %s", e)
                QMessageBox.warning(
                    self, "格式化失败",
                    f"XML格式错误:\n{str(e)}"
                )

        elif self._file_type == 'HTML':
            try:
                import html5lib  # type: ignore[import-untyped]
                from html5lib import serialize
                from xml.etree import ElementTree

                parsed = html5lib.parse(
                    content,
                    treebuilder="etree",
                    namespaceHTMLElements=False,
                )
                # html5lib.parse 返回 ElementTree，用 minidom 做 pretty-print
                raw_xml = ElementTree.tostring(parsed, encoding="unicode")
                dom = minidom.parseString(raw_xml.encode("utf-8"))
                formatted = dom.toprettyxml(indent="  ")

                # 去掉 <?xml?> 声明和空行
                lines = formatted.split('\n')
                result_lines = [l for l in lines if l.strip() and not l.strip().startswith('<?xml')]
                formatted = '\n'.join(result_lines)

                with self.programmatic_modify():
                    self.setPlainText(formatted)

            except ImportError:
                QMessageBox.warning(
                    self, "格式化失败",
                    "HTML格式化需要安装 html5lib 库\n请运行: pip install html5lib"
                )
            except Exception as e:
                get_logger(__name__).warning("HTML格式化失败: %s", e)
                QMessageBox.warning(
                    self, "格式化失败",
                    f"HTML格式错误:\n{str(e)}"
                )

        elif self._file_type == 'YAML':
            try:
                import yaml
                parsed = yaml.safe_load(content)
                indent = self._get_config_indent()
                formatted = yaml.dump(parsed, allow_unicode=True, default_flow_style=False, indent=indent)
                with self.programmatic_modify():
                    self.setPlainText(formatted)
            except ImportError:
                QMessageBox.warning(self, "格式化失败", "YAML格式化需要安装 pyyaml 库\n请运行: pip install pyyaml")
            except Exception as e:
                get_logger(__name__).warning("YAML格式化失败: %s", e)
                QMessageBox.warning(self, "格式化失败", f"YAML格式错误:\n{str(e)}")

        elif self._file_type == 'TOML':
            try:
                import tomli_w
                import tomli  # type: ignore[import-not-found]
                parsed = tomli.loads(content)
                formatted = tomli_w.dumps(parsed)
                with self.programmatic_modify():
                    self.setPlainText(formatted)
            except ImportError:
                QMessageBox.warning(self, "格式化失败", "TOML格式化需要安装 tomli 和 tomli_w 库\n请运行: pip install tomli tomli_w")
            except Exception as e:
                get_logger(__name__).warning("TOML格式化失败: %s", e)
                QMessageBox.warning(self, "格式化失败", f"TOML格式错误:\n{str(e)}")

        elif self._file_type == 'CSS':
            try:
                import cssbeautifier
                opts = cssbeautifier.default_options()
                opts.indent_size = self._get_config_indent()
                formatted = cssbeautifier.beautify(content, opts)
                with self.programmatic_modify():
                    self.setPlainText(formatted)
            except ImportError:
                QMessageBox.warning(self, "格式化失败", "CSS格式化需要安装 cssbeautifier 库\n请运行: pip install cssbeautifier")
            except Exception as e:
                get_logger(__name__).warning("CSS格式化失败: %s", e)
                QMessageBox.warning(self, "格式化失败", f"CSS格式错误:\n{str(e)}")

        else:
            from ..utils.error_handler import ErrorHandler, ErrorCategory
            ErrorHandler.show_error(
                ErrorCategory.EDITOR, "格式化失败",
                f"不支持对 {self._file_type} 类型文件进行格式化",
                "目前支持 JSON、XML、HTML、YAML、TOML、CSS 文件的格式化。"
            )

    # ═══════════════════ CJK 引号辅助 ═══════════════════

    def _pick_single_cjk_quote(self, ch: str, pos: int) -> str:
        pairs = [
            ("\u201c", "\u201d"),
            ("\u2018", "\u2019"),
            ("\u300c", "\u300d"),
            ("\u300e", "\u300f"),
        ]
        open_to_close = {l: r for l, r in pairs}
        close_to_open = {r: l for l, r in pairs}
        opens = set(open_to_close.keys())
        closes = set(close_to_open.keys())

        open_ch: Optional[str] = None
        close_ch: Optional[str] = None
        for l, r in pairs:
            if ch == l or ch == r:
                open_ch, close_ch = l, r
                break
        if open_ch is None:
            return ch

        scan_start = max(0, pos - 20000)
        scan_cursor = QTextCursor(self.document())
        scan_cursor.setPosition(scan_start)
        scan_cursor.setPosition(pos, QTextCursor.MoveMode.KeepAnchor)
        prefix = scan_cursor.selectedText()

        stack: list[str] = []
        for c in prefix:
            if c in opens:
                stack.append(c)
            elif c in closes:
                expected_open = close_to_open[c]
                if stack and stack[-1] == expected_open:
                    stack.pop()

        if stack and stack[-1] == open_ch:
            return close_ch
        return open_ch
