# -*- coding: utf-8 -*-
"""
主题感知混入
组件继承此混入后可自动订阅 theme_changed 信号并更新样式
"""

from ..themes.theme_engine import ThemeEngine


class ThemeAwareMixin:
    """主题感知混入

    使用方式：
    1. 组件继承 ThemeAwareMixin
    2. 在 __init__ 中调用 _init_theme(theme_engine)
    3. 实现 _apply_theme_colors(colors) 方法，用主题颜色更新组件样式
    """

    def _init_theme(self, theme_engine: ThemeEngine):
        self._theme_engine = theme_engine
        theme_engine.theme_changed.connect(self._on_theme_changed)
        self._apply_theme_colors(theme_engine.get_active_theme().colors)

    def _on_theme_changed(self, theme_id: str):
        theme = self._theme_engine.get_theme(theme_id)
        if theme:
            self._apply_theme_colors(theme.colors)

    def _apply_theme_colors(self, colors):
        raise NotImplementedError("子类必须实现 _apply_theme_colors 方法")
