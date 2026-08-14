# -*- coding: utf-8 -*-
"""
延迟高亮管理器
为大文件提供延迟语法高亮

核心策略：
1. 延迟高亮：仅对可视区域 ± buffer_lines 行的 block 进行高亮
2. 滚动触发：滚动时动态更新高亮区域
"""

from PyQt6.QtCore import QObject, QTimer, Qt
from PyQt6.QtGui import QTextCursor, QTextBlock
from PyQt6.QtWidgets import QPlainTextEdit

from ..utils.logger import get_logger
from ..utils.feature_flags import is_enabled
from ..utils.perf_probe import measure as _perf_measure

BUFFER_LINES = 100
CHUNK_SIZE = 5000
LARGE_FILE_THRESHOLD = 10000


class LazyHighlightManager(QObject):
    """延迟高亮管理器

    管理大文件的延迟语法高亮。
    当 feature flag "lazy_highlight" 关闭时，所有方法为空操作。
    """

    def __init__(self, editor: QPlainTextEdit):
        super().__init__(editor)
        self._editor = editor
        self._highlighter = None
        self._is_large_file = False
        self._highlighted_blocks: set[int] = set()
        self._pending_highlight_timer = QTimer(self)
        self._pending_highlight_timer.setSingleShot(True)
        self._pending_highlight_timer.setInterval(50)
        self._pending_highlight_timer.timeout.connect(self._do_pending_highlight)
        self._pending_ranges: list[tuple[int, int]] = []

        vbar = self._editor.verticalScrollBar()
        if vbar is not None:
            vbar.valueChanged.connect(self._on_scroll)

    def set_highlighter(self, highlighter):
        self._highlighter = highlighter

    def load_content(self, content: str) -> bool:
        if not is_enabled("lazy_highlight"):
            return False

        line_count = content.count('\n') + 1
        if line_count < LARGE_FILE_THRESHOLD:
            return False

        self._is_large_file = True
        self._highlighted_blocks.clear()
        editor = self._editor

        if self._highlighter:
            self._highlighter.setDocument(None)

        try:
            editor.setPlainText(content)
        except Exception as e:
            get_logger(__name__).error("延迟高亮加载失败，回退普通模式", exc_info=True)
            self._is_large_file = False
            if self._highlighter:
                self._highlighter.setDocument(editor.document())
            return False

        if self._highlighter:
            self._highlighter.setDocument(editor.document())

        self._schedule_visible_highlight()
        return True

    def _on_scroll(self):
        if self._is_large_file and is_enabled("lazy_highlight"):
            self._schedule_visible_highlight()

    def _schedule_visible_highlight(self):
        self._pending_highlight_timer.start()

    def _do_pending_highlight(self):
        if not self._highlighter or not self._is_large_file:
            return
        # E1 profiling：首屏 / 滚动后的高亮调度耗时
        _perf_measure("lazy_highlight.pending", self._highlight_visible_range)

    def _highlight_visible_range(self):
        first_block = self._editor.firstVisibleBlock()
        first_line = first_block.blockNumber()

        viewport = self._editor.viewport()
        if viewport is None:
            return
        viewport_h = viewport.height()
        block = first_block
        visible_count = 0
        while block.isValid():
            rect = self._editor.blockBoundingGeometry(block)
            if rect.top() - self._editor.contentOffset().y() > viewport_h:
                break
            visible_count += 1
            block = block.next()

        start = max(0, first_line - BUFFER_LINES)
        end = first_line + visible_count + BUFFER_LINES

        if self._highlighter:
            doc = self._editor.document()
            for i in range(start, min(end, doc.blockCount())):
                if i not in self._highlighted_blocks:
                    block = doc.findBlockByNumber(i)
                    if block.isValid():
                        self._highlighter.rehighlightBlock(block)
                        self._highlighted_blocks.add(i)

    def on_content_changed(self):
        if self._is_large_file:
            self._highlighted_blocks.clear()
            self._schedule_visible_highlight()

    def is_active(self) -> bool:
        return self._is_large_file and is_enabled("lazy_highlight")

    def goto_line(self, line: int):
        if self._is_large_file:
            self._schedule_visible_highlight()
