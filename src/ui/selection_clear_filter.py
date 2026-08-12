# -*- coding: utf-8 -*-
"""
窗口级点击过滤器（独立文件）
原 MainWindow._SelectionClearFilter 纯移动，逻辑逐字节不变。

创建者：MainWindow.__init__（app.installEventFilter 安装）
持有者：QApplication（事件过滤器生命周期由 Qt 管理）
"""

from typing import Optional

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QMainWindow,
    QWidget,
)


class SelectionClearFilter(QObject):
    """窗口级点击过滤器。

    当用户在 MainWindow 范围内点击"任何项目视图
    （QAbstractItemView/QTreeWidget/QListWidget 等）之外的区域"时，
    清空所有子项视图的选中态，使选中高亮蓝色块在"跳出列表区域"时消失。

    点击范围内：交给 Qt 内部 selectionModel 处理（切换选中项/
    Ctrl/Shift 多选逻辑保持不变）。
    """

    def eventFilter(self, watched: Optional[QObject], event: Optional[QEvent]) -> bool:
        if (
            event is None
            or not isinstance(event, QMouseEvent)
            or event.type() != QEvent.Type.MouseButtonPress
        ):
            return super().eventFilter(watched, event)
        if event.button() != Qt.MouseButton.LeftButton:
            return super().eventFilter(watched, event)

        mw = self.parent()
        if not isinstance(mw, QMainWindow):
            return super().eventFilter(watched, event)

        # 弹出模态/菜单时不操作，避免干扰对话框列表
        modal = QApplication.activeModalWidget()
        if modal is not None:
            return super().eventFilter(watched, event)

        # 优先使用 globalPosition() 直接拿到屏幕坐标（对应用级过滤器最可靠）
        screen_pos: Optional[QPoint] = None
        if hasattr(event, "globalPosition"):
            gp = event.globalPosition()
            if gp is not None:
                screen_pos = QPoint(int(gp.x()), int(gp.y()))

        # 回退方案：如果 globalPosition 不可用，尝试 position() + mapToGlobal
        if screen_pos is None and isinstance(watched, QWidget) and hasattr(event, "position"):
            pos = event.position()
            if pos is not None:
                local_pt = QPoint(int(pos.x()), int(pos.y()))
                screen_pos = watched.mapToGlobal(local_pt)

        if screen_pos is None:
            return super().eventFilter(watched, event)

        # 判断点击是否落在 MainWindow 内（跨窗口点击时忽略）
        win_rect_global = QRect(
            mw.mapToGlobal(mw.rect().topLeft()),
            mw.mapToGlobal(mw.rect().bottomRight()),
        )
        if not win_rect_global.contains(screen_pos):
            return super().eventFilter(watched, event)

        # 判断点击的屏幕坐标是否落在任何子 ItemView 的可视矩形内
        views = mw.findChildren(QAbstractItemView)
        for view in views:
            if not view.isVisible():
                continue
            vp = view.viewport()
            if vp is None:
                continue
            view_rect_global = QRect(
                vp.mapToGlobal(vp.rect().topLeft()),
                vp.mapToGlobal(vp.rect().bottomRight()),
            )
            if view_rect_global.contains(screen_pos):
                # 范围点击：保留原有选中切换逻辑
                return super().eventFilter(watched, event)

        # 点击不在任何 ItemView 的可视矩形内：清空全部选中
        for view in views:
            if not view.isVisible():
                continue
            sel_model = view.selectionModel()
            if sel_model is not None and sel_model.hasSelection():
                sel_model.clearSelection()
            # 同时清空 currentIndex，避免焦点矩形残留
            model = view.model()
            invalid_idx = model.index(-1, -1) if model is not None else view.rootIndex()
            view.setCurrentIndex(invalid_idx)

        return super().eventFilter(watched, event)
