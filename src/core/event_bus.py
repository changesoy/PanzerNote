# -*- coding: utf-8 -*-
"""
事件总线模块
集中管理主窗口的信号连接，降低 MainWindow 与各子组件之间的耦合。
事件处理逻辑已移回 MainWindow，本模块仅负责信号路由。
"""

from typing import Any, Optional

from PyQt5.QtCore import QObject

from ..core.config import Config
from ..utils.logger import get_logger


class EventBus(QObject):
    """信号路由器

    将 MainWindow 的信号连接集中管理。
    事件处理逻辑由 MainWindow 自身的方法实现。
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
