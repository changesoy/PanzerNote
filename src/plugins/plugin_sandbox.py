# -*- coding: utf-8 -*-
"""
插件包装器

提供插件线程隔离、超时控制和资源访问限制。
插件在独立线程中执行，设置最大执行超时时间。
注意：本模块并非进程隔离沙箱，仅提供线程级隔离。

权限模型：
  每个插件在 manifest.json 中声明所需权限，PluginAPI 在执行前
  检查权限。MVP 阶段 ACCESS_FILESYSTEM 和 ACCESS_NETWORK 为
  写入类权限，默认禁止。

  新增权限：
  - OPEN_FILE: 打开文件到编辑器
  - SHOW_MESSAGE: 通过小秘书显示消息
  - REGISTER_COMMAND: 注册自定义命令到命令面板
  - GET_CONFIG: 获取运行时配置对象（只读访问）
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
    MAX_EXECUTION_TIMEOUT = 30

    def __init__(
        self,
        config,
        permissions: List[PluginPermission],
        open_file_callback: Optional[Callable[[str], bool]] = None,
        show_message_callback: Optional[Callable[[str], None]] = None,
        register_command_callback: Optional[Callable[[str, Callable], None]] = None,
    ):
        self._config = config
        self._permissions = set(permissions)
        self._mvp_read_only = True
        self._logger = get_logger(__name__)
        self._open_file_callback = open_file_callback
        self._show_message_callback = show_message_callback
        self._register_command_callback = register_command_callback
        self._registered_commands: Dict[str, Callable] = {}

    def _check_permission(self, perm: PluginPermission) -> None:
        if perm not in self._permissions:
            raise SandboxViolationError(
                f"插件缺少权限: {perm.value}"
            )
        if self._mvp_read_only and perm in (
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

    def open_file(self, filepath: str) -> bool:
        """打开文件到编辑器

        Args:
            filepath: 文件绝对路径

        Returns:
            True 表示成功打开

        Raises:
            SandboxViolationError: 缺少 OPEN_FILE 权限
        """
        self._check_permission(PluginPermission.OPEN_FILE)
        if self._open_file_callback is None:
            self._logger.warning("open_file 回调未注册")
            return False
        return self._open_file_callback(filepath)

    def show_message(self, message: str) -> None:
        """通过小秘书显示消息

        Args:
            message: 消息内容

        Raises:
            SandboxViolationError: 缺少 SHOW_MESSAGE 权限
        """
        self._check_permission(PluginPermission.SHOW_MESSAGE)
        if self._show_message_callback is None:
            self._logger.warning("show_message 回调未注册")
            return
        self._show_message_callback(message)

    def register_command(self, command_id: str, handler: Callable) -> None:
        """注册自定义命令

        Args:
            command_id: 命令唯一标识，建议格式 "plugin_name:action"
            handler: 命令处理函数，无参数

        Raises:
            SandboxViolationError: 缺少 REGISTER_COMMAND 权限
            ValueError: command_id 已被注册
        """
        self._check_permission(PluginPermission.REGISTER_COMMAND)
        if self._register_command_callback is None:
            self._logger.warning("register_command 回调未注册")
            return
        if self._registered_commands.setdefault(command_id, handler) is not handler:
            raise ValueError(f"命令已注册: {command_id}")
        self._register_command_callback(command_id, handler)

    def get_config(self) -> Any:
        """获取运行时配置对象（只读访问）

        插件应仅通过此对象读取配置，不应修改。

        Returns:
            Config 实例

        Raises:
            SandboxViolationError: 缺少 GET_CONFIG 权限
        """
        self._check_permission(PluginPermission.GET_CONFIG)
        return self._config

    def get_registered_commands(self) -> Dict[str, Callable]:
        """获取本插件注册的所有命令"""
        return dict(self._registered_commands)


class PluginSandbox:
    def __init__(self, config, timeout: int = 30):
        self._config = config
        self._timeout = timeout
        self._logger = get_logger(__name__)
        self._open_file_callback: Optional[Callable[[str], bool]] = None
        self._show_message_callback: Optional[Callable[[str], None]] = None
        self._register_command_callback: Optional[Callable[[str, Callable], None]] = None

    def set_open_file_callback(self, callback: Callable[[str], bool]) -> None:
        self._open_file_callback = callback

    def set_show_message_callback(self, callback: Callable[[str], None]) -> None:
        self._show_message_callback = callback

    def set_register_command_callback(self, callback: Callable[[str, Callable], None]) -> None:
        self._register_command_callback = callback

    def create_api(self, plugin: PluginBase) -> PluginAPI:
        permissions = []
        if plugin.meta:
            permissions = list(plugin.meta.permissions)
        return PluginAPI(
            self._config,
            permissions,
            open_file_callback=self._open_file_callback,
            show_message_callback=self._show_message_callback,
            register_command_callback=self._register_command_callback,
        )

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
