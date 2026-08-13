# -*- coding: utf-8 -*-
"""
视图协调器（Wave 3 分支 E）

承载 MainWindow 的视图/分屏/面板切换编排逻辑：
- switch_view / split_editor / close_split / set_wrap_mode
- toggle_md_preview / toggle_minimap / toggle_file_tree /
  toggle_side_panel / toggle_secretary / toggle_shortcut_panel

设计约束（沿用 hotfix.txt / Wave 3 方案）：
- 依赖全部构造注入；MainWindow 通过回调注入信号连接方法
  （connect_tabs_signals）与菜单同步方法（on_wrap_mode_changed），
  本类不持有 MainWindow 引用，避免反向依赖。
- _current_view / _split_tabs 状态迁入本类，MainWindow 通过
  current_view / split_tabs 属性读取（保存状态、keyPressEvent、
  _focused_editor_tabs、_update_outline 使用）。
- 不迁移：_toggle_fullscreen（窗口级）、命令面板、keyPressEvent。
"""

from typing import Callable, List

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QSplitter, QWidget

from ..core.config import Config
from ..editor.editor_tabs import EditorTabWidget
from ..editor.find_replace import FindReplaceBar
from ..editor.webengine_runtime import WebEngineRuntime
from ..game.game_sidebar import GameSidebar
from ..game.secretary_widget import SecretaryWidget
from ..themes.theme_engine import ThemeEngine
from .shortcut_panel import ShortcutPanel
from .side_panel_host import SidePanelHost


class ViewCoordinator:
    """视图/分屏/面板切换协调器（不持有 MainWindow 引用）。"""

    def __init__(
        self,
        config: Config,
        theme_engine: ThemeEngine,
        webengine_runtime: WebEngineRuntime,
        editor_splitter: QSplitter,
        editor_tabs: EditorTabWidget,
        find_replace_bar: FindReplaceBar,
        side_panel_host: SidePanelHost,
        splitter: QSplitter,
        game_view_container: QWidget,
        game_sidebar: GameSidebar,
        secretary: SecretaryWidget,
        shortcut_panel: ShortcutPanel,
        connect_tabs_signals: Callable[[EditorTabWidget], None],
        on_wrap_mode_changed: Callable[[str], None],
    ) -> None:
        self._config = config
        self._theme_engine = theme_engine
        self._webengine_runtime = webengine_runtime
        self._editor_splitter = editor_splitter
        self._editor_tabs = editor_tabs
        self._find_replace_bar = find_replace_bar
        self._side_panel_host = side_panel_host
        self._splitter = splitter
        self._game_view_container = game_view_container
        self._game_sidebar = game_sidebar
        self._secretary = secretary
        self._shortcut_panel = shortcut_panel
        self._connect_tabs_signals = connect_tabs_signals
        self._on_wrap_mode_changed = on_wrap_mode_changed

        self._current_view = "editor"
        self._split_tabs: List[EditorTabWidget] = []

    @property
    def current_view(self) -> str:
        """当前视图状态（editor / construction / garage / collection）。"""
        return self._current_view

    @property
    def split_tabs(self) -> List[EditorTabWidget]:
        """当前分屏 tab widget 列表（MainWindow 保存/大纲等逻辑只读使用）。"""
        return self._split_tabs

    # === 视图切换 ===

    def switch_view(self, view: str) -> None:
        """切换主视图（编辑区与游戏侧栏互斥显隐）。"""
        if view == self._current_view:
            return

        if view == "editor":
            self._side_panel_host.show_panel("filetree")
            self._splitter.show()
            self._game_view_container.hide()
            self._game_sidebar.set_current_view(None)
        else:
            self._splitter.hide()
            self._game_view_container.show()
            self._game_sidebar.set_current_view(view)

        self._current_view = view

    # === 分屏 ===

    def split_editor(self, orientation: Qt.Orientation) -> None:
        """创建独立分屏（复用 MainWindow 注入的信号连接回调）。"""
        if self._split_tabs:
            return
        self._editor_splitter.setOrientation(orientation)
        split_tabs = EditorTabWidget(
            self._config,
            theme_engine=self._theme_engine,
            webengine_runtime=self._webengine_runtime,
        )
        split_tabs.set_find_bar(self._find_replace_bar)
        self._connect_tabs_signals(split_tabs)
        self._editor_splitter.addWidget(split_tabs)
        self._split_tabs.append(split_tabs)
        split_tabs.new_file()
        total = self._editor_splitter.width()
        self._editor_splitter.setSizes([total // 2, total // 2])
        self._secretary.show_message(
            "已启用分屏。注意：分屏中编辑的是独立文件，与主面板不同步。"
        )

    def close_split(self, parent: QWidget) -> None:
        """关闭最后一个分屏（未保存时确认）。"""
        if not self._split_tabs:
            return
        split_tabs = self._split_tabs.pop()
        unsaved = split_tabs.get_unsaved_files()
        if unsaved:
            reply = QMessageBox.question(
                parent, "关闭分屏",
                "分屏中有未保存的文件，是否关闭？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                self._split_tabs.append(split_tabs)
                return
        split_tabs.save_all_to_temp()
        split_tabs.close_all_tabs()
        split_tabs.setParent(None)
        split_tabs.deleteLater()

    # === 行宽模式 ===

    def set_wrap_mode(self, mode: str) -> None:
        """设置行宽模式（保存配置 + 应用到全部 tab + 回调同步菜单）。"""
        self._config.set_editor_setting("wrap_mode", mode)
        self._editor_tabs.set_wrap_mode_all(mode)
        self._on_wrap_mode_changed(mode)

    # === 面板显隐 ===

    def toggle_md_preview(self) -> None:
        """切换 Markdown 预览。"""
        self._editor_tabs.toggle_md_preview()

    def toggle_minimap(self) -> None:
        """切换代码缩略图。"""
        self._editor_tabs.toggle_minimap()

    def toggle_file_tree(self) -> None:
        """切换文件树显示/隐藏。"""
        self._side_panel_host.toggle("filetree")

    def toggle_side_panel(self) -> None:
        """切换侧栏面板宿主显示/隐藏。"""
        if self._side_panel_host.isVisible():
            self._side_panel_host.hide_panel()
        else:
            current_id = self._side_panel_host.current_panel_id()
            if current_id is not None:
                self._side_panel_host.show_panel(current_id)
            else:
                # 无激活面板时默认显示大纲
                self._side_panel_host.show_panel("outline")

    def toggle_secretary(self) -> None:
        """切换小秘书显示/隐藏并持久化。"""
        self._secretary.setVisible(not self._secretary.isVisible())
        self._config.set_secretary_setting(
            "show_secretary", self._secretary.isVisible()
        )

    def toggle_shortcut_panel(self) -> None:
        """切换快捷键提示面板。"""
        if self._shortcut_panel.isVisible():
            self._shortcut_panel.hide()
        else:
            self._shortcut_panel.refresh()
            self._shortcut_panel.show()
            self._shortcut_panel.raise_()
