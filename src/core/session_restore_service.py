# -*- coding: utf-8 -*-
"""
会话恢复服务

编排会话恢复与崩溃恢复流程，替代 MainWindow 中的
_build_restore_plan / _restore_state 文件恢复部分 /
_check_session_recovery / _recover_session / _restore_cursor_for_tab /
_open_next_pending_file 等私有方法。

依赖 WorkspaceStore + FileOpenService，不依赖 Config 全量。
UI 弹窗（QMessageBox）保留在 MainWindow，本服务只做纯逻辑。

v1.7.0 改动：
  - 新增 session_restore_service.py（hotfix 阶段 3 / Wave 3.1）
"""

import os
from typing import List, Optional, Tuple

from ..utils.logger import get_logger
from ..editor.temp_session_manager import TempSessionManager
from .workspace_store import WorkspaceStore
from ..editor.file_open_service import (
    FileOpenService,
    FileOpenSource,
    FileOpenSecurityError,
)


class SessionRestoreService:
    """会话恢复编排服务"""

    def __init__(
        self,
        workspace_store: WorkspaceStore,
        file_open_service: FileOpenService,
    ):
        self._workspace_store = workspace_store
        self._file_open_service = file_open_service
        self._pending_files: List[dict] = []

    # === 常规会话恢复 ===

    def build_restore_plan(self, open_files: list) -> Tuple[list, list]:
        """构建会话恢复计划

        返回 (pre_show_entries, deferred_entries)

        pre_show_entries: 显示前同步恢复的文件列表
          - 原本的首个标签
          - 会话中的首个 Markdown 标签（若二者是同一个，只恢复一次）

        deferred_entries: 显示后异步恢复的文件列表
        """
        pre_show_entries = []
        deferred_entries = []

        first_file_index = None
        first_md_index = None

        for idx, entry in enumerate(open_files):
            entry_with_index = {"index": idx, **entry}
            if entry.get("is_new"):
                # 3.5.10：未命名文件同步恢复（无 IO 开销），保持原编号与内容
                pre_show_entries.append(entry_with_index)
                continue
            filepath = entry.get("path")
            if filepath and os.path.exists(filepath):
                ext = os.path.splitext(filepath)[1].lower()
                is_md = ext in ('.md', '.markdown')

                if first_file_index is None:
                    first_file_index = idx
                    pre_show_entries.append(entry_with_index)
                elif is_md and first_md_index is None:
                    first_md_index = idx
                    pre_show_entries.append(entry_with_index)
                else:
                    deferred_entries.append(entry_with_index)
            else:
                deferred_entries.append(entry_with_index)

        return pre_show_entries, deferred_entries

    def restore_session(self, editor_tabs) -> bool:
        """恢复会话文件到标签页

        返回是否有待异步恢复的 pending 文件（供 MainWindow 调度 QTimer）。
        """
        open_files = self._workspace_store.get_open_files()
        if open_files:
            pre_show_entries, deferred_entries = self.build_restore_plan(open_files)

            for entry in pre_show_entries:
                if entry.get("is_new"):
                    # 3.5.10：未命名文件恢复（沿用编号，dirty 内容一并还原）
                    editor_tabs.restore_untitled_file(
                        entry.get("untitled_number") or 1,
                        entry.get("display_name", "未命名"),
                        entry.get("content"),
                    )
                    continue
                filepath = entry.get("path")
                if filepath and os.path.exists(filepath):
                    index = editor_tabs.open_file(
                        filepath,
                        activate=False,
                        insert_index=entry.get("index"),
                        render_preview=False,
                    )
                    if index >= 0:
                        self.restore_cursor(editor_tabs, entry, index)

            self._pending_files = deferred_entries

            if editor_tabs.count() == 0:
                editor_tabs.new_file()
        else:
            self._pending_files = []
            editor_tabs.new_file()

        return bool(self._pending_files)

    def open_next_pending(self, editor_tabs) -> bool:
        """恢复下一个 pending 文件，返回是否还有 pending"""
        if not self._pending_files:
            return False

        file_info = self._pending_files.pop(0)
        filepath = file_info.get("path")
        if filepath and os.path.exists(filepath):
            index = editor_tabs.open_file(
                filepath,
                activate=False,
                insert_index=file_info.get("index"),
                render_preview=True,
            )
            if index >= 0:
                self.restore_cursor(editor_tabs, file_info, index)

        return bool(self._pending_files)

    def restore_cursor(self, editor_tabs, file_info: dict, tab_index: int) -> None:
        """恢复指定索引标签的光标/滚动位置（分屏会话恢复亦复用此方法）"""
        cursor_pos = file_info.get("cursor_position")
        scroll_pos = file_info.get("scroll_position")
        if cursor_pos is None and scroll_pos is None:
            return

        from ..editor.editor import Editor
        from ..editor.markdown_preview import MarkdownPreviewWidget
        widget = editor_tabs.widget(tab_index)
        if widget is None:
            return

        editor = None
        if isinstance(widget, Editor):
            editor = widget
        elif isinstance(widget, MarkdownPreviewWidget):
            editor = widget.editor

        if editor:
            if cursor_pos is not None:
                cursor = editor.textCursor()
                cursor.setPosition(min(cursor_pos, len(editor.toPlainText())))
                editor.setTextCursor(cursor)
            if scroll_pos:
                vbar = editor.verticalScrollBar()
                if vbar is not None:
                    vbar.setValue(scroll_pos)
                    if vbar.value() != scroll_pos:
                        # 首帧布局未完成时 setValue 会被 clamp：
                        # 等待滚动范围就绪后重试一次（文档加载/窗口尺寸变化会触发 rangeChanged）
                        def _apply_scroll(vmin, vmax):
                            if vmax >= scroll_pos:
                                vbar.setValue(scroll_pos)
                                try:
                                    vbar.rangeChanged.disconnect(_apply_scroll)
                                except TypeError:
                                    pass

                        vbar.rangeChanged.connect(_apply_scroll)

    # === 崩溃恢复 ===

    def check_crash_recovery(self, session_manager: TempSessionManager) -> Optional[dict]:
        """查找可恢复的异常退出会话

        无 recoverable 会话时清理干净会话并返回 None。
        返回首个含文件的可恢复会话。
        """
        recoverable = session_manager.find_recoverable_sessions()

        if not recoverable:
            session_manager.cleanup_all_clean_sessions()
            return None

        session = recoverable[0]
        files = session.get("files", [])
        if not files:
            return None

        return session

    def describe_crash_files(self, session: dict) -> List[str]:
        """生成崩溃会话的文件名列表（供 UI 弹窗显示）"""
        files = session.get("files", [])
        file_names = []
        for f in files:
            original = f.get("original_path", "")
            if original:
                file_names.append(os.path.basename(original))
            else:
                file_names.append("未命名文件")
        return file_names

    def restore_after_crash(
        self,
        editor_tabs,
        session: dict,
        session_manager: TempSessionManager,
        split_tabs=None,
    ) -> int:
        """恢复崩溃会话的文件内容，返回成功恢复的文件数

        内部只使用 editor_tabs 的公开接口（open_file / new_file /
        set_tab_content / mark_tab_dirty），不穿透私有成员。

        split_tabs（3.5.8 R6）：分屏面板列表。autosave 记录的 panel 归属
        （main / split_N）决定恢复到哪个面板——强制关闭（任务管理器）时
        workspace 未保存分屏布局，若全塞回主面板则分屏文件"漂移"到左侧。
        """
        session_dir = session.get("session_dir", "")
        files = session.get("files", [])
        restored = 0
        panel_index = {f"split_{i}": t for i, t in enumerate(split_tabs or [])}
        panel_index["main"] = editor_tabs

        for f in files:
            original_path = f.get("original_path", "")
            autosave_name = f.get("autosave_path", "")
            encoding = f.get("encoding", "UTF-8")
            is_new = f.get("is_new", False)
            # 3.5.8（R6）：按面板归属路由；旧会话无 panel 字段 → 主面板兜底。
            # 注意不能用 `get(panel) or main` 短路——未显示的面板 bool() 为 False，
            # 会把分屏文件错误兜底到主面板（"漂移"到左侧）。
            panel = f.get("panel", "main")
            target_tabs = panel_index.get(panel)
            if target_tabs is None:
                target_tabs = panel_index["main"]

            content = session_manager.read_autosave_content(session_dir, autosave_name, encoding)
            if content is None:
                continue

            if original_path and os.path.isfile(original_path) and not is_new:
                try:
                    validated = self._file_open_service.validate_open_request(
                        original_path, FileOpenSource.SESSION_RESTORE
                    )
                except FileOpenSecurityError:
                    get_logger(__name__).warning(
                        "恢复会话文件被安全策略拒绝: %s", original_path
                    )
                    continue
                index = target_tabs.open_file(validated)
                if index >= 0:
                    widget = target_tabs.widget(index)
                    tab_id = getattr(widget, 'tab_id', None) if widget is not None else None
                    if tab_id is not None:
                        target_tabs.set_tab_content(tab_id, content)
                        target_tabs.mark_tab_dirty(tab_id)
                        restored += 1
            else:
                index = target_tabs.new_file()
                if index >= 0:
                    widget = target_tabs.widget(index)
                    tab_id = getattr(widget, 'tab_id', None) if widget is not None else None
                    if tab_id is not None:
                        target_tabs.set_tab_content(tab_id, content)
                        target_tabs.mark_tab_dirty(tab_id)
                        restored += 1

        session_manager.remove_recovered_session(session_dir)
        return restored
