# -*- coding: utf-8 -*-
"""
事件总线模块
集中管理主窗口的信号连接和事件路由
"""

from typing import Any, Optional

from PyQt5.QtCore import QObject

from ..core.config import Config
from ..utils.logger import get_logger


class EventBus(QObject):
    """事件路由器

    将 MainWindow 的信号连接和事件分发集中管理，
    降低 MainWindow 与各子组件之间的耦合。
    """

    def __init__(self, config: Config, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._logger = get_logger(__name__)

    def connect_signals(self, main_window: Any) -> None:
        """连接主窗口的所有信号

        Args:
            main_window: MainWindow 实例
        """
        mw = main_window

        mw.game_sidebar.view_changed.connect(mw._on_view_changed)
        mw.file_tree.file_open_requested.connect(mw._open_file)
        mw.file_tree.file_move_requested.connect(mw._on_file_move_from_tree)
        mw.editor_tabs.current_changed.connect(mw._on_tab_changed)
        mw.editor_tabs.content_modified.connect(mw._on_content_modified)
        mw.editor_tabs.tab_count_changed.connect(mw._on_tab_count_changed)

    def handle_view_changed(self, main_window: Any, view: str) -> None:
        """处理视图切换事件"""
        if view == "back":
            if main_window._current_view != "editor":
                main_window._switch_view("editor")
            else:
                main_window._undo()
        else:
            main_window._switch_view(view)

    def handle_file_saved(self, main_window: Any, char_count: int) -> None:
        """处理文件保存后事件"""
        main_window.resource_bar.refresh()
        main_window.secretary.show_message("文件已保存！")

    def handle_tab_count_changed(self, main_window: Any, count: int) -> None:
        """处理标签页数量变化事件"""
        if count == 0:
            main_window.secretary.show_event_message("欢迎")

    def handle_file_move(self, main_window: Any, src_filepath: str, dest_folder: str) -> None:
        """处理文件移动事件"""
        import os
        success = main_window.editor_tabs.move_file_to_folder(src_filepath, dest_folder)
        if success:
            main_window.secretary.show_message(
                f"已将 {os.path.basename(src_filepath)} 移动到 {os.path.basename(dest_folder)}/"
            )
