# -*- coding: utf-8 -*-
"""
代码缩略图（Minimap）组件
在编辑器右侧显示整个文件的鸟瞰图，支持点击/拖拽快速导航
仿 PyCharm / VS Code Minimap 风格

性能策略：
  - 全量缓存：内容变更时重建整个 minimap 缓存（QPixmap）
  - 块级渲染缓存（feature flag "minimap_block_cache"）：
    将文档按 BLOCK_SIZE 行分块，每块缓存为 QPicture。
    v1.6.6 改进：监听 QTextDocument.contentsChange 信号，
    精确标记受影响的缓存块为脏块，仅重新渲染脏块。
    行数变化时后续块也标记为脏，确保缓存索引一致。
"""

from typing import Optional

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QPixmap, QPicture

from ..utils.feature_flags import is_enabled
from ..themes.theme_aware_mixin import ThemeAwareMixin
from ..themes.theme_v2.consumer import v2_color, v2_token
from ..utils.logger import get_logger


BLOCK_SIZE = 50


class MinimapWidget(ThemeAwareMixin, QWidget):
    """代码缩略图组件"""

    MINIMAP_WIDTH = 80
    BASE_LINE_HEIGHT = 2.5
    CHAR_WIDTH = 1.2
    LEFT_MARGIN = 4
    TOP_MARGIN = 2
    MIN_LINE_HEIGHT = 0.8

    def __init__(self, editor, theme_engine, parent=None):
        super().__init__(parent if parent else editor)
        if theme_engine is None:
            raise RuntimeError("Minimap 必须传入 theme_engine，不允许为 None")
        self._editor = editor
        self._dragging = False

        self.setFixedWidth(self.MINIMAP_WIDTH)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setMouseTracking(True)

        self._cache_pixmap: Optional[QPixmap] = None
        self._cache_valid = False

        self._block_cache: dict = {}
        self._block_dirty: set = set()
        self._use_block_cache = is_enabled("minimap_block_cache")

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(150)
        self._update_timer.timeout.connect(self._invalidate_and_repaint)

        editor.document().contentsChange.connect(self._on_contents_change)
        editor.verticalScrollBar().valueChanged.connect(self.update)
        editor.blockCountChanged.connect(self._on_content_changed)

        self._init_theme(theme_engine)

    def _apply_theme_colors(self):
        # B2：minimap 消费 v2 minimap recipe + 语义 token，无 v1 回退
        # 补漏 D P1-2：viewport 接线 minimap recipe viewport 键（→ minimap_viewport
        # 变体 token），替换原 accent+alpha 硬编码派生。
        # 2026-08-17 修正：视口指示保持"浅色半透明矩形"观感——半透明 alpha 是绘制
        # 细节（填充 90 / 边框 150，透出下方代码纹理），颜色来源走 recipe token。
        self._bg_color = v2_color(self._theme_engine, "minimap", "background", "#FFFFFF")
        self._border_color = v2_token(self._theme_engine, "border_muted", "#E0E0E0")
        self._text_color = v2_color(self._theme_engine, "minimap", "text", "#BDBDBD")
        viewport_color = QColor(
            v2_color(self._theme_engine, "minimap", "viewport", "#E0E0E0")
        )
        self._viewport_color = QColor(
            viewport_color.red(), viewport_color.green(), viewport_color.blue(), 90
        )
        self._viewport_border_color = QColor(
            viewport_color.red(), viewport_color.green(), viewport_color.blue(), 150
        )
        self._cache_valid = False
        if self._use_block_cache:
            self._block_cache.clear()
        self.update()

    def _on_content_changed(self):
        if self._use_block_cache:
            self._block_dirty.clear()
            self._block_cache.clear()
        self._update_timer.start()

    def _on_contents_change(self, from_pos: int, chars_removed: int, chars_added: int):
        if not self._use_block_cache:
            self._cache_valid = False
            self._update_timer.start()
            return

        doc = self._editor.document()
        start_block = doc.findBlock(from_pos)
        end_pos = from_pos + max(chars_added, chars_removed)
        end_block = doc.findBlock(end_pos)

        start_line = start_block.blockNumber()
        end_line = end_block.blockNumber()

        start_cache = start_line // BLOCK_SIZE
        end_cache = end_line // BLOCK_SIZE
        for cache_idx in range(start_cache, end_cache + 1):
            self._block_dirty.add(cache_idx)

        if chars_added != chars_removed:
            total_blocks = doc.blockCount()
            num_cache_blocks = (total_blocks + BLOCK_SIZE - 1) // BLOCK_SIZE
            for cache_idx in range(end_cache + 1, num_cache_blocks):
                self._block_dirty.add(cache_idx)

        self._update_timer.start()

    def _invalidate_and_repaint(self):
        self._cache_valid = False
        if not self._use_block_cache:
            pass
        elif self._block_dirty:
            pass
        else:
            self._block_cache.clear()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._cache_valid = False
        if self._use_block_cache:
            self._block_cache.clear()

    def _get_line_height(self) -> float:
        doc = self._editor.document()
        assert doc is not None
        block_count = max(1, self._count_visible_blocks())
        available = self.height() - self.TOP_MARGIN * 2
        natural = block_count * self.BASE_LINE_HEIGHT
        if natural <= available:
            return float(self.BASE_LINE_HEIGHT)
        return float(max(self.MIN_LINE_HEIGHT, available / block_count))

    def _count_visible_blocks(self) -> int:
        """统计可见 block 数（跳过被折叠隐藏的）。"""
        doc = self._editor.document()
        if doc is None:
            return 1
        count = 0
        block = doc.begin()
        while block.isValid():
            if block.isVisible():
                count += 1
            block = block.next()
        return max(1, count)

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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        painter.fillRect(self.rect(), QColor(self._bg_color))
        painter.setPen(QColor(self._border_color))
        painter.drawLine(0, 0, 0, self.height())

        if not self._cache_valid or self._cache_pixmap is None:
            self._rebuild_cache()
        if self._cache_pixmap:
            painter.drawPixmap(0, 0, self._cache_pixmap)

        vp = self._get_viewport_rect()
        painter.fillRect(vp, self._viewport_color)
        painter.setPen(self._viewport_border_color)
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
        self._cache_pixmap.fill(QColor(self._bg_color))

        painter = QPainter(self._cache_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

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
                painter.drawPicture(0, int(y_offset), picture)
            else:
                picture = QPicture()
                pic_painter = QPainter(picture)
                pic_painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                y: float = self.TOP_MARGIN

                for line_num in range(start_line, end_line):
                    block = doc.findBlockByNumber(line_num)
                    if not block.isValid() or not block.isVisible():
                        break
                    self._render_line(pic_painter, block, y, line_h)
                    y += line_h

                pic_painter.end()
                self._block_cache[cache_idx] = picture
                self._block_dirty.discard(cache_idx)

                y_offset = start_line * line_h + self.TOP_MARGIN
                painter.drawPicture(0, int(y_offset), picture)

    def _render_content(self, painter: QPainter):
        doc = self._editor.document()
        line_h = self._get_line_height()
        default_color = QColor(self._text_color)
        char_w = self.CHAR_WIDTH
        left = self.LEFT_MARGIN
        max_x = self.width() - 2
        y = float(self.TOP_MARGIN)

        block = doc.begin()
        while block.isValid():
            if y > self.height():
                break

            if block.isVisible():
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
                                get_logger(__name__).debug("QTextBlockFormat 无 formats/additionalFormats 属性")

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
        default_color = QColor(self._text_color)
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
                    get_logger(__name__).debug("QTextBlockFormat 无 formats/additionalFormats 属性")

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
        if event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._preview_at_y(event.pos().y())
            else:
                self._dragging = True
                self._scroll_to_y(event.pos().y())

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._jump_to_y(event.pos().y())

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._scroll_to_y(event.pos().y())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
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

    def _jump_to_y(self, y: int):
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
            # 自动展开包含目标行的折叠区域
            folding = getattr(self._editor, '_folding', None)
            if folding is not None:
                folding.ensure_visible(target_line + 1)
            self._editor.ensureCursorVisible()
            self._editor.setFocus()

    def _preview_at_y(self, y: int):
        line_h = self._get_line_height()
        if line_h <= 0:
            return

        target_line = int((y - self.TOP_MARGIN) / line_h)
        doc = self._editor.document()
        target_line = max(0, min(target_line, doc.blockCount() - 1))

        block = doc.findBlockByNumber(target_line)
        if block.isValid():
            vsb = self._editor.verticalScrollBar()
            block_rect = self._editor.blockBoundingRect(block)
            vsb.setValue(int(block_rect.top()))
