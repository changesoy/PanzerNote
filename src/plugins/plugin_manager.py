# -*- coding: utf-8 -*-
"""
插件管理器

负责插件的扫描、加载、激活、停用和卸载。
支持从 plugins/ 目录递归扫描插件包，验证完整性，提供热加载机制。

Wave 5（Batch 1）变更：
- 移除 PluginSandbox 线程包装 / 30s 超时（D3），lifecycle 全部在主线程直调。
- 装配命名空间式 PluginContext（D4），manifest 权限字段改为 capabilities（D6）。
- 异常隔离两层规则（D7）：生命周期异常 → ERROR；回调异常 → 仅 log（不自动禁插件，D8）。

Wave 5（Batch 5）变更：
- 启动延迟加载（D5）：activate_enabled_plugins 由主窗口在窗口显示后
  QTimer.singleShot(0, ...) 调用，插件不进启动关键路径。
- 启动恢复 marker（D14）：on_load 前写入、on_activate 成功后清除；
  残留 marker（上次启动在启动阶段异常退出）→ 插件进入安全模式，下次启动跳过。
"""

import importlib
import importlib.util
import json
import os
import re
import sys
from typing import Any, Callable, Dict, List, Optional, Type, cast

from ..utils.logger import get_logger
from .capability_registry import CapabilityRegistry
from .plugin_base import PluginBase, PluginState
from .plugin_context import PluginContext


class PluginLoadError(Exception):
    pass


class PluginValidationError(Exception):
    pass


class PluginManager:
    PLUGIN_MANIFEST = "plugin.json"
    PLUGIN_ENTRY_CLASS = "Plugin"
    REQUIRED_MANIFEST_FIELDS = {"name", "version", "entry"}
    # Batch 5（D14）：启动恢复 marker 文件后缀（目录下 {plugin_id}.marker）
    STARTUP_MARKER_SUFFIX = ".marker"

    def __init__(self, config, plugins_dir: Optional[str] = None, event_bus=None,
                 startup_markers_dir: Optional[str] = None):
        self._config = config
        self._plugins_dir = plugins_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "plugins"
        )
        # Batch 4：事件订阅总线（卸载自动解绑；测试可传 None）
        self._event_bus = event_bus
        # Batch 5（D14）：启动恢复 marker 目录（用户数据目录下，跨启动持久）
        self._startup_markers_dir = startup_markers_dir or self._default_startup_markers_dir()
        self._plugins: Dict[str, PluginBase] = {}
        self._manifests: Dict[str, Dict] = {}
        self._disabled_plugins: set = set()
        self._registry = CapabilityRegistry()
        # 卸载钩子：宿主清理插件注册的宿主侧资源（如命令面板命令）
        self._unload_hooks: List[Callable[[str], None]] = []
        self._logger = get_logger(__name__)

    def _default_startup_markers_dir(self) -> str:
        get_base_path = getattr(self._config, "get_base_path", None)
        if callable(get_base_path):
            base: str = get_base_path()
        else:
            base = self._config.get_app_dir()
        return os.path.join(base, "data", "plugin_startup")

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    @property
    def plugins_dir(self) -> str:
        return self._plugins_dir

    def scan_plugins(self) -> List[str]:
        discovered: List[str] = []
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
                # Batch 5（D14）：残留 marker → 安全模式（上次启动在启动阶段异常退出）
                self._restore_safe_mode(plugin_id)
                discovered.append(plugin_id)
                self._logger.info("发现插件: %s v%s", plugin_id, manifest["version"])
            except (PluginValidationError, json.JSONDecodeError, OSError) as e:
                self._logger.warning("跳过无效插件 %s: %s", entry, e)

        return discovered

    # === 启动恢复 marker（Batch 5 / D14） ===

    def get_startup_marker_path(self, plugin_id: str) -> str:
        return os.path.join(self._startup_markers_dir, plugin_id + self.STARTUP_MARKER_SUFFIX)

    def is_safe_mode(self, plugin_id: str) -> bool:
        """插件是否处于安全模式（上次启动在启动阶段异常退出，需手动处理）"""
        return plugin_id in self._disabled_plugins

    def get_safe_mode_plugins(self) -> List[str]:
        return sorted(self._disabled_plugins)

    def _restore_safe_mode(self, plugin_id: str) -> None:
        """扫描时检测残留启动 marker → 进入安全模式（D14）。"""
        if os.path.exists(self.get_startup_marker_path(plugin_id)):
            self._disabled_plugins.add(plugin_id)
            self._logger.warning(
                "检测到残留启动 marker，插件 %s 进入安全模式（上次启动可能异常退出）",
                plugin_id,
            )

    def _write_startup_marker(self, plugin_id: str) -> None:
        """on_load 前写入「正在启动插件 X」marker（D14）。"""
        try:
            os.makedirs(self._startup_markers_dir, exist_ok=True)
            with open(self.get_startup_marker_path(plugin_id), "w", encoding="utf-8") as fh:
                fh.write(plugin_id)
        except OSError:
            self._logger.exception("写入插件启动 marker 失败: %s", plugin_id)

    def _clear_startup_marker(self, plugin_id: str) -> None:
        """清除启动 marker。on_activate 成功后调用；普通异常（程序未崩溃）也调用，
        使异常被隔离处理后下次启动仍可重试。仅进程级崩溃（死循环/硬崩溃）才残留 marker。
        """
        marker_path = self.get_startup_marker_path(plugin_id)
        if os.path.exists(marker_path):
            try:
                os.remove(marker_path)
            except OSError:
                self._logger.exception("清除插件启动 marker 失败: %s", marker_path)

    def load_plugin(self, plugin_id: str) -> PluginBase:
        if plugin_id in self._plugins:
            plugin = self._plugins[plugin_id]
            if plugin.state in (PluginState.LOADED, PluginState.ACTIVATED):
                return plugin

        if plugin_id not in self._manifests:
            raise PluginLoadError(f"未发现插件: {plugin_id}")

        manifest = self._manifests[plugin_id]
        plugin_path = os.path.join(self._plugins_dir, self._find_plugin_dir(plugin_id))

        # Batch 5（D14）：手动加载 = 用户处理安全模式 → 解除并清理残留 marker
        self._disabled_plugins.discard(plugin_id)
        self._clear_startup_marker(plugin_id)

        try:
            plugin_class = self._import_plugin(plugin_path, manifest["entry"])
            plugin = plugin_class()
            plugin.meta = plugin.get_meta()

            self._registry.authorize(plugin_id, manifest.get("capabilities", []))
            ctx = PluginContext(plugin_id, manifest["version"], self._registry)
            # Batch 5（D14）：on_load 前写入「正在启动插件 X」
            self._write_startup_marker(plugin_id)
            plugin.on_load(ctx)

            self._plugins[plugin_id] = plugin
            self._logger.info("插件已加载: %s", plugin_id)
            return plugin

        except Exception as e:
            # Batch 5（D14）：普通异常已被隔离（程序未崩溃）→ 清除 marker，下次可重试
            self._clear_startup_marker(plugin_id)
            if plugin_id in self._plugins:
                self._plugins[plugin_id].state = PluginState.ERROR
            raise PluginLoadError(f"加载插件 {plugin_id} 失败: {e}") from e

    def activate_plugin(self, plugin_id: str) -> None:
        plugin = self._get_plugin(plugin_id)
        if plugin_id in self._disabled_plugins:
            raise PluginLoadError(
                f"插件 {plugin_id} 处于安全模式（上次启动异常），请先在插件管理中处理"
            )
        if plugin.state == PluginState.ACTIVATED:
            self._logger.info("插件已激活: %s", plugin_id)
            return
        if plugin.state not in (PluginState.LOADED, PluginState.DEACTIVATED):
            raise PluginLoadError(
                f"插件 {plugin_id} 状态为 {plugin.state.name}，无法激活"
            )
        try:
            plugin.on_activate()
            # Batch 5（D14）：on_activate 成功后清除启动 marker
            self._clear_startup_marker(plugin_id)
            self._logger.info("插件已激活: %s", plugin_id)
        except Exception as e:
            # Batch 5（D14）：异常已被隔离（程序未崩溃）→ 清除 marker，下次可重试
            self._clear_startup_marker(plugin_id)
            plugin.state = PluginState.ERROR
            self._logger.exception("激活插件 %s 失败: %s", plugin_id, e)
            raise PluginLoadError(f"激活插件 {plugin_id} 失败: {e}") from e

    def activate_enabled_plugins(self) -> List[str]:
        """Batch 5（D5）：启动延迟加载——加载并激活所有启用且非安全模式的插件。

        由主窗口在 session 恢复 + 窗口显示后经 QTimer.singleShot(0, ...) 调用。
        单个插件失败不影响其余插件；返回成功激活的插件 id 列表。
        """
        activated: List[str] = []
        for plugin_id in self._manifests:
            if not self._is_enabled(plugin_id):
                self._logger.debug("跳过未启用插件: %s", plugin_id)
                continue
            if plugin_id in self._disabled_plugins:
                self._logger.warning("跳过安全模式插件: %s", plugin_id)
                continue
            try:
                self.load_plugin(plugin_id)
                self.activate_plugin(plugin_id)
                activated.append(plugin_id)
            except Exception as e:
                self._logger.exception("自动启动插件 %s 失败: %s", plugin_id, e)
        return activated

    def _is_enabled(self, plugin_id: str) -> bool:
        manifest = self._manifests.get(plugin_id, {})
        return bool(manifest.get("enabled", True))

    def deactivate_plugin(self, plugin_id: str) -> None:
        plugin = self._get_plugin(plugin_id)
        if plugin.state != PluginState.ACTIVATED:
            return
        try:
            plugin.on_deactivate()
            self._logger.info("插件已停用: %s", plugin_id)
        except Exception as e:
            plugin.state = PluginState.ERROR
            self._logger.exception("停用插件 %s 失败: %s", plugin_id, e)

    def unload_plugin(self, plugin_id: str) -> None:
        if plugin_id not in self._plugins:
            return
        plugin = self._plugins[plugin_id]
        if plugin.state == PluginState.ACTIVATED:
            self.deactivate_plugin(plugin_id)
        try:
            plugin.on_unload()
        except Exception as e:
            self._logger.exception("卸载插件 %s 失败: %s", plugin_id, e)
        finally:
            if self._event_bus is not None:
                # Batch 4：卸载自动解绑事件订阅（D9）
                self._event_bus.unsubscribe_all(plugin_id)
            self._registry.revoke(plugin_id)
            self._notify_unloaded(plugin_id)
            del self._plugins[plugin_id]
            self._logger.info("插件已卸载: %s", plugin_id)

    def add_unload_hook(self, hook: Callable[[str], None]) -> None:
        """注册插件卸载钩子，宿主在插件卸载后清理其注册的宿主侧资源。"""
        self._unload_hooks.append(hook)

    def _notify_unloaded(self, plugin_id: str) -> None:
        for hook in self._unload_hooks:
            try:
                hook(plugin_id)
            except Exception:
                self._logger.exception("插件卸载钩子异常: %s", plugin_id)

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
        info["state"] = self._plugin_state_name(plugin_id)
        return info

    def get_discovered_plugins(self) -> List[Dict[str, Any]]:
        result = []
        for plugin_id, manifest in self._manifests.items():
            info = dict(manifest)
            info["state"] = self._plugin_state_name(plugin_id)
            result.append(info)
        return result

    def _plugin_state_name(self, plugin_id: str) -> str:
        if plugin_id in self._plugins:
            return self._plugins[plugin_id].state.name
        if plugin_id in self._disabled_plugins:
            return "SAFE_MODE"
        return PluginState.UNLOADED.name

    @staticmethod
    def _load_manifest(manifest_path: str) -> Dict:
        with open(manifest_path, 'r', encoding='utf-8') as fh:
            return cast(Dict[str, Any], json.load(fh))

    def _validate_manifest(self, manifest: Dict) -> None:
        missing = self.REQUIRED_MANIFEST_FIELDS - set(manifest.keys())
        if missing:
            raise PluginValidationError(f"manifest 缺少必需字段: {missing}")

        name = manifest["name"]
        if not isinstance(name, str) or not name.strip():
            raise PluginValidationError("插件名称无效")
        # 插件名用作文件系统路径（data/plugin_data/{name}、启动 marker {name}.marker），
        # 限制为安全字符集，防止路径分隔符 / 相对路径污染数据目录
        if not re.fullmatch(r"[A-Za-z0-9_\-]+", name):
            raise PluginValidationError(
                f"插件名称仅允许字母/数字/下划线/连字符: {name!r}"
            )

        version = manifest["version"]
        if not isinstance(version, str) or not version.strip():
            raise PluginValidationError("插件版本无效")

        entry = manifest["entry"]
        if not isinstance(entry, str) or not entry.strip():
            raise PluginValidationError("插件入口无效")

        caps = manifest.get("capabilities", [])
        if not isinstance(caps, list):
            raise PluginValidationError("capabilities 必须为列表")
        for cap in caps:
            if not isinstance(cap, str) or not cap.strip():
                raise PluginValidationError(f"无效能力声明: {cap}")

        # Batch 5（D5）：enabled（可选，默认 true）控制启动时是否自动加载激活
        enabled = manifest.get("enabled", True)
        if not isinstance(enabled, bool):
            raise PluginValidationError("enabled 必须为布尔值")

    def _find_plugin_path(self, plugin_id: str) -> str:
        return os.path.join(self._plugins_dir, self._find_plugin_dir(plugin_id))

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
                    self._logger.debug("加载清单失败: %s", manifest_path)
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

        return cast(Type[PluginBase], plugin_class)

    def _get_plugin(self, plugin_id: str) -> PluginBase:
        if plugin_id not in self._plugins:
            raise PluginLoadError(f"插件未加载: {plugin_id}")
        return self._plugins[plugin_id]
