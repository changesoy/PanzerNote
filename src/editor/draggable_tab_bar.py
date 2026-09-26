# -*- coding: utf-8 -*-
"""可拖拽标签栏与标签关闭按钮（从 editor_tabs.py 拆出，纯结构重构不改行为）。

- DraggableTabBar：标签栏内拖拽 = 释放时一次性落位重排；向外拖拽（文件树 /
  跨分屏）= 发起 QDrag 携带 MIME_TAB_FILEPATH / MIME_TAB_ID。
- TabCloseButton：自定义关闭按钮容器，让 × 图标落在文字与 tab 右边界之间。
"""

from typing import cast

from PyQt6.QtCore import QPoint, QMimeData, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDrag, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QTabBar,
    QTabWidget,
    QToolButton,
    QWidget,
)

from ..themes.theme_v2.consumer import v2_color

# 自定义 MIME 类型
MIME_TAB_FILEPATH = "application/x-panzernote-tab-filepath"
# 3.5.11：未命名标签（无 filepath）拖拽时携带 tab_id，供迁移/落盘定位源标签
MIME_TAB_ID = "application/x-panzernote-tab-id"


class DraggableTabBar(QTabBar):
    """可拖拽标签栏

    在 QTabBar 内部拖拽 → 正常的标签重新排序
    向外拖拽（如文件树） → 发起 QDrag，携带文件路径信息，可移动文件
    """

    file_drop_requested = pyqtSignal(str, str)  # (src_filepath, dest_folder)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_start_pos = QPoint()
        self._drag_tab_index = -1

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self._drag_tab_index = self.tabAt(event.pos())
        elif event.button() == Qt.MouseButton.MiddleButton:
            tab_index = self.tabAt(event.pos())
            if tab_index >= 0:
                self.tabCloseRequested.emit(tab_index)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return

        if self._drag_tab_index < 0:
            super().mouseMoveEvent(event)
            return

        # 只有鼠标离开标签栏区域才发起外部拖拽
        if self.rect().contains(event.pos()):
            # 3.5.8（R6）：不调用 super() 的原生 movable 逻辑——原生行为是
            # 拖动中途扫过其它标签就实时 moveTab 换位，用户拖拽会被"替换"。
            # 改为只在鼠标释放时按落点一次性落位（见 mouseReleaseEvent）。
            event.accept()
            return

        # 距离阈值
        distance = (event.pos() - self._drag_start_pos).manhattanLength()
        if distance < QApplication.startDragDistance():
            super().mouseMoveEvent(event)
            return

        # 获取该标签对应的 tab_id 与文件路径（3.5.11：未命名标签无路径也可拖拽）
        tab_widget = cast(QTabWidget, self.parent())
        if not tab_widget or not hasattr(tab_widget, '_get_filepath_for_index'):
            super().mouseMoveEvent(event)
            return

        widget = tab_widget.widget(self._drag_tab_index)
        if widget is None:
            super().mouseMoveEvent(event)
            return
        # 图片标签按设计不带 tab_id（不参与保存状态机），但同样应可拖拽跨分屏迁移：
        # 用 image_path 作身份标记塞进 MIME_TAB_ID（接收方只判「存在该格式」，不解析内容）。
        tab_id = getattr(widget, 'tab_id', None)
        identity = tab_id if tab_id is not None else getattr(widget, 'image_path', None)
        if identity is None:
            super().mouseMoveEvent(event)
            return

        # 图片标签不携带文件路径：否则拖到文件树会触发「移动图片文件」这类副作用
        # （本版未定义该行为，保持与迁移一致的纯内部搬动）。
        filepath = ""
        if tab_id is not None:
            filepath = tab_widget._get_filepath_for_index(self._drag_tab_index) or ""

        # 发起 QDrag
        # 注意：MIME_TAB_FILEPATH 仅对已保存文件设置——空数据格式在平台拖拽协议中
        # 可能被丢弃，导致目标 hasFormat 判断失败；未命名标签靠 MIME_TAB_ID 识别。
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_TAB_ID, str(identity).encode('utf-8'))
        if filepath:
            mime.setData(MIME_TAB_FILEPATH, filepath.encode('utf-8'))
        drag.setMimeData(mime)

        # B6（8.1 拖拽视觉）：拖拽体为半透明的标签缩略图，随鼠标跟手。
        # 不携带 text/plain——避免编辑器把 tab 拖拽当文本拖放而写入文件名。
        rect = self.tabRect(self._drag_tab_index)
        pixmap = self.grab(rect)
        if not pixmap.isNull():
            img = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
            painter = QPainter(img)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            painter.fillRect(img.rect(), QColor(0, 0, 0, 150))  # ~60% 不透明度
            painter.end()
            drag.setPixmap(QPixmap.fromImage(img))
            # 热点 = 按下点在源 tab 内的相对偏移：缩略图初始与源 tab 垂直对齐，
            # 拖拽过程中保持按下时的相对位置（VS Code 行为）。
            hx = max(0, min(rect.width() - 1, self._drag_start_pos.x() - rect.left()))
            hy = max(0, min(rect.height() - 1, self._drag_start_pos.y() - rect.top()))
            drag.setHotSpot(QPoint(hx, hy))

        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction)
        self._drag_tab_index = -1

    def mouseReleaseEvent(self, event):
        # 3.5.8（R6）：标签栏内拖动结束时按落点一次性落位（替代原生实时换位）。
        # moveTab 会 emit tabMoved，QTabWidget 据此同步 widget 顺序。
        # 注意：落位后必须直接 return，不能调用 super().mouseReleaseEvent()——
        # QTabBar 原生释放逻辑会再做一次内部换位，与 moveTab 叠加导致落位偏差。
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._drag_tab_index >= 0
            and self.rect().contains(event.pos())
        ):
            target = self.tabAt(event.pos())
            if target >= 0 and target != self._drag_tab_index:
                self.moveTab(self._drag_tab_index, target)
            self._drag_tab_index = -1
            event.accept()
            return
        super().mouseReleaseEvent(event)


class TabCloseButton(QWidget):
    """标签关闭按钮容器。

    原生 QTabBar 关闭按钮是固定贴右边缘的 QToolButton widget，
    QSS 的 subcontrol-position / right / margin 对它无效，
    tab 的 padding-right 也不影响其位置。
    本容器用固定宽度 + QHBoxLayout 的 contentsMargins 右侧留白，
    让内部小按钮左移，使 × 图标落在文字与 tab 右边界之间。
    """

    def __init__(self, theme_engine, parent=None):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("TabCloseButton 必须传入 theme_engine，不允许为 None")
        self._theme_engine = theme_engine
        self.setFixedSize(28, 22)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 10, 1)
        layout.setSpacing(0)

        self._btn = QToolButton()
        self._btn.setObjectName("tabCloseInnerBtn")
        self._btn.setFixedSize(15, 16)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setText("×")
        self._apply_btn_style()
        layout.addWidget(self._btn)
        layout.addStretch()

        self._btn.clicked.connect(self._on_clicked)

    def _apply_btn_style(self) -> None:
        close_hover = v2_color(self._theme_engine, "tab", "close_hover", "#BBDEFB")
        self._btn.setStyleSheet(
            f"#tabCloseInnerBtn {{ border: none; background: transparent; border-radius: 2px; padding: 0; }}"
            f"#tabCloseInnerBtn:hover {{ background: {close_hover}; }}"
        )

    def _on_clicked(self):
        tab_bar = self.parent()
        while tab_bar is not None and not isinstance(tab_bar, QTabBar):
            tab_bar = tab_bar.parent()
        if tab_bar is None:
            return
        for i in range(tab_bar.count()):
            if tab_bar.tabButton(i, QTabBar.ButtonPosition.RightSide) is self:
                tab_widget = tab_bar.parent()
                while tab_widget is not None and not isinstance(tab_widget, QTabWidget):
                    tab_widget = tab_widget.parent()
                if tab_widget is not None and hasattr(tab_widget, '_on_tab_close_requested'):
                    tab_widget._on_tab_close_requested(i)
                return
