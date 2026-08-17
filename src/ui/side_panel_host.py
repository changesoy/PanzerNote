# -*- coding: utf-8 -*-
"""侧栏面板宿主——管理多个面板的注册、切换与持久化。"""

from __future__ import annotations

from typing import Dict

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.themes.theme_aware_mixin import ThemeAwareMixin
from src.themes.theme_v2.consumer import v2_design_value, v2_token


class SidePanelHost(ThemeAwareMixin, QWidget):
    """侧栏面板宿主。

    活动栏（左侧窄按钮栏）+ 内容区（QStackedWidget）。
    支持面板注册、切换、显示/隐藏。
    """

    panel_visibility_changed = pyqtSignal(bool)  # True=显示, False=隐藏

    def __init__(self, theme_engine, parent: QWidget | None = None):
        QWidget.__init__(self, parent)
        if theme_engine is None:
            raise RuntimeError("SidePanelHost 必须传入 theme_engine，不允许为 None")

        self._panels: Dict[str, QWidget] = {}
        self._buttons: Dict[str, QToolButton] = {}
        self._current_panel_id: str | None = None
        self._last_width: int = 200
        self._theme_applied = False

        self._init_theme(theme_engine)

        self.setObjectName("side_panel_host")
        self.setMinimumWidth(36)

        # 水平布局：[活动栏 | 内容区]
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        from PyQt6.QtWidgets import QHBoxLayout
        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(0)

        # 活动栏（垂直按钮栏）
        self._activity_bar = QWidget()
        self._activity_bar.setObjectName("activity_bar")
        self._activity_bar.setFixedWidth(36)
        self._activity_layout = QVBoxLayout(self._activity_bar)
        self._activity_layout.setContentsMargins(2, 4, 2, 4)
        self._activity_layout.setSpacing(2)
        self._activity_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 内容区
        self._stack = QStackedWidget()
        self._stack.setObjectName("panel_stack")

        h_layout.addWidget(self._activity_bar)
        h_layout.addWidget(self._stack)
        root_layout.addLayout(h_layout)

    # ------------------------------------------------------------------
    # 面板管理
    # ------------------------------------------------------------------

    def register_panel(
        self, panel_id: str, panel: QWidget,
        icon_text: str, tooltip: str,
    ) -> None:
        """注册一个面板到宿主。"""
        self._panels[panel_id] = panel

        # 创建活动栏按钮
        btn = QToolButton()
        btn.setText(icon_text)
        btn.setObjectName(f"panel_btn_{panel_id}")
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setFixedSize(32, 32)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        btn.setAutoRaise(True)
        btn.clicked.connect(lambda: self.switch_to(panel_id))
        self._buttons[panel_id] = btn

        # 查找插入位置（保持注册顺序）
        insert_idx = len(self._buttons) - 1
        self._activity_layout.insertWidget(insert_idx, btn)

        # 添加到栈
        self._stack.addWidget(panel)

        if self._theme_applied:
            self._style_button(btn)

    def switch_to(self, panel_id: str) -> None:
        """切换到指定面板。若当前已激活则隐藏整个宿主。"""
        if panel_id not in self._panels:
            return

        # 如果点击的是当前已激活面板 → 隐藏宿主
        if self._current_panel_id == panel_id and self.isVisible():
            self.hide_panel()
            return

        self._current_panel_id = panel_id
        self._stack.setCurrentWidget(self._panels[panel_id])

        # 更新按钮选中态
        for bid, btn in self._buttons.items():
            btn.setChecked(bid == panel_id)

        self.show()

        if not self.signalsBlocked():
            self.panel_visibility_changed.emit(True)

    def show_panel(self, panel_id: str) -> None:
        """显示指定面板（不切换：若面板已打开且为其他 panel 则切换到它）。"""
        if panel_id not in self._panels:
            return

        if self._current_panel_id != panel_id:
            self._current_panel_id = panel_id
            self._stack.setCurrentWidget(self._panels[panel_id])
            for bid, btn in self._buttons.items():
                btn.setChecked(bid == panel_id)

        self.show()
        self.panel_visibility_changed.emit(True)

    def hide_panel(self) -> None:
        """隐藏整个宿主区域。"""
        self.hide()
        for btn in self._buttons.values():
            btn.setChecked(False)
        self.panel_visibility_changed.emit(False)

    def toggle(self, panel_id: str) -> None:
        """切换面板显示：已激活则隐藏，未激活则显示。"""
        if self._current_panel_id == panel_id and self.isVisible():
            self.hide_panel()
        else:
            self.show_panel(panel_id)

    # ------------------------------------------------------------------
    # 状态持久化
    # ------------------------------------------------------------------

    def current_panel_id(self) -> str | None:
        """返回当前激活的面板 ID，无面板时返回 None。"""
        return self._current_panel_id

    def save_state(self, config) -> None:
        """将宽度和激活面板写入 config。"""
        config.set_view_setting("panel_width", self._last_width)
        config.set_view_setting("active_panel", self._current_panel_id or "")

    def restore_state(self, config) -> None:
        """从 config 恢复宽度记录（不调用 setFixedWidth，由 QSplitter 管理实际宽度）。"""
        width = config.get_view_setting("panel_width", 200)
        self._last_width = max(140, min(800, width))

    # ------------------------------------------------------------------
    # 主题
    # ------------------------------------------------------------------

    def _apply_theme_colors(self) -> None:
        self._theme_applied = True
        # B4：侧栏消费 v2 token（侧栏/活动栏 = surface_secondary），无 v1 回退
        bg = v2_token(self._theme_engine, "surface_secondary", "#FAFAFA")
        border = v2_token(self._theme_engine, "border_muted", "#E0E0E0")

        self.setStyleSheet(f"""
            #side_panel_host {{
                background-color: {bg};
                border-left: 1px solid {border};
            }}
            #activity_bar {{
                background-color: {bg};
                border-right: 1px solid {border};
            }}
            #panel_stack {{
                background-color: {bg};
            }}
        """)

        for btn in self._buttons.values():
            self._style_button(btn)

    def _style_button(self, btn: QToolButton) -> None:
        """给单个按钮设样式。"""
        if not self._theme_applied:
            return
        text = v2_token(self._theme_engine, "text_primary", "#212121")
        border = v2_token(self._theme_engine, "border_muted", "#E0E0E0")
        accent = v2_token(self._theme_engine, "accent", "#2196F3")
        on_accent = v2_token(self._theme_engine, "on_accent", "#FFFFFF")
        pressed_bg = v2_token(self._theme_engine, "border_strong", "#BDBDBD")
        # 补漏 C：radius 走 design.json（radius_sm），font-size 为活动栏专属尺度保留；
        # B9 P2-4：补 pressed 态（按下变深，比 hover 更明确）
        radius = v2_design_value(self._theme_engine, "radius", "radius_sm", 3)
        btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: 1px solid transparent;
                color: {text};
                font-size: 13px;
                font-weight: bold;
                border-radius: {radius}px;
            }}
            QToolButton:hover {{
                background-color: {border};
                border-color: {border};
            }}
            QToolButton:pressed {{
                background-color: {pressed_bg};
                border-color: {pressed_bg};
            }}
            QToolButton:checked {{
                background-color: {accent};
                border-color: {accent};
                color: {on_accent};
            }}
        """)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.isVisible() and self.width() > 36:
            self._last_width = self.width()
