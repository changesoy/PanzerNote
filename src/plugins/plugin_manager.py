# -*- coding: utf-8 -*-
"""
插件管理器

负责插件的扫描、加载、激活、停用和卸载。
支持从 plugins/ 目录递归扫描插件包，验证完整性，
提供热加载机制。
"""

import importlib
import importlib.util
import json
import os
import sys
from typing import Any, Dict, List, Optional, Type

from ..utils.logger import get_logger
from .plugin_base import PluginBase, PluginMeta, PluginPermission, PluginState
from .plugin_sandbox import PluginAPI, PluginSandbox, SandboxTimeoutError, SandboxViolationError


class PluginLoadError(Exception):
    pass


class PluginValidationError(Exception):
    pass


class PluginManager:
    PLUGIN_MANIFEST = "plugin.json"
    PLUGIN_ENTRY_CLASS = "Plugin"
    REQUIRED_MANIFEST_FIELDS = {"name", "version", "entry"}

    def __init__(self, config, plugins_dir: Optional[str] = None):
        self._config = config
        self._plugins_dir = plugins_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "plugins"
        )
        self._plugins: Dict[str, PluginBase] = {}
        self._manifests: Dict[str, Dict] = {}
        self._sandbox = PluginSandbox(config, timeout=30)
        self._logger = get_logger(__name__)

    @property
    def plugins_dir(self) -> str:
        return self._plugins_dir

    def scan_plugins(self) -> List[str]:
        discovered = []
        if not os.path.isdir(self._plugins_dir):
            self._logger.info("插件目录不存在: %s", self._plugins_dir)
            return discovered

        for entry in os.listdir(self._plugins_dir):
            plugin_path = os.path.join(self._plugins_dir, entry)
            if not os.path.isdir(plugin_path):
                continue
            manifest_path = os.path.join(plugin_path, self.PLUGIN_MANIFEST)
            if not os.path.isfile(manifest_path):
                self._logger.debug("跳过无 manifest 的目录: %s", entry)
                continue
            try:
                manifest = self._load_manifest(manifest_path)
                self._validate_manifest(manifest)
                plugin_id = manifest["name"]
                self._manifests[plugin_id] = manifest
                discovered.append(plugin_id)
                self._logger.info("发现插件: %s v%s", plugin_id, manifest["version"])
            except (PluginValidationError, json.JSONDecodeError, OSError) as e:
                self._logger.warning("跳过无效插件 %s: %s", entry, e)

        return discovered

    def load_plugin(self, plugin_id: str) -> PluginBase:
        if plugin_id in self._plugins:
            plugin = self._plugins[plugin_id]
            if plugin.state in (PluginState.LOADED, PluginState.ACTIVATED):
                return plugin

        if plugin_id not in self._manifests:
            raise PluginLoadError(f"未发现插件: {plugin_id}")

        manifest = self._manifests[plugin_id]
        plugin_path = os.path.join(self._plugins_dir, self._find_plugin_dir(plugin_id))

        try:
            plugin_class = self._import_plugin(plugin_path, manifest["entry"])
            plugin = plugin_class()
            plugin.meta = plugin.get_meta()

            api = self._sandbox.create_api(plugin)
            self._sandbox.safe_load(plugin, api)

            self._plugins[plugin_id] = plugin
            self._logger.info("插件已加载: %s", plugin_id)
            return plugin

        except Exception as e:
            raise PluginLoadError(f"加载插件 {plugin_id} 失败: {e}") from e

    def activate_plugin(self, plugin_id: str) -> None:
        plugin = self._get_plugin(plugin_id)
        if plugin.state == PluginState.ACTIVATED:
            self._logger.info("插件已激活: %s", plugin_id)
            return
        if plugin.state not in (PluginState.LOADED, PluginState.DEACTIVATED):
            raise PluginLoadError(
                f"插件 {plugin_id} 状态为 {plugin.state.name}，无法激活"
            )
        try:
            self._sandbox.safe_activate(plugin)
            self._logger.info("插件已激活: %s", plugin_id)
        except (SandboxTimeoutError, Exception) as e:
            plugin.state = PluginState.ERROR
            raise PluginLoadError(f"激活插件 {plugin_id} 失败: {e}") from e

    def deactivate_plugin(self, plugin_id: str) -> None:
        plugin = self._get_plugin(plugin_id)
        if plugin.state != PluginState.ACTIVATED:
            return
        try:
            self._sandbox.safe_deactivate(plugin)
            self._logger.info("插件已停用: %s", plugin_id)
        except (SandboxTimeoutError, Exception) as e:
            plugin.state = PluginState.ERROR
            self._logger.warning("停用插件 %s 失败: %s", plugin_id, e)

    def unload_plugin(self, plugin_id: str) -> None:
        if plugin_id not in self._plugins:
            return
        plugin = self._plugins[plugin_id]
        if plugin.state == PluginState.ACTIVATED:
            self.deactivate_plugin(plugin_id)
        try:
            self._sandbox.safe_unload(plugin)
        except (SandboxTimeoutError, Exception) as e:
            self._logger.warning("卸载插件 %s 失败: %s", plugin_id, e)
        finally:
            del self._plugins[plugin_id]
            self._logger.info("插件已卸载: %s", plugin_id)

    def reload_plugin(self, plugin_id: str) -> PluginBase:
        was_activated = (
            plugin_id in self._plugins
            and self._plugins[plugin_id].state == PluginState.ACTIVATED
        )

        plugin_path = self._find_plugin_path(plugin_id)
        module_name = f"panzernote_plugin_{os.path.basename(plugin_path)}"

        self.unload_plugin(plugin_id)

        if module_name in sys.modules:
            del sys.modules[module_name]

        plugin = self.load_plugin(plugin_id)
        if was_activated:
            self.activate_plugin(plugin_id)
        return plugin

    def get_plugin(self, plugin_id: str) -> Optional[PluginBase]:
        return self._plugins.get(plugin_id)

    def get_all_plugins(self) -> Dict[str, PluginBase]:
        return dict(self._plugins)

    def get_plugin_info(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        if plugin_id not in self._manifests:
            return None
        manifest = self._manifests[plugin_id]
        info = dict(manifest)
        if plugin_id in self._plugins:
            info["state"] = self._plugins[plugin_id].state.name
        else:
            info["state"] = PluginState.UNLOADED.name
        return info

    def get_discovered_plugins(self) -> List[Dict[str, Any]]:
        result = []
        for plugin_id, manifest in self._manifests.items():
            info = dict(manifest)
            if plugin_id in self._plugins:
                info["state"] = self._plugins[plugin_id].state.name
            else:
                info["state"] = PluginState.UNLOADED.name
            result.append(info)
        return result

    def _load_manifest(self, manifest_path: str) -> Dict:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _validate_manifest(self, manifest: Dict) -> None:
        missing = self.REQUIRED_MANIFEST_FIELDS - set(manifest.keys())
        if missing:
            raise PluginValidationError(f"manifest 缺少必需字段: {missing}")

        name = manifest["name"]
        if not isinstance(name, str) or not name.strip():
            raise PluginValidationError("插件名称无效")

        version = manifest["version"]
        if not isinstance(version, str) or not version.strip():
            raise PluginValidationError("插件版本无效")

        entry = manifest["entry"]
        if not isinstance(entry, str) or not entry.strip():
            raise PluginValidationError("插件入口无效")

        perms = manifest.get("permissions", [])
        if not isinstance(perms, list):
            raise PluginValidationError("permissions 必须为列表")
        for p in perms:
            try:
                PluginPermission(p)
            except ValueError:
                raise PluginValidationError(f"无效权限: {p}")

    def _find_plugin_dir(self, plugin_id: str) -> str:
        for entry in os.listdir(self._plugins_dir):
            plugin_path = os.path.join(self._plugins_dir, entry)
            if not os.path.isdir(plugin_path):
                continue
            manifest_path = os.path.join(plugin_path, self.PLUGIN_MANIFEST)
            if os.path.isfile(manifest_path):
                try:
                    m = self._load_manifest(manifest_path)
                    if m.get("name") == plugin_id:
                        return entry
                except Exception:
                    pass
        raise PluginLoadError(f"找不到插件目录: {plugin_id}")

    def _import_plugin(self, plugin_path: str, entry_module: str) -> Type[PluginBase]:
        module_path = os.path.join(plugin_path, entry_module)
        if not os.path.isfile(module_path):
            module_path = os.path.join(plugin_path, entry_module + ".py")
        if not os.path.isfile(module_path):
            raise PluginLoadError(f"插件入口文件不存在: {entry_module}")

        module_name = f"panzernote_plugin_{os.path.basename(plugin_path)}"

        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise PluginLoadError(f"无法创建模块规范: {module_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            if module_name in sys.modules:
                del sys.modules[module_name]
            raise PluginLoadError(f"执行插件模块失败: {e}") from e

        if not hasattr(module, self.PLUGIN_ENTRY_CLASS):
            if module_name in sys.modules:
                del sys.modules[module_name]
            raise PluginLoadError(
                f"插件模块缺少 {self.PLUGIN_ENTRY_CLASS} 类"
            )

        plugin_class = getattr(module, self.PLUGIN_ENTRY_CLASS)
        if not issubclass(plugin_class, PluginBase):
            if module_name in sys.modules:
                del sys.modules[module_name]
            raise PluginLoadError(
                f"{self.PLUGIN_ENTRY_CLASS} 必须继承 PluginBase"
            )

        return plugin_class

    def _get_plugin(self, plugin_id: str) -> PluginBase:
        if plugin_id not in self._plugins:
            raise PluginLoadError(f"插件未加载: {plugin_id}")
        return self._plugins[plugin_id]
