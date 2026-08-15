# -*- coding: utf-8 -*-
"""
Hello Panzer - 生命周期 + 只读资源 API 示例插件

展示插件生命周期管理和命名空间式只读 API（Wave 5）使用。
"""

from src.plugins.plugin_base import PluginBase, PluginMeta
from src.utils.logger import get_logger
from src import __version__ as _app_version

logger = get_logger("plugins.hello_panzer")


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
        logger.info("插件已加载 (应用版本: %s)", version)

    def on_activate(self) -> None:
        super().on_activate()
        if self._ctx:
            try:
                resources = self._ctx.savegame.resources()
                logger.info(
                    "当前资源: 燃料=%s, 弹药=%s, 钢材=%s, 铝材=%s",
                    resources.get("fuel", 0),
                    resources.get("ammo", 0),
                    resources.get("steel", 0),
                    resources.get("bauxite", 0),
                )
            except Exception as e:
                logger.warning("读取资源失败: %s", e)
        logger.info("插件已激活！指挥官好！")

    def on_deactivate(self) -> None:
        super().on_deactivate()
        logger.info("插件已停用，再见！")

    def on_unload(self) -> None:
        logger.info("插件已卸载")
        super().on_unload()
