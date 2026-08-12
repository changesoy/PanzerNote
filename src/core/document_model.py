# -*- coding: utf-8 -*-
"""
文档状态模型模块

TabState：类型化的标签页文档状态，替代 editor_tabs._tab_info 的无类型 dict。
TabStateRegistry：管理 tab_id → TabState 的映射，提供类型安全的访问接口。

v1.7.0 改动：
  - 新增 document_model.py（Wave 4.1 TabState）
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TabState:
    """单个标签页的文档状态（替代 _tab_info 的无类型 dict）"""

    # 标识
    tab_id: int
    filepath: Optional[str] = None       # None 表示新建未保存
    display_name: str = "未命名"          # 标签显示名（文件名，含后缀）

    # 文件属性
    encoding: str = "UTF-8"
    eol: str = "LF"                      # LF / CRLF / CR
    is_markdown: bool = False
    is_new: bool = True

    # 修改状态
    is_modified: bool = False
    last_saved_content: str = ""
    last_saved_chars: int = 0
    last_text_length: int = 0

    # 恢复状态（关闭后用于 reopen_closed_tab / workspace.json 导出）
    cursor_position: Optional[int] = None
    scroll_position: Optional[int] = None

    # 预留
    history: List = field(default_factory=list)

    # 运行时编号（仅 is_new=True 时使用）
    untitled_number: Optional[int] = None

    def mark_saved(self, content: str) -> None:
        """保存成功后更新状态（集中副作用）"""
        self.is_modified = False
        self.last_saved_content = content
        self.last_saved_chars = len(content)
        self.last_text_length = len(content)

    def mark_modified(self) -> None:
        """标记为已修改"""
        self.is_modified = True

    def mark_new_saved(self, filepath: str, encoding: str) -> None:
        """新建文件首次保存后"""
        self.is_new = False
        self.filepath = filepath
        self.encoding = encoding
        self.display_name = os.path.basename(filepath)

    def to_open_files_entry(self) -> Optional[dict]:
        """转换为 workspace.json 的 open_files 条目"""
        if self.is_new or not self.filepath:
            return None
        return {
            "path": self.filepath,
            "cursor_position": self.cursor_position or 0,
            "scroll_position": self.scroll_position or 0,
        }

    @classmethod
    def from_open_files_entry(cls, tab_id: int, entry: dict) -> "TabState":
        """从 workspace.json 的 open_files 条目恢复"""
        return cls(
            tab_id=tab_id,
            filepath=entry.get("path"),
            is_new=False,
            is_markdown=entry.get("path", "").lower().endswith((".md", ".markdown")),
            cursor_position=entry.get("cursor_position"),
            scroll_position=entry.get("scroll_position"),
        )


class TabStateRegistry:
    """管理 tab_id → TabState 的映射，替代 _tab_info dict"""

    def __init__(self) -> None:
        self._states: Dict[int, TabState] = {}

    def register(self, tab_id: int, state: TabState) -> None:
        self._states[tab_id] = state

    def unregister(self, tab_id: int) -> None:
        self._states.pop(tab_id, None)

    def get(self, tab_id: int) -> Optional[TabState]:
        return self._states.get(tab_id)

    def get_required(self, tab_id: int) -> TabState:
        """获取状态，不存在则抛 KeyError"""
        return self._states[tab_id]

    def all_states(self) -> List[TabState]:
        return list(self._states.values())

    def modified_states(self) -> List[TabState]:
        return [s for s in self._states.values() if s.is_modified]

    def find_by_filepath(self, filepath: str) -> Optional[TabState]:
        for s in self._states.values():
            if s.filepath == filepath:
                return s
        return None

    def to_open_files_list(self) -> List[dict]:
        """导出为 workspace.json 的 open_files 格式"""
        result = []
        for s in self._states.values():
            entry = s.to_open_files_entry()
            if entry is not None:
                result.append(entry)
        return result

    def get_failed_filenames(self, failed_tab_ids: List[int]) -> List[str]:
        """根据失败的 tab_id 列表返回文件名（供关闭流程提示）"""
        names = []
        for tab_id in failed_tab_ids:
            state = self._states.get(tab_id)
            if state is None:
                continue
            if state.filepath:
                names.append(os.path.basename(state.filepath))
            else:
                names.append(state.display_name)
        return names
