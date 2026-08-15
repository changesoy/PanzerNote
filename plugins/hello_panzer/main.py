# -*- coding: utf-8 -*-
"""
Hello Panzer - 生命周期 + 只读资源 API 示例插件

展示插件生命周期管理和命名空间式只读 API（Wave 5）使用。
"""

from src.plugins.plugin_base import PluginBase, PluginMeta
from src import __version__ as _app_version


class Plugin(PluginBase):

    def get_meta(self) -> PluginMeta:
        return PluginMeta(
            name="hello_panzer",
            version="1.0.0",
            description="生命周期 + 只读资源 API 示例插件",
            author="PanzerNote Team",
            min_app_version=_app_version,
            capabilities=["app.version", "settings.read", "savegame.read"],
            tags=["demo", "basic"],
        )

    def on_load(self, ctx) -> None:
        super().on_load(ctx)
        version = ctx.app.version()
        print(f"[HelloPanzer] 插件已加载 (应用版本: {version})")

    def on_activate(self) -> None:
        super().on_activate()
        if self._ctx:
            try:
                resources = self._ctx.savegame.resources()
                print(f"[HelloPanzer] 当前资源: 燃料={resources.get('fuel', 0)}, "
                      f"弹药={resources.get('ammo', 0)}, "
                      f"钢材={resources.get('steel', 0)}, "
                      f"铝材={resources.get('bauxite', 0)}")
            except Exception as e:
                print(f"[HelloPanzer] 读取资源失败: {e}")
        print("[HelloPanzer] 插件已激活！指挥官好！")

    def on_deactivate(self) -> None:
        super().on_deactivate()
        print("[HelloPanzer] 插件已停用，再见！")

    def on_unload(self) -> None:
        print("[HelloPanzer] 插件已卸载")
        super().on_unload()
