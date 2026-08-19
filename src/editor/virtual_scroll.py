# -*- coding: utf-8 -*-
"""
延迟高亮管理器
为大文件提供延迟语法高亮

核心策略：
1. 延迟高亮：仅对可视区域 ± buffer_lines 行的 block 进行高亮
2. 滚动触发：滚动时动态更新高亮区域
"""

from typing import Optional

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtGui import QSyntaxHighlighter, QTextDocument
from PyQt6.QtWidgets import QPlainTextEdit

from ..utils.logger import get_logger
from ..utils.feature_flags import is_enabled
from ..utils.perf_probe import measure as _perf_measure

BUFFER_LINES = 100
CHUNK_SIZE = 5000
LARGE_FILE_THRESHOLD = 10000


class DocumentLazyHighlightCoordinator(QObject):
    """Document 级延迟高亮协调器（Wave 4 批次 E2）。

    多 View 共享同一 SharedDocument + 同一 highlighter 时，各 View 的滚动事件
    统一调度：维护 Document 级已高亮块集合（visibleRanges = ∪ 各 View 区间，
    增量去重），保证任一 View 滚动都能高亮其可视区（含分屏 View——此前分屏
    View 无 lazy 驱动，滚动区域块不被高亮）。highlighter 始终挂在 Document 上，
    不摘除不重建。
    """

    def __init__(
        self,
        document: QTextDocument,
        highlighter: Optional[QSyntaxHighlighter] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._document = document
        self._highlighter = highlighter
        self._views: list[QPlainTextEdit] = []
        self._highlighted_blocks: set[int] = set()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._do_highlight)

    def set_highlighter(self, highlighter) -> None:
        self._highlighter = highlighter
        # highlighter 就绪（set_file_type）后立即调度一次，保证首次可视区高亮
        # 不依赖后续滚动（open_file 时序 attach→load_content→set_file_type）。
        self.schedule()

    def register(self, view) -> None:
        """注册一个 View（其滚动事件驱动本协调器调度）。"""
        if view in self._views:
            return
        self._views.append(view)
        vbar = view.verticalScrollBar()
        if vbar is not None:
            vbar.valueChanged.connect(self.schedule)
        self.schedule()

    def unregister(self, view) -> None:
        if view not in self._views:
            return
        self._views.remove(view)
        vbar = view.verticalScrollBar()
        if vbar is not None:
            try:
                vbar.valueChanged.disconnect(self.schedule)
            except (TypeError, RuntimeError):
                pass

    def schedule(self) -> None:
        self._timer.start()

    def on_content_changed(self) -> None:
        self._highlighted_blocks.clear()
        self.schedule()

    def _do_highlight(self) -> None:
        highlighter = self._highlighter
        if highlighter is None:
            return
        doc = highlighter.document()
        if doc is None:
            return
        block_count = doc.blockCount()
        if block_count < LARGE_FILE_THRESHOLD:
            # 非大文件：全量高亮已覆盖全文档，coordinator 不干预（避免共享
            # 小文件场景对已高亮块做无谓的可见区重着色）。
            return
        targets: set[int] = set()
        for view in self._views:
            try:
                rng = self._visible_range(view, block_count)
            except RuntimeError:
                # 防御：View 未 detach 即被销毁（正常关闭路径会先 unregister）。
                # 直接移除悬垂引用，避免滚动高亮对已删除 C++ 对象调用崩溃。
                self._views.remove(view)
                continue
            if rng is not None:
                targets.update(range(rng[0], rng[1]))
        for i in sorted(targets):
            if i not in self._highlighted_blocks:
                block = doc.findBlockByNumber(i)
                if block.isValid():
                    highlighter.rehighlightBlock(block)
                    self._highlighted_blocks.add(i)

    def _visible_range(self, view, block_count: int):
        """返回 view 可视区 ± buffer 的 [start, end) 行区间。"""
        first_block = view.firstVisibleBlock()
        first_line = first_block.blockNumber()

        viewport = view.viewport()
        if viewport is None:
            return None
        viewport_h = viewport.height()
        block = first_block
        visible_count = 0
        while block.isValid():
            rect = view.blockBoundingGeometry(block)
            if rect.top() - view.contentOffset().y() > viewport_h:
                break
            visible_count += 1
            block = block.next()

        start = max(0, first_line - BUFFER_LINES)
        end = first_line + visible_count + BUFFER_LINES
        return start, min(end, block_count)


class LazyHighlightManager(QObject):
    """延迟高亮管理器

    管理大文件的延迟语法高亮。
    当 feature flag "lazy_highlight" 关闭时，所有方法为空操作。
    """

    def __init__(self, editor: QPlainTextEdit):
        super().__init__(editor)
        self._editor = editor
        self._highlighter = None
        # Wave 4 E2：共享 Document 时绑定 Document 级协调器（None = 独立编辑，per-View 行为）
        self._coordinator: Optional[DocumentLazyHighlightCoordinator] = None
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

    def set_coordinator(self, coordinator: Optional[DocumentLazyHighlightCoordinator]) -> None:
        """共享 Document 路径：绑定/解绑 Document 级 lazy 协调器（Wave 4 E2）。

        attach 共享 Document 时传入 coordinator（本 View 的滚动/高亮统一交给
        Document 级调度，visibleRanges = ∪ 各 View 区间）；detach 后传 None
        恢复 per-View 行为。
        """
        self._coordinator = coordinator

    def set_highlighter(self, highlighter):
        self._highlighter = highlighter
        if self._coordinator is not None:
            self._coordinator.set_highlighter(highlighter)

    def _lazy_enabled(self) -> bool:
        """E4：lazy 高亮激活条件——显式 lazy_highlight flag，或大文件模式
        （large_file_mode 开启时达阈值文件自动启用，无需手动开 flag）。
        flag 默认值不写死 True（实施方案约束），仅运行时按需判定；
        无全局状态，关闭 large_file_mode / 关闭 tab 即自然恢复，不残留。
        """
        return is_enabled("lazy_highlight") or is_enabled("large_file_mode")

    def load_content(self, content: str) -> bool:
        if not self._lazy_enabled():
            return False

        line_count = content.count('\n') + 1
        if line_count < LARGE_FILE_THRESHOLD:
            return False

        self._is_large_file = True
        self._highlighted_blocks.clear()

        if self._coordinator is not None:
            # E2 共享 Document 路径：内容已由主面板 load_content 加载到共享
            # qdocument，这里不重复 setPlainText、不摘除 Document 级 highlighter
            # （缺口 G3）；仅清集 + 触发 Document 级首次高亮调度（缺口 G1）。
            self._coordinator.on_content_changed()
            return True

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
        if self._is_large_file and self._lazy_enabled():
            if self._coordinator is not None:
                self._coordinator.schedule()
            else:
                self._schedule_visible_highlight()

    def _schedule_visible_highlight(self):
        self._pending_highlight_timer.start()

    def _do_pending_highlight(self):
        if not self._highlighter or not self._is_large_file:
            return
        if self._coordinator is not None:
            # 共享路径由 Document 级协调器统一调度，本 View 不再独立高亮
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
            if self._coordinator is not None:
                self._coordinator.on_content_changed()
            else:
                self._highlighted_blocks.clear()
                self._schedule_visible_highlight()

    def is_active(self) -> bool:
        return self._is_large_file and self._lazy_enabled()

    def goto_line(self, line: int):
        if self._is_large_file:
            if self._coordinator is not None:
                self._coordinator.schedule()
            else:
                self._schedule_visible_highlight()
