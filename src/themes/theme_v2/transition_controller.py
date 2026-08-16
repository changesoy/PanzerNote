# -*- coding: utf-8 -*-
"""Theme v2 切换视觉过渡（Wave 8 B7 设计文档第八节）。

ThemeTransitionController + Snapshot Overlay：
- ``duration_for(level, motion_level)``：时长决策纯函数（controller 常量，不写
  motion.json；L0=150ms / L1=250ms，normal 全值 / reduced 半值 / off 瞬时）。
- ``run()``：逐窗口 grab 旧帧 → overlay 置顶 → 同步执行 ``switch_callable`` →
  淡出动画 → 销毁 overlay。grab 失败的窗口独立降级为 opaque veil（surface_primary
  纯色遮罩，同窗淡出）。
- 重入保护：动画进行中再次 ``run()`` → 直接同步执行 ``switch_callable``
  （不叠加第二层 overlay，设计 8.4）。

不依赖 ThemeV2Service / Config：veil 颜色、motion_level、easing 全部由调用点
传入，保持 theme_v2 契约层的纯净性。
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, cast

from PyQt6.QtCore import (
    QEasingCurve,
    QObject,
    Qt,
    QVariantAnimation,
)
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from .types import ThemeSwitchLevel

# 时长分档常量（设计 8.2：fade 时长不写入 motion.json；L1 分支由测试驱动）
_DURATION_BY_LEVEL: Dict[ThemeSwitchLevel, int] = {
    ThemeSwitchLevel.L0: 150,
    ThemeSwitchLevel.L1: 250,
}


def duration_for(level: ThemeSwitchLevel, motion_level: str) -> Optional[int]:
    """时长决策纯函数（设计 8.1 步骤 1）。

    - ``motion_level == "off"`` → None（瞬时）
    - ``"normal"`` → 基值 {L0: 150, L1: 250}
    - ``"reduced"`` → 基值 // 2
    """
    base = _DURATION_BY_LEVEL[level]
    if motion_level == "off":
        return None
    if motion_level == "reduced":
        return base // 2
    return base


def easing_for(name: str) -> QEasingCurve.Type:
    """motion.json ``easing`` 字符串 → QEasingCurve；未知值回落 ease-out。"""
    mapping = {
        "linear": QEasingCurve.Type.Linear,
        "ease-in": QEasingCurve.Type.InCubic,
        "ease-out": QEasingCurve.Type.OutCubic,
        "ease-in-out": QEasingCurve.Type.InOutCubic,
    }
    return mapping.get(name, QEasingCurve.Type.OutCubic)


class _SnapshotOverlay(QWidget):
    """全区域覆盖遮罩：pixmap 有效时绘制旧帧，否则填 surface_primary 纯色 veil。

    与 QGraphicsOpacityEffect 不同，直接自绘 pixmap + 全局 alpha（主设计 4.5），
    避免对 WebEngine / 复杂 widget 引入 effect 副作用。动画期间不吞鼠标事件
    （150~250ms，避免切换瞬间点击丢失）。
    """

    def __init__(self, parent: QWidget, pixmap: Optional[QPixmap], veil_color: str) -> None:
        super().__init__(parent)
        self._pixmap = pixmap
        self._veil_color = QColor(veil_color)
        self._opacity = 1.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setGeometry(parent.rect())
        self.raise_()

    def set_fade_opacity(self, value: float) -> None:
        """动画驱动：透明度 1→0。"""
        self._opacity = value
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setOpacity(self._opacity)
        if self._pixmap is not None and not self._pixmap.isNull():
            painter.drawPixmap(self.rect(), self._pixmap)
        else:
            painter.fillRect(self.rect(), self._veil_color)
        painter.end()


class ThemeTransitionController(QObject):
    """主题切换视觉过渡编排（设计 8.1 / 8.3 / 8.4）。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._running = False
        self._overlays: List[_SnapshotOverlay] = []
        self._animation: Optional[QVariantAnimation] = None

    @property
    def is_running(self) -> bool:
        """淡出动画进行中（重入保护标志 + 测试可观测）。"""
        return self._running

    def run(
        self,
        windows: Sequence[QWidget],
        switch_callable: Callable[[], None],
        *,
        level: ThemeSwitchLevel = ThemeSwitchLevel.L0,
        motion_level: str = "normal",
        allow_animation: bool = True,
        veil_color: str = "#FFFFFF",
        easing: QEasingCurve.Type = QEasingCurve.Type.OutCubic,
    ) -> None:
        """带 Snapshot Overlay 的主题切换（设计 8.1）。

        ``windows`` 由调用点筛选（主窗口 + 可见顶层对话框，排除瞬时浮层）；
        grab 失败的窗口独立降级为纯色 veil（8.3）。动画进行中再次调用 →
        直接同步执行 ``switch_callable``（重入保护，8.4），不叠加第二层 overlay。
        """
        if self._running:
            switch_callable()
            return

        duration = None if not allow_animation else duration_for(level, motion_level)
        if duration is None or not windows:
            # 瞬时路径：无遮罩，直接同步切换（D11 动画不制造人为延迟）
            switch_callable()
            return

        # 2. 逐窗口 grab 旧帧（失败该窗口降 veil）
        overlays: List[_SnapshotOverlay] = []
        for window in windows:
            pixmap: Optional[QPixmap] = window.grab()
            if pixmap is None or pixmap.isNull() or pixmap.width() == 0 or pixmap.height() == 0:
                pixmap = None
            else:
                pixmap.setDevicePixelRatio(window.devicePixelRatioF())
            overlay = _SnapshotOverlay(window, pixmap, veil_color)
            overlay.show()
            overlays.append(overlay)

        # 4. 同步执行真实切换（manager commit + QSS 重涂全在内），完成后才开始淡出
        switch_callable()

        # 5. QVariantAnimation 驱动全部 overlay 透明度 1→0
        self._overlays = overlays
        self._running = True
        animation = QVariantAnimation(self)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.setDuration(duration)
        animation.setEasingCurve(easing)
        animation.valueChanged.connect(self._on_fade_value)
        animation.finished.connect(self._on_fade_finished)
        self._animation = animation
        animation.start()

    def _on_fade_value(self, value: object) -> None:
        opacity = cast(float, value)  # QVariantAnimation 值域为 1.0→0.0
        for overlay in self._overlays:
            overlay.set_fade_opacity(opacity)

    def _on_fade_finished(self) -> None:
        for overlay in self._overlays:
            overlay.deleteLater()
        self._overlays = []
        self._animation = None
        self._running = False
