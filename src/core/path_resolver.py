# -*- coding: utf-8 -*-
"""
路径解析模块

负责 base_path / app_dir / user_data_path.txt 读写、各目录 getter、
ensure_directories。同时提供配置 JSON 读写与深合并工具函数，
供 SettingsStore / WorkspaceStore 复用。

v1.7.0 改动：
  - 从 Config 拆出 PathResolver（hotfix 阶段 0）
"""

import os
import json
from typing import Dict, Any, Optional, cast

from ..utils.logger import get_logger
from ..utils.exceptions import safe_call
from ..security.path_validator import PathValidator, PathSecurityError
from ..security.file_guard import FileGuard, FileSizeExceededError, FileOperationTimeoutError
from ..security.file_access_context import FileAccessContext


INTERNAL_CONFIG_CTX = FileAccessContext.INTERNAL_CONFIG


# ─── 配置 JSON 工具（供 SettingsStore / WorkspaceStore 复用） ───


def load_json(file_guard: FileGuard, filepath: str, default: Dict) -> Dict:
    """安全读取 JSON 文件，失败或不存在返回 default.copy()"""
    if os.path.exists(filepath):
        try:
            content = file_guard.safe_read(filepath, context=INTERNAL_CONFIG_CTX)
            return cast(Dict[str, Any], json.loads(content))
        except (json.JSONDecodeError, IOError, FileSizeExceededError,
                FileOperationTimeoutError, PathSecurityError) as e:
            get_logger(__name__).warning("加载配置文件失败: %s, 错误: %s", filepath, e)
            return default.copy()
    return default.copy()


def save_json(file_guard: FileGuard, filepath: str, data: Dict) -> None:
    """安全写入 JSON 文件"""
    content = json.dumps(data, ensure_ascii=False, indent=2)
    file_guard.safe_write(filepath, content, context=INTERNAL_CONFIG_CTX)


def merge_dicts(default: Dict, current: Dict) -> Dict:
    """递归合并：以 default 为底，current 覆盖同名键"""
    result = default.copy()
    for key, value in current.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


class PathResolver:
    """路径管理：base_path / app_dir / 各数据目录

    职责：
      - 记忆用户数据路径（user_data_path.txt）
      - 提供 base_path / app_dir 及各数据目录 getter
      - ensure_directories 创建目录骨架
    """

    def __init__(
        self,
        app_dir: Optional[str],
        file_guard: FileGuard,
        path_validator: PathValidator,
    ):
        self._app_dir = app_dir or os.path.dirname(os.path.dirname(__file__))
        self._base_path: Optional[str] = None
        self._file_guard = file_guard
        self._path_validator = path_validator

        self._path_validator.add_allowed_root(self._app_dir)

        self.load_user_data_path()

        if self._base_path:
            self._path_validator.add_allowed_root(self._base_path)

    # === user_data_path.txt 读写 ===

    def _get_user_data_path_file(self) -> str:
        return os.path.join(self._app_dir, "user_data_path.txt")

    @safe_call(catch=Exception)
    def load_user_data_path(self) -> None:
        path_file = self._get_user_data_path_file()
        if os.path.exists(path_file):
            try:
                path = self._file_guard.safe_read(
                    path_file, encoding='utf-8', context=INTERNAL_CONFIG_CTX
                )
                if path and os.path.exists(path):
                    self._base_path = path.strip()
            except Exception:
                get_logger(__name__).debug("读取 user_data_path.txt 失败")

    @safe_call()
    def save_user_data_path(self) -> None:
        if self._base_path:
            path_file = self._get_user_data_path_file()
            self._file_guard.safe_write(
                path_file, self._base_path, encoding='utf-8', context=INTERNAL_CONFIG_CTX
            )

    # === 基础路径 ===

    def has_base_path(self) -> bool:
        """是否设置了显式的用户数据路径"""
        return self._base_path is not None

    def get_base_path(self) -> str:
        return self._base_path or self._app_dir

    def set_base_path(self, path: str) -> None:
        self._base_path = path
        self._path_validator.add_allowed_root(path)
        self.save_user_data_path()

    def get_app_dir(self) -> str:
        return self._app_dir

    # === 数据目录 ===

    def get_config_dir(self) -> str:
        if self._base_path:
            return os.path.join(self._base_path, "data", "config")
        return os.path.join(self._app_dir, "data", "config")

    def get_gamedata_dir(self) -> str:
        if self._base_path:
            return os.path.join(self._base_path, "data", "gamedata")
        return os.path.join(self._app_dir, "data", "gamedata")

    def get_plugin_data_dir(self) -> str:
        """插件私有数据根目录（Wave 5 Batch 3）：plugin_data/{plugin_id}/"""
        if self._base_path:
            return os.path.join(self._base_path, "data", "plugin_data")
        return os.path.join(self._app_dir, "data", "plugin_data")

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
                        "data/plugin_data", "temp/autosave"]:
            os.makedirs(os.path.join(base, subdir), exist_ok=True)
