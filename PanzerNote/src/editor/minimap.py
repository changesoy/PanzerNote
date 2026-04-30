# -*- coding: utf-8 -*-
"""
代码缩略图（Minimap）组件
在编辑器右侧显示整个文件的鸟瞰图，支持点击/拖拽快速导航
仿 PyCharm / VS Code Minimap 风格
"""

from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import QPainter, QColor, QPixmap


class MinimapWidget(QWidget):
    """代码缩略图组件

    以极小的像素块绘制每一行代码的颜色信息，
    并用半透明矩形标注当前编辑器的可视区域。
    """

    MINIMAP_WIDTH = 80          # 缩略图固定宽度（像素）
    BASE_LINE_HEIGHT = 2.5      # 基础行高（像素）
    CHAR_WIDTH = 1.2            # 单字符宽度（像素）
    LEFT_MARGIN = 4             # 左侧留白
    TOP_MARGIN = 2              # 顶部留白
    MIN_LINE_HEIGHT = 0.8       # 缩放后最小行高

    def __init__(self, editor, parent=None):
        """
        Args:
            editor: 关联的 QPlainTextEdit 实例
            parent: 父控件（默认使用 editor）
        """
        super().__init__(parent if parent else editor)
        self._editor = editor
        self._dragging = False

        self.setFixedWidth(self.MINIMAP_WIDTH)
        self.setCursor(Qt.ArrowCursor)
        self.setMouseTracking(True)

        # ── 内容缓存 ──
        self._cache_pixmap: QPixmap = None
        self._cache_valid = False

        # ── 防抖定时器：文档内容变化时延迟重绘 ──
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(150)
        self._update_timer.timeout.connect(self._invalidate_and_repaint)

        # ── 信号连接 ──
        editor.document().contentsChanged.connect(self._on_content_changed)
        editor.verticalScrollBar().valueChanged.connect(self.update)
        editor.blockCountChanged.connect(self._on_content_changed)

    # ───────────────────── 缓存管理 ─────────────────────

    def _on_content_changed(self):
        """文档内容变化，启动防抖"""
        self._update_timer.start()

    def _invalidate_and_repaint(self):
        self._cache_valid = False
        self.update()

    def resizeEvent(self, event):
        """尺寸变化时也需要重建缓存"""
        super().resizeEvent(event)
        self._cache_valid = False

    # ───────────────────── 几何计算 ─────────────────────

    def _get_line_height(self) -> float:
        """根据文档总行数自动缩放行高，确保内容不超出组件高度"""
        block_count = max(1, self._editor.document().blockCount())
        available = self.height() - self.TOP_MARGIN * 2
        natural = block_count * self.BASE_LINE_HEIGHT

        if natural <= available:
            return self.BASE_LINE_HEIGHT
        return max(self.MIN_LINE_HEIGHT, available / block_count)

    def _get_viewport_rect(self) -> QRectF:
        """计算当前编辑器可视区域在缩略图上的矩形"""
        editor = self._editor
        doc = editor.document()
        block_count = max(1, doc.blockCount())
        line_h = self._get_line_height()

        first_block = editor.firstVisibleBlock()
        first_line = first_block.blockNumber()

        # 估算可见行数
        viewport_h = editor.viewport().height()
        block_h = editor.blockBoundingRect(first_block).height()
        if block_h <= 0:
            block_h = 20
        visible_lines = viewport_h / block_h

        y = first_line * line_h + self.TOP_MARGIN
        h = max(8, visible_lines * line_h)  # 最小高度 8px，否则太窄不好点

        return QRectF(0, y, self.width(), h)

    # ───────────────────── 绘制 ─────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        # 背景
        painter.fillRect(self.rect(), QColor("#f8f8f8"))

        # 左侧分隔线
        painter.setPen(QColor("#e0e0e0"))
        painter.drawLine(0, 0, 0, self.height())

        # 内容（使用缓存）
        if not self._cache_valid or self._cache_pixmap is None:
            self._rebuild_cache()
        if self._cache_pixmap:
            painter.drawPixmap(0, 0, self._cache_pixmap)

        # 视口指示器（每帧实时绘制）
        vp = self._get_viewport_rect()
        painter.fillRect(vp, QColor(100, 140, 200, 30))
        painter.setPen(QColor(100, 140, 200, 70))
        painter.drawLine(int(vp.left()), int(vp.top()),
                         int(vp.right()), int(vp.top()))
        painter.drawLine(int(vp.left()), int(vp.bottom()),
                         int(vp.right()), int(vp.bottom()))

        painter.end()

    def _rebuild_cache(self):
        """重建内容缓存位图"""
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        self._cache_pixmap = QPixmap(w, h)
        self._cache_pixmap.fill(QColor("#f8f8f8"))

        painter = QPainter(self._cache_pixmap)
        painter.setRenderHint(QPainter.Antialiasing, False)
        self._render_content(painter)
        painter.end()

        self._cache_valid = True

    def _render_content(self, painter: QPainter):
        """将文档中每行代码以微型色块绘制到 painter 上"""
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
                # 获取语法高亮格式
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

                # 逐字符绘制色块
                x = float(left)
                for i, ch in enumerate(text):
                    if x > max_x:
                        break
                    if ch == ' ':
                        x += char_w
                        continue
                    if ch == '\t':
                        x += char_w * 4
                        continue

                    # 查找该位置的前景色
                    color = default_color
                    for fr in fmt_ranges:
                        if fr.start <= i < fr.start + fr.length:
                            fg = fr.format.foreground()
                            if fg.style() != 0:
                                color = fg.color()
                            break

                    rect_h = max(1.0, line_h - 0.5)
                    painter.fillRect(QRectF(x, y, char_w, rect_h), color)
                    x += char_w

            y += line_h
            block = block.next()

    # ───────────────────── 鼠标交互 ─────────────────────

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
        """将编辑器滚动到缩略图上 y 坐标对应的行"""
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
