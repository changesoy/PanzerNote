# -*- coding: utf-8 -*-
"""
编辑器辅助操作模块
将行操作、大小写转换、文档格式化等辅助功能从 Editor 中抽离

采用 Mixin 模式，Editor 通过多继承获得这些能力。
"""

import json
import xml.dom.minidom as minidom
from typing import Optional

from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QMessageBox

from ..utils.logger import get_logger


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

    # ═══════════════════ 行操作 ═══════════════════

    def delete_current_line(self) -> None:
        """删除当前行"""
        cursor = self.textCursor()
        cursor.beginEditBlock()

        with self.programmatic_modify():
            cursor.movePosition(cursor.StartOfBlock)

            if cursor.block().next().isValid():
                cursor.movePosition(cursor.EndOfBlock, cursor.KeepAnchor)
                cursor.movePosition(cursor.NextCharacter, cursor.KeepAnchor)
            elif cursor.block().blockNumber() > 0:
                anchor = cursor.position()
                cursor.movePosition(cursor.PreviousCharacter)
                cursor.setPosition(anchor, cursor.KeepAnchor)
                cursor.movePosition(cursor.EndOfBlock, cursor.KeepAnchor)
            else:
                cursor.movePosition(cursor.EndOfBlock, cursor.KeepAnchor)

            cursor.removeSelectedText()
        cursor.endEditBlock()

    def duplicate_line(self) -> None:
        """复制当前行到下一行"""
        cursor = self.textCursor()
        cursor.beginEditBlock()

        with self.programmatic_modify():
            cursor.movePosition(cursor.StartOfBlock)
            cursor.movePosition(cursor.EndOfBlock, cursor.KeepAnchor)
            line_text = cursor.selectedText()

            cursor.movePosition(cursor.EndOfBlock)
            cursor.insertText('\n' + line_text)

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
            cursor.setPosition(end_pos, cursor.KeepAnchor)

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
            cursor.setPosition(end_pos, cursor.KeepAnchor)

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
        cursor.setPosition(start + len(new_text), cursor.KeepAnchor)
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
        cursor.setPosition(start + len(new_text), cursor.KeepAnchor)
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
        cursor.setPosition(start + len(new_text), cursor.KeepAnchor)
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
        cursor.setPosition(start + len(new_text), cursor.KeepAnchor)
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

    # ═══════════════════ 文档格式化 ═══════════════════

    def format_document(self) -> None:
        """格式化JSON/XML/HTML/YAML/TOML/CSS文档"""
        content = self.toPlainText()

        if self._file_type == 'JSON':
            try:
                indent = self._config.get_editor_setting("code_indent_size", 4)
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

        elif self._file_type in ('XML', 'HTML'):
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
                get_logger(__name__).warning("XML/HTML格式化失败: %s", e)
                QMessageBox.warning(
                    self, "格式化失败",
                    f"XML/HTML格式错误:\n{str(e)}"
                )

        elif self._file_type == 'YAML':
            try:
                import yaml
                parsed = yaml.safe_load(content)
                indent = self._config.get_editor_setting("code_indent_size", 4)
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
                import tomli
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
                opts.indent_size = self._config.get_editor_setting("code_indent_size", 4)
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
        scan_cursor.setPosition(pos, QTextCursor.KeepAnchor)
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
