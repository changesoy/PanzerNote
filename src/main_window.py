# -*- coding: utf-8 -*-
"""
主窗口模块
包含菜单栏、资源栏、侧边栏、编辑区、状态栏

v1.5.4 改动：
  - 集成 FindReplaceBar 查找替换功能（Ctrl+F / Ctrl+H）
  - 设置菜单新增「自动缩略图」选项（仅代码文件显示缩略图）
  - 文件树接受标签拖拽，实现"移动文件到文件夹"
"""

import os
import gc
from functools import partial
import shiboken6  # type: ignore[import-not-found]  # 显式依赖（pyproject.toml dependencies），mypy 无 stub
from PyQt6.QtWidgets import (
    QMainWindow,
    QMenu,
    QMessageBox,
    QApplication,
    QDialog
)
from PyQt6.QtCore import Qt, QTimer, QEvent, QPoint, QRect, QEasingCurve
from PyQt6.QtGui import QIcon, QCloseEvent, QAction
from typing import Any, Callable, Dict, Optional, Tuple, cast

from . import __version__
from .core.document_registry import DocumentRegistry
from .core.app_context import AppContext
from .core.session_restore_service import SessionRestoreService
from .core.timer_manager import TimerManager
from .core.event_bus import EventBus
from .core.menu_builder import MenuBuilder
from .core.shortcut_manager import ShortcutManager
from .core.path_resolver import load_json, save_json
from .game.game_engine import GameEngine
from .editor.editor_tabs import EditorTabWidget
from .editor.webengine_runtime import WebEngineRuntime
from .editor.status_bar import StatusBarWidget
from .editor.file_open_service import FileOpenService, FileOpenSource, FileOpenSecurityError, _is_inside_root
from .editor.file_action_controller import FileActionController
from .editor.export_action_controller import ExportActionController
from .editor.edit_action_controller import EditActionController
from .editor.settings_action_controller import SettingsActionController
from .security.file_guard import FileGuard, FileSizeExceededError
from .plugins.plugin_manager import PluginManager
from .plugins.plugin_base import PluginPermission
from .plugins.capability_registry import PluginCapabilityError
from .plugins.plugin_event_bus import PluginEventBus
from .themes.theme_engine import ThemeEngine
from .themes.theme_preview import ThemePreviewDialog
from .themes.theme_v2.consumer import v2_active_variant, v2_token
from .themes.theme_v2.transition import CommitResult
from .themes.theme_v2.transition_controller import ThemeTransitionController, easing_for
from .themes.theme_v2.types import ThemeSwitchLevel
from .ui.command_palette import CommandPalette
from .utils.logger import get_logger
from .utils.feature_flags import is_enabled
from .utils.dpi_helper import scale
from .utils.window_theme import (
    apply_native_dark_titlebar,
    install_native_titlebar_theme_filter,
)
from .ui.main_window_ui import MainWindowUIBuilder
from .ui.selection_clear_filter import SelectionClearFilter
from .ui.view_coordinator import ViewCoordinator
from .ui.unsaved_files_dialog import UnsavedChoice, UnsavedFilesDialog


class MainWindow(QMainWindow):
    """主窗口"""

    # 插件私有数据单文件大小上限（Wave 5 Batch 3，设计 §3.5）
    PLUGIN_DATA_MAX_SIZE = 1 * 1024 * 1024

    def __init__(self, app_context: AppContext, parent=None):
        super().__init__(parent)
        self.app_context = app_context
        # 过渡期：保留 Config 门面引用，旧代码零改动；新代码优先用 app_context.xxx
        self.config = app_context.config
        # 预声明由 MenuBuilder 动态挂载的属性
        self.recent_menu: QMenu
        self._wrap_no_wrap_action: QAction
        self._wrap_limit_action: QAction
        # 插件注册的菜单项容器（首次注册时惰性创建）
        self._plugin_menu: Optional[QMenu] = None
        # 插件数据专用 FileGuard（1MB 上限，不污染全局 50MB 配置）
        self._plugin_data_guard = FileGuard(
            self.config.get_path_validator(),
            max_file_size=self.PLUGIN_DATA_MAX_SIZE,
        )
        # 保存引用，避免事件过滤器被 GC
        self._selection_clear_filter: Optional[SelectionClearFilter] = None
        self._file_open_service = FileOpenService(
            self.config.get_path_validator(),
            self.config.get_notebooks_path(),
        )
        self._session_restore_service = SessionRestoreService(
            self.app_context.workspace_store,
            self._file_open_service,
        )
        self._closing = False
        self._closing_pending_save = False
        self._closing_awaiting: list = []
        self.setAcceptDrops(True)

        self.game_engine = GameEngine(self.config)
        self.timer_manager = TimerManager(self.config, self)
        self.event_bus = EventBus(self.config, self)
        self.shortcut_manager = ShortcutManager(self.config)
        self._cmd_palette: Optional[CommandPalette] = None
        # 插件注册的命令：action_id -> (plugin_id, command_id, handler)，随插件卸载清理
        self._plugin_commands: Dict[str, Tuple[str, str, Callable]] = {}
        self.editor_tabs: EditorTabWidget  # 在 _init_ui 中初始化
        self.theme_engine = ThemeEngine(self.config)
        self.theme_engine.initialize_active_theme()

        # B7：切换视觉过渡编排（启动期恢复主题不经 controller、无动画）
        self._theme_transition = ThemeTransitionController(self)

        self._native_titlebar_filter = install_native_titlebar_theme_filter(
            cast(QApplication, QApplication.instance()),
            lambda: v2_active_variant(self.theme_engine) == "dark",
            parent=self,
        )

        self.webengine_runtime = WebEngineRuntime(self)

        # 保存待恢复的最大化状态（不在 __init__ 期间显示窗口）
        self._initial_maximized = bool(
            self.config.get_window_setting("maximized", False)
        )
        self._presented = False

        # Batch 4：插件事件总线（白名单 + 节流 + 订阅上限；卸载自动解绑）
        self._plugin_event_bus = PluginEventBus(self)
        self.plugin_manager = PluginManager(self.config, event_bus=self._plugin_event_bus)
        self.plugin_manager.scan_plugins()
        # 插件卸载后清理其注册的命令（防止 handler 引用泄漏）
        self.plugin_manager.add_unload_hook(self._on_plugin_unloaded)
        self._register_plugin_capabilities()

        self._save_notify_timer = QTimer(self)
        self._save_notify_timer.setSingleShot(True)
        self._save_notify_timer.timeout.connect(self._do_save_notify)

        # 3.5.8（批次 4a）：Document 生命周期全局唯一——主面板与全部分屏共享同一 registry
        self._document_registry = DocumentRegistry()

        self._ui_builder = MainWindowUIBuilder(
            self.config,
            self.theme_engine,
            self.shortcut_manager,
            self.webengine_runtime,
            self._document_registry,
        )

        self._init_ui()
        # 3.5.3：最近聚焦的编辑器面板（文件树/对话框夺焦后打开文件仍落在用户正在操作的面板）
        self._last_focused_editor_tabs: Optional[EditorTabWidget] = self.editor_tabs
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.focusChanged.connect(self._on_focus_changed)
        self._file_action_controller = FileActionController(
            lambda: self._focused_editor_tabs() or self.editor_tabs,
            self.app_context.workspace_store,
            self.app_context.path_resolver,
            self._file_open_service,
        )
        self.export_actions = ExportActionController(
            self.editor_tabs,
            self.theme_engine,
            self.secretary,
            self,
        )
        self.edit_actions = EditActionController(
            self.editor_tabs,
            self.secretary,
        )
        self.settings_actions = SettingsActionController(
            self.config,
            self.editor_tabs,
            self.secretary,
            self.timer_manager,
            self._file_open_service,
            self,
        )
        self._init_menubar()
        self._init_statusbar()
        self._init_timers()
        self._register_command_palette()
        self._restore_state()
        self._connect_signals()
        self._apply_theme()

        icon_path = os.path.join(self.config.get_assets_path(), "icons", "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # 安装应用级点击过滤器，用于点击空白处取消选中高亮
        # 必须在 _init_ui 之后安装，确保所有子视图已创建
        self._selection_clear_filter = SelectionClearFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self._selection_clear_filter)

        QTimer.singleShot(0, self._check_session_recovery)

    def _init_ui(self):
        """初始化UI：widget 创建与布局委托给 MainWindowUIBuilder，信号集中连接"""
        self.setWindowTitle("PanzerNote")
        self.setMinimumSize(scale(800), scale(600))

        ui = self._ui_builder.build(self)
        # 解包
        self.resource_bar = ui.resource_bar
        self.line1 = ui.line1
        self.game_sidebar = ui.game_sidebar
        self.line2 = ui.line2
        self.splitter = ui.splitter
        self.side_panel_host = ui.side_panel_host
        self.file_tree = ui.file_tree
        self.outline_panel = ui.outline_panel
        self.find_in_files_panel = ui.find_in_files_panel
        self.editor_container = ui.editor_container
        self.find_replace_bar = ui.find_replace_bar
        self.editor_splitter = ui.editor_splitter
        self.editor_tabs = ui.editor_tabs
        self.game_view_container = ui.game_view_container
        self._game_placeholder = ui.game_placeholder
        self.secretary = ui.secretary
        self.shortcut_panel = ui.shortcut_panel

        self.webengine_runtime.prepare_startup_anchor(self.editor_container)
        self.view_coordinator = ViewCoordinator(
            self.config,
            self.theme_engine,
            self.webengine_runtime,
            self.editor_splitter,
            self.editor_tabs,
            self.find_replace_bar,
            self.side_panel_host,
            self.splitter,
            self.game_view_container,
            self.game_sidebar,
            self.secretary,
            self.shortcut_panel,
            self._connect_editor_tabs_signals,
            lambda _mode: self._sync_wrap_menu(),
            self._document_registry,
        )
        self._connect_ui_signals()

    def _connect_ui_signals(self):
        """集中连接主 UI 信号（与重构前散落 connect 逐项核对一致）。

        仅包含 _init_ui 创建的组件信号；状态栏信号在 _init_statusbar 连接。
        """
        self.game_sidebar.view_changed.connect(self._on_view_changed)
        self.file_tree.file_open_requested.connect(self._open_file)
        self.file_tree.file_move_requested.connect(self._on_file_move_from_tree)
        self.file_tree.file_copy_requested.connect(self._on_file_copy_from_tree)
        self.file_tree.file_deleted.connect(self._on_file_deleted)
        self.file_tree.untitled_save_requested.connect(self._on_untitled_save_from_tree)
        self.outline_panel.heading_clicked.connect(self._on_outline_heading_clicked)
        self.find_in_files_panel.result_clicked.connect(self._on_find_in_files_result)
        self.shortcut_panel.set_edit_callback(self._on_shortcut_edited)
        # Batch 4：主题切换 / 文件树变化 → 插件事件（B8：订阅 manager 信号）
        theme_manager = getattr(self.theme_engine, "theme_manager", None)
        if theme_manager is not None:
            theme_manager.theme_committed.connect(
                lambda _pkg, variant: self._plugin_event_bus.emit("theme.changed", variant)
            )
        self.file_tree.tree_changed.connect(
            lambda: self._plugin_event_bus.emit("file_tree.changed")
        )
        self._connect_editor_tabs_signals(self.editor_tabs)

    def _connect_editor_tabs_signals(self, tabs: EditorTabWidget):
        """主面板与分屏复用，保证信号配置永远一致。"""
        tabs.current_changed.connect(self._on_tab_changed)
        tabs.content_modified.connect(self._on_content_modified)
        tabs.tab_count_changed.connect(partial(self._on_tab_count_changed, tabs))
        tabs.chars_typed.connect(self._on_chars_typed)
        tabs.cursor_position_changed.connect(self._update_stats)
        tabs.word_count_updated.connect(self._update_stats)
        tabs.file_saved.connect(self._on_file_saved)
        # Batch 4：文档打开/关闭/光标移动 → 插件事件（高频事件由总线节流）
        tabs.document_opened.connect(
            lambda fp: self._plugin_event_bus.emit("document.opened", fp)
        )
        tabs.document_closed.connect(
            lambda fp: self._plugin_event_bus.emit("document.closed", fp)
        )
        tabs.cursor_position_changed.connect(
            lambda: self._plugin_event_bus.emit("cursor.changed")
        )

    def _init_menubar(self):
        """初始化菜单栏"""
        builder = MenuBuilder(self.config, self.shortcut_manager)
        mb = self.menuBar()
        assert mb is not None
        builder.build(mb, self)

    def _init_statusbar(self):
        """初始化状态栏"""
        self.status_bar_widget = StatusBarWidget(theme_engine=self.theme_engine)
        self.status_bar_widget.eol_toggled.connect(self._on_eol_toggled)
        self.setStatusBar(self.status_bar_widget)

    def _init_timers(self):
        """初始化定时器"""
        self.timer_manager.setup(
            on_auto_save=self._auto_save,
            on_update_stats=self._update_stats,
            on_idle_reward=self._on_idle_reward,
        )

    def _restore_window_geometry(self) -> None:
        """在窗口不可见状态下恢复几何和最大化状态。

        最大化场景：预缩放控件树到屏幕可用尺寸，确保 showMaximized()
        首帧 paint 时 backing store 已是正确尺寸，消除视觉撕裂。
        """
        width = self.config.get_window_setting("width", 1200)
        height = self.config.get_window_setting("height", 800)
        x = self.config.get_window_setting("x", 100)
        y = self.config.get_window_setting("y", 100)

        if self._initial_maximized:
            screen = QApplication.screenAt(QPoint(x, y)) or QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                self.resize(avail.width(), avail.height())
            state = self.windowState()
            state &= ~Qt.WindowState.WindowMinimized
            state |= Qt.WindowState.WindowMaximized
            self.setWindowState(state)
        else:
            self.setGeometry(x, y, width, height)

    def _restore_state(self):
        """恢复窗口状态"""
        self._restore_window_geometry()

        self._calculate_offline_rewards()
        self._check_daily_checkin()

        has_pending = self._session_restore_service.restore_session(self.editor_tabs)
        if has_pending:
            QTimer.singleShot(0, self._open_next_pending_file)
        else:
            active_index = self.config.get_active_tab_index()
            if active_index < self.editor_tabs.count():
                self.editor_tabs.setCurrentIndex(active_index)

        self._restore_split_state()

        # 3.5.9：启动空会话兜底（主面板总有一个可编辑位置）
        if self.editor_tabs.count() == 0:
            self.editor_tabs.new_file()
        # 3.5.9：旧配置残留的空分屏（3.5.9 之前保存的空面板）→ 自动关闭
        for tabs in list(self.view_coordinator.split_tabs):
            if tabs.count() == 0:
                self.view_coordinator.close_split(self)

        current_view = self.config.get_current_view()
        if current_view != "editor":
            self._switch_view(current_view)

        self.file_tree.refresh_external_files()

        self.side_panel_host.restore_state(self.config)

        self.config.update_last_login()
        self.config.save_savegame()

    def _open_next_pending_file(self):
        """打开下一个待恢复的会话文件（由 QTimer 单次驱动）

        逻辑委托 SessionRestoreService.open_next_pending。
        """
        if not self._session_restore_service.open_next_pending(self.editor_tabs):
            return
        QTimer.singleShot(0, self._open_next_pending_file)

    def _restore_split_state(self):
        """恢复分屏状态（方向 / 分割比例 / 各分屏文件与激活标签）。

        旧配置无分屏字段（split_active 默认 False）时直接跳过，行为与
        未分屏时一致，保证向后兼容。
        """
        if not self.config.get_split_active():
            return
        orientation = (
            Qt.Orientation.Vertical
            if self.config.get_split_orientation() == "Vertical"
            else Qt.Orientation.Horizontal
        )
        split_tabs_config = self.config.get_split_tabs()
        if not split_tabs_config:
            return
        self.view_coordinator.restore_split(orientation, self.config.get_split_sizes())
        split_widgets = self.view_coordinator.split_tabs
        if not split_widgets:
            return
        for tabs, tab_config in zip(split_widgets, split_tabs_config):
            open_files = tab_config.get("open_files", []) if isinstance(tab_config, dict) else []
            if not isinstance(open_files, list):
                open_files = []
            for entry in open_files:
                if not isinstance(entry, dict):
                    continue
                if entry.get("is_new"):
                    # 3.5.10：分屏内未命名文件恢复（沿用编号，dirty 内容一并还原）
                    tabs.restore_untitled_file(
                        entry.get("untitled_number") or 1,
                        entry.get("display_name", "未命名"),
                        entry.get("content"),
                    )
                    continue
                filepath = entry.get("path")
                if filepath and os.path.exists(filepath):
                    index = tabs.open_file(filepath, activate=False)
                    if index >= 0:
                        self._session_restore_service.restore_cursor(tabs, entry, index)
            active_index = tab_config.get("active_tab_index", 0) if isinstance(tab_config, dict) else 0
            if isinstance(active_index, int) and 0 <= active_index < tabs.count():
                tabs.setCurrentIndex(active_index)

    def _connect_signals(self):
        """连接信号"""
        self.event_bus.connect_signals(self)

    def _save_state(self):
        """保存窗口状态"""
        if not self.isMaximized():
            self.config.set_window_setting("width", self.width())
            self.config.set_window_setting("height", self.height())
            self.config.set_window_setting("x", self.x())
            self.config.set_window_setting("y", self.y())
        self.config.set_window_setting("maximized", self.isMaximized())

        open_files = self.editor_tabs.get_open_files_info()
        self.config.set_open_files(open_files)

        self.config.set_active_tab_index(self.editor_tabs.currentIndex())
        self.config.set_current_view(self.view_coordinator.current_view)

        # 分屏状态持久化（3.5.2）
        split_tabs = self.view_coordinator.split_tabs
        self.config.set_split_active(bool(split_tabs))
        if split_tabs:
            self.config.set_split_orientation(
                "Vertical"
                if self.editor_splitter.orientation() == Qt.Orientation.Vertical
                else "Horizontal"
            )
            self.config.set_split_sizes(self.editor_splitter.sizes())
            self.config.set_split_tabs(
                [
                    {
                        "open_files": t.get_open_files_info(),
                        "active_tab_index": t.currentIndex(),
                    }
                    for t in split_tabs
                ]
            )

        sizes = self.splitter.sizes()
        if len(sizes) >= 2:
            self.config.set_view_setting("sidebar_width", sizes[0])
            self.config.set_view_setting("editor_area_width", sizes[1])

        self.side_panel_host.save_state(self.config)

        # 书签持久化
        self.editor_tabs.save_all_bookmarks()

        # 折叠状态持久化
        self.editor_tabs.save_all_folds()

        self.config.update_last_login()

        self.config.save_settings()
        self.config.save_workspace()

        from .core.savegame_manager import SavegameSaveResult
        result = self.config.save_savegame()
        if result == SavegameSaveResult.WRITE_FAILED:
            QMessageBox.warning(
                self,
                "游戏存档保存失败",
                "游戏进度保存失败。请检查磁盘空间或文件权限。"
            )

    def _save_to_temp(self):
        """保存到暂存文件（主面板 + 全部分屏，3.5.2）"""
        for tabs in [self.editor_tabs, *self.view_coordinator.split_tabs]:
            tabs.save_all_to_temp()

    def _check_session_recovery(self):
        """检查是否有可恢复的异常退出会话

        在 window.show() 之后由 QTimer.singleShot(0, ...) 触发，
        不在 __init__ 中直接弹窗。查找与命名委托
        SessionRestoreService，UI 弹窗保留在本方法。

        创建者：MainWindow.__init__（通过 QTimer.singleShot 延迟）
        持有者：TempSessionManager
        完成通知：同步完成
        失败通知：日志记录，不中断启动
        关闭时行为：恢复的会话在关闭时走正常保存流程
        """
        session_mgr = self.editor_tabs.session_manager
        session = self._session_restore_service.check_crash_recovery(session_mgr)
        if session is None:
            return

        file_names = self._session_restore_service.describe_crash_files(session)
        file_list = "\n".join([f"• {n}" for n in file_names[:5]])
        if len(file_names) > 5:
            file_list += f"\n...等{len(file_names)}个文件"

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("恢复会话")
        msg_box.setText(f"检测到上次异常退出，以下文件可能未保存：\n\n{file_list}\n\n是否恢复？")
        msg_box.setIcon(QMessageBox.Icon.Question)

        recover_btn = msg_box.addButton("恢复", QMessageBox.ButtonRole.AcceptRole)
        discard_btn = msg_box.addButton("丢弃", QMessageBox.ButtonRole.DestructiveRole)
        msg_box.exec()

        clicked = msg_box.clickedButton()
        if clicked == recover_btn:
            self._recover_session(session)
        elif clicked == discard_btn:
            confirm = QMessageBox.question(
                self, "确认丢弃",
                "丢弃后将无法恢复这些文件，确定要丢弃吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if confirm == QMessageBox.StandardButton.Yes:
                session_mgr.remove_recovered_session(session["session_dir"])
            else:
                self._recover_session(session)

    def _recover_session(self, session: dict):
        """恢复指定会话的文件（逻辑委托 SessionRestoreService）"""
        session_mgr = self.editor_tabs.session_manager
        self._session_restore_service.restore_after_crash(
            self.editor_tabs,
            session,
            session_mgr,
            split_tabs=list(self.view_coordinator.split_tabs),
        )

    # === 挂机机制 ===

    def _on_idle_reward(self):
        """在线挂机奖励（每分钟触发）"""
        self.game_engine.apply_idle_reward()
        self.resource_bar.refresh()

    def _calculate_offline_rewards(self):
        """计算离线挂机收益"""
        reward = self.game_engine.apply_offline_reward()
        if reward is None:
            return

        time_str = GameEngine.format_offline_time(reward["offline_minutes"])
        fuel = reward["fuel"]
        ammo = reward["ammo"]
        steel = reward["steel"]
        bauxite = reward["bauxite"]

        QTimer.singleShot(2000, lambda: self.secretary.show_message(
            f"离线{time_str}，获得资源！\n燃料+{fuel} 弹药+{ammo}\n钢材+{steel} 铝材+{bauxite}",
            5000
        ))

    def _check_daily_checkin(self):
        if self.config.check_daily_checkin():
            QTimer.singleShot(3000, lambda: self.secretary.show_message(
                "每日签到成功！\n燃料+100 弹药+100\n钢材+100 铝材+100",
                5000
            ))
            self.resource_bar.refresh()

    # === 事件处理 ===

    def present(self) -> None:
        """唯一的窗口显示入口

        确保 MainWindow.__init__() 期间窗口始终不可见，
        第一个同步恢复的文件在主窗口显示前完成控件挂载。
        最大化场景使用 showMaximized() 让 Qt 在一步内以最终
        尺寸完成首次渲染，避免普通尺寸 → 最大化尺寸的两段式跳变。
        """
        if self._presented:
            return

        self._presented = True
        if self._initial_maximized:
            self.showMaximized()
        else:
            self.show()

        # Batch 5（D5）：窗口显示后延迟启动启用插件，插件不进启动关键路径
        QTimer.singleShot(0, self._activate_enabled_plugins)

    def showEvent(self, event):
        super().showEvent(event)

        def apply_later() -> None:
            try:
                self._update_title_bar_theme(v2_active_variant(self.theme_engine) == "dark")
            except Exception:
                pass

        QTimer.singleShot(0, apply_later)

    def changeEvent(self, event: Optional[QEvent]):
        """窗口状态变化事件"""
        if event is None:
            return
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                self._save_to_temp()
        super().changeEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    event.acceptProposedAction()
                    return
        event.ignore()

    _SUPPORTED_DROP_EXTS = frozenset({
        '.txt', '.md', '.py', '.c', '.cpp', '.h', '.java', '.js',
        '.json', '.html', '.css', '.xml', '.yaml', '.yml', '.toml',
        '.ini', '.log', '.sql', '.sh', '.go', '.rs', '',
    })

    def _drop_target_panel(self, pos: QPoint) -> Optional[EditorTabWidget]:
        """按释放位置确定目标面板（主面板/分屏，3.5.7）。

        拖放期间焦点通常停留在文件树（拖拽源），焦点追踪只能回退到"最近
        聚焦面板"，与释放位置可能不一致；改为按释放点落在哪个面板矩形内
        决定打开目标。点落在任何面板之外（分割条、边距等）返回 None，
        由调用方回退到焦点面板。
        """
        for tabs in [self.editor_tabs, *self.view_coordinator.split_tabs]:
            if not tabs.isVisible():
                continue
            origin = tabs.mapTo(self, QPoint(0, 0))
            if QRect(origin, tabs.size()).contains(pos):
                return tabs
        return None

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            target = self._drop_target_panel(event.position().toPoint())
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    filepath = url.toLocalFile()
                    ext = os.path.splitext(filepath)[1].lower()
                    if not os.path.isfile(filepath):
                        continue
                    if ext not in self._SUPPORTED_DROP_EXTS:
                        QMessageBox.warning(self, "不支持的文件类型",
                                            f"PanzerNote 不支持打开 {ext or '无扩展名'} 类型的文件。")
                        continue
                    try:
                        validated = self._file_open_service.validate_open_request(
                            filepath, FileOpenSource.DRAG_DROP
                        )
                    except FileOpenSecurityError as e:
                        QMessageBox.warning(self, "无法打开文件", str(e))
                        continue
                    self._open_file_bypass_service(validated, target_tabs=target)
            event.acceptProposedAction()
        else:
            event.ignore()

    def closeEvent(self, event: Optional[QCloseEvent]):
        """关闭窗口事件（两阶段关闭，3.5.7 多面板版）

        阶段1：统计主面板 + 全部分屏的未保存文件（1 个单文件弹窗 / 多个汇总弹窗，
              含「取消」按钮）：
              - 保存并关闭 → event.ignore()，遍历全面板 save_all_for_close()
                （任一另存为取消 / 保存提交失败 → 提示并中止，窗口保留）
              - 不保存并关闭 → _finalize_close()
              - 取消 → event.ignore()
        阶段2：等待各面板 SaveTaskManager.all_tasks_finished 全部完成
              全部成功 → _finalize_close()
              任一失败 → 取消关闭，恢复 UI
        """
        if event is None:
            return
        if self._closing:
            event.accept()
            return

        self._save_to_temp()

        panels = [self.editor_tabs, *self.view_coordinator.split_tabs]

        if any(p.save_manager.any_saving() for p in panels):
            QMessageBox.information(
                self, "请稍候",
                "正在保存文件，请等待保存完成后再关闭。"
            )
            event.ignore()
            return

        unsaved_infos = []
        seen_docs = set()
        for p in panels:
            for info in p.get_unsaved_tab_infos():
                # 3.5.8：共享 Document 在主面板与分屏各有一个 View，按 document_id
                # 去重——退出确认框同一文件只列一次（保存/不保存对 Document 生效一次即可）
                doc_id = info.get("document_id")
                if doc_id is not None:
                    if doc_id in seen_docs:
                        continue
                    seen_docs.add(doc_id)
                unsaved_infos.append(info)

        if not unsaved_infos:
            self._finalize_close()
            event.accept()
            return

        choice = UnsavedFilesDialog.ask(
            self,
            [info["title"] for info in unsaved_infos],
            show_cancel=True,
            window_title="确认退出",
        )
        if choice == UnsavedChoice.CANCEL:
            event.ignore()
            return
        if choice == UnsavedChoice.DISCARD:
            self._finalize_close()
            event.accept()
            return

        # 保存并关闭
        event.ignore()
        self._closing_pending_save = True
        self._closing_awaiting = []
        for p in panels:
            if not p.save_all_for_close():
                self._closing_pending_save = False
                self._closing_awaiting = []
                QMessageBox.warning(
                    self, "保存失败",
                    "部分文件保存失败或另存为已取消，无法关闭窗口。\n"
                    "请检查磁盘空间或文件权限后重试。",
                )
                return
            if p.save_manager.has_pending_tasks():
                self._closing_awaiting.append(p)
        if not self._closing_awaiting:
            # 兜底：无待保存任务（理论上有未保存则必有提交）
            self._closing_pending_save = False
            self._finalize_close()
            return
        for p in self._closing_awaiting:
            p.save_manager.all_tasks_finished.connect(self._on_close_save_finished)

    def _finalize_close(self):
        """最终关闭逻辑：保存窗口状态、清理临时文件、关闭窗口"""
        self._closing = True
        self._save_state()
        for tabs in [self.editor_tabs, *self.view_coordinator.split_tabs]:
            tabs.clear_temp_files()
        self.close()

    def _on_close_save_finished(self):
        """异步保存全部完成后的回调（3.5.7：多面板聚合）

        创建者：MainWindow.closeEvent（用户选择保存并关闭时，连接到各面板
              SaveTaskManager.all_tasks_finished）
        持有者：各面板 SaveTaskManager.all_tasks_finished 信号连接
        完成通知：全部面板的 SaveTaskManager.all_tasks_finished
        失败通知：SaveTaskManager.save_failed（每个失败任务单独触发）
        关闭时行为：断开信号连接，重置关闭标志
        """
        # 任一面板仍有未完成任务 → 继续等待（all_tasks_finished 各自触发）
        if any(p.save_manager.has_pending_tasks() for p in self._closing_awaiting):
            return

        for p in self._closing_awaiting:
            try:
                p.save_manager.all_tasks_finished.disconnect(self._on_close_save_finished)
            except (TypeError, RuntimeError):
                pass
        self._closing_awaiting = []

        if not self._closing_pending_save:
            return

        panels = [self.editor_tabs, *self.view_coordinator.split_tabs]
        failed_files = []
        for p in panels:
            failed_tabs = p.save_manager.get_failed_tab_ids()
            if failed_tabs:
                failed_files.extend(p.get_failed_filenames(failed_tabs))
        if failed_files:
            self._closing_pending_save = False
            file_list = "\n".join([f"• {f}" for f in failed_files[:5]])
            if len(failed_files) > 5:
                file_list += f"\n...等{len(failed_files)}个文件"
            QMessageBox.warning(
                self, "保存失败",
                f"以下文件保存失败，无法关闭：\n\n{file_list}"
            )
            return

        self._closing_pending_save = False
        self._finalize_close()

    def keyPressEvent(self, event):
        """键盘事件"""
        if event.key() == Qt.Key.Key_Escape and self.view_coordinator.current_view != "editor":
            self._switch_view("editor")
            return
        if event.key() == Qt.Key.Key_F1:
            self._show_command_palette()
            return
        super().keyPressEvent(event)

    # === 文件操作 ===

    def _new_file(self):
        """新建文件（焦点在分屏时新建到分屏，与 Ctrl+S 焦点感知一致）"""
        (self._focused_editor_tabs() or self.editor_tabs).new_file()

    def _new_folder(self):
        """新建文件夹"""
        self.file_tree.create_new_folder()

    def _open_file_dialog(self):
        """打开文件对话框

        3.5.3：文件对话框会夺取焦点，目标面板须在弹窗前捕获（焦点感知），
        否则对话框关闭后 provider 求值会落回主面板。
        """
        target_tabs = self._focused_editor_tabs() or self.editor_tabs
        filepath = self._file_action_controller.show_open_dialog(self)
        if filepath:
            self._open_file(filepath, target_tabs=target_tabs)

    def _open_file(self, filepath: str, target_tabs: Optional[EditorTabWidget] = None):
        """打开文件（编排委托 FileActionController）"""
        try:
            _, is_external = self._file_action_controller.open_file(
                filepath, target_tabs=target_tabs
            )
        except FileOpenSecurityError as e:
            QMessageBox.warning(self, "无法打开文件", str(e))
            return
        if is_external:
            self.file_tree.refresh_external_files()
        self._update_recent_menu()

    def _open_file_bypass_service(
        self, filepath: str, target_tabs: Optional[EditorTabWidget] = None
    ):
        """由拖放等已通过 FileOpenService 校验后调用，不再重复校验。

        target_tabs：拖放按释放位置确定的目标面板；未传时落最近聚焦面板。
        """
        _, is_external = self._file_action_controller.open_file_bypass_service(
            filepath, target_tabs=target_tabs
        )
        if is_external:
            self.file_tree.refresh_external_files()
        self._update_recent_menu()

    def _on_focus_changed(self, old, new):
        """3.5.3：焦点变化时记录最近聚焦的编辑器面板（主面板或分屏）。

        点击编辑器内部（QTextEdit 等子控件）时 FocusIn 发往子控件而非
        EditorTabWidget 本身，事件过滤器收不到；故用全局 focusChanged 信号。
        焦点转移到文件树等非编辑器控件时保持最近记录不变。
        """
        if new is None:
            return
        for tabs in [self.editor_tabs, *self.view_coordinator.split_tabs]:
            if tabs is new or tabs.isAncestorOf(new):
                self._last_focused_editor_tabs = tabs
                return

    def _focused_editor_tabs(self) -> Optional[EditorTabWidget]:
        """返回当前焦点所在的 EditorTabWidget（主面板或分屏），无则最近聚焦的面板。

        分屏聚焦时按 Ctrl+S 应保存分屏中正在编辑的文件，而非固定主面板；
        点击文件树等夺焦控件后打开文件，同样落在最近聚焦的面板。
        """
        focus = QApplication.focusWidget()
        if focus is not None:
            for tabs in [self.editor_tabs, *self.view_coordinator.split_tabs]:
                if tabs is focus or tabs.isAncestorOf(focus):
                    return tabs
        last = self._last_focused_editor_tabs
        if last is not None and not shiboken6.isValid(last):
            # 3.5.8（批次 5 修复）：分屏关闭销毁后旧引用悬垂
            # （C++ deleted）——清掉并回退主面板，避免 open_file 崩溃
            self._last_focused_editor_tabs = None
            return self.editor_tabs
        return last

    def _save_current(self):
        """保存当前文件（焦点在分屏时保存分屏）"""
        tabs = self._focused_editor_tabs() or self.editor_tabs
        tabs.save_current()

    def _save_as(self):
        """另存为（焦点在分屏时另存为分屏）"""
        tabs = self._focused_editor_tabs() or self.editor_tabs
        tabs.save_current_as()

    def _save_all(self):
        """保存所有文件（主面板 + 全部分屏）"""
        self.editor_tabs.save_all()
        for tabs in self.view_coordinator.split_tabs:
            tabs.save_all()

    def _export_pdf(self):
        """导出当前文档为 PDF（委托 ExportActionController）"""
        self.export_actions.export_pdf()

    def _export_html(self):
        """导出当前文档为 HTML（委托 ExportActionController）"""
        self.export_actions.export_html()

    def _close_current_tab(self):
        """关闭当前标签"""
        self.editor_tabs.close_current_tab()

    def _close_all_tabs(self):
        """关闭所有标签"""
        self.editor_tabs.close_all_tabs()

    def _reopen_closed_tab(self):
        """重新打开最近关闭的标签"""
        self.editor_tabs.reopen_closed_tab()

    def _release_memory(self):
        """释放占用内存"""
        self.editor_tabs.release_memory()
        gc.collect()
        self.secretary.show_message("已释放内存占用")

    def _update_recent_menu(self):
        """更新最近打开菜单（数据过滤委托服务，菜单构建保留）"""
        recent_files = self._file_action_controller.refresh_recent_files()
        self.recent_menu.clear()

        if not recent_files:
            action = QAction("(空)", self)
            action.setEnabled(False)
            self.recent_menu.addAction(action)
            return

        for filepath in recent_files[:10]:
            filename = os.path.basename(filepath)
            action = QAction(filename, self)
            action.setToolTip(filepath)
            action.triggered.connect(lambda checked, f=filepath: self._open_file(f))
            self.recent_menu.addAction(action)

    # === 编辑操作 ===

    def _undo(self):
        """撤销"""
        self.edit_actions.undo()

    def _redo(self):
        """重做"""
        self.edit_actions.redo()

    def _cut(self):
        """剪切"""
        self.edit_actions.cut()

    def _copy(self):
        """复制"""
        self.edit_actions.copy()

    def _paste(self):
        """粘贴"""
        self.edit_actions.paste()

    def _select_all(self):
        """全选"""
        self.edit_actions.select_all()

    def _find(self):
        """查找"""
        self.edit_actions.find()

    def _replace(self):
        """替换"""
        self.edit_actions.replace()

    # === 行操作 ===

    def _delete_current_line(self):
        self.edit_actions.delete_current_line()

    def _move_line_up(self):
        self.edit_actions.move_line_up()

    def _move_line_down(self):
        self.edit_actions.move_line_down()

    def _copy_line(self):
        self.edit_actions.copy_line()

    def _paste_line(self):
        self.edit_actions.paste_line()

    def _goto_line(self):
        self.edit_actions.goto_line()

    # === 大小写转换 ===

    def _toggle_case(self):
        self.edit_actions.toggle_case()

    def _to_uppercase(self):
        self.edit_actions.to_uppercase()

    def _to_lowercase(self):
        self.edit_actions.to_lowercase()

    def _to_titlecase(self):
        self.edit_actions.to_titlecase()

    # === 书签与折叠 ===

    def _toggle_bookmark(self):
        self.edit_actions.toggle_bookmark()

    def _next_bookmark(self):
        self.edit_actions.next_bookmark()

    def _prev_bookmark(self):
        self.edit_actions.prev_bookmark()

    def _toggle_fold_all(self):
        """折叠/展开全部 Markdown 标题。"""
        self.edit_actions.toggle_fold_all()

    # === 视图操作 ===

    def _on_view_changed(self, view: str):
        """游戏侧边栏视图切换"""
        if view == "back":
            if self.view_coordinator.current_view != "editor":
                self._switch_view("editor")
            else:
                self._undo()
        else:
            self._switch_view(view)

    def _switch_view(self, view: str):
        """切换视图（委托 ViewCoordinator）"""
        self.view_coordinator.switch_view(view)

    def _set_wrap_mode(self, mode: str):
        """设置行宽模式（委托 ViewCoordinator）"""
        self.view_coordinator.set_wrap_mode(mode)

    def _toggle_md_preview(self):
        """切换Markdown预览（委托 ViewCoordinator）"""
        self.view_coordinator.toggle_md_preview()

    def _toggle_minimap(self):
        """切换代码缩略图（委托 ViewCoordinator）"""
        self.view_coordinator.toggle_minimap()

    def _split_editor_horizontal(self):
        """水平分屏（委托 ViewCoordinator）"""
        self.view_coordinator.split_editor(Qt.Orientation.Horizontal)

    def _split_editor_vertical(self):
        """垂直分屏（委托 ViewCoordinator）"""
        self.view_coordinator.split_editor(Qt.Orientation.Vertical)

    def _close_split(self):
        """关闭分屏（委托 ViewCoordinator）"""
        self.view_coordinator.close_split(self)

    def _reset_split_layout(self):
        """重置分屏布局（委托 ViewCoordinator）"""
        self.view_coordinator.reset_split_layout()

    def _toggle_file_tree(self):
        """切换文件树显示/隐藏（委托 ViewCoordinator）"""
        self.view_coordinator.toggle_file_tree()

    def _toggle_side_panel(self):
        """切换侧栏面板宿主显示/隐藏（委托 ViewCoordinator）"""
        self.view_coordinator.toggle_side_panel()

    def _toggle_secretary(self):
        """切换小秘书显示/隐藏（委托 ViewCoordinator）"""
        self.view_coordinator.toggle_secretary()

    def _toggle_shortcut_panel(self):
        """切换快捷键提示面板（委托 ViewCoordinator）"""
        self.view_coordinator.toggle_shortcut_panel()

    @staticmethod
    def _on_shortcut_edited(action_id: str, new_shortcut: str):
        """快捷键编辑回调"""
        from .utils.logger import get_logger
        get_logger(__name__).info("快捷键已更新: %s -> %s", action_id, new_shortcut)

    # === 命令面板 ===

    def _register_command_palette(self):
        """注册命令面板快捷键。"""
        action = self.shortcut_manager.register(
            "command_palette", "命令面板", "Ctrl+Shift+P",
            self._show_command_palette, "帮助"
        )
        if action:
            self.addAction(action)

    def _show_command_palette(self):
        """切换命令面板。已打开则关闭，未打开则打开。"""
        if self._cmd_palette is not None and self._cmd_palette.isVisible():
            self._cmd_palette.close()
            return

        all_shortcuts = self.shortcut_manager.get_all_shortcuts()
        commands = []
        for _category, cmds in all_shortcuts.items():
            for action_id, info in cmds.items():
                commands.append((info["name"], info["shortcut"], action_id))
        # 插件命令（无快捷键；显示插件提供的 command_id）
        for action_id, (plugin_id, command_id, _handler) in self._plugin_commands.items():
            if self.plugin_manager.get_plugin(plugin_id) is not None:
                commands.append((command_id, "", action_id))

        actual_shortcut = self.shortcut_manager.get_shortcut("command_palette") or "Ctrl+Shift+P"

        palette = CommandPalette(commands, shortcut=actual_shortcut, theme_engine=self.theme_engine, parent=self)
        palette.command_triggered.connect(self._dispatch_command)
        palette.destroyed.connect(self._on_palette_closed)

        if CommandPalette._last_known_pos is not None:
            palette.move(CommandPalette._last_known_pos)
        else:
            tabs_pos = self.editor_tabs.mapToGlobal(QPoint(0, 0))
            palette.move(
                tabs_pos.x() + (self.editor_tabs.width() - palette.width()) // 2,
                tabs_pos.y(),
            )

        palette.show()
        self._cmd_palette = palette

    def _on_palette_closed(self):
        """面板关闭后清理引用。"""
        self._cmd_palette = None

    def _dispatch_command(self, action_id: str) -> None:
        """执行命令面板选中的命令。"""
        entry = self._plugin_commands.get(action_id)
        if entry is not None:
            plugin_id, command_id, handler = entry
            if self.plugin_manager.get_plugin(plugin_id) is None:
                get_logger(__name__).warning(
                    "插件命令所属插件已卸载: %s", command_id
                )
                return
            self._safe_plugin_callback(command_id, handler)
            return
        action = self.shortcut_manager.get_action(action_id)
        if action:
            action.trigger()
        else:
            get_logger(__name__).warning("未找到命令注册: %s", action_id)

    def _toggle_fullscreen(self):
        """切换全屏"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _zoom_in(self):
        """放大"""
        self.editor_tabs.zoom_in()

    def _zoom_out(self):
        """缩小"""
        self.editor_tabs.zoom_out()

    def _zoom_reset(self):
        """重置缩放"""
        self.editor_tabs.zoom_reset()

    # === 游戏功能 ===

    def _import_characters(self):
        """导入角色数据"""
        QMessageBox.information(self, "提示", "该功能尚在开发中")

    def _import_document(self):
        """导入外部文档"""
        QMessageBox.information(self, "提示", "该功能尚在开发中")

    def _show_typing_stats(self):
        """显示打字统计"""
        QMessageBox.information(self, "提示", "该功能尚在开发中")

    def _show_construction_stats(self):
        """显示建造记录"""
        QMessageBox.information(self, "提示", "该功能尚在开发中")

    def _show_collection_stats(self):
        """显示图鉴完成度"""
        QMessageBox.information(self, "提示", "该功能尚在开发中")

    def _emit_plugin_event(self, event_name: str, payload: Any = None) -> None:
        """派发插件事件；总线未装配（如 __new__ 构造的测试窗口）时安全跳过。

        用 __dict__ 直接读取而非 getattr：__new__ 构造的 PyQt 对象上访问
        未设置属性会抛 RuntimeError（C++ 部分未初始化），而非返回默认值。
        """
        bus = self.__dict__.get("_plugin_event_bus")
        if bus is not None:
            bus.emit(event_name, payload)

    def _on_file_saved(self):
        """文件保存成功后防抖通知（由 SaveState.CLEAN 回调触发）"""
        self._save_notify_timer.start(300)
        # Batch 4：文档保存事件（低频率，直接派发）
        self._emit_plugin_event("document.saved")

    def _do_save_notify(self):
        """防抖到期后执行保存通知"""
        self.resource_bar.refresh()
        self.secretary.show_message("文件已保存！")

    def _on_tab_count_changed(self, tabs: EditorTabWidget, count: int):
        """标签页数量变化

        3.5.9：标签全关时的空会话兜底 / 自动关闭分屏。
        - 主面板标签全关 → 自动新建未命名1（总有一个可编辑位置）。
        - 分屏标签全关 → 自动关闭分屏（分屏是临时任务视图，任务完成即清理）；
          分屏不新建未命名，否则与自动关闭冲突。
        """
        if count == 0:
            if tabs is self.editor_tabs:
                tabs.new_file()
            else:
                self.view_coordinator.close_split(self)

    def _on_file_move_from_tree(self, src_filepath: str, dest_folder: str):
        """文件树请求移动文件（标签拖拽到文件夹）"""
        success = self.editor_tabs.move_file_to_folder(src_filepath, dest_folder)
        if success:
            self.secretary.show_message(
                f"已将 {os.path.basename(src_filepath)} 移动到 {os.path.basename(dest_folder)}/"
            )
            # Batch 4：移动成功 → 文件树变化事件
            self._emit_plugin_event("file_tree.changed")

    def _on_file_copy_from_tree(self, src_filepath: str, dest_folder: str):
        """文件树请求复制文件（标签拖拽到文件夹）"""
        success = self.editor_tabs.copy_file_to_folder(src_filepath, dest_folder)
        if success:
            self.secretary.show_message(
                f"已将 {os.path.basename(src_filepath)} 复制到 {os.path.basename(dest_folder)}/"
            )
            # Batch 4：复制成功 → 文件树变化事件
            self._emit_plugin_event("file_tree.changed")

    def _on_file_deleted(self, path: str, is_dir: bool):
        """文件树删除文件/文件夹后，同步关闭所有（含分屏）已打开的对应标签页"""
        for tabs in [self.editor_tabs, *self.view_coordinator.split_tabs]:
            tabs.close_tabs_of_deleted_path(path, is_dir)

    @staticmethod
    def _on_untitled_save_from_tree(source_tabs, tab_id: int, dest_folder: str):
        """3.5.11：未命名标签拖到文件树 → 落盘保存（一行委托）"""
        source_tabs.save_untitled_to_folder(tab_id, dest_folder)

    # === 设置 ===

    def _show_editor_settings(self):
        """显示记事本设置（委托 SettingsActionController，完成后同步换行菜单）"""
        self.settings_actions.show_editor_settings()
        self._sync_wrap_menu()

    def _sync_wrap_menu(self):
        """同步换行菜单选中态（show/apply/reset/import 后统一调用）"""
        wrap_mode = self.config.get_editor_setting("wrap_mode", "no_wrap")
        self._wrap_no_wrap_action.setChecked(wrap_mode == "no_wrap")
        self._wrap_limit_action.setChecked(wrap_mode == "limit_width")

    def _show_game_settings(self):
        """显示游戏设置"""
        QMessageBox.information(self, "提示", "该功能尚在开发中")

    def _export_settings(self):
        """导出设置（委托 SettingsActionController）"""
        self.settings_actions.export_settings()

    def _import_settings(self):
        """导入设置（委托 SettingsActionController，完成后同步换行菜单）"""
        self.settings_actions.import_settings()
        self._sync_wrap_menu()

    def _save_settings(self):
        """保存设置（委托 SettingsActionController）"""
        self.settings_actions.save_settings()

    def _apply_editor_settings(self):
        """从 config 读取当前设置并应用到 UI（委托，完成后同步换行菜单）"""
        self.settings_actions.apply_editor_settings()
        self._sync_wrap_menu()

    def _reset_settings(self):
        """恢复默认设置（委托 SettingsActionController，完成后同步换行菜单）"""
        self.settings_actions.reset_settings()
        self._sync_wrap_menu()

    # === 帮助 ===

    def _show_guide(self):
        """显示新手攻略"""
        QMessageBox.information(self, "提示", "该功能尚在开发中")

    def _show_manual(self):
        """显示使用说明"""
        QMessageBox.information(self, "提示", "该功能尚在开发中")

    def _show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "关于 PanzerNote",
            f"PanzerNote v{__version__}\n\n"
            "一款以《战车少女》为主题的笔记工具。\n"
            "通过书写获取资源，建造收集角色，点亮完整图鉴。\n\n"
            "让日常记录变成一场温暖的怀旧之旅。"
        )

    # === 自动保存和统计 ===

    def _auto_save(self):
        """自动保存"""
        if any(
            tabs.has_modified_files()
            for tabs in [self.editor_tabs, *self.view_coordinator.split_tabs]
        ):
            self._save_to_temp()

    def _update_stats(self):
        editor = self.editor_tabs.current_editor()
        if editor:
            if is_enabled("signal_driven_stats"):
                char_count = editor.get_fast_char_count()
                word_count = editor.get_debounced_word_count()
            else:
                char_count = editor.get_char_count()
                word_count = editor.get_word_count()
            line = editor.get_current_line()
            col = editor.get_current_column()
            file_type = editor.get_file_type()
            encoding = self.editor_tabs.get_current_encoding()
            eol = self.editor_tabs.get_current_eol()

            self.status_bar_widget.update_stats(
                char_count, line, col, encoding, file_type, word_count, eol
            )

        today_chars = self.config.get_today_chars_typed()
        total_docs = self.config.get_total_documents()
        self.resource_bar.update_typing_stats(today_chars, total_docs)

    def _on_tab_changed(self, index: int):
        """标签页切换"""
        self._update_stats()
        self._update_outline()

    def _update_outline(self):
        """根据当前编辑器类型显示/隐藏大纲面板"""
        # 从所有 tab widget 中找到当前编辑器
        editor = None
        for tw in [self.editor_tabs] + self.view_coordinator.split_tabs:
            e = tw.current_editor()
            if e is not None:
                editor = e
                break
            w = tw.currentWidget()
            if w is not None and w.hasFocus():
                editor = e
                break

        if editor is not None:
            try:
                file_type = editor.get_file_type()
            except (RuntimeError, AttributeError):
                file_type = ""
        else:
            file_type = ""

        if file_type == "Markdown":
            self.outline_panel.set_editor(editor)
        else:
            self.outline_panel.set_editor(None)

    def _on_outline_heading_clicked(self, line_num: int):
        """大纲面板点击标题 → 跳转到对应行"""
        editor = self.editor_tabs.current_editor()
        if editor is not None and editor.get_file_type() == "Markdown":
            editor.goto_line(line_num)

    def _show_find_in_files(self):
        """显示/切换跨文件搜索面板。"""
        self.side_panel_host.show_panel("search")
        self.find_in_files_panel.focus_search()

    def _on_find_in_files_result(self, filepath: str, line_num: int):
        """跨文件搜索结果双击 → 打开文件并跳转到行"""
        # 如果已在标签页中打开，直接跳转
        editor = self.editor_tabs.current_editor()
        if editor is not None:
            current_path = editor.filepath() if hasattr(editor, "filepath") else ""
            if current_path and os.path.normpath(current_path) == os.path.normpath(filepath):
                editor.goto_line(line_num)
                return

        # 尝试打开文件
        try:
            validated = self._file_open_service.validate_open_request(
                filepath, FileOpenSource.USER_DIALOG
            )
        except FileOpenSecurityError:
            QMessageBox.warning(self, "无法打开文件", f"文件不在允许的范围内:\n{filepath}")
            return

        notebook_path = os.path.normpath(self.config.get_notebooks_path())
        if not _is_inside_root(os.path.normpath(validated), notebook_path):
            self.config.add_external_file(validated)
            self.file_tree.refresh_external_files()

        self.editor_tabs.open_file(validated)
        self.config.add_recent_file(validated)
        self._update_recent_menu()

        # 跳转到行
        e = self.editor_tabs.current_editor()
        if e is not None:
            e.goto_line(line_num)

    def _on_content_modified(self):
        """内容修改"""
        self._update_stats()
        # Batch 4：内容变更事件（高频，由总线 100ms 窗口合并节流）
        self._emit_plugin_event("content.changed")

    def _on_eol_toggled(self, new_eol: str):
        """状态栏 EOL 标签点击切换"""
        self.editor_tabs.set_current_eol(new_eol)
        self._update_stats()

    def _on_chars_typed(self, delta: int):
        """处理打字字符数变化，应用递减收益算法"""
        if delta <= 0:
            return
        today_chars = self.config.get_today_chars_typed()
        daily_limit = self.config.get_game_setting("daily_typing_limit", 10000)
        if today_chars >= daily_limit:
            return
        remaining = daily_limit - today_chars
        effective = min(delta, remaining)
        if today_chars + effective <= 1000:
            reward = effective
        elif today_chars + effective <= 3000:
            over_1000 = max(0, 1000 - today_chars)
            in_1000_3000 = effective - over_1000
            reward = over_1000 + int(in_1000_3000 * 0.4)
        else:
            over_1000 = max(0, 1000 - today_chars)
            in_1000_3000 = min(2000, max(0, 3000 - today_chars - over_1000))
            over_3000 = effective - over_1000 - in_1000_3000
            reward = over_1000 + int(in_1000_3000 * 0.4) + int(over_3000 * 0.1)
        self.config.add_chars_typed(effective)
        if reward > 0:
            self.game_engine.add_typing_reward(reward)
            self._update_stats()

    # === 主题管理 ===

    def _apply_theme(self):
        stylesheet = self.theme_engine.generate_stylesheet()
        self.setStyleSheet(stylesheet)
        text_disabled = v2_token(self.theme_engine, "text_muted", "#BDBDBD")
        border = v2_token(self.theme_engine, "border_muted", "#E0E0E0")
        self._game_placeholder.setStyleSheet(f"color: {text_disabled}; font-size: 18px;")
        self.line1.setStyleSheet(f"background-color: {border};")
        self.line2.setStyleSheet(f"background-color: {border};")

        # Windows 下设置标题栏暗色模式（DWM API）
        self._update_title_bar_theme(v2_active_variant(self.theme_engine) == "dark")

    def _update_title_bar_theme(self, is_dark: bool):
        """更新当前主窗口原生标题栏深/浅色。"""
        apply_native_dark_titlebar(self, is_dark)

        # 运行时切换主题时，顺手更新当前已经存在的顶层窗口。
        app = cast(QApplication, QApplication.instance())
        if app is not None:
            for widget in app.topLevelWidgets():
                if widget.isVisible():
                    apply_native_dark_titlebar(widget, is_dark)

    def _show_theme_dialog(self):
        dialog = ThemePreviewDialog(self.theme_engine, self)
        dialog.theme_applied.connect(self._on_theme_applied)
        dialog.exec()

    def _on_theme_applied(self, package_id: str, variant_id: str):
        """B7：唯一切换编排点（设计文档 9.2）。

        包一层 Snapshot Overlay 过渡：逐窗口 grab 旧帧 → 同步执行真实切换 →
        淡出。motion off / 大文件模式下恒瞬时（allow_animation=False）。
        B8：theme_preview 已多包化，切换参数为 (package_id, variant_id)。
        """
        self._theme_transition.run(
            self._transition_windows(),
            lambda: self._switch_theme_now(package_id, variant_id),
            level=ThemeSwitchLevel.L0,  # B7 生产路径恒 L0（同包变体切换）
            motion_level=self._motion_level(),
            allow_animation=self._animations_allowed(),
            veil_color=self._transition_veil_color(),
            easing=self._transition_easing(),
        )

    def _switch_theme_now(self, package_id: str, variant_id: str) -> None:
        """过渡 callable：经 manager 完成 v2 事务（同包变体切换）
        + 持久化 view.theme（package/variant）+ _apply_theme（全局 QSS
        重涂 + DWM 标题栏）——全部同步完成。
        """
        manager = getattr(self.theme_engine, "theme_manager", None)
        if manager is None or manager.request(package_id, variant_id) is not CommitResult.COMMITTED:
            return
        self.config.set_view_setting("theme", f"{package_id}/{variant_id}")
        self._apply_theme()
        self.secretary.show_message("已切换主题")

    def _transition_windows(self) -> list:
        """参与过渡的窗口：主窗口 + 可见顶层 QDialog/QMainWindow。

        瞬时浮层（tooltip/menu/命令面板等）排除：CommandPalette 是 QDialog
        需显式跳过，QMenu/QToolTip 非 QDialog/QMainWindow 天然排除。
        """
        windows: list = [self]
        app = cast(QApplication, QApplication.instance())
        if app is None:
            return windows
        for widget in app.topLevelWidgets():
            if widget is self or not widget.isVisible():
                continue
            if isinstance(widget, (QDialog, QMainWindow)) and not isinstance(widget, CommandPalette):
                windows.append(widget)
        return windows

    def _motion_level(self) -> str:
        return str(self.config.get_view_setting("motion_level", "normal"))

    def _animations_allowed(self) -> bool:
        """D11 force Off：motion off 或当前编辑器大文件模式下禁用动画。"""
        if self._motion_level() == "off":
            return False
        widget = self.editor_tabs.currentWidget()
        editor = getattr(widget, "editor", None)
        if editor is not None and getattr(editor, "is_large_file_mode", lambda: False)():
            return False
        return True

    def _transition_veil_color(self) -> str:
        """overlay 降级遮罩纯色 = 当前变体 surface_primary（旧主题色）。"""
        return v2_token(self.theme_engine, "surface_primary", "#FFFFFF")

    def _transition_easing(self) -> QEasingCurve.Type:
        """缓动取自 motion.json（motion_level 档位不写 motion.json）。"""
        svc = getattr(self.theme_engine, "theme_v2", None)
        if svc is None:
            return QEasingCurve.Type.OutCubic
        snapshot = svc.snapshot()
        if snapshot is None:
            return QEasingCurve.Type.OutCubic
        return easing_for(snapshot.motion.easing)

    # === 插件管理 ===

    def _activate_enabled_plugins(self) -> None:
        """Batch 5（D5）：窗口显示后延迟启动启用插件。

        session 恢复 + 窗口显示已完成，插件能看到恢复后的编辑器/会话状态；
        插件代码不进入启动关键路径。安全模式插件（上次启动启动阶段异常退出）
        会被跳过，仅记录日志，由用户在插件管理中手动处理。
        """
        manager = self.__dict__.get("plugin_manager")
        if manager is None:
            return
        try:
            activated = manager.activate_enabled_plugins()
            if activated:
                get_logger(__name__).info("已启动插件: %s", ", ".join(activated))
            safe_mode = manager.get_safe_mode_plugins()
            if safe_mode:
                get_logger(__name__).warning(
                    "插件处于安全模式（上次启动异常退出），已跳过: %s",
                    ", ".join(safe_mode),
                )
        except Exception:
            get_logger(__name__).exception("启用插件启动失败")

    def _register_plugin_capabilities(self):
        """将宿主能力注册到 CapabilityRegistry（Wave 5 Batch 1 保留能力）"""
        registry = self.plugin_manager.registry

        registry.register("app.version", None, lambda: __version__)
        registry.register(
            "settings.read",
            PluginPermission.READ_SETTINGS,
            self._plugin_settings_impl,
        )
        registry.register(
            "savegame.read",
            PluginPermission.READ_SAVEGAME,
            self._plugin_savegame_impl,
        )
        registry.register(
            "workspace.recent_files",
            PluginPermission.READ_WORKSPACE,
            lambda: self.config.get_recent_files(),
        )
        registry.register(
            "workspace.open_file",
            PluginPermission.OPEN_FILE,
            self._plugin_open_file,
            copy_result=False,
        )
        registry.register(
            "file_tree.read",
            PluginPermission.READ_FILE_TREE,
            lambda: self.config.get_notebooks_path(),
        )
        registry.register(
            "ui.show_message",
            PluginPermission.SHOW_MESSAGE,
            self._plugin_show_message,
            copy_result=False,
        )
        registry.register(
            "ui.register_command",
            PluginPermission.REGISTER_COMMAND,
            self._plugin_register_command,
            copy_result=False,
            pass_plugin_id=True,
        )
        registry.register(
            "editor.read_text",
            PluginPermission.EDITOR_READ,
            self._plugin_editor_read_text,
        )
        registry.register(
            "editor.selection.read",
            PluginPermission.EDITOR_READ,
            self._plugin_editor_selection_read,
        )
        registry.register(
            "editor.selection.replace",
            PluginPermission.EDITOR_WRITE,
            self._plugin_editor_replace,
            copy_result=False,
        )
        registry.register(
            "editor.read_path",
            PluginPermission.EDITOR_READ,
            self._plugin_editor_read_path,
        )
        registry.register(
            "ui.notify",
            PluginPermission.UI_NOTIFY,
            self._plugin_notify,
            copy_result=False,
        )
        registry.register(
            "ui.register_menu_item",
            PluginPermission.REGISTER_MENU,
            self._plugin_register_menu_item,
            copy_result=False,
        )
        # data.read / data.write：内置能力（无需声明），单 JSON 文件 + 1MB 上限
        # pass_plugin_id：impl 需按调用者插件 id 隔离数据命名空间
        registry.register(
            "data.read",
            None,
            lambda plugin_id, key: self._plugin_data_impl("read", plugin_id, key),
            copy_result=False,
            pass_plugin_id=True,
        )
        registry.register(
            "data.write",
            None,
            lambda plugin_id, key, value: self._plugin_data_impl(
                "write", plugin_id, key, value
            ),
            copy_result=False,
            pass_plugin_id=True,
        )
        # event.subscribe：事件订阅（EVENT_SUBSCRIBE，白名单 + 节流由总线控制）
        registry.register(
            "event.subscribe",
            PluginPermission.EVENT_SUBSCRIBE,
            lambda plugin_id, name, handler: self._plugin_event_bus.subscribe(
                plugin_id, name, handler
            ),
            copy_result=False,
            pass_plugin_id=True,
        )

    def _plugin_settings_impl(self, action: str, key: str, default: Any = None):
        if action == "get":
            return self.config.get_setting(key, default)
        if action == "editor":
            return self.config.get_editor_setting(key, default)
        if action == "game":
            return self.config.get_game_setting(key, default)
        if action == "secretary":
            return self.config.get_secretary_setting(key, default)
        raise PluginCapabilityError(f"未知设置读取类型: {action}")

    def _plugin_savegame_impl(self, action: str, key: Optional[str] = None, default: Any = None):
        if action == "resources":
            return self.config.get_resources()
        if action == "field":
            return self.config.get_savegame_field(cast(str, key), default)
        raise PluginCapabilityError(f"未知存档读取类型: {action}")

    def _plugin_data_impl(self, action: str, plugin_id: str, key: str, value: Any = None):
        """data.read / data.write 实现：plugin_data/{plugin_id}/data.json

        - 仅限本插件命名空间（目录由宿主从 plugin_id 派生，插件不可指定路径）
        - 单 JSON 文件，写盘走 FileGuard.safe_write（原子写）
        - 1MB 上限；不可 JSON 序列化的值拒绝写入
        """
        if not isinstance(key, str) or not key.strip():
            raise PluginCapabilityError("数据 key 必须为非空字符串")
        data_dir = os.path.join(
            self.app_context.path_resolver.get_plugin_data_dir(), plugin_id
        )
        data_file = os.path.join(data_dir, "data.json")
        guard = self._plugin_data_guard
        if action == "read":
            return load_json(guard, data_file, {}).get(key)
        if action == "write":
            data = load_json(guard, data_file, {})
            data[key] = value
            try:
                save_json(guard, data_file, data)
            except TypeError as e:
                raise PluginCapabilityError(f"插件数据无法 JSON 序列化: {e}") from e
            except FileSizeExceededError as e:
                raise PluginCapabilityError(f"插件数据超过 1MB 上限: {e}") from e
            return None
        raise PluginCapabilityError(f"未知数据操作: {action}")

    def _plugin_open_file(self, filepath: str) -> bool:
        try:
            from .editor.file_open_service import FileOpenSource, FileOpenSecurityError
            validated = self._file_open_service.validate_open_request(
                filepath, FileOpenSource.PLUGIN
            )
            self.editor_tabs.open_file(validated)
            return True
        except FileOpenSecurityError as e:
            get_logger(__name__).warning("插件 open_file 被安全策略拒绝: %s", e)
            return False
        except Exception as e:
            get_logger(__name__).warning("插件 open_file 失败: %s", e)
            return False

    def _plugin_show_message(self, message: str) -> None:
        self.secretary.show_message(message)

    def _plugin_register_command(self, plugin_id: str, command_id: str, handler) -> None:
        """将插件命令接入命令面板。

        - action_id 使用 plugin:{plugin_id}:{command_id} 前缀避免与内置命令冲突
        - 命令面板显示插件提供的 command_id（建议格式 插件名:动作）
        - 插件卸载时经 _on_plugin_unloaded 清理，防止 handler 引用泄漏
        """
        if not isinstance(command_id, str) or not command_id.strip():
            raise PluginCapabilityError("命令 id 必须为非空字符串")
        action_id = f"plugin:{plugin_id}:{command_id}"
        self._plugin_commands[action_id] = (plugin_id, command_id, handler)
        get_logger(__name__).info("插件注册命令: %s -> %s", command_id, action_id)

    def _on_plugin_unloaded(self, plugin_id: str) -> None:
        """插件卸载后清理其注册的命令（unload hook，见 PluginManager.add_unload_hook）。"""
        removed = [
            aid
            for aid, (pid, _cid, _handler) in self._plugin_commands.items()
            if pid == plugin_id
        ]
        for action_id in removed:
            del self._plugin_commands[action_id]
        if removed:
            get_logger(__name__).info(
                "插件 %s 卸载，清理 %d 个命令", plugin_id, len(removed)
            )

    def _plugin_editor_read_text(self) -> str:
        editor = self.editor_tabs.current_editor()
        return editor.toPlainText() if editor is not None else ""

    def _plugin_editor_selection_read(self) -> str:
        editor = self.editor_tabs.current_editor()
        if editor is None:
            return ""
        return editor.textCursor().selectedText()

    def _plugin_editor_replace(self, text: str) -> None:
        editor = self.editor_tabs.current_editor()
        if editor is None:
            return
        cursor = editor.textCursor()
        cursor.insertText(text)
        editor.setTextCursor(cursor)

    def _plugin_editor_read_path(self) -> Optional[str]:
        widget = self.editor_tabs.currentWidget()
        if widget is None:
            return None
        shared_doc = getattr(widget, "shared_doc", None)
        if shared_doc is None:
            return None
        filepath = shared_doc.filepath
        return str(filepath) if filepath else None

    def _plugin_notify(self, message: str, level: str = "info") -> None:
        prefix = {"warning": "⚠ ", "error": "✕ "}.get(level, "")
        status_bar = self.statusBar()
        if status_bar is not None:
            status_bar.showMessage(prefix + message, 3000)

    def _plugin_register_menu_item(self, label: str, handler) -> None:
        mb = self.menuBar()
        if mb is None:
            return
        if self._plugin_menu is None:
            plugin_menu = mb.addMenu("插件")
            if plugin_menu is None:
                return
            self._plugin_menu = plugin_menu
        action = QAction(label, self)
        action.triggered.connect(
            lambda checked=False, h=handler: self._safe_plugin_callback(label, h)
        )
        self._plugin_menu.addAction(action)

    @staticmethod
    def _safe_plugin_callback(label: str, handler) -> None:
        """命令/菜单/事件回调异常 → 仅 log，插件保持 ACTIVE（D7）"""
        try:
            handler()
        except Exception:
            get_logger(__name__).exception("插件回调异常: %s", label)

    def _show_plugin_manager(self):
        from .plugins.plugin_manager_dialog import PluginManagerDialog
        dialog = PluginManagerDialog(self.plugin_manager, self.secretary, self.theme_engine, parent=self)
        dialog.exec()
