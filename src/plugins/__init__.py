# -*- coding: utf-8 -*-
"""
PanzerNote 插件系统

提供插件生命周期管理、沙箱隔离和权限控制。
"""

from .plugin_base import PluginBase, PluginMeta, PluginPermission, PluginState
from .plugin_manager import PluginManager
from .plugin_sandbox import PluginSandbox

__all__ = [
    "PluginBase",
    "PluginMeta",
    "PluginPermission",
    "PluginState",
    "PluginManager",
    "PluginSandbox",
]
