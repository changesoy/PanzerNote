# -*- coding: utf-8 -*-
"""
能力注册表（Wave 5 Batch 1）

能力声明（manifest.capabilities）→ 内部权限（PluginPermission）→ 运行时检查。
插件清单只写能力 id，不出现 permissions 字段；CAPABILITY_PERMISSIONS 属实现细节，
能力 → 权限的换算可自由重构而不影响任何插件 manifest。

异常两层命名（D12）：
- PluginCapabilityError：capability 未声明 / 不存在
- PluginPermissionError：capability 已知，但授权不满足
"""

from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .plugin_base import PluginPermission


class PluginCapabilityError(Exception):
    """capability 未声明 / 不存在"""


class PluginPermissionError(Exception):
    """capability 已知，但授权不满足"""


# 内置能力：无需在 manifest 中声明（权限 None + 跳过声明检查）。
# 当前仅 data.read / data.write（插件私有数据命名空间天然隔离，无越权面）。
BUILTIN_CAPABILITIES: Set[str] = {"data.read", "data.write"}

# 能力 id → 内部权限（实现细节，可自由重构）。None 表示无需权限。
CAPABILITY_PERMISSIONS: Dict[str, Optional[PluginPermission]] = {
    "app.version": None,
    "data.read": None,
    "data.write": None,
    "settings.read": PluginPermission.READ_SETTINGS,
    "savegame.read": PluginPermission.READ_SAVEGAME,
    "workspace.recent_files": PluginPermission.READ_WORKSPACE,
    "workspace.open_file": PluginPermission.OPEN_FILE,
    "file_tree.read": PluginPermission.READ_FILE_TREE,
    "editor.read_text": PluginPermission.EDITOR_READ,
    "editor.selection.read": PluginPermission.EDITOR_READ,
    "editor.selection.replace": PluginPermission.EDITOR_WRITE,
    "editor.read_path": PluginPermission.EDITOR_READ,
    "ui.notify": PluginPermission.UI_NOTIFY,
    "ui.show_message": PluginPermission.SHOW_MESSAGE,
    "ui.register_command": PluginPermission.REGISTER_COMMAND,
    "ui.register_menu_item": PluginPermission.REGISTER_MENU,
}


class _Capability:
    """单个能力的注册信息"""

    __slots__ = ("permission", "impl", "copy_result", "pass_plugin_id")

    def __init__(
        self,
        permission: Optional[PluginPermission],
        impl: Callable,
        copy_result: bool,
        pass_plugin_id: bool,
    ) -> None:
        self.permission = permission
        self.impl = impl
        self.copy_result = copy_result
        self.pass_plugin_id = pass_plugin_id


class CapabilityRegistry:
    """能力注册与检查中心

    主程序启动时注册能力实现（CapabilityRegistry.register），插件加载时
    登记其声明的 capabilities（CapabilityRegistry.authorize）。运行时插件
    通过 PluginContext 调用能力，经 invoke 做检查与异常隔离。
    """

    def __init__(self) -> None:
        self._capabilities: Dict[str, _Capability] = {}
        self._auth: Dict[str, Tuple[Set[str], Set[PluginPermission]]] = {}

    def register(
        self,
        cap_id: str,
        permission: Optional[PluginPermission],
        impl: Callable,
        copy_result: bool = True,
        pass_plugin_id: bool = False,
    ) -> None:
        """注册能力实现（由主程序 / 编辑器等宿主注入）

        pass_plugin_id=True 时，调用方插件 id 会作为 impl 第一个位置参数传入
        （命名空间类能力如 data.read/write 需要知道调用者以隔离数据）。
        """
        self._capabilities[cap_id] = _Capability(permission, impl, copy_result, pass_plugin_id)

    def has(self, cap_id: str) -> bool:
        return cap_id in self._capabilities

    def resolve_permissions(self, capabilities: List[str]) -> Set[PluginPermission]:
        """将 manifest 中的能力列表换算为内部权限集合"""
        perms: Set[PluginPermission] = set()
        for cap in capabilities:
            perm = CAPABILITY_PERMISSIONS.get(cap)
            if perm is not None:
                perms.add(perm)
        return perms

    def authorize(self, plugin_id: str, capabilities: List[str]) -> None:
        """登记插件声明的能力（加载插件时调用）"""
        self._auth[plugin_id] = (set(capabilities), self.resolve_permissions(capabilities))

    def revoke(self, plugin_id: str) -> None:
        """撤销插件授权（卸载插件时调用）"""
        self._auth.pop(plugin_id, None)

    def invoke(self, cap_id: str, plugin_id: str, *args: Any, **kwargs: Any) -> Any:
        """权限检查 + 调用实现 + 深拷贝保护

        内置能力（BUILTIN_CAPABILITIES）无需在 manifest 声明，跳过声明检查。

        Raises:
            PluginCapabilityError: 能力不存在，或插件清单未声明该能力（非内置）
            PluginPermissionError: 能力已知，但内部权限换算不通过
        """
        cap = self._capabilities.get(cap_id)
        if cap is None:
            raise PluginCapabilityError(f"能力不存在或未注册: {cap_id}")

        declared, perms = self._auth.get(plugin_id, (set(), set()))
        if cap_id not in declared and cap_id not in BUILTIN_CAPABILITIES:
            raise PluginCapabilityError(f"插件 {plugin_id} 未声明能力: {cap_id}")
        if cap.permission is not None and cap.permission not in perms:
            raise PluginPermissionError(
                f"能力 {cap_id} 需要权限 {cap.permission.value}，"
                f"插件 {plugin_id} 授权不满足"
            )

        if cap.pass_plugin_id:
            result = cap.impl(plugin_id, *args, **kwargs)
        else:
            result = cap.impl(*args, **kwargs)
        if cap.copy_result:
            from copy import deepcopy
            return deepcopy(result)
        return result
