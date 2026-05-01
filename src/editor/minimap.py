# -*- coding: utf-8 -*-
"""
代码缩略图（Minimap）组件
在编辑器右侧显示整个文件的鸟瞰图，支持点击/拖拽快速导航
仿 PyCharm / VS Code Minimap 风格

v2.0 性能优化：
  - 块级渲染缓存：将文档分割为 block_size 行的块单元进行缓存管理
  - 整行批量渲染：消除逐字符渲染模式，按颜色段批量绘制
  - 缓存失效策略：仅在内容变更时更新对应缓存块
"""

from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import QPainter, QColor, QPixmap, QPicture

from ..utils.feature_flags import is_enabled


BLOCK_SIZE = 50


class MinimapWidget(QWidget):
    """代码缩略图组件"""

    MINIMAP_WIDTH = 80
    BASE_LINE_HEIGHT = 2.5
    CHAR_WIDTH = 1.2
    LEFT_MARGIN = 4
    TOP_MARGIN = 2
    MIN_LINE_HEIGHT = 0.8

    def __init__(self, editor, parent=None):
        super().__init__(parent if parent else editor)
        self._editor = editor
        self._dragging = False

        self.setFixedWidth(self.MINIMAP_WIDTH)
        self.setCursor(Qt.ArrowCursor)
        self.setMouseTracking(True)

        self._cache_pixmap: QPixmap = None
        self._cache_valid = False

        self._block_cache: dict = {}
        self._block_dirty: set = set()
        self._use_block_cache = is_enabled("minimap_block_cache")

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(150)
        self._update_timer.timeout.connect(self._invalidate_and_repaint)

        editor.document().contentsChanged.connect(self._on_content_changed)
        editor.verticalScrollBar().valueChanged.connect(self.update)
        editor.blockCountChanged.connect(self._on_content_changed)

    def _on_content_changed(self):
        self._update_timer.start()

    def _invalidate_and_repaint(self):
        self._cache_valid = False
        if self._use_block_cache:
            self._block_cache.clear()
            self._block_dirty.clear()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._cache_valid = False
        if self._use_block_cache:
            self._block_cache.clear()

    def _get_line_height(self) -> float:
        block_count = max(1, self._editor.document().blockCount())
        available = self.height() - self.TOP_MARGIN * 2
        natural = block_count * self.BASE_LINE_HEIGHT
        if natural <= available:
            return self.BASE_LINE_HEIGHT
        return max(self.MIN_LINE_HEIGHT, available / block_count)

    def _get_viewport_rect(self) -> QRectF:
        editor = self._editor
        doc = editor.document()
        line_h = self._get_line_height()

        first_block = editor.firstVisibleBlock()
        first_line = first_block.blockNumber()

        viewport_h = editor.viewport().height()
        block_h = editor.blockBoundingRect(first_block).height()
        if block_h <= 0:
            block_h = 20
        visible_lines = viewport_h / block_h

        y = first_line * line_h + self.TOP_MARGIN
        h = max(8, visible_lines * line_h)
        return QRectF(0, y, self.width(), h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        painter.fillRect(self.rect(), QColor("#f8f8f8"))
        painter.setPen(QColor("#e0e0e0"))
        painter.drawLine(0, 0, 0, self.height())

        if not self._cache_valid or self._cache_pixmap is None:
            self._rebuild_cache()
        if self._cache_pixmap:
            painter.drawPixmap(0, 0, self._cache_pixmap)

        vp = self._get_viewport_rect()
        painter.fillRect(vp, QColor(100, 140, 200, 30))
        painter.setPen(QColor(100, 140, 200, 70))
        painter.drawLine(int(vp.left()), int(vp.top()),
                         int(vp.right()), int(vp.top()))
        painter.drawLine(int(vp.left()), int(vp.bottom()),
                         int(vp.right()), int(vp.bottom()))

        painter.end()

    def _rebuild_cache(self):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        self._cache_pixmap = QPixmap(w, h)
        self._cache_pixmap.fill(QColor("#f8f8f8"))

        painter = QPainter(self._cache_pixmap)
        painter.setRenderHint(QPainter.Antialiasing, False)

        if self._use_block_cache:
            self._render_with_block_cache(painter)
        else:
            self._render_content(painter)

        painter.end()
        self._cache_valid = True

    def _render_with_block_cache(self, painter: QPainter):
        doc = self._editor.document()
        line_h = self._get_line_height()
        total_blocks = doc.blockCount()
        num_cache_blocks = (total_blocks + BLOCK_SIZE - 1) // BLOCK_SIZE

        for cache_idx in range(num_cache_blocks):
            start_line = cache_idx * BLOCK_SIZE
            end_line = min(start_line + BLOCK_SIZE, total_blocks)

            if cache_idx in self._block_cache and cache_idx not in self._block_dirty:
                picture = self._block_cache[cache_idx]
                y_offset = start_line * line_h + self.TOP_MARGIN
                painter.drawPicture(0, y_offset, picture)
            else:
                picture = QPicture()
                pic_painter = QPainter(picture)
                pic_painter.setRenderHint(QPainter.Antialiasing, False)
                y = self.TOP_MARGIN

                for line_num in range(start_line, end_line):
                    block = doc.findBlockByNumber(line_num)
                    if not block.isValid():
                        break
                    self._render_line(pic_painter, block, y, line_h)
                    y += line_h

                pic_painter.end()
                self._block_cache[cache_idx] = picture
                self._block_dirty.discard(cache_idx)

                y_offset = start_line * line_h + self.TOP_MARGIN
                painter.drawPicture(0, y_offset, picture)

    def _render_content(self, painter: QPainter):
        doc = self._editor.document()
        line_h = self._get_line_height()
        default_color = QColor("#b0b0b0")
        char_w = self.CHAR_WIDTH
        left = self.LEFT_MARGIN
        max_x = self.width() - 2
        y = float(self.TOP_MARGIN)

        block = doc.begin()
        while block.isValid():
            if y > self.height():
                break

            text = block.text()
            if text.strip():
                layout = block.layout()
                fmt_ranges = []
                if layout:
                    try:
                        fmt_ranges = layout.formats()
                    except AttributeError:
                        try:
                            fmt_ranges = layout.additionalFormats()
                        except AttributeError:
                            pass

                segments = self._build_color_segments(text, fmt_ranges, default_color)
                x = float(left)
                rect_h = max(1.0, line_h - 0.5)
                for seg_start, seg_end, color in segments:
                    seg_x = left + seg_start * char_w
                    seg_w = (seg_end - seg_start) * char_w
                    if seg_x + seg_w > max_x:
                        seg_w = max(0, max_x - seg_x)
                    if seg_w > 0:
                        painter.fillRect(QRectF(seg_x, y, seg_w, rect_h), color)

            y += line_h
            block = block.next()

    def _render_line(self, painter: QPainter, block, y: float, line_h: float):
        text = block.text()
        if not text.strip():
            return

        default_color = QColor("#b0b0b0")
        char_w = self.CHAR_WIDTH
        left = self.LEFT_MARGIN
        max_x = self.width() - 2

        layout = block.layout()
        fmt_ranges = []
        if layout:
            try:
                fmt_ranges = layout.formats()
            except AttributeError:
                try:
                    fmt_ranges = layout.additionalFormats()
                except AttributeError:
                    pass

        segments = self._build_color_segments(text, fmt_ranges, default_color)
        rect_h = max(1.0, line_h - 0.5)
        for seg_start, seg_end, color in segments:
            seg_x = left + seg_start * char_w
            seg_w = (seg_end - seg_start) * char_w
            if seg_x + seg_w > max_x:
                seg_w = max(0, max_x - seg_x)
            if seg_w > 0:
                painter.fillRect(QRectF(seg_x, y, seg_w, rect_h), color)

    @staticmethod
    def _build_color_segments(text: str, fmt_ranges: list, default_color: QColor):
        if not text:
            return []

        char_colors = [default_color] * len(text)

        for fr in fmt_ranges:
            fg = fr.format.foreground()
            if fg.style() != 0:
                color = fg.color()
                for i in range(fr.start, min(fr.start + fr.length, len(text))):
                    char_colors[i] = color

        segments = []
        seg_start = 0
        skip = False
        current_color = char_colors[0]

        for i, ch in enumerate(text):
            if ch == ' ' or ch == '\t':
                if not skip and i > seg_start:
                    segments.append((seg_start, i, current_color))
                skip = True
                seg_start = i + 1
                continue

            if skip:
                skip = False
                seg_start = i
                current_color = char_colors[i]
                continue

            if char_colors[i] != current_color:
                segments.append((seg_start, i, current_color))
                seg_start = i
                current_color = char_colors[i]

        if not skip and len(text) > seg_start:
            segments.append((seg_start, len(text), current_color))

        return segments

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._scroll_to_y(event.pos().y())

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._scroll_to_y(event.pos().y())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False

    def _scroll_to_y(self, y: int):
        line_h = self._get_line_height()
        if line_h <= 0:
            return

        target_line = int((y - self.TOP_MARGIN) / line_h)
        doc = self._editor.document()
        target_line = max(0, min(target_line, doc.blockCount() - 1))

        block = doc.findBlockByNumber(target_line)
        if block.isValid():
            cursor = self._editor.textCursor()
            cursor.setPosition(block.position())
            self._editor.setTextCursor(cursor)
            self._editor.centerCursor()
