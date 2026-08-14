# -*- coding: utf-8 -*-
"""
工作区存储模块

负责 workspace dict 的读写、open_files / active_tab / current_view /
bookmarks / folds / recent / external 等会话状态访问。

v1.7.0 改动：
  - 从 Config 拆出 WorkspaceStore（hotfix 阶段 0）
"""

import copy
import os
from typing import Dict, Any, List, Optional, cast

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
            },
            # 分屏状态（3.5.2）：旧配置无这些字段时由 merge_dicts 填充默认值，
            # 默认 split_active=False，行为与未分屏时完全一致（向后兼容）。
            "split_active": False,
            "split_orientation": "Horizontal",
            "split_sizes": [],
            "split_tabs": [],
        },
        "bookmarks": {},
        "folds": {},
        "recent_files": [],
        "external_files": [],
        # 关闭标签页时的光标/滚动位置记忆（重新打开文件时恢复）
        "closed_tabs_memory": {}
    }

    # 白名单直接由 DEFAULT_WORKSPACE 派生，避免两份定义漂移
    _KNOWN_WORKSPACE_KEYS = frozenset(DEFAULT_WORKSPACE.keys())

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
        """返回深拷贝，避免调用方拿到内部引用后绕过封装修改状态"""
        return copy.deepcopy(self._workspace)

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

    # === 分屏状态（3.5.2） ===

    def set_split_active(self, active: bool) -> None:
        self._workspace["last_session"]["split_active"] = bool(active)

    def get_split_active(self) -> bool:
        return bool(self._workspace.get("last_session", {}).get("split_active", False))

    def set_split_orientation(self, orientation: str) -> None:
        self._workspace["last_session"]["split_orientation"] = orientation

    def get_split_orientation(self) -> str:
        return str(
            self._workspace.get("last_session", {}).get("split_orientation", "Horizontal")
        )

    def set_split_sizes(self, sizes: List[int]) -> None:
        self._workspace["last_session"]["split_sizes"] = list(sizes)

    def get_split_sizes(self) -> List[int]:
        sizes = self._workspace.get("last_session", {}).get("split_sizes", [])
        if not isinstance(sizes, list):
            return []
        return [int(s) for s in sizes if isinstance(s, (int, float))]

    def set_split_tabs(self, tabs: List[Dict]) -> None:
        self._workspace["last_session"]["split_tabs"] = list(tabs)

    def get_split_tabs(self) -> List[Dict]:
        tabs = self._workspace.get("last_session", {}).get("split_tabs", [])
        if not isinstance(tabs, list):
            return []
        return cast(List[Dict[str, Any]], [t for t in tabs if isinstance(t, dict)])

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

    # === closed_tabs 位置记忆 ===

    def set_closed_tab_memory(
        self, filepath: str, cursor_position: int, scroll_position: int
    ) -> None:
        """记录关闭标签页时的光标/滚动位置，供重新打开该文件时恢复。"""
        memory = self._workspace.setdefault("closed_tabs_memory", {})
        memory[filepath] = {
            "cursor_position": cursor_position,
            "scroll_position": scroll_position,
        }

    def get_closed_tab_memory(self, filepath: str) -> Optional[Dict[str, int]]:
        """读取关闭标签页时的位置记忆；无记录时返回 None。"""
        memory = self._workspace.get("closed_tabs_memory", {})
        if not isinstance(memory, dict):
            return None
        return cast(Optional[Dict[str, int]], memory.get(filepath))

    def clear_closed_tab_memory(self, filepath: str) -> None:
        """清除指定文件的位置记忆（重新打开并恢复后调用）。"""
        memory = self._workspace.get("closed_tabs_memory")
        if memory and filepath in memory:
            memory.pop(filepath, None)

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
