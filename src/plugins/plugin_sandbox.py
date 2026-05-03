# -*- coding: utf-8 -*-
"""
插件沙箱

提供插件运行隔离、超时控制和资源访问限制。
插件在独立线程中执行，设置最大执行超时时间。
"""

import threading
from typing import Any, Callable, Dict, List, Optional

from ..utils.logger import get_logger
from .plugin_base import PluginBase, PluginPermission, PluginState


class SandboxViolationError(Exception):
    pass


class SandboxTimeoutError(Exception):
    pass


class PluginAPI:
    MVP_READ_ONLY = True
    MAX_EXECUTION_TIMEOUT = 30

    def __init__(self, config, permissions: List[PluginPermission]):
        self._config = config
        self._permissions = set(permissions)
        self._logger = get_logger(__name__)

    def _check_permission(self, perm: PluginPermission) -> None:
        if perm not in self._permissions:
            raise SandboxViolationError(
                f"插件缺少权限: {perm.value}"
            )
        if self.MVP_READ_ONLY and perm in (
            PluginPermission.ACCESS_FILESYSTEM,
            PluginPermission.ACCESS_NETWORK,
        ):
            raise SandboxViolationError(
                f"MVP 阶段禁止写入权限: {perm.value}"
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        self._check_permission(PluginPermission.READ_SETTINGS)
        return self._config.get_setting(key, default)

    def get_editor_setting(self, key: str, default: Any = None) -> Any:
        self._check_permission(PluginPermission.READ_SETTINGS)
        return self._config.get_editor_setting(key, default)

    def get_game_setting(self, key: str, default: Any = None) -> Any:
        self._check_permission(PluginPermission.READ_SETTINGS)
        return self._config.get_game_setting(key, default)

    def get_secretary_setting(self, key: str, default: Any = None) -> Any:
        self._check_permission(PluginPermission.READ_SETTINGS)
        return self._config.get_secretary_setting(key, default)

    def get_resources(self) -> Dict[str, int]:
        self._check_permission(PluginPermission.READ_SAVEGAME)
        return self._config.get_resources()

    def get_savegame_field(self, key: str, default: Any = None) -> Any:
        self._check_permission(PluginPermission.READ_SAVEGAME)
        return self._config.get_savegame().get(key, default)

    def get_recent_files(self) -> List[str]:
        self._check_permission(PluginPermission.READ_WORKSPACE)
        return self._config.get_recent_files()

    def get_notebooks_path(self) -> str:
        self._check_permission(PluginPermission.READ_FILE_TREE)
        return self._config.get_notebooks_path()

    def get_app_version(self) -> str:
        from .. import __version__
        return __version__


class PluginSandbox:
    def __init__(self, config, timeout: int = 30):
        self._config = config
        self._timeout = timeout
        self._logger = get_logger(__name__)

    def create_api(self, plugin: PluginBase) -> PluginAPI:
        permissions = []
        if plugin.meta:
            permissions = list(plugin.meta.permissions)
        return PluginAPI(self._config, permissions)

    def execute_safe(
        self,
        func: Callable,
        *args,
        timeout: Optional[int] = None,
        **kwargs,
    ) -> Any:
        actual_timeout = timeout or self._timeout
        result: List[Any] = [None]
        error: List[Optional[Exception]] = [None]

        def _target():
            try:
                result[0] = func(*args, **kwargs)
            except Exception as e:
                error[0] = e

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()
        thread.join(timeout=actual_timeout)

        if thread.is_alive():
            raise SandboxTimeoutError(
                f"插件执行超时 ({actual_timeout}秒)"
            )

        if error[0] is not None:
            raise error[0]

        return result[0]

    def safe_load(self, plugin: PluginBase, api: PluginAPI) -> None:
        self.execute_safe(plugin.on_load, api, timeout=self._timeout)

    def safe_activate(self, plugin: PluginBase) -> None:
        self.execute_safe(plugin.on_activate, timeout=self._timeout)

    def safe_deactivate(self, plugin: PluginBase) -> None:
        self.execute_safe(plugin.on_deactivate, timeout=self._timeout)

    def safe_unload(self, plugin: PluginBase) -> None:
        self.execute_safe(plugin.on_unload, timeout=self._timeout)
