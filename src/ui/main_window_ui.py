# -*- coding: utf-8 -*-
"""
主窗口 UI 组装器（Wave 3 分支 B）
把 MainWindow._init_ui 的"widget 创建 + 布局"整体移入本文件。

设计约束（沿用 hotfix.txt 规划）：
- MainWindowUIBuilder 不持有 MainWindow 引用，build() 仅把 MainWindow 当作挂载点。
- 不连接任何业务信号：信号连接由 MainWindow._connect_ui_signals 集中负责，
  避免"信号连接交织拆出裂缝"。
- 布局与视觉呈现保持与原 _init_ui 完全一致。
"""

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..core.config import Config
from ..core.shortcut_manager import ShortcutManager
from ..editor.editor_tabs import EditorTabWidget
from ..editor.find_in_files_panel import FindInFilesPanel
from ..editor.find_replace import FindReplaceBar
from ..editor.webengine_runtime import WebEngineRuntime
from ..game.game_sidebar import GameSidebar
from ..game.resource_bar import ResourceBar
from ..game.secretary_widget import SecretaryWidget
from ..themes.theme_engine import ThemeEngine
from ..utils.dpi_helper import scale
from ..editor.file_tree import FileTreeWidget
from ..editor.outline_panel import OutlinePanel
from .shortcut_panel import ShortcutPanel
from .side_panel_host import SidePanelHost


@dataclass
class BuiltUI:
    """MainWindowUIBuilder.build() 的产物：主窗口全部 UI 组件。"""

    resource_bar: ResourceBar
    line1: QFrame
    game_sidebar: GameSidebar
    line2: QFrame
    splitter: QSplitter
    side_panel_host: SidePanelHost
    file_tree: FileTreeWidget
    outline_panel: OutlinePanel
    find_in_files_panel: FindInFilesPanel
    editor_container: QWidget
    find_replace_bar: FindReplaceBar
    editor_splitter: QSplitter
    editor_tabs: EditorTabWidget
    game_view_container: QWidget
    game_placeholder: QLabel
    secretary: SecretaryWidget
    shortcut_panel: ShortcutPanel


class MainWindowUIBuilder:
    """主窗口 UI 组装器：只创建与布局，不连接信号。

    构造注入 config/theme_engine/shortcut_manager/webengine_runtime，
    build() 把 MainWindow 当挂载点，返回 BuiltUI。
    """

    def __init__(
        self,
        config: Config,
        theme_engine: ThemeEngine,
        shortcut_manager: ShortcutManager,
        webengine_runtime: WebEngineRuntime,
    ) -> None:
        self._config = config
        self._theme_engine = theme_engine
        self._shortcut_manager = shortcut_manager
        self._webengine_runtime = webengine_runtime

    def build(self, main_window: QMainWindow) -> BuiltUI:
        """构建全部 UI 组件与布局（不连接信号）。

        注意：创建顺序与原 _init_ui 保持一致；editor_tabs 的晚绑定闭包
        （find_in_files_panel.get_open_files）在用户触发搜索时才求值，
        届时 editor_tabs 已创建。
        """
        # 中心部件
        central_widget = QWidget()
        main_window.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 资源栏
        resource_bar = ResourceBar(self._config, theme_engine=self._theme_engine)
        main_layout.addWidget(resource_bar)

        # 分隔线
        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.NoFrame)
        line1.setFixedHeight(1)
        main_layout.addWidget(line1)

        # 内容区域
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # 游戏图标侧边栏
        game_sidebar = GameSidebar(theme_engine=self._theme_engine)
        game_sidebar.setFixedWidth(scale(50))
        content_layout.addWidget(game_sidebar)

        # 分隔线
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.NoFrame)
        line2.setFixedWidth(1)
        content_layout.addWidget(line2)

        # 分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 侧栏面板宿主（统一管理文件树、大纲等面板）
        side_panel_host = SidePanelHost(theme_engine=self._theme_engine)

        # 文件树注册到宿主（默认面板）
        file_tree = FileTreeWidget(self._config, theme_engine=self._theme_engine)
        side_panel_host.register_panel("filetree", file_tree, "≡", "文件树")

        # 大纲面板注册到宿主
        outline_panel = OutlinePanel()
        side_panel_host.register_panel("outline", outline_panel, "§", "大纲")

        # 跨文件搜索面板注册到宿主（晚绑定闭包，调用时 editor_tabs 已存在）
        editor_tabs: EditorTabWidget
        find_in_files_panel = FindInFilesPanel(
            self._config.get_notebooks_path,
            get_open_files=lambda: editor_tabs.get_open_filepaths(),
            get_recent_files=lambda: self._config.get_recent_files(),
            theme_engine=self._theme_engine,
        )
        side_panel_host.register_panel("search", find_in_files_panel, "🔍", "跨文件搜索")

        side_panel_host.setMinimumWidth(scale(100))
        splitter.addWidget(side_panel_host)

        side_panel_host.show_panel("filetree")

        # 编辑区容器
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        # v1.5.4: 查找替换栏（嵌入在编辑器标签页上方）
        find_replace_bar = FindReplaceBar(theme_engine=self._theme_engine)
        find_replace_bar.hide()
        editor_layout.addWidget(find_replace_bar)

        # 编辑器分屏容器
        editor_splitter = QSplitter(Qt.Orientation.Horizontal)
        editor_splitter.setChildrenCollapsible(False)

        # 编辑器标签页
        editor_tabs = EditorTabWidget(
            self._config,
            theme_engine=self._theme_engine,
            webengine_runtime=self._webengine_runtime,
        )
        editor_tabs.set_find_bar(find_replace_bar)
        editor_splitter.addWidget(editor_tabs)

        editor_layout.addWidget(editor_splitter)

        splitter.addWidget(editor_container)

        # 设置分割器初始大小
        sidebar_width = self._config.get_view_setting("sidebar_width", 200)
        editor_width = self._config.get_view_setting("editor_area_width", 800)
        splitter.setSizes([sidebar_width, editor_width])

        content_layout.addWidget(splitter)

        # 内容容器
        content_widget = QWidget()
        content_widget.setLayout(content_layout)
        main_layout.addWidget(content_widget, 1)

        # 游戏界面容器
        game_view_container = QWidget()
        game_view_container.hide()
        _game_layout = QVBoxLayout(game_view_container)
        _game_layout.setContentsMargins(0, 0, 0, 0)
        game_placeholder = QLabel("该功能尚在开发中")
        game_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        game_placeholder.setStyleSheet(
            f"color: {self._theme_engine.get_active_theme().colors.text_disabled}; font-size: 18px;"
        )
        _game_layout.addWidget(game_placeholder)
        main_layout.addWidget(game_view_container)

        # 小秘书（覆盖在编辑区右下角，自动跟随父容器大小变化）
        secretary = SecretaryWidget(
            self._config,
            theme_engine=self._theme_engine,
            parent=editor_container,
        )

        # 快捷键提示面板
        shortcut_panel = ShortcutPanel(
            self._shortcut_manager,
            theme_engine=self._theme_engine,
            parent=main_window,
        )
        shortcut_panel.hide()

        return BuiltUI(
            resource_bar=resource_bar,
            line1=line1,
            game_sidebar=game_sidebar,
            line2=line2,
            splitter=splitter,
            side_panel_host=side_panel_host,
            file_tree=file_tree,
            outline_panel=outline_panel,
            find_in_files_panel=find_in_files_panel,
            editor_container=editor_container,
            find_replace_bar=find_replace_bar,
            editor_splitter=editor_splitter,
            editor_tabs=editor_tabs,
            game_view_container=game_view_container,
            game_placeholder=game_placeholder,
            secretary=secretary,
            shortcut_panel=shortcut_panel,
        )
