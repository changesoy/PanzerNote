# -*- coding: utf-8 -*-
"""
主题解析引擎

负责加载、解析和应用主题文件。
支持 JSON 和 YAML 两种格式，提供颜色方案、布局配置和资源引用。
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from PyQt6.QtCore import QObject, pyqtSignal

from ..utils.logger import get_logger


@dataclass
class ThemeColorScheme:
    primary: str = "#2196F3"
    primary_dark: str = "#1976D2"
    primary_light: str = "#BBDEFB"
    accent: str = "#FF9800"
    background: str = "#FFFFFF"
    surface: str = "#F5F5F5"
    card: str = "#FFFFFF"
    text_primary: str = "#212121"
    text_secondary: str = "#757575"
    text_disabled: str = "#BDBDBD"
    border: str = "#E0E0E0"
    divider: str = "#EEEEEE"
    error: str = "#F44336"
    warning: str = "#FF9800"
    success: str = "#4CAF50"
    info: str = "#2196F3"
    sidebar_bg: str = "#FAFAFA"
    editor_bg: str = "#FFFFFF"
    editor_line_number: str = "#BDBDBD"
    editor_current_line: str = "#FFF9C4"
    editor_selection: str = "#BBDEFB"
    editor_bracket_match_bg: str = "#E6F2E6"
    editor_bracket_match_fg: str = "#1A1A1A"
    editor_bracket_unmatched: str = "#E06C75"
    minimap_bg: str = "#F5F5F5"
    minimap_viewport: str = "#E0E0E0"
    statusbar_bg: str = "#F5F5F5"
    menubar_bg: str = "#FAFAFA"
    dialog_bg: str = "#FFFFFF"
    secretary_bubble_bg: str = "#FFFFFF"
    secretary_bubble_border: str = "#E0E0E0"
    resource_fuel: str = "#4CAF50"
    resource_ammo: str = "#F44336"
    resource_steel: str = "#9E9E9E"
    resource_bauxite: str = "#2196F3"

    def to_dict(self) -> Dict[str, str]:
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "ThemeColorScheme":
        defaults = cls()
        for k, v in data.items():
            if hasattr(defaults, k):
                setattr(defaults, k, v)
        return defaults


@dataclass
class LayoutConfig:
    sidebar_width: int = 200
    statusbar_height: int = 24
    menubar_height: int = 28
    tab_height: int = 32
    editor_margin: int = 4
    minimap_width: int = 80
    secretary_margin: int = 10

    def to_dict(self) -> Dict[str, int]:
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LayoutConfig":
        defaults = cls()
        for k, v in data.items():
            if hasattr(defaults, k) and isinstance(v, int):
                setattr(defaults, k, v)
        return defaults


@dataclass
class ThemeDefinition:
    id: str
    name: str
    version: str = "1.0"
    author: str = ""
    description: str = ""
    is_dark: bool = False
    colors: ThemeColorScheme = field(default_factory=ThemeColorScheme)
    layout: LayoutConfig = field(default_factory=LayoutConfig)
    resources: Dict[str, str] = field(default_factory=dict)
    stylesheet_overrides: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "is_dark": self.is_dark,
            "colors": self.colors.to_dict(),
            "layout": self.layout.to_dict(),
            "resources": self.resources,
            "stylesheet_overrides": self.stylesheet_overrides,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThemeDefinition":
        colors_data = data.get("colors", {})
        layout_data = data.get("layout", {})
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            version=data.get("version", "1.0"),
            author=data.get("author", ""),
            description=data.get("description", ""),
            is_dark=data.get("is_dark", False),
            colors=ThemeColorScheme.from_dict(colors_data),
            layout=LayoutConfig.from_dict(layout_data),
            resources=data.get("resources", {}),
            stylesheet_overrides=data.get("stylesheet_overrides", {}),
        )


class ThemeEngine(QObject):
    theme_changed = pyqtSignal(str)

    BUILTIN_THEMES_DIR = "themes"

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._themes: Dict[str, ThemeDefinition] = {}
        self._active_theme_id: Optional[str] = None
        self._logger = get_logger(__name__)
        self._load_builtin_themes()

    def _get_themes_dir(self) -> str:
        app_dir = self._config.get_app_dir()
        return os.path.join(app_dir, self.BUILTIN_THEMES_DIR)

    def _load_builtin_themes(self) -> None:
        light_theme = ThemeDefinition(
            id="light",
            name="浅色主题",
            is_dark=False,
        )
        self._themes["light"] = light_theme

        dark_theme = ThemeDefinition(
            id="dark",
            name="深色主题",
            is_dark=True,
            colors=ThemeColorScheme(
                primary="#BB86FC",
                primary_dark="#985EFF",
                primary_light="#264F78",
                accent="#03DAC6",
                background="#1E1E1E",
                surface="#1E1E1E",
                card="#2D2D2D",
                text_primary="#E0E0E0",
                text_secondary="#A0A0A0",
                text_disabled="#7A7A7A",
                border="#3C3C3C",
                divider="#2D2D2D",
                error="#CF6679",
                warning="#FFB74D",
                success="#81C784",
                info="#64B5F6",
                sidebar_bg="#1E1E1E",
                editor_bg="#1E1E1E",
                editor_line_number="#858585",
                editor_current_line="#2A2D2E",
                editor_selection="#264F78",
                editor_bracket_match_bg="#1A3A3A",
                editor_bracket_match_fg="#E0E0E0",
                editor_bracket_unmatched="#F44747",
                minimap_bg="#1E1E1E",
                minimap_viewport="#3C3C3C",
                statusbar_bg="#1E1E1E",
                menubar_bg="#1E1E1E",
                dialog_bg="#2D2D2D",
                secretary_bubble_bg="#2D2D2D",
                secretary_bubble_border="#3C3C3C",
                resource_fuel="#81C784",
                resource_ammo="#CF6679",
                resource_steel="#9E9E9E",
                resource_bauxite="#64B5F6",
            ),
        )
        self._themes["dark"] = dark_theme

    def load_external_themes(self) -> List[str]:
        themes_dir = self._get_themes_dir()
        if not os.path.isdir(themes_dir):
            return []

        loaded = []
        for filename in os.listdir(themes_dir):
            filepath = os.path.join(themes_dir, filename)
            if not os.path.isfile(filepath):
                continue

            ext = os.path.splitext(filename)[1].lower()
            if ext not in ('.json', '.yaml', '.yml'):
                continue

            try:
                theme = self._load_theme_file(filepath)
                if theme and theme.id not in self._themes:
                    self._themes[theme.id] = theme
                    loaded.append(theme.id)
                    self._logger.info("加载外部主题: %s (%s)", theme.name, theme.id)
            except Exception as e:
                self._logger.warning("加载主题文件 %s 失败: %s", filename, e)

        return loaded

    def _load_theme_file(self, filepath: str) -> Optional[ThemeDefinition]:
        ext = os.path.splitext(filepath)[1].lower()
        data = None

        if ext == '.json':
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        elif ext in ('.yaml', '.yml'):
            if not HAS_YAML:
                self._logger.warning("未安装 PyYAML，无法加载 YAML 主题: %s", filepath)
                return None
            with open(filepath, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

        if data is None:
            return None

        if "id" not in data:
            data["id"] = os.path.splitext(os.path.basename(filepath))[0]

        return ThemeDefinition.from_dict(data)

    def get_theme(self, theme_id: str) -> Optional[ThemeDefinition]:
        return self._themes.get(theme_id)

    def get_all_themes(self) -> Dict[str, ThemeDefinition]:
        return dict(self._themes)

    def get_active_theme(self) -> ThemeDefinition:
        if self._active_theme_id and self._active_theme_id in self._themes:
            return self._themes[self._active_theme_id]
        return self._themes.get("light", ThemeDefinition(id="light", name="浅色主题"))

    def set_active_theme(self, theme_id: str) -> bool:
        if theme_id not in self._themes:
            self._logger.warning("主题不存在: %s", theme_id)
            return False
        self._active_theme_id = theme_id
        self._config.set_view_setting("theme", theme_id)
        self._logger.info("切换主题: %s", theme_id)
        self.theme_changed.emit(theme_id)
        return True

    def generate_stylesheet(self, theme: Optional[ThemeDefinition] = None) -> str:
        t = theme or self.get_active_theme()
        c = t.colors

        parts = []

        parts.append(f"""
QMainWindow {{
    background-color: {c.background};
    color: {c.text_primary};
}}
QMenuBar {{
    background-color: {c.menubar_bg};
    color: {c.text_primary};
    border-bottom: 1px solid {c.border};
}}
QMenuBar::item:selected {{
    background-color: {c.primary_light};
}}
QMenu {{
    background-color: {c.surface};
    color: {c.text_primary};
    border: 1px solid {c.border};
    padding: 4px;
}}
QMenu::item {{
    padding: 4px 32px 4px 12px;
}}
QMenu::item:selected {{
    background-color: {c.primary_light};
}}
""")

        parts.append(f"""
QTabWidget {{
    background-color: {c.background};
}}
QTabWidget::pane {{
    background-color: {c.background};
    border: 1px solid {c.border};
}}
QTabBar {{
    background-color: {c.background};
}}
QTabBar::tab {{
    background-color: {c.surface};
    color: {c.text_secondary};
    border: 1px solid {c.border};
    padding: 4px 12px;
}}
QTabBar::tab:selected {{
    background-color: {c.card};
    color: {c.text_primary};
}}
""")

        parts.append(f"""
QTreeView {{
    background-color: {c.sidebar_bg};
    color: {c.text_primary};
    border: none;
}}
QTreeView::item:selected {{
    background-color: {c.primary_light};
}}
QListWidget {{
    background-color: {c.card};
    color: {c.text_primary};
    border: 1px solid {c.border};
    outline: none;
}}
QListWidget::item:selected {{
    background-color: {c.primary_light};
    color: {c.text_primary};
}}
""")

        parts.append(f"""
QStatusBar {{
    background-color: {c.statusbar_bg};
    color: {c.text_secondary};
    border-top: 1px solid {c.border};
}}
QLabel {{
    color: {c.text_primary};
}}
QPushButton {{
    background-color: {c.primary};
    color: white;
    border: none;
    padding: 6px 16px;
    border-radius: 4px;
}}
QPushButton:hover {{
    background-color: {c.primary_dark};
}}
QPushButton:pressed {{
    background-color: {c.primary_dark};
}}
QLineEdit {{
    border: 1px solid {c.border};
    padding: 4px 8px;
    background-color: {c.card};
    color: {c.text_primary};
}}
QLineEdit:focus {{
    border-color: {c.primary};
}}
QCheckBox {{
    color: {c.text_primary};
}}
QSlider::groove:horizontal {{
    background-color: {c.border};
    height: 4px;
}}
QSlider::handle:horizontal {{
    background-color: {c.primary};
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QGroupBox {{
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 16px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}
QDialog {{
    background-color: {c.dialog_bg};
    color: {c.text_primary};
}}
QMessageBox {{
    background-color: {c.dialog_bg};
}}
QSplitter::handle {{
    background-color: {c.border};
}}
QScrollBar:vertical {{
    background-color: {c.surface};
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background-color: {c.border};
    border-radius: 6px;
    min-height: 20px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {c.text_disabled};
}}
QScrollBar::handle:vertical:pressed {{
    background-color: {c.text_secondary};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background-color: {c.surface};
    height: 12px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background-color: {c.border};
    border-radius: 6px;
    min-width: 20px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {c.text_disabled};
}}
QScrollBar::handle:horizontal:pressed {{
    background-color: {c.text_secondary};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
""")

        if t.stylesheet_overrides:
            for selector, styles in t.stylesheet_overrides.items():
                parts.append(f"{selector} {{\n    {styles}\n}}\n")

        return "\n".join(parts)

    def initialize_active_theme(self) -> None:
        saved_theme = self._config.get_view_setting("theme", "light")
        if saved_theme in self._themes:
            self._active_theme_id = saved_theme
        else:
            self._active_theme_id = "light"
