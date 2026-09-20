# -*- coding: utf-8 -*-
"""图片查看器（以标签页形式打开，Markdown 图片工作流）。

支持格式与解码口径统一交给 `image_decoder`：Qt 原生格式 + HEIF/HEIC + AVIF。
**查看全程只读**：字节经 FileGuard 读取、内存中解码，
不写回、不重编码、不改动源文件；竖拍照片按 EXIF 方向纠正**仅作用于显示**。

默认缩放至适应窗口，单击在「适应窗口 / 原始大小」间切换，超尺寸时可滚动查看。
不设自定义配色：跟随应用级 QSS。
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..security.file_guard import FileGuard
from . import image_formats as fmt
from .image_decoder import decode_image_file

# 视口小于该尺寸时不做适应缩放（首帧布局未完成，视口可能只有占位大小）
_MIN_VIEWPORT_EDGE = 32


class ImageViewerWidget(QWidget):
    """标签页形式的图片查看器；单击切换 适应窗口 / 原始大小。"""

    def __init__(self, filepath: str, file_guard: FileGuard, parent=None):
        super().__init__(parent)
        self.image_path = os.path.abspath(filepath)
        self._pixmap: QPixmap | None = None
        self._fit_mode = True
        self._failure = ""

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._scroll = QScrollArea(self)
        self._scroll.setWidget(self._label)
        self._scroll.setWidgetResizable(True)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._hint = QLabel(self)
        self._hint.setContentsMargins(8, 4, 8, 4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._scroll, 1)
        layout.addWidget(self._hint, 0)

        # 点击图片本体也要能切换缩放：子控件默认吃掉鼠标事件，装过滤器转发
        for target in (self._scroll.viewport(), self._label):
            if target is not None:
                target.installEventFilter(self)

        self._load(file_guard)

    # ---------- 加载 ----------

    def _load(self, file_guard: FileGuard) -> None:
        result = decode_image_file(self.image_path, file_guard, exif_orientation=True)
        if result.image is None:
            self._failure = result.reason or "无法打开该图片。"
            # 标签页形态下不弹模态框：把原因直接显示在页内
            self._label.setText(self._failure)
            self._hint.setText(os.path.basename(self.image_path))
            return

        self._pixmap = QPixmap.fromImage(result.image)
        self._apply_scaling()

    @property
    def failure_reason(self) -> str:
        """解码失败原因；成功时为空串（供测试与调用方判断）。"""
        return self._failure

    # ---------- 缩放 ----------

    def _toggle_fit(self) -> None:
        if self._pixmap is None:
            return
        self._fit_mode = not self._fit_mode
        self._apply_scaling()

    def _apply_scaling(self) -> None:
        if self._pixmap is None:
            return
        viewport = self._scroll.viewport()
        if viewport is None:
            return
        size = viewport.size()
        fitted = (
            self._fit_mode
            and size.width() > _MIN_VIEWPORT_EDGE
            and size.height() > _MIN_VIEWPORT_EDGE
        )
        # 适应窗口只缩不放：比视口小的图按原始像素显示（放大只会糊）
        if fitted and (
            self._pixmap.width() > size.width()
            or self._pixmap.height() > size.height()
        ):
            shown = self._pixmap.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            shown = self._pixmap
        self._label.setPixmap(shown)
        self._label.adjustSize()
        self._update_hint(shown.width(), shown.height(), self._fit_mode)

    def _update_hint(self, shown_w: int, shown_h: int, fitted: bool) -> None:
        if self._pixmap is None:
            return
        mode = "适应窗口" if fitted else "原始大小"
        self._hint.setText(
            f"{os.path.basename(self.image_path)}   "
            f"{self._pixmap.width()}×{self._pixmap.height()}   "
            f"显示 {shown_w}×{shown_h} · {mode}（单击切换）"
        )

    # ---------- 事件 ----------

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().showEvent(event)
        # 首帧布局完成后视口才是真实尺寸；此前视口仍可能是极小占位值，
        # 若此时做过适应缩放，图片会被压成一点点大。故延到本轮事件循环末尾再算。
        QTimer.singleShot(0, self._apply_scaling)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().resizeEvent(event)
        if self._fit_mode:
            self._apply_scaling()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._handle_press(event)

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:  # noqa: N802 - Qt 命名
        if event is not None and event.type() == QEvent.Type.MouseButtonPress:
            self._handle_press(event)
        return super().eventFilter(obj, event)

    def _handle_press(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_fit()


def is_viewable_image(filepath: str) -> bool:
    """文件是否可作为图片直接查看（按扩展名判定，与查看器解码口径同源）。"""
    return os.path.isfile(filepath) and fmt.is_viewable(filepath)
