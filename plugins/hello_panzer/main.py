# -*- coding: utf-8 -*-
"""
Hello Panzer - 基础功能示例插件

展示插件生命周期管理和只读 API 使用。
"""

from src.plugins.plugin_base import PluginBase, PluginMeta, PluginPermission
from src import __version__ as _app_version


class Plugin(PluginBase):

    def get_meta(self) -> PluginMeta:
        return PluginMeta(
            name="hello_panzer",
            version="1.0.0",
            description="基础功能示例插件 - 在日志中输出问候信息",
            author="PanzerNote Team",
            min_app_version=_app_version,
            permissions=[PluginPermission.READ_SETTINGS, PluginPermission.READ_SAVEGAME],
            tags=["demo", "basic"],
        )

    def on_load(self, api) -> None:
        super().on_load(api)
        version = api.get_app_version()
        print(f"[HelloPanzer] 插件已加载 (应用版本: {version})")

    def on_activate(self) -> None:
        super().on_activate()
        if self._api:
            try:
                resources = self._api.get_resources()
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
