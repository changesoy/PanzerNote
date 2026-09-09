# -*- coding: utf-8 -*-
"""
设置存储模块

负责 settings dict 的读写、命名空间设置访问、reset_to_defaults。
SettingsStore 只关心设置本身，路径由 PathResolver 提供。

v1.7.0 改动：
  - 从 Config 拆出 SettingsStore（hotfix 阶段 0）
"""

import copy
import os
from typing import Dict, Any

from ..security.file_guard import FileGuard
from .path_resolver import PathResolver, load_json, save_json, merge_dicts


class SettingsStore:
    """设置存储：settings dict + 命名空间访问"""

    DEFAULT_SETTINGS = {
        "initialized": False,
        "base_path": "",
        "editor": {
            "font_family": "Microsoft YaHei",
            "font_size": 12,
            "line_spacing": 1.5,
            "show_line_numbers": True,
            "auto_wrap": False,
            "wrap_mode": "no_wrap",
            "highlight_current_line": True,
            "auto_save_interval": 30,
            "max_history_count": 40,
            "default_encoding": "utf-8",
            "line_ending": "LF",
            "code_highlight_theme": "pycharm_light",
            "show_minimap": True,
            "auto_minimap": False,
            "auto_pair_brackets": True,
            "indent_size": 4,
            "use_tabs": False,
            "enable_completion": False,
            "completion_min_chars": 2,
        },
        "game": {
            "typing_reward_rate": 1.0,
            "idle_reward_rate": 1.0,
            "daily_typing_limit": 10000,
            "construction_time_rate": 1.0,
            "construction_slots": 2,
        },
        "secretary": {
            "character_id": None,
            "character_name": None,
            "skin_name": None,
            "state": "正常",
            "user_nickname": "指挥官",
            "secretary_self": "我",
            "enable_voice": False,
            "show_secretary": True,
            "size_percent": 7
        },
        "view": {
            "theme": "light",
            "sidebar_width": 200,
            "show_file_tree": True
        },
        "window": {
            "width": 1200,
            "height": 800,
            "x": 100,
            "y": 100,
            "maximized": False
        },
        "shortcuts": {}
    }

    def __init__(
        self,
        path_resolver: PathResolver,
        file_guard: FileGuard,
    ):
        self._path_resolver = path_resolver
        self._file_guard = file_guard
        self._settings: Dict[str, Any] = {}

    # === 读写 ===

    def load(self) -> None:
        """从 config_dir 加载 settings.json 并合并默认值"""
        config_dir = self._path_resolver.get_config_dir()
        settings_path = os.path.join(config_dir, "settings.json")
        self._settings = merge_dicts(
            self.DEFAULT_SETTINGS,
            load_json(self._file_guard, settings_path, self.DEFAULT_SETTINGS),
        )

    def save(self) -> None:
        """保存 settings.json"""
        config_dir = self._path_resolver.get_config_dir()
        os.makedirs(config_dir, exist_ok=True)
        save_json(
            self._file_guard,
            os.path.join(config_dir, "settings.json"),
            self._settings,
        )

    def as_dict(self) -> Dict[str, Any]:
        """返回深拷贝，避免调用方拿到内部引用后绕过封装修改状态"""
        return copy.deepcopy(self._settings)

    # === 初始化状态 ===

    def is_initialized(self) -> bool:
        if self._path_resolver.has_base_path() and os.path.exists(self._path_resolver.get_base_path()):
            settings_path = os.path.join(self._path_resolver.get_config_dir(), "settings.json")
            return os.path.exists(settings_path)
        return False

    def set_initialized(self, value: bool) -> None:
        self._settings["initialized"] = value

    # === 设置访问 ===

    def _get_ns_setting(self, namespace: str, key: str, default: Any = None) -> Any:
        return self._settings.get(namespace, {}).get(key, default)

    def _set_ns_setting(self, namespace: str, key: str, value: Any) -> None:
        if namespace not in self._settings:
            self._settings[namespace] = {}
        self._settings[namespace][key] = value

    def get_editor_setting(self, key: str, default: Any = None) -> Any:
        return self._get_ns_setting("editor", key, default)

    def set_editor_setting(self, key: str, value: Any) -> None:
        self._set_ns_setting("editor", key, value)

    def get_game_setting(self, key: str, default: Any = None) -> Any:
        return self._get_ns_setting("game", key, default)

    def set_game_setting(self, key: str, value: Any) -> None:
        self._set_ns_setting("game", key, value)

    def get_secretary_setting(self, key: str, default: Any = None) -> Any:
        return self._get_ns_setting("secretary", key, default)

    def set_secretary_setting(self, key: str, value: Any) -> None:
        self._set_ns_setting("secretary", key, value)

    def get_view_setting(self, key: str, default: Any = None) -> Any:
        return self._get_ns_setting("view", key, default)

    def set_view_setting(self, key: str, value: Any) -> None:
        self._set_ns_setting("view", key, value)

    def get_window_setting(self, key: str, default: Any = None) -> Any:
        return self._get_ns_setting("window", key, default)

    def set_window_setting(self, key: str, value: Any) -> None:
        self._set_ns_setting("window", key, value)

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        self._settings[key] = value

    def reset_to_defaults(self) -> None:
        self._settings = copy.deepcopy(self.DEFAULT_SETTINGS)
        self.save()
