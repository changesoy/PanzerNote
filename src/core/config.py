# -*- coding: utf-8 -*-
"""
配置管理模块
负责读写程序设置、会话状态等
支持方案A：在程序目录保存user_data_path.txt记住用户数据路径

v1.6.4 改动：
  - 拆出 SavegameManager 管理游戏存档
  - 拆出 SecurityManager 管理安全组件
  - Config 保留设置、工作区状态，并代理存档/安全接口
"""

import os
import json
from typing import Optional, Dict, Any, List, cast

from ..utils.logger import get_logger
from ..utils.exceptions import safe_call
from ..security.path_validator import PathValidator, PathSecurityError
from ..security.file_guard import FileGuard, FileSizeExceededError, FileOperationTimeoutError
from ..security.file_access_context import FileAccessContext
from ..security.crypto_manager import CryptoManager
from ..security.input_validator import InputValidator
from .savegame_manager import SavegameManager
from .security_manager import SecurityManager


class Config:
    """配置管理类

    职责：设置读写、工作区状态、路径管理。
    游戏存档委托给 SavegameManager，安全组件委托给 SecurityManager。
    """

    INTERNAL_CONFIG_CTX = FileAccessContext.INTERNAL_CONFIG
    INTERNAL_SAVEGAME_CTX = FileAccessContext.INTERNAL_SAVEGAME

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

    DEFAULT_WORKSPACE = {
        "last_session": {
            "open_files": [],
            "active_tab_index": 0,
            "current_view": "editor",
            "file_tree_state": {
                "expanded_folders": []
            }
        },
        "recent_files": [],
        "external_files": []
    }

    def __init__(self, app_dir: Optional[str] = None):
        self._app_dir = app_dir or os.path.dirname(os.path.dirname(__file__))
        self._base_path = None
        self._settings: Dict[str, Any] = {}
        self._workspace: Dict[str, Any] = {}

        self._path_validator = PathValidator()
        self._input_validator = InputValidator()

        self._path_validator.add_allowed_root(self._app_dir)

        self._file_guard = FileGuard(
            path_validator=self._path_validator,
            max_file_size=50 * 1024 * 1024,
            timeout=15,
        )

        self._load_user_data_path()

        if self._base_path:
            self._path_validator.add_allowed_root(self._base_path)

        self._crypto_manager = CryptoManager(
            self._get_config_dir(), savegame_dir=self._get_gamedata_dir()
        )

        self._security_manager = SecurityManager(
            path_validator=self._path_validator,
            file_guard=self._file_guard,
            input_validator=self._input_validator,
        )

        self._savegame_manager = SavegameManager(
            file_guard=self._file_guard,
            crypto_manager=self._crypto_manager,
            gamedata_dir=self._get_gamedata_dir(),
        )

        self._load_all()

    def _get_user_data_path_file(self) -> str:
        return os.path.join(self._app_dir, "user_data_path.txt")

    @safe_call(catch=Exception)
    def _load_user_data_path(self) -> None:
        path_file = self._get_user_data_path_file()
        if os.path.exists(path_file):
            try:
                path = self._file_guard.safe_read(
                    path_file, encoding='utf-8', context=self.INTERNAL_CONFIG_CTX
                )
                if path and os.path.exists(path):
                    self._base_path = path.strip()
            except Exception:
                get_logger(__name__).debug("读取 user_data_path.txt 失败")

    @safe_call()
    def _save_user_data_path(self) -> None:
        if self._base_path:
            path_file = self._get_user_data_path_file()
            self._file_guard.safe_write(
                path_file, self._base_path, encoding='utf-8', context=self.INTERNAL_CONFIG_CTX
            )

    def _get_config_dir(self) -> str:
        if self._base_path:
            return os.path.join(self._base_path, "data", "config")
        return os.path.join(self._app_dir, "data", "config")

    def _get_gamedata_dir(self) -> str:
        if self._base_path:
            return os.path.join(self._base_path, "data", "gamedata")
        return os.path.join(self._app_dir, "data", "gamedata")

    def _load_json(self, filepath: str, default: Dict) -> Dict:
        if os.path.exists(filepath):
            try:
                content = self._file_guard.safe_read(filepath, context=self.INTERNAL_CONFIG_CTX)
                return cast(Dict[str, Any], json.loads(content))
            except (json.JSONDecodeError, IOError, FileSizeExceededError,
                    FileOperationTimeoutError, PathSecurityError) as e:
                get_logger(__name__).warning("加载配置文件失败: %s, 错误: %s", filepath, e)
                return default.copy()
        return default.copy()

    def _save_json(self, filepath: str, data: Dict) -> None:
        content = json.dumps(data, ensure_ascii=False, indent=2)
        self._file_guard.safe_write(filepath, content, context=self.INTERNAL_CONFIG_CTX)

    def _load_all(self) -> None:
        config_dir = self._get_config_dir()

        settings_path = os.path.join(config_dir, "settings.json")
        self._settings = self._load_json(settings_path, self.DEFAULT_SETTINGS)

        if not self._base_path and self._settings.get("base_path"):
            saved_path = self._settings["base_path"]
            if os.path.exists(saved_path):
                self._base_path = saved_path
                config_dir = self._get_config_dir()
                settings_path = os.path.join(config_dir, "settings.json")
                self._settings = self._load_json(settings_path, self.DEFAULT_SETTINGS)

        self._workspace = self._load_json(
            os.path.join(config_dir, "workspace.json"),
            self.DEFAULT_WORKSPACE
        )

        self._savegame_manager.load()

        self._settings = self._merge_dict(self.DEFAULT_SETTINGS, self._settings)
        self._workspace = self._merge_dict(self.DEFAULT_WORKSPACE, self._workspace)

        self._savegame_manager.migrate_bauxite_counter(self._settings)

    def _merge_dict(self, default: Dict, current: Dict) -> Dict:
        result = default.copy()
        for key, value in current.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_dict(result[key], value)
            else:
                result[key] = value
        return result

    # === 保存 ===

    def save(self) -> None:
        self.save_settings()
        self.save_workspace()
        self.save_savegame()
        self._save_user_data_path()

    def save_settings(self) -> None:
        config_dir = self._get_config_dir()
        os.makedirs(config_dir, exist_ok=True)
        self._save_json(os.path.join(config_dir, "settings.json"), self._settings)
        self._save_user_data_path()

    def save_workspace(self) -> None:
        config_dir = self._get_config_dir()
        os.makedirs(config_dir, exist_ok=True)
        self._save_json(os.path.join(config_dir, "workspace.json"), self._workspace)

    def save_savegame(self) -> Any:
        from .savegame_manager import SavegameSaveResult
        return self._savegame_manager.save()

    # === 路径管理 ===

    def get_base_path(self) -> str:
        return self._base_path or self._app_dir

    def set_base_path(self, path: str) -> None:
        self._settings["base_path"] = path
        self._base_path = path
        self._path_validator.add_allowed_root(path)
        self._save_user_data_path()

    def get_app_dir(self) -> str:
        return self._app_dir

    def get_notebooks_path(self) -> str:
        return os.path.join(self.get_base_path(), "notebooks")

    def get_temp_path(self) -> str:
        return os.path.join(self.get_base_path(), "temp", "autosave")

    def get_assets_path(self) -> str:
        return os.path.join(self._app_dir, "data", "assets")

    def get_portraits_path(self) -> str:
        return os.path.join(self.get_assets_path(), "portraits")

    def ensure_directories(self) -> None:
        portraits = self.get_portraits_path()
        for subdir in ["原始/正常", "原始/大破", "皮肤/正常", "皮肤/大破"]:
            os.makedirs(os.path.join(portraits, subdir), exist_ok=True)

        base = self.get_base_path()
        for subdir in ["notebooks/工作", "notebooks/回忆", "notebooks/日记",
                        "data/config", "data/gamedata", "data/logs",
                        "temp/autosave"]:
            os.makedirs(os.path.join(base, subdir), exist_ok=True)

    # === 初始化状态 ===

    def is_initialized(self) -> bool:
        if self._base_path and os.path.exists(self._base_path):
            settings_path = os.path.join(self._base_path, "data", "config", "settings.json")
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
        import copy
        self._settings = copy.deepcopy(self.DEFAULT_SETTINGS)
        self.save_settings()

    # === 工作区状态 ===

    _KNOWN_WORKSPACE_KEYS = frozenset({
        "last_session", "recent_files", "external_files",
        "editor", "game", "secretary", "view", "window",
        "resources", "cores",
    })

    def update_workspace_field(self, key: str, value: Any) -> None:
        if key not in self._KNOWN_WORKSPACE_KEYS:
            raise KeyError(f"未知的 workspace 字段: {key}")
        self._workspace[key] = value

    def get_workspace(self) -> Dict:
        return self._workspace

    def set_open_files(self, files: List[Dict]) -> None:
        self._workspace["last_session"]["open_files"] = files

    def get_open_files(self) -> List[Dict]:
        return cast(List[Dict[str, Any]], self._workspace.get("last_session", {}).get("open_files", []))

    def set_active_tab_index(self, index: int) -> None:
        self._workspace["last_session"]["active_tab_index"] = index

    def get_active_tab_index(self) -> int:
        return int(self._workspace.get("last_session", {}).get("active_tab_index", 0))

    def set_current_view(self, view: str) -> None:
        self._workspace["last_session"]["current_view"] = view

    def get_current_view(self) -> str:
        return str(self._workspace.get("last_session", {}).get("current_view", "editor"))

    def add_recent_file(self, filepath: str) -> None:
        recent = self._workspace.get("recent_files", [])
        if filepath in recent:
            recent.remove(filepath)
        recent.insert(0, filepath)
        self._workspace["recent_files"] = recent[:20]

    def get_recent_files(self) -> List[str]:
        return cast(List[str], self._workspace.get("recent_files", []))

    def get_external_files(self) -> List[str]:
        return cast(List[str], self._workspace.get("external_files", []))

    def add_external_file(self, filepath: str) -> None:
        if "external_files" not in self._workspace:
            self._workspace["external_files"] = []
        external = self._workspace["external_files"]
        if filepath not in external:
            external.append(filepath)
            self.save_workspace()

    def remove_external_file(self, filepath: str) -> None:
        external = self._workspace.get("external_files", [])
        if filepath in external:
            external.remove(filepath)
            self.save_workspace()

    # === 存档代理（向后兼容） ===

    @property
    def savegame_manager(self) -> SavegameManager:
        return self._savegame_manager

    def get_savegame(self) -> Dict:
        return self._savegame_manager.get_savegame()

    def get_resources(self) -> Dict[str, int]:
        return self._savegame_manager.get_resources()

    def set_resources(self, resources: Dict[str, int]) -> None:
        self._savegame_manager.set_resources(resources)

    def add_resource(self, resource_type: str, amount: int) -> None:
        self._savegame_manager.add_resource(resource_type, amount)

    def get_cores(self) -> int:
        return self._savegame_manager.get_cores()

    def set_cores(self, amount: int) -> None:
        self._savegame_manager.set_cores(amount)

    def add_cores(self, amount: int) -> None:
        self._savegame_manager.add_cores(amount)

    def get_today_chars_typed(self) -> int:
        return self._savegame_manager.get_today_chars_typed()

    def add_chars_typed(self, count: int) -> None:
        self._savegame_manager.add_chars_typed(count)

    def get_total_documents(self) -> int:
        return self._savegame_manager.get_total_documents()

    def set_total_documents(self, count: int) -> None:
        self._savegame_manager.set_total_documents(count)

    def update_last_login(self) -> None:
        self._savegame_manager.update_last_login()

    def get_last_login(self) -> Optional[str]:
        return self._savegame_manager.get_last_login()

    # === 安全代理（向后兼容） ===

    @property
    def security_manager(self) -> SecurityManager:
        return self._security_manager

    def get_path_validator(self) -> PathValidator:
        return self._path_validator

    def get_file_guard(self) -> FileGuard:
        return self._file_guard

    def get_input_validator(self) -> InputValidator:
        return self._input_validator

    def is_savegame_encrypted(self) -> bool:
        return self._savegame_manager.is_savegame_encrypted()

    def set_encryption_password(self, password: str) -> None:
        self._savegame_manager.set_encryption_password(password)

    def has_encryption_password(self) -> bool:
        return self._savegame_manager.has_encryption_password()

    def enable_encryption(self, password: str) -> bool:
        return self._savegame_manager.enable_encryption(password)

    def disable_encryption(self, password: str) -> bool:
        return self._savegame_manager.disable_encryption(password)

    def verify_encryption_password(self, password: str) -> bool:
        return self._savegame_manager.verify_encryption_password(password)

    def validate_setting_value(
        self,
        key: str,
        value: Any,
        expected_type: type,
        min_val: Any = None,
        max_val: Any = None,
        allowed_values: Any = None,
    ) -> Any:
        return self._security_manager.validate_setting_value(
            key, value, expected_type,
            min_val=min_val,
            max_val=max_val,
            allowed_values=allowed_values,
        )
