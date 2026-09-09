# -*- coding: utf-8 -*-
"""
主题引擎（Theme v2 唯一运行时）

职责：
- 初始化 Theme v2（default 包加载、组件库、管理器）
- 提供全局 QSS 生成入口（单一真相源：当前激活 variant）
- 恢复持久化的主题配置（config view.theme，package/variant 语义）

v1 遗留类型、builtin/外部主题加载、YAML 解析与降级回退路径已随
Wave8 Batch C 全部删除。
v2 加载失败 → 启动显式报错（ThemeLoadError），永不静默回退。
"""

from pathlib import Path

from PyQt6.QtCore import QObject

from ..utils.logger import get_logger
from .theme_v2.errors import ThemeLoadError
from .theme_v2.library import ThemeComponentLibrary
from .theme_v2.manager import ThemeManager
from .theme_v2.service import ThemeV2Service
from .theme_v2.transition import CommitResult


class ThemeEngine(QObject):
    """Theme v2 运行时装配与全局 QSS 入口。"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._logger = get_logger(__name__)
        self._init_theme_v2()

    def _init_theme_v2(self) -> None:
        """初始化 Theme v2 运行时（default 包）。

        加载失败 → 抛 ThemeLoadError（启动显式报错，永不静默回退 v1）。
        """
        themes_dir = Path(__file__).resolve().parents[2] / "themes"
        self.theme_v2 = ThemeV2Service(themes_dir, parent=self)
        self.components = ThemeComponentLibrary(self.theme_v2)
        if not self.theme_v2.load_default():
            raise ThemeLoadError(
                "主题 v2 加载失败：请检查 themes/default/ 数据完整性，详细错误见日志。"
            )
        self.theme_manager = ThemeManager(themes_dir, self.theme_v2, parent=self)

    @staticmethod
    def _parse_theme_setting(value: str) -> tuple[str, str]:
        """解析 config view.theme：``package/variant`` 或旧版 ``variant id``。

        旧值 ``light``/``dark`` 在读取时迁移为 ``("default", "light")``/``("default", "dark")``。
        """
        if "/" in value:
            package_id, variant_id = value.split("/", 1)
            return package_id, variant_id
        return "default", value

    def generate_stylesheet(self) -> str:
        """全局 QSS：结构段消费激活 variant token，Core Controls 走 library。

        单一真相源：``svc.active_variant()``（与 ThemeAwareMixin 消费一致），
        不再依赖任何 v1 明暗状态推导。
        """
        svc = self.theme_v2
        vid = svc.active_variant()
        if not vid:
            vid = svc.variant_for_dark(False)
        variant = svc.variant_snapshot(vid)
        assert variant is not None  # load_default 成功即保证 snapshot 非空
        tokens = variant.tokens
        tab = self.components.resolve("tab", vid) or {}
        # 补漏 C：QStatusBar 全局段收敛到 statusbar recipe（与 status_bar.py 局部 QSS 同源）
        statusbar = self.components.resolve("statusbar", vid) or {}

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
    background-color: {statusbar.get('background', tokens['surface_secondary'])};
    color: {statusbar.get('text', tokens['text_secondary'])};
    border-top: 1px solid {statusbar.get('border', tokens['border_muted'])};
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
        return "\n".join(parts)

    def initialize_active_theme(self) -> None:
        """恢复持久化主题（config view.theme）→ 经 manager 激活 v2 变体。

        ``package/variant`` 语义；旧值 ``light``/``dark`` 在读取时迁移为 default 包。
        恢复失败回退 light 变体（启动期不弹错）。
        """
        manager = getattr(self, "theme_manager", None)
        if manager is None:
            return
        saved = self._config.get_view_setting("theme", "default/light")
        package_id, variant_id = self._parse_theme_setting(saved)
        if manager.request(package_id, variant_id) is not CommitResult.COMMITTED:
            self._logger.warning(
                "恢复主题失败: %s/%s，回退 light", package_id, variant_id
            )
            manager.request_variant_for_dark(False)
