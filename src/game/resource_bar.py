# -*- coding: utf-8 -*-
"""
资源栏组件
显示四项资源和打字统计

v1.6.4 改动：
  - 主题感知：订阅 theme_changed 信号
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ..core.config import Config
from ..themes.theme_aware_mixin import ThemeAwareMixin
from .game_palette import game_palette


class ResourceItem(QWidget):

    def __init__(self, icon_path: str, name: str, parent=None):
        super().__init__(parent)
        self.name = name
        self._value = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 10, 2)
        layout.setSpacing(5)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(24, 24)
        layout.addWidget(self.icon_label)

        self.value_label = QLabel("0")
        self.value_label.setFont(QFont("Consolas", 11))
        self.value_label.setMinimumWidth(60)
        layout.addWidget(self.value_label)

    def apply_theme_colors(self, colors):
        # 资源色固定（D28），不随主题明暗变化；文字仍主题感知
        palette = game_palette()
        color_map = {
            "fuel": palette["resource_fuel"],
            "ammo": palette["resource_ammo"],
            "steel": palette["resource_steel"],
            "bauxite": palette["resource_bauxite"],
        }
        color = color_map.get(self.name, colors.text_secondary)
        self.icon_label.setStyleSheet(f"""
            background-color: {color};
            border-radius: 4px;
        """)
        self.value_label.setStyleSheet(f"color: {colors.text_primary};")

    def set_value(self, value: int):
        self._value = value
        self.value_label.setText(f"{value:,}")

    def get_value(self) -> int:
        return self._value


class ResourceBar(ThemeAwareMixin, QWidget):

    def __init__(self, config: Config, theme_engine, parent=None):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("ResourceBar 必须传入 theme_engine，不允许为 None")
        self.config = config

        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(5)

        assets_path = config.get_assets_path()

        self.fuel = ResourceItem(f"{assets_path}/icons/fuel.png", "fuel")
        layout.addWidget(self.fuel)

        self.ammo = ResourceItem(f"{assets_path}/icons/ammo.png", "ammo")
        layout.addWidget(self.ammo)

        self.steel = ResourceItem(f"{assets_path}/icons/steel.png", "steel")
        layout.addWidget(self.steel)

        self.bauxite = ResourceItem(f"{assets_path}/icons/bauxite.png", "bauxite")
        layout.addWidget(self.bauxite)

        layout.addStretch()

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        self.docs_label = QLabel("文档:0")
        self.docs_label.setFont(QFont("Microsoft YaHei", 10))
        layout.addWidget(self.docs_label)

        layout.addSpacing(15)

        self.typing_label = QLabel("今日:0字")
        self.typing_label.setFont(QFont("Microsoft YaHei", 10))
        layout.addWidget(self.typing_label)

        self._init_theme(theme_engine)

        self.refresh()

    def _apply_theme_colors(self, colors):
        self.setStyleSheet(f"""
            ResourceBar {{
                background-color: {colors.statusbar_bg};
                border-bottom: 1px solid {colors.border};
            }}
        """)
        for item in (self.fuel, self.ammo, self.steel, self.bauxite):
            item.apply_theme_colors(colors)
        self.docs_label.setStyleSheet(f"color: {colors.text_secondary};")
        self.typing_label.setStyleSheet(f"color: {colors.text_secondary};")

    def refresh(self):
        resources = self.config.get_resources()
        self.fuel.set_value(resources.get("fuel", 0))
        self.ammo.set_value(resources.get("ammo", 0))
        self.steel.set_value(resources.get("steel", 0))
        self.bauxite.set_value(resources.get("bauxite", 0))

    def update_typing_stats(self, today_chars: int, total_docs: int):
        self.docs_label.setText(f"文档:{total_docs}")
        self.typing_label.setText(f"今日:{today_chars}字")

    def add_resources(self, fuel: int = 0, ammo: int = 0, steel: int = 0, bauxite: int = 0):
        if fuel:
            self.config.add_resource("fuel", fuel)
        if ammo:
            self.config.add_resource("ammo", ammo)
        if steel:
            self.config.add_resource("steel", steel)
        if bauxite:
            self.config.add_resource("bauxite", bauxite)

        self.refresh()
