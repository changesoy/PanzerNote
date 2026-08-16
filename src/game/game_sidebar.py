# -*- coding: utf-8 -*-
"""
游戏侧边栏组件
包含返回、建造、车库、图鉴按钮

v1.6.4 改动：
  - 主题感知：订阅 theme_changed 信号
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QToolButton, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont

from ..themes.theme_aware_mixin import ThemeAwareMixin
from ..themes.theme_v2.consumer import v2_token
from .game_palette import game_palette


class GameIconButton(QToolButton):

    def __init__(self, icon_name: str, tooltip: str, color: str = "#666666", parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.tooltip_text = tooltip
        self.color = color
        self._is_current = False

        self.setFixedSize(50, 50)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._create_placeholder_icon()

    def _create_placeholder_icon(self):
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setBrush(QColor(self.color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(2, 2, 28, 28, 6, 6)

        painter.setPen(QColor("white"))
        painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))

        char_map = {
            "back": "←",
            "construction": "建",
            "garage": "库",
            "collection": "鉴"
        }
        char = char_map.get(self.icon_name, "?")
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, char)

        painter.end()

        self.setIcon(QIcon(pixmap))
        self.setIconSize(QSize(32, 32))

    def update_style_with_colors(self, colors):
        if self._is_current:
            self.setStyleSheet(f"""
                QToolButton {{
                    background-color: {colors["primary_light"]};
                    border: 2px solid {colors["primary"]};
                    border-radius: 8px;
                }}
                QToolButton:hover {{
                    background-color: {colors["editor_selection"]};
                    border-color: {colors["primary"]};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QToolButton {{
                    background-color: transparent;
                    border: 2px solid transparent;
                    border-radius: 8px;
                }}
                QToolButton:hover {{
                    background-color: {colors["surface"]};
                    border: 2px solid {colors["border"]};
                }}
            """)

    def update_color(self, color: str):
        """更新图标主色并重绘占位图标"""
        self.color = color
        self._create_placeholder_icon()

    def set_current(self, is_current: bool):
        self._is_current = is_current


class GameSidebar(ThemeAwareMixin, QWidget):

    view_changed = pyqtSignal(str)

    def __init__(self, theme_engine, parent=None):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("GameSidebar 必须传入 theme_engine，不允许为 None")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        back_color = v2_token(theme_engine, "text_muted", "#BDBDBD")
        # 游戏侧图标色固定（D28），不随主题明暗变化
        palette = game_palette()
        build_color = palette["game_build"]
        garage_color = palette["game_garage"]
        collection_color = palette["game_collection"]

        self.back_btn = GameIconButton("back", "返回 (Ctrl+Z / Esc)", back_color)
        self.back_btn.clicked.connect(lambda: self.view_changed.emit("back"))
        layout.addWidget(self.back_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.HLine)
        line1.setFrameShadow(QFrame.Shadow.Sunken)
        line1.setFixedWidth(40)
        layout.addWidget(line1, 0, Qt.AlignmentFlag.AlignHCenter)

        self.construction_btn = GameIconButton("construction", "建造 (Ctrl+2)", build_color)
        self.construction_btn.clicked.connect(lambda: self._on_btn_clicked("construction"))
        layout.addWidget(self.construction_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setFrameShadow(QFrame.Shadow.Sunken)
        line2.setFixedWidth(40)
        layout.addWidget(line2, 0, Qt.AlignmentFlag.AlignHCenter)

        self.garage_btn = GameIconButton("garage", "车库 (Ctrl+3)", garage_color)
        self.garage_btn.clicked.connect(lambda: self._on_btn_clicked("garage"))
        layout.addWidget(self.garage_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        line3 = QFrame()
        line3.setFrameShape(QFrame.Shape.HLine)
        line3.setFrameShadow(QFrame.Shadow.Sunken)
        line3.setFixedWidth(40)
        layout.addWidget(line3, 0, Qt.AlignmentFlag.AlignHCenter)

        self.collection_btn = GameIconButton("collection", "图鉴 (Ctrl+4)", collection_color)
        self.collection_btn.clicked.connect(lambda: self._on_btn_clicked("collection"))
        layout.addWidget(self.collection_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        # 图标名 → 游戏固定配色 key 映射（D28：不读主题 token）
        self._icon_token_map = {
            "construction": "game_build",
            "garage": "game_garage",
            "collection": "game_collection",
        }

        layout.addStretch()

        self._buttons = {
            "construction": self.construction_btn,
            "garage": self.garage_btn,
            "collection": self.collection_btn
        }

        self._init_theme(theme_engine)

    def _btn_style_colors(self) -> dict:
        """B3：按钮状态配色（主题感知）从 v2 token 解析，无 v1 回退。"""
        eng = self._theme_engine
        return {
            "primary_light": v2_token(eng, "accent_soft", "#BBDEFB"),
            "primary": v2_token(eng, "accent", "#2196F3"),
            "editor_selection": v2_token(eng, "accent_soft", "#BBDEFB"),
            "surface": v2_token(eng, "surface_secondary", "#F5F5F5"),
            "border": v2_token(eng, "border_muted", "#E0E0E0"),
        }

    def _apply_theme_colors(self):
        # B3：侧栏消费 v2 token（无 v1 回退，B8：字面量 = v1 light 值）
        self.setStyleSheet(f"""
            GameSidebar {{
                background-color: {v2_token(self._theme_engine, "surface_secondary", "#FAFAFA")};
                border-right: 1px solid {v2_token(self._theme_engine, "border_muted", "#E0E0E0")};
            }}
        """)
        palette = game_palette()
        style_colors = self._btn_style_colors()
        for name, btn in self._buttons.items():
            color = palette.get(self._icon_token_map.get(name, ""))
            if color:
                btn.update_color(color)
            btn.update_style_with_colors(style_colors)
        self.back_btn.update_style_with_colors(style_colors)

    def _on_btn_clicked(self, view: str):
        self.view_changed.emit(view)

    def set_current_view(self, view: Optional[str]):
        for name, btn in self._buttons.items():
            btn.set_current(name == view)
        style_colors = self._btn_style_colors()
        for btn in self._buttons.values():
            btn.update_style_with_colors(style_colors)
        self.back_btn.update_style_with_colors(style_colors)
