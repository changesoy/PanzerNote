# -*- coding: utf-8 -*-
"""
工作区存储模块

负责 workspace dict 的读写、open_files / active_tab / current_view /
bookmarks / folds / recent / external 等会话状态访问。

v1.7.0 改动：
  - 从 Config 拆出 WorkspaceStore（hotfix 阶段 0）
"""

import os
from typing import Dict, Any, List, cast

from ..security.file_guard import FileGuard
from .path_resolver import PathResolver, load_json, save_json, merge_dicts, INTERNAL_CONFIG_CTX


class WorkspaceStore:
    """工作区存储：workspace dict + 会话状态访问"""

    DEFAULT_WORKSPACE = {
        "last_session": {
            "open_files": [],
            "active_tab_index": 0,
            "current_view": "editor",
            "file_tree_state": {
                "expanded_folders": []
            }
        },
        "bookmarks": {},
        "folds": {},
        "recent_files": [],
        "external_files": []
    }

    _KNOWN_WORKSPACE_KEYS = frozenset({
        "last_session", "recent_files", "external_files",
        "editor", "game", "secretary", "view", "window",
        "resources", "cores",
    })

    def __init__(
        self,
        path_resolver: PathResolver,
        file_guard: FileGuard,
    ):
        self._path_resolver = path_resolver
        self._file_guard = file_guard
        self._workspace: Dict[str, Any] = {}

    # === 读写 ===

    def load(self) -> None:
        """从 config_dir 加载 workspace.json 并合并默认值"""
        config_dir = self._path_resolver.get_config_dir()
        self._workspace = merge_dicts(
            self.DEFAULT_WORKSPACE,
            load_json(
                self._file_guard,
                os.path.join(config_dir, "workspace.json"),
                self.DEFAULT_WORKSPACE,
            ),
        )

    def save(self) -> None:
        """保存 workspace.json"""
        config_dir = self._path_resolver.get_config_dir()
        os.makedirs(config_dir, exist_ok=True)
        save_json(
            self._file_guard,
            os.path.join(config_dir, "workspace.json"),
            self._workspace,
        )

    def as_dict(self) -> Dict[str, Any]:
        return self._workspace

    # === 通用字段 ===

    def update_workspace_field(self, key: str, value: Any) -> None:
        if key not in self._KNOWN_WORKSPACE_KEYS:
            raise KeyError(f"未知的 workspace 字段: {key}")
        self._workspace[key] = value

    # === last_session ===

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

    # === bookmarks / folds ===

    def get_bookmarks(self, filepath: str) -> list:
        """获取指定文件的书签行号列表。"""
        return list(self._workspace.get("bookmarks", {}).get(filepath, []))

    def set_bookmarks(self, filepath: str, lines: list) -> None:
        """设置指定文件的书签行号列表。"""
        bookmarks = self._workspace.setdefault("bookmarks", {})
        if lines:
            bookmarks[filepath] = sorted(lines)
        else:
            bookmarks.pop(filepath, None)

    def get_folds(self, filepath: str) -> list:
        """获取指定文件的折叠状态（被折叠标题行号列表）。"""
        return list(self._workspace.get("folds", {}).get(filepath, []))

    def set_folds(self, filepath: str, lines: list) -> None:
        """设置指定文件的折叠状态（被折叠标题行号列表）。"""
        folds = self._workspace.setdefault("folds", {})
        if lines:
            folds[filepath] = sorted(lines)
        else:
            folds.pop(filepath, None)

    # === recent / external ===

    def add_recent_file(self, filepath: str) -> None:
        recent = self._workspace.get("recent_files", [])
        if filepath in recent:
            recent.remove(filepath)
        recent.insert(0, filepath)
        self._workspace["recent_files"] = recent[:20]

    def set_recent_files(self, files: List[str]) -> None:
        self._workspace["recent_files"] = files[:20]

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
            self.save()

    def remove_external_file(self, filepath: str) -> None:
        external = self._workspace.get("external_files", [])
        if filepath in external:
            external.remove(filepath)
            self.save()
