# -*- coding: utf-8 -*-
"""
配置管理模块（门面）

负责协调 PathResolver / SettingsStore / WorkspaceStore /
SavegameManager / SecurityManager 五个子模块，对外保持 v1.6.x 的
完整接口不变，所有现有调用方零改动。

v1.7.0 改动：
  - 拆出 PathResolver / SettingsStore / WorkspaceStore（hotfix 阶段 0）
  - Config 保留为门面，原有方法全部改为委托
"""

import os
from typing import Optional, Dict, Any, List, Mapping

from ..security.path_validator import PathValidator
from ..security.file_guard import FileGuard
from ..security.file_access_context import FileAccessContext
from ..security.input_validator import InputValidator
from .savegame_manager import SavegameManager, SavegameSaveResult
from .security_manager import SecurityManager
from .path_resolver import PathResolver
from .settings_store import SettingsStore
from .workspace_store import WorkspaceStore


class Config:
    """配置管理类（门面）

    职责：协调设置读写、工作区状态、路径管理。
    具体实现委托给 PathResolver / SettingsStore / WorkspaceStore，
    游戏存档委托给 SavegameManager，安全组件委托给 SecurityManager。
    """

    INTERNAL_CONFIG_CTX = FileAccessContext.INTERNAL_CONFIG
    INTERNAL_SAVEGAME_CTX = FileAccessContext.INTERNAL_SAVEGAME

    DEFAULT_SETTINGS = SettingsStore.DEFAULT_SETTINGS
    DEFAULT_WORKSPACE = WorkspaceStore.DEFAULT_WORKSPACE

    def __init__(self, app_dir: Optional[str] = None):
        self._app_dir = app_dir or os.path.dirname(os.path.dirname(__file__))

        self._path_validator = PathValidator()
        self._input_validator = InputValidator()

        self._file_guard = FileGuard(
            path_validator=self._path_validator,
            max_file_size=50 * 1024 * 1024,
            timeout=15,
        )

        self._path_resolver = PathResolver(
            app_dir=self._app_dir,
            file_guard=self._file_guard,
            path_validator=self._path_validator,
        )

        self._security_manager = SecurityManager(
            path_validator=self._path_validator,
            file_guard=self._file_guard,
            input_validator=self._input_validator,
        )

        self._settings_store = SettingsStore(
            path_resolver=self._path_resolver,
            file_guard=self._file_guard,
        )

        self._workspace_store = WorkspaceStore(
            path_resolver=self._path_resolver,
            file_guard=self._file_guard,
        )

        self._savegame_manager = SavegameManager(
            file_guard=self._file_guard,
            gamedata_dir=self._path_resolver.get_gamedata_dir(),
        )

        self._load_all()

    def _load_all(self) -> None:
        self._settings_store.load()

        # base_path 恢复：user_data_path.txt 未设置时，从 settings.json 恢复
        if not self._path_resolver.has_base_path():
            saved_path = self._settings_store.get_setting("base_path")
            if saved_path and os.path.exists(saved_path):
                self._path_resolver.set_base_path(saved_path)
                self._settings_store.load()

        self._workspace_store.load()

        self._savegame_manager.load()

        self._savegame_manager.migrate_bauxite_counter(self._settings_store.as_dict())

    # === 保存 ===

    def save(self) -> None:
        self.save_settings()
        self.save_workspace()
        self.save_savegame()
        self._path_resolver.save_user_data_path()

    def save_settings(self) -> None:
        self._settings_store.save()
        self._path_resolver.save_user_data_path()

    def save_workspace(self) -> None:
        self._workspace_store.save()

    def save_savegame(self) -> SavegameSaveResult:
        return self._savegame_manager.save()

    # === 路径管理（委托 PathResolver） ===

    def get_base_path(self) -> str:
        return self._path_resolver.get_base_path()

    def set_base_path(self, path: str) -> None:
        self._settings_store.set_setting("base_path", path)
        self._path_resolver.set_base_path(path)

    def get_app_dir(self) -> str:
        return self._path_resolver.get_app_dir()

    def get_notebooks_path(self) -> str:
        return self._path_resolver.get_notebooks_path()

    def get_temp_path(self) -> str:
        return self._path_resolver.get_temp_path()

    def get_assets_path(self) -> str:
        return self._path_resolver.get_assets_path()

    def get_portraits_path(self) -> str:
        return self._path_resolver.get_portraits_path()

    def ensure_directories(self) -> None:
        self._path_resolver.ensure_directories()

    # === 初始化状态（委托 SettingsStore） ===

    def is_initialized(self) -> bool:
        return self._settings_store.is_initialized()

    def set_initialized(self, value: bool) -> None:
        self._settings_store.set_initialized(value)

    # === 设置访问（委托 SettingsStore） ===

    def get_editor_setting(self, key: str, default: Any = None) -> Any:
        return self._settings_store.get_editor_setting(key, default)

    def set_editor_setting(self, key: str, value: Any) -> None:
        self._settings_store.set_editor_setting(key, value)

    def get_game_setting(self, key: str, default: Any = None) -> Any:
        return self._settings_store.get_game_setting(key, default)

    def set_game_setting(self, key: str, value: Any) -> None:
        self._settings_store.set_game_setting(key, value)

    def get_secretary_setting(self, key: str, default: Any = None) -> Any:
        return self._settings_store.get_secretary_setting(key, default)

    def set_secretary_setting(self, key: str, value: Any) -> None:
        self._settings_store.set_secretary_setting(key, value)

    def get_view_setting(self, key: str, default: Any = None) -> Any:
        return self._settings_store.get_view_setting(key, default)

    def set_view_setting(self, key: str, value: Any) -> None:
        self._settings_store.set_view_setting(key, value)

    def get_window_setting(self, key: str, default: Any = None) -> Any:
        return self._settings_store.get_window_setting(key, default)

    def set_window_setting(self, key: str, value: Any) -> None:
        self._settings_store.set_window_setting(key, value)

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self._settings_store.get_setting(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        self._settings_store.set_setting(key, value)

    def reset_to_defaults(self) -> None:
        self._settings_store.reset_to_defaults()

    # === 工作区状态（委托 WorkspaceStore） ===

    def update_workspace_field(self, key: str, value: Any) -> None:
        self._workspace_store.update_workspace_field(key, value)

    def get_workspace(self) -> Dict:
        return self._workspace_store.as_dict()

    def get_settings(self) -> Dict:
        return self._settings_store.as_dict()

    def set_open_files(self, files: List[Dict]) -> None:
        self._workspace_store.set_open_files(files)

    def get_open_files(self) -> List[Dict]:
        return self._workspace_store.get_open_files()

    def set_active_tab_index(self, index: int) -> None:
        self._workspace_store.set_active_tab_index(index)

    def get_active_tab_index(self) -> int:
        return self._workspace_store.get_active_tab_index()

    def set_current_view(self, view: str) -> None:
        self._workspace_store.set_current_view(view)

    def get_current_view(self) -> str:
        return self._workspace_store.get_current_view()

    def get_bookmarks(self, filepath: str) -> list:
        return self._workspace_store.get_bookmarks(filepath)

    def set_bookmarks(self, filepath: str, lines: list) -> None:
        self._workspace_store.set_bookmarks(filepath, lines)

    def get_folds(self, filepath: str) -> list:
        return self._workspace_store.get_folds(filepath)

    def set_folds(self, filepath: str, lines: list) -> None:
        self._workspace_store.set_folds(filepath, lines)

    def add_recent_file(self, filepath: str) -> None:
        self._workspace_store.add_recent_file(filepath)

    def set_recent_files(self, files: List[str]) -> None:
        self._workspace_store.set_recent_files(files)

    def get_recent_files(self) -> List[str]:
        return self._workspace_store.get_recent_files()

    def get_external_files(self) -> List[str]:
        return self._workspace_store.get_external_files()

    def add_external_file(self, filepath: str) -> None:
        self._workspace_store.add_external_file(filepath)

    def remove_external_file(self, filepath: str) -> None:
        self._workspace_store.remove_external_file(filepath)

    # === 子模块访问（供服务组装，AppContext 阶段使用） ===

    @property
    def path_resolver(self) -> PathResolver:
        return self._path_resolver

    @property
    def settings_store(self) -> SettingsStore:
        return self._settings_store

    @property
    def workspace_store(self) -> WorkspaceStore:
        return self._workspace_store

    # === 存档代理（向后兼容） ===

    @property
    def savegame_manager(self) -> SavegameManager:
        return self._savegame_manager

    def get_savegame(self) -> Mapping[str, Any]:
        return self._savegame_manager.get_savegame()

    def get_savegame_field(self, key: str, default: Any = None) -> Any:
        return self._savegame_manager.get_savegame_field(key, default)

    def set_savegame_field(self, key: str, value: Any) -> None:
        self._savegame_manager.set_savegame_field(key, value)

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

    def check_daily_checkin(self) -> bool:
        return self._savegame_manager.check_daily_checkin()

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
