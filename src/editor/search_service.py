# -*- coding: utf-8 -*-
"""
搜索服务

封装查找和替换逻辑，FindReplaceBar 不再直接扫描全文或操作高亮。
普通搜索使用 QTextDocument.find() 获取权威光标位置，
正则搜索使用 Python re 并通过 QTextCursor 校验位置，
替换操作包在 beginEditBlock/endEditBlock 内从后向前逐匹配替换。
"""

import re
from typing import List, Optional, Tuple

from PyQt6.QtGui import QTextCursor, QTextDocument
from PyQt6.QtCore import Qt

from ..utils.logger import get_logger

MatchPos = Tuple[int, int]


class SearchService:
    """编辑器搜索服务

    用法：
        service = SearchService(editor)
        matches = service.find_all("hello", case_sensitive=False)
        count = service.replace_all("hello", "world", case_sensitive=False)
    """

    def __init__(self, editor):
        self._editor = editor
        self._logger = get_logger(__name__)

    @property
    def _doc(self) -> QTextDocument:
        return self._editor.document()

    def find_all(
        self,
        query: str,
        case_sensitive: bool = False,
        whole_word: bool = False,
        use_regex: bool = False,
    ) -> List[MatchPos]:
        """搜索所有匹配，返回 (start, end) 光标位置列表

        Args:
            query: 搜索文本或正则表达式
            case_sensitive: 大小写敏感
            whole_word: 全词匹配
            use_regex: 是否使用正则表达式

        Returns:
            [(start, end), ...] 每个匹配的 QTextCursor 位置
        """
        if not query or len(query) > 500:
            return []

        if use_regex:
            return self._find_all_regex(query, case_sensitive)
        else:
            return self._find_all_plain(query, case_sensitive, whole_word)

    def _find_all_plain(
        self,
        query: str,
        case_sensitive: bool,
        whole_word: bool,
    ) -> List[MatchPos]:
        matches: List[MatchPos] = []
        flags = QTextDocument.FindFlags(0)
        if case_sensitive:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if whole_word:
            flags |= QTextDocument.FindFlag.FindWholeWords

        cursor = QTextCursor(self._doc)
        while True:
            cursor = self._doc.find(query, cursor, flags)
            if cursor is None or cursor.isNull():
                break
            matches.append((cursor.selectionStart(), cursor.selectionEnd()))

        return matches

    def _find_all_regex(
        self,
        query: str,
        case_sensitive: bool,
    ) -> List[MatchPos]:
        matches: List[MatchPos] = []

        flags = 0
        if not case_sensitive:
            flags |= re.IGNORECASE

        try:
            pattern = re.compile(query, flags)
        except re.error:
            self._logger.debug("无效正则: %s", query)
            return []

        text = self._editor.toPlainText()
        cursor = self._editor.textCursor()
        for m in pattern.finditer(text):
            if m.start() == m.end():
                continue
            cursor.setPosition(m.start())
            cursor.setPosition(m.end(), QTextCursor.MoveMode.KeepAnchor)
            actual = cursor.selectedText().replace("\u2029", "\n")
            if actual == m.group():
                matches.append((cursor.selectionStart(), cursor.selectionEnd()))

        return matches

    def replace_all(
        self,
        query: str,
        replacement: str,
        case_sensitive: bool = False,
        whole_word: bool = False,
        use_regex: bool = False,
    ) -> int:
        """替换所有匹配，返回替换数量

        从后向前逐匹配替换，避免位置偏移。
        替换操作包在 beginEditBlock/endEditBlock 内。

        Args:
            query: 搜索文本或正则表达式
            replacement: 替换文本
            case_sensitive: 大小写敏感
            whole_word: 全词匹配
            use_regex: 是否使用正则表达式

        Returns:
            替换匹配数
        """
        matches = self.find_all(query, case_sensitive, whole_word, use_regex)
        if not matches:
            return 0

        cursor = self._editor.textCursor()
        cursor.beginEditBlock()
        count = 0
        try:
            with self._editor.programmatic_modify():
                for start, end in reversed(matches):
                    cursor.setPosition(start)
                    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                    repl = replacement
                    if use_regex:
                        selected = cursor.selectedText().replace("\u2029", "\n")
                        pattern = self._build_regex(query, case_sensitive)
                        if pattern:
                            try:
                                repl = pattern.sub(replacement, selected, count=1)
                            except re.error:
                                repl = replacement
                    cursor.insertText(repl)
                    count += 1
        finally:
            cursor.endEditBlock()

        return count

    def _build_regex(self, query: str, case_sensitive: bool) -> Optional[re.Pattern]:
        flags = 0
        if not case_sensitive:
            flags |= re.IGNORECASE
        try:
            return re.compile(query, flags)
        except re.error:
            return None
