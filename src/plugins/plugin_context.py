# -*- coding: utf-8 -*-
"""
命名空间式 PluginContext（Wave 5 Batch 1）

插件通过 PluginContext 的子命名空间访问能力（能力边界 = API 边界）：
ctx.app / ctx.settings / ctx.savegame / ctx.workspace / ctx.file_tree / ctx.ui。

每个命名空间方法内部经 CapabilityRegistry.invoke 完成权限检查与深拷贝保护，
插件永远不直接持有 Config / SavegameManager / MainWindow 等内部对象。

后续批次扩展：ctx.editor（Batch 2）、ctx.data（Batch 3）、ctx.events（Batch 4）。
"""

from typing import Any, Callable, Dict, List, Optional, cast

from .capability_registry import CapabilityRegistry


class _NamespaceAPI:
    """命名空间基类：持有 registry 与当前插件 id"""

    def __init__(self, registry: CapabilityRegistry, plugin_id: str) -> None:
        self._registry = registry
        self._plugin_id = plugin_id


class AppAPI(_NamespaceAPI):
    """应用信息（app.version）"""

    def version(self) -> str:
        return cast(str, self._registry.invoke("app.version", self._plugin_id))


class SettingsAPI(_NamespaceAPI):
    """设置读取（settings.read）"""

    def get(self, key: str, default: Any = None) -> Any:
        return self._registry.invoke("settings.read", self._plugin_id, "get", key, default)

    def get_editor(self, key: str, default: Any = None) -> Any:
        return self._registry.invoke("settings.read", self._plugin_id, "editor", key, default)

    def get_game(self, key: str, default: Any = None) -> Any:
        return self._registry.invoke("settings.read", self._plugin_id, "game", key, default)

    def get_secretary(self, key: str, default: Any = None) -> Any:
        return self._registry.invoke("settings.read", self._plugin_id, "secretary", key, default)


class SavegameAPI(_NamespaceAPI):
    """存档读取（savegame.read）"""

    def resources(self) -> Dict[str, int]:
        return cast(Dict[str, int], self._registry.invoke("savegame.read", self._plugin_id, "resources"))

    def field(self, key: str, default: Any = None) -> Any:
        return self._registry.invoke("savegame.read", self._plugin_id, "field", key, default)


class WorkspaceAPI(_NamespaceAPI):
    """工作区（workspace.recent_files / workspace.open_file）"""

    def recent_files(self) -> List[str]:
        return cast(List[str], self._registry.invoke("workspace.recent_files", self._plugin_id))

    def open_file(self, filepath: str) -> bool:
        """打开文件到编辑器（经宿主安全校验）"""
        return cast(bool, self._registry.invoke("workspace.open_file", self._plugin_id, filepath))


class FileTreeAPI(_NamespaceAPI):
    """笔记库（file_tree.read）"""

    def notebooks_path(self) -> str:
        return cast(str, self._registry.invoke("file_tree.read", self._plugin_id))


class EditorAPI(_NamespaceAPI):
    """编辑器能力（editor.read_text / selection / read_path）"""

    def __init__(self, registry: CapabilityRegistry, plugin_id: str) -> None:
        super().__init__(registry, plugin_id)
        self.selection = EditorSelectionAPI(registry, plugin_id)

    def get_text(self) -> str:
        """读取当前文档全文"""
        return cast(str, self._registry.invoke("editor.read_text", self._plugin_id))

    def get_current_path(self) -> Optional[str]:
        """获取当前文件路径（未保存的新文件返回 None）"""
        return cast(Optional[str], self._registry.invoke("editor.read_path", self._plugin_id))

    def replace_text(self, text: str) -> None:
        """用给定文本替换当前选区"""
        self._registry.invoke("editor.selection.replace", self._plugin_id, text)


class EditorSelectionAPI(_NamespaceAPI):
    """编辑器选区读取（editor.selection.read）"""

    def get_text(self) -> str:
        """读取当前选区文本（无选区返回空串）"""
        return cast(str, self._registry.invoke("editor.selection.read", self._plugin_id))


class UIAPI(_NamespaceAPI):
    """UI 能力（ui.notify / show_message / register_command / register_menu_item）"""

    def notify(self, message: str, level: str = "info") -> None:
        """状态栏轻提示（level: info / warning / error）"""
        self._registry.invoke("ui.notify", self._plugin_id, message, level)

    def show_message(self, message: str) -> None:
        """通过小秘书显示消息"""
        self._registry.invoke("ui.show_message", self._plugin_id, message)

    def register_command(self, command_id: str, handler: Callable) -> None:
        """注册命令到命令面板（command_id 建议格式 plugin_name:action）"""
        self._registry.invoke("ui.register_command", self._plugin_id, command_id, handler)

    def register_menu_item(self, label: str, handler: Callable) -> None:
        """注册菜单项到插件菜单"""
        self._registry.invoke("ui.register_menu_item", self._plugin_id, label, handler)


class PluginContext:
    """宿主给当前插件的运行上下文（原 PluginAPI 更名而来，D4）"""

    def __init__(
        self,
        plugin_id: str,
        plugin_version: str,
        registry: CapabilityRegistry,
    ) -> None:
        self.plugin_id = plugin_id
        self.plugin_version = plugin_version
        self.app = AppAPI(registry, plugin_id)
        self.settings = SettingsAPI(registry, plugin_id)
        self.savegame = SavegameAPI(registry, plugin_id)
        self.workspace = WorkspaceAPI(registry, plugin_id)
        self.file_tree = FileTreeAPI(registry, plugin_id)
        self.editor = EditorAPI(registry, plugin_id)
        self.ui = UIAPI(registry, plugin_id)
        # Batch 3: self.data / Batch 4: self.events
