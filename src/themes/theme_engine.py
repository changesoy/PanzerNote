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
from .theme_v2.library import ThemeComponentLibrary
from .theme_v2.manager import ThemeManager
from .theme_v2.service import ThemeV2Service


@dataclass
class ThemeColorScheme:
    primary: str = "#2196F3"
    primary_dark: str = "#1976D2"
    primary_light: str = "#BBDEFB"
    accent: str = "#FF9800"
    accent_fg: str = "#FFFFFF"
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

    game_build: str = "#4CAF50"
    game_garage: str = "#FF9800"
    game_collection: str = "#9C27B0"

    bg_codeblock: str = "#EDF3FA"
    codeblock_border: str = "#D8DEE9"

    selection_bg: str = "#BBDEFB"
    selection_fg: str = "#212121"
    hover_bg: str = "#BBDEFB"
    active_bg: str = "#1976D2"
    focus_border: str = "#2196F3"

    search_match_bg: str = "#FFEE58"
    search_current_bg: str = "#FF9800"
    search_current_fg: str = "#FFFFFF"

    editor_bookmark_bg: str = "#FF9800"
    editor_bookmark_fg: str = "#FFFFFF"
    editor_fold_marker: str = "#4CAF50"
    editor_fold_marker_collapsed: str = "#66BB6A"

    md_h1_fg: str = "#000000"
    md_h2_fg: str = "#000000"
    md_h3_fg: str = "#000000"
    md_h456_fg: str = "#2b2b2b"
    md_bold_fg: str = "#2b2b2b"
    md_italic_fg: str = "#2b2b2b"
    md_code_fg: str = "#008000"
    md_code_bg: str = "#f2f2f2"
    md_link_fg: str = "#2470B3"
    md_image_fg: str = "#6A1B9A"
    md_list_fg: str = "#2b2b2b"
    md_quote_fg: str = "#808080"
    md_hr_fg: str = "#AAAAAA"
    md_fence_fg: str = "#808080"
    md_code_block_fg: str = "#2b2b2b"
    md_code_block_bg: str = "#f5f5f5"

    # ── 语法高亮 token ──
    syntax_keyword: str = "#0033B3"
    syntax_keyword_type: str = "#0033B3"
    syntax_builtin: str = "#8000FF"
    syntax_class: str = "#000000"
    syntax_function: str = "#00627A"
    syntax_variable: str = "#660E7A"
    syntax_tag: str = "#000080"
    syntax_namespace: str = "#000000"

    syntax_string: str = "#067D17"
    syntax_string_escape: str = "#0037A6"
    syntax_string_affix: str = "#0033B3"
    syntax_string_doc: str = "#067D17"
    syntax_number: str = "#1750EB"

    syntax_comment: str = "#8C8C8C"

    syntax_operator: str = "#000000"
    syntax_punctuation: str = "#000000"
    syntax_text: str = "#2b2b2b"
    syntax_error: str = "#FF0000"

    # ── 语法高亮装饰（bold/italic 由 highlight_themes.py 控制）──
    syntax_deleted: str = "#A31515"
    syntax_inserted: str = "#067D17"
    syntax_heading: str = "#000000"
    syntax_output: str = "#2b2b2b"

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
        self._init_theme_v2()

    def _init_theme_v2(self) -> None:
        """B2：初始化 Theme v2 运行时（default 包），跟随 v1 主题明暗选择变体。

        v2 加载失败时保持禁用，消费方回退 v1 机制，不影响应用启动。
        B7：v2 激活态写入口唯一收口到 ThemeManager（设计文档 9.1）。
        """
        themes_dir = os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "themes"
        ))
        self.theme_v2 = ThemeV2Service(themes_dir, parent=self)
        # B3：Core Controls 统一视觉实现入口（available() 为 False 时回退 v1 全局 QSS）
        self.components = ThemeComponentLibrary(self.theme_v2)
        if not self.theme_v2.load_default():
            return
        self.theme_manager = ThemeManager(themes_dir, self.theme_v2, parent=self)
        active = self.get_active_theme()
        self.theme_manager.request_variant_for_dark(active.is_dark)
        self.theme_changed.connect(self._on_theme_changed_v2)

    def _on_theme_changed_v2(self, theme_id: str) -> None:
        """B7：v1 theme_changed → 委托 ThemeManager 切换 v2 变体（service 不再直写激活态）。"""
        theme = self.get_theme(theme_id) or self.get_active_theme()
        manager = getattr(self, "theme_manager", None)
        if manager is not None:
            manager.request_variant_for_dark(theme.is_dark)

    def _get_themes_dir(self) -> str:
        app_dir = self._config.get_app_dir()
        return os.path.join(app_dir, self.BUILTIN_THEMES_DIR)

    def _load_builtin_themes(self) -> None:
        builtin_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "themes", "builtin"
        )
        builtin_dir = os.path.normpath(builtin_dir)
        if not os.path.isdir(builtin_dir):
            self._logger.warning("内置主题目录不存在: %s", builtin_dir)
            self._themes["light"] = ThemeDefinition(id="light", name="浅色主题", is_dark=False)
            return

        for filename in sorted(os.listdir(builtin_dir)):
            filepath = os.path.join(builtin_dir, filename)
            if not os.path.isfile(filepath):
                continue
            if not filename.endswith('.json'):
                continue
            try:
                theme = self._load_theme_file(filepath)
                if theme and theme.id not in self._themes:
                    self._themes[theme.id] = theme
                    self._logger.info("加载内置主题: %s (%s)", theme.name, theme.id)
            except Exception as e:
                self._logger.warning("加载内置主题文件 %s 失败: %s", filename, e)

        if "light" not in self._themes:
            self._themes["light"] = ThemeDefinition(id="light", name="浅色主题", is_dark=False)

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
        # B8 v1 清理：view.theme 语义 = package/variant（当前仅 default 包）
        self._config.set_view_setting("theme", f"default/{theme_id}")
        self._logger.info("切换主题: %s", theme_id)
        self.theme_changed.emit(theme_id)
        return True

    @staticmethod
    def _parse_theme_setting(value: str) -> str:
        """解析 config view.theme（package/variant 或旧版 variant id）。"""
        return value.rsplit("/", 1)[-1] if "/" in value else value

    def generate_stylesheet(self, theme: Optional[ThemeDefinition] = None) -> str:
        t = theme or self.get_active_theme()
        # B3：v2 可用时 Core Controls 整段走 recipe（单次组装原子性），否则回退 v1
        components = getattr(self, "components", None)
        if components is not None and components.available():
            # 运行时（theme is None）取 v2 激活变体为唯一真相源，保证全局 QSS
            # 与 ThemeAwareMixin 消费一致；显式传 theme（预览/测试）按明暗选择。
            return self._generate_stylesheet_v2(t, use_active=theme is None)
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
QTabWidget::pane {{
    border: 1px solid {c.border};
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

        # 3.5.12：标签 tooltip 路径区分，随主题配色
        parts.append(f"""
QToolTip {{
    background-color: {c.surface};
    color: {c.text_primary};
    border: 1px solid {c.border};
    padding: 4px 8px;
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
    background-color: {c.active_bg};
}}
QLineEdit {{
    border: 1px solid {c.border};
    padding: 4px 8px;
    background-color: {c.card};
    color: {c.text_primary};
}}
QLineEdit:focus {{
    border-color: {c.focus_border};
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
QFrame[frameShape="4"] {{
    background-color: {c.border};
    border: none;
    max-height: 1px;
}}
QFrame[frameShape="5"] {{
    background-color: {c.border};
    border: none;
    max-width: 1px;
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

    def _generate_stylesheet_v2(
        self,
        theme: ThemeDefinition,
        use_active: bool = False,
    ) -> str:
        """B3：全局 QSS 由 v2 recipe 驱动（结构段 token + 控件段 library）。

        仅在 ``generate_stylesheet`` 确认 ``components.available()`` 后调用：
        结构段消费变体 token，Core Controls 与结构辅助（group_box/dialog）
        消费 library 解析结果，整段原子切换（v2 不可用则整体回退 v1）。

        variant 选择（单一真相源，修复深色模式遗漏根因 1）：
          - ``use_active=True``（运行时 _apply_theme）：取 ``svc.active_variant()``
            当前真正激活变体，保证全局 QSS 与 ThemeAwareMixin 消费一致，
            不再依赖 v1 遗留 ``_active_theme_id`` 推导明暗；
          - ``use_active=False``（显式传 theme，如预览/测试）：按传入主题明暗
            选择（``variant_for_dark(theme.is_dark)``）。
        """
        svc = self.theme_v2
        if use_active:
            vid = svc.active_variant()
            if not vid:
                vid = svc.variant_for_dark(theme.is_dark)
        else:
            vid = svc.variant_for_dark(theme.is_dark)
        variant = svc.variant_snapshot(vid)
        assert variant is not None  # available() 已保证 snapshot 非空
        tokens = variant.tokens
        tab = self.components.resolve("tab", vid) or {}

        parts = [f"""
QMainWindow {{
    background-color: {tokens['surface_primary']};
    color: {tokens['text_primary']};
}}
QMenuBar {{
    background-color: {tokens['surface_secondary']};
    color: {tokens['text_primary']};
    border-bottom: 1px solid {tokens['border_muted']};
}}
QMenuBar::item:selected {{
    background-color: {tokens['surface_raised']};
}}
QTabWidget::pane {{
    border: 1px solid {tokens['border_muted']};
}}
QTabBar::tab {{
    background-color: {tab.get('background', tokens['surface_secondary'])};
    color: {tab.get('text', tokens['text_secondary'])};
    border: 1px solid {tab.get('border', tokens['border_muted'])};
    padding: 4px 12px;
}}
QTabBar::tab:selected {{
    background-color: {tab.get('active_background', tokens['surface_primary'])};
    color: {tab.get('active_text', tokens['text_primary'])};
}}
QStatusBar {{
    background-color: {tokens['surface_secondary']};
    color: {tokens['text_secondary']};
    border-top: 1px solid {tokens['border_muted']};
}}
QLabel {{
    color: {tokens['text_primary']};
}}
QSplitter::handle {{
    background-color: {tokens['border_muted']};
}}
QFrame[frameShape="4"] {{
    background-color: {tokens['border_muted']};
    border: none;
    max-height: 1px;
}}
QFrame[frameShape="5"] {{
    background-color: {tokens['border_muted']};
    border: none;
    max-width: 1px;
}}
"""]

        parts.append(self.components.all_qss(vid))

        if theme.stylesheet_overrides:
            for selector, styles in theme.stylesheet_overrides.items():
                parts.append(f"{selector} {{\n    {styles}\n}}\n")

        return "\n".join(parts)

    def initialize_active_theme(self) -> None:
        saved_theme = self._parse_theme_setting(
            self._config.get_view_setting("theme", "light")
        )
        if saved_theme in self._themes:
            self._active_theme_id = saved_theme
        else:
            self._active_theme_id = "light"
        # B2：恢复持久化主题后同步 Theme v2 variant（initialize 不触发 theme_changed）。
        # B7：走 ThemeManager（9.1），不经 controller（启动期无动画）。
        manager = getattr(self, "theme_manager", None)
        if manager is not None:
            manager.request_variant_for_dark(self.get_active_theme().is_dark)
