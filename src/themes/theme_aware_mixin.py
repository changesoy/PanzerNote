# -*- coding: utf-8 -*-
"""
主题感知混入
组件继承此混入后可自动订阅 Theme v2 manager 信号并更新样式
"""

from ..themes.theme_engine import ThemeEngine


class ThemeAwareMixin:
    """主题感知混入

    使用方式：
    1. 组件继承 ThemeAwareMixin
    2. 在 __init__ 中调用 _init_theme(theme_engine)
    3. 实现 _apply_theme_colors() 方法，用 Theme v2 token 更新组件样式

    B8 v1 清理：订阅 ThemeManager.theme_committed（package/variant 语义），
    不再使用 v1 遗留信号与配色对象。
    """

    def _init_theme(self, theme_engine: ThemeEngine):
        self._theme_engine = theme_engine
        manager = getattr(theme_engine, "theme_manager", None)
        if manager is not None:
            manager.theme_committed.connect(self._on_theme_committed)
        self._apply_theme_colors()

    def _on_theme_committed(self, *_args):
        self._apply_theme_colors()

    def _apply_theme_colors(self):
        raise NotImplementedError("子类必须实现 _apply_theme_colors 方法")
