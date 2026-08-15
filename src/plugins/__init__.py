# -*- coding: utf-8 -*-
"""
PanzerNote 插件系统

提供插件生命周期管理、能力注册与命名空间式运行上下文。
Wave 5：可信插件 + capabilities 声明 + 统一主线程模型。
"""

from .plugin_base import PluginBase, PluginMeta, PluginPermission, PluginState
from .plugin_manager import PluginManager
from .capability_registry import (
    CapabilityRegistry,
    PluginCapabilityError,
    PluginPermissionError,
)
from .plugin_context import PluginContext

__all__ = [
    "PluginBase",
    "PluginMeta",
    "PluginPermission",
    "PluginState",
    "PluginManager",
    "CapabilityRegistry",
    "PluginCapabilityError",
    "PluginPermissionError",
    "PluginContext",
]
