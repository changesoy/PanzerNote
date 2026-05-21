# -*- coding: utf-8 -*-
"""
插件 API 只读视图

为插件提供受限的配置访问接口，禁止暴露修改能力。
插件通过 PluginAPI.get_config() 获取 ReadOnlyConfigView，
而非真实的 Config 实例，防止插件越权修改全局配置。
"""

from typing import Any, Dict, List


class ReadOnlyConfigView:
    """只读配置视图，暴露安全的读取方法，禁止写入和访问内部对象"""

    _DENIED_ATTRS = frozenset({
        'set_', 'save', 'get_file_guard', 'get_security_manager',
        '_settings', '_workspace', '_savegame_manager',
        '_path_validator', '_file_guard', '_input_validator',
        '_crypto_manager', '_security_manager',
        'set_base_path', 'set_initialized', 'reset_to_defaults',
        'set_editor_setting', 'set_game_setting', 'set_secretary_setting',
        'set_view_setting', 'set_window_setting', 'set_setting',
        'set_open_files', 'set_active_tab_index', 'set_current_view',
        'add_recent_file', 'add_external_file', 'remove_external_file',
        'set_resources', 'add_resource', 'set_cores', 'add_cores',
        'add_chars_typed', 'set_total_documents',
        'set_encryption_password', 'enable_encryption', 'disable_encryption',
        'update_last_login', 'ensure_directories',
        'save', 'save_settings', 'save_workspace', 'save_savegame',
        '_save_user_data_path',
    })

    def __init__(self, config):
        self._config = config

    def get_editor_setting(self, key: str, default: Any = None) -> Any:
        return self._config.get_editor_setting(key, default)

    def get_game_setting(self, key: str, default: Any = None) -> Any:
        return self._config.get_game_setting(key, default)

    def get_secretary_setting(self, key: str, default: Any = None) -> Any:
        return self._config.get_secretary_setting(key, default)

    def get_recent_files(self) -> List[str]:
        return self._config.get_recent_files()

    def get_base_path(self) -> str:
        return self._config.get_base_path()

    def get_app_version(self) -> str:
        from .. import __version__
        return __version__

    def get_notebooks_path(self) -> str:
        return self._config.get_notebooks_path()

    def get_resources(self) -> Dict[str, int]:
        return self._config.get_resources()

    def get_savegame_field(self, key: str, default: Any = None) -> Any:
        return self._config.get_savegame().get(key, default)

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self._config.get_setting(key, default)

    def __getattr__(self, name: str) -> Any:
        for prefix in ('set_', 'save', '_'):
            if name.startswith(prefix) or name in self._DENIED_ATTRS:
                raise AttributeError(
                    f"插件无权访问: {name}"
                )
        raise AttributeError(
            f"ReadOnlyConfigView 无此属性: {name}"
        )
