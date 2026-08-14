# -*- coding: utf-8 -*-
"""文件动作编排控制器（hotfix 阶段 4，Wave 3.2）

职责：文件打开相关动作的编排——安全校验、外部文件判定、
打开标签、最近文件更新。UI 副作用（错误弹窗、文件树刷新、
最近菜单构建）保留在 MainWindow。

不包含（1 行委托保留在 MainWindow）：
  _new_file / _save_current / _save_as / _save_all /
  _close_current_tab / _close_all_tabs / _reopen_closed_tab
"""
import os
from typing import Callable, List, Optional, Tuple

from PyQt6.QtWidgets import QFileDialog

from ..core.path_resolver import PathResolver
from ..core.workspace_store import WorkspaceStore
from .editor_tabs import EditorTabWidget
from .file_open_service import (
    FileOpenService,
    FileOpenSource,
    FileOpenSecurityError,
    _is_inside_root,
)


class FileActionController:
    """文件打开动作编排（依赖编辑器、工作区、路径、安全打开服务）。

    3.5.3：目标面板改为构造注入 Callable 提供者（焦点感知），
    MainWindow 传入 `lambda: self._focused_editor_tabs() or self.editor_tabs`，
    使打开的文件进入当前焦点的分屏而非固定主面板。
    """

    def __init__(
        self,
        editor_tabs_provider: Callable[[], EditorTabWidget],
        workspace_store: WorkspaceStore,
        path_resolver: PathResolver,
        file_open_service: FileOpenService,
    ):
        self._editor_tabs_provider = editor_tabs_provider
        self._workspace_store = workspace_store
        self._path_resolver = path_resolver
        self._file_open_service = file_open_service

    # === 打开 ===

    def open_file(
        self,
        filepath: str,
        target_tabs: Optional[EditorTabWidget] = None,
    ) -> Tuple[int, bool]:
        """编排打开文件：安全校验 → 外部文件判定 → 打开 → 最近文件。

        安全校验失败抛出 FileOpenSecurityError（由调用方负责提示）。
        返回 (tab_index, is_external)。

        3.5.3：target_tabs 为调用方在弹窗前捕获的目标面板（避免文件对话框
        夺焦导致 provider 求值落回主面板）；未传时由 provider 即时求值。
        """
        validated = self._file_open_service.validate_open_request(
            filepath, FileOpenSource.USER_DIALOG
        )
        is_external = self._register_external_if_needed(validated)
        tabs = (
            target_tabs
            if target_tabs is not None
            else self._editor_tabs_provider()
        )
        index = tabs.open_file(validated)
        self._workspace_store.add_recent_file(validated)
        return index, is_external

    def open_file_bypass_service(
        self, filepath: str, target_tabs: Optional[EditorTabWidget] = None
    ) -> Tuple[int, bool]:
        """拖放等已通过 FileOpenService 校验的路径直接打开，不再重复校验。

        target_tabs：拖放等调用方按释放位置捕获的目标面板（避免拖拽期间
        焦点在文件树上，provider 求值落回最近聚焦面板）；未传时由 provider
        即时求值。返回 (tab_index, is_external)。
        """
        is_external = self._register_external_if_needed(filepath)
        tabs = (
            target_tabs
            if target_tabs is not None
            else self._editor_tabs_provider()
        )
        index = tabs.open_file(filepath)
        self._workspace_store.add_recent_file(filepath)
        return index, is_external

    def show_open_dialog(self, parent=None) -> Optional[str]:
        """弹出打开文件对话框；取消返回 None。"""
        filepath, _ = QFileDialog.getOpenFileName(
            parent,
            "打开文件",
            self._path_resolver.get_notebooks_path(),
            "所有支持的文件 (*.txt *.md *.py *.c *.cpp *.h *.java *.js *.json *.html *.css *.xml);;"
            "文本文件 (*.txt);;"
            "Markdown (*.md);;"
            "Python (*.py);;"
            "C/C++ (*.c *.cpp *.h);;"
            "Java (*.java);;"
            "Web (*.html *.css *.js);;"
            "所有文件 (*.*)"
        )
        return filepath or None

    # === 最近文件 ===

    def refresh_recent_files(self) -> List[str]:
        """过滤并持久化最近文件列表（剔除已不存在的路径）。

        返回过滤后的有效列表；菜单构建由 MainWindow 完成。
        """
        recent_files = self._workspace_store.get_recent_files()
        valid_files = [f for f in recent_files if os.path.exists(f)]
        if valid_files != recent_files:
            self._workspace_store.set_recent_files(valid_files)
        return valid_files

    # === 内部 ===

    def _register_external_if_needed(self, filepath: str) -> bool:
        """文件不在 notebooks_path 下时记为外部文件；返回是否外部文件。"""
        notebooks_path = os.path.normpath(self._path_resolver.get_notebooks_path())
        if not _is_inside_root(os.path.normpath(filepath), notebooks_path):
            self._workspace_store.add_external_file(filepath)
            return True
        return False
