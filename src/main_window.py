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
import html as html_module
from functools import partial
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QMenuBar, QMenu, QStatusBar,
    QLabel, QMessageBox, QTabWidget,
    QToolButton, QFrame, QSizePolicy, QApplication,
    QLineEdit
)
from PyQt6.QtCore import Qt, QTimer, QEvent, pyqtSignal, QPoint, QRect
from PyQt6.QtGui import QIcon, QCloseEvent, QAction
from typing import Optional, cast

from . import __version__
from .core.app_context import AppContext
from .core.session_restore_service import SessionRestoreService
from .core.timer_manager import TimerManager
from .core.event_bus import EventBus
from .core.menu_builder import MenuBuilder
from .core.shortcut_manager import ShortcutManager
from .game.game_engine import GameEngine
from .editor.editor_tabs import EditorTabWidget
from .editor.webengine_runtime import WebEngineRuntime
from .editor.status_bar import StatusBarWidget
from .editor.file_open_service import FileOpenService, FileOpenSource, FileOpenSecurityError, _is_inside_root
from .editor.file_action_controller import FileActionController
from .editor.export_action_controller import ExportActionController
from .editor.edit_action_controller import EditActionController
from .editor.settings_action_controller import SettingsActionController
from .plugins.plugin_manager import PluginManager
from .themes.theme_engine import ThemeEngine
from .themes.theme_preview import ThemePreviewDialog
from .ui.command_palette import CommandPalette
from .utils.logger import get_logger
from .utils.error_handler import ErrorHandler, ErrorCategory
from .utils.feature_flags import is_enabled
from .utils.dpi_helper import scale, scale_size
from .utils.window_theme import (
    apply_native_dark_titlebar,
    install_native_titlebar_theme_filter,
)
from .ui.main_window_ui import MainWindowUIBuilder
from .ui.selection_clear_filter import SelectionClearFilter
from .ui.view_coordinator import ViewCoordinator


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self, app_context: AppContext, parent=None):
        super().__init__(parent)
        self.app_context = app_context
        # 过渡期：保留 Config 门面引用，旧代码零改动；新代码优先用 app_context.xxx
        self.config = app_context.config
        # 预声明由 MenuBuilder 动态挂载的属性
        self.recent_menu: QMenu
        self._wrap_no_wrap_action: QAction
        self._wrap_limit_action: QAction
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
        self.setAcceptDrops(True)

        self.game_engine = GameEngine(self.config)
        self.timer_manager = TimerManager(self.config, self)
        self.event_bus = EventBus(self.config, self)
        self.shortcut_manager = ShortcutManager(self.config)
        self._cmd_palette: Optional[CommandPalette] = None
        self.editor_tabs: EditorTabWidget  # 在 _init_ui 中初始化
        self.theme_engine = ThemeEngine(self.config)
        self.theme_engine.load_external_themes()
        self.theme_engine.initialize_active_theme()

        self._native_titlebar_filter = install_native_titlebar_theme_filter(
            cast(QApplication, QApplication.instance()),
            lambda: self.theme_engine.get_active_theme().is_dark,
            parent=self,
        )

        self.webengine_runtime = WebEngineRuntime(self)

        # 保存待恢复的最大化状态（不在 __init__ 期间显示窗口）
        self._initial_maximized = bool(
            self.config.get_window_setting("maximized", False)
        )
        self._presented = False

        self.plugin_manager = PluginManager(self.config)
        self.plugin_manager.scan_plugins()
        self._register_plugin_callbacks()

        self._save_notify_timer = QTimer(self)
        self._save_notify_timer.setSingleShot(True)
        self._save_notify_timer.timeout.connect(self._do_save_notify)

        self._ui_builder = MainWindowUIBuilder(
            self.config,
            self.theme_engine,
            self.shortcut_manager,
            self.webengine_runtime,
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
            self.editor_tabs, session, session_mgr
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

    def showEvent(self, event):
        super().showEvent(event)

        def apply_later() -> None:
            try:
                theme = self.theme_engine.get_active_theme()
                self._update_title_bar_theme(theme.is_dark)
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

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
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
                    self._open_file_bypass_service(validated)
            event.acceptProposedAction()
        else:
            event.ignore()

    def closeEvent(self, event: Optional[QCloseEvent]):
        """关闭窗口事件（两阶段关闭）

        阶段1：检查是否有未保存/保存中/保存失败的文件
              如有，提示用户选择保存/不保存/取消
              用户选择保存时，event.ignore()，启动异步保存
        阶段2：等待 SaveTaskManager.all_tasks_finished 信号
              全部成功 → _finalize_close()
              任一失败 → 取消关闭，恢复 UI
        """
        if event is None:
            return
        if self._closing:
            event.accept()
            return

        self._save_to_temp()

        save_mgr = self.editor_tabs.save_manager

        if save_mgr.any_saving():
            QMessageBox.information(
                self, "请稍候",
                "正在保存文件，请等待保存完成后再关闭。"
            )
            event.ignore()
            return

        unsaved_files = self.editor_tabs.get_unsaved_files()

        if unsaved_files:
            file_list = "\n".join([f"• {f}" for f in unsaved_files[:5]])
            if len(unsaved_files) > 5:
                file_list += f"\n...等{len(unsaved_files)}个文件"

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("确认退出")
            msg_box.setText(f"有{len(unsaved_files)}个文件未保存：\n\n{file_list}\n\n是否保存并退出？")
            msg_box.setIcon(QMessageBox.Icon.Question)

            save_btn = msg_box.addButton("保存", QMessageBox.ButtonRole.AcceptRole)
            discard_btn = msg_box.addButton("不保存", QMessageBox.ButtonRole.DestructiveRole)
            cancel_btn = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)

            msg_box.exec()

            clicked = msg_box.clickedButton()
            if clicked == save_btn:
                event.ignore()
                self._closing_pending_save = True
                self.editor_tabs.save_all()
                if save_mgr.has_unsaved_work() and not save_mgr.has_pending_tasks():
                    self._closing_pending_save = False
                    return
                if save_mgr.has_pending_tasks():
                    save_mgr.all_tasks_finished.connect(self._on_close_save_finished)
                else:
                    self._finalize_close()
            elif clicked == discard_btn:
                self._finalize_close()
                event.accept()
            else:
                event.ignore()
        else:
            self._finalize_close()
            event.accept()

    def _finalize_close(self):
        """最终关闭逻辑：保存窗口状态、清理临时文件、关闭窗口"""
        self._closing = True
        self._save_state()
        for tabs in [self.editor_tabs, *self.view_coordinator.split_tabs]:
            tabs.clear_temp_files()
        self.close()

    def _on_close_save_finished(self):
        """异步保存全部完成后的回调

        创建者：MainWindow.closeEvent（用户选择保存并退出时）
        持有者：SaveTaskManager.all_tasks_finished 信号连接
        完成通知：SaveTaskManager.all_tasks_finished
        失败通知：SaveTaskManager.save_failed（每个失败任务单独触发）
        关闭时行为：断开信号连接，重置关闭标志
        """
        save_mgr = self.editor_tabs.save_manager
        try:
            save_mgr.all_tasks_finished.disconnect(self._on_close_save_finished)
        except (TypeError, RuntimeError):
            pass

        if not self._closing_pending_save:
            return

        failed_tabs = save_mgr.get_failed_tab_ids()
        if failed_tabs:
            self._closing_pending_save = False
            failed_files = self.editor_tabs.get_failed_filenames(failed_tabs)
            file_list = "\n".join([f"• {f}" for f in failed_files[:5]])
            if len(failed_files) > 5:
                file_list += f"\n...等{len(failed_files)}个文件"
            QMessageBox.warning(
                self, "保存失败",
                f"以下文件保存失败，无法关闭：\n\n{file_list}"
            )
            return

        if save_mgr.has_unsaved_work():
            self._closing_pending_save = False
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

    def _open_file_bypass_service(self, filepath: str):
        """由拖放等已通过 FileOpenService 校验后调用，不再重复校验"""
        _, is_external = self._file_action_controller.open_file_bypass_service(filepath)
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
        return self._last_focused_editor_tabs

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
        import gc
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

    def _on_shortcut_edited(self, action_id: str, new_shortcut: str):
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

    def _on_file_saved(self):
        """文件保存成功后防抖通知（由 SaveState.CLEAN 回调触发）"""
        self._save_notify_timer.start(300)

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
        import os
        success = self.editor_tabs.move_file_to_folder(src_filepath, dest_folder)
        if success:
            self.secretary.show_message(
                f"已将 {os.path.basename(src_filepath)} 移动到 {os.path.basename(dest_folder)}/"
            )

    def _on_file_copy_from_tree(self, src_filepath: str, dest_folder: str):
        """文件树请求复制文件（标签拖拽到文件夹）"""
        import os
        success = self.editor_tabs.copy_file_to_folder(src_filepath, dest_folder)
        if success:
            self.secretary.show_message(
                f"已将 {os.path.basename(src_filepath)} 复制到 {os.path.basename(dest_folder)}/"
            )

    def _on_file_deleted(self, path: str, is_dir: bool):
        """文件树删除文件/文件夹后，同步关闭所有（含分屏）已打开的对应标签页"""
        for tabs in [self.editor_tabs, *self.view_coordinator.split_tabs]:
            tabs.close_tabs_of_deleted_path(path, is_dir)

    def _on_untitled_save_from_tree(self, source_tabs, tab_id: int, dest_folder: str):
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
        theme = self.theme_engine.get_active_theme()
        colors = theme.colors
        self._game_placeholder.setStyleSheet(f"color: {colors.text_disabled}; font-size: 18px;")
        self.line1.setStyleSheet(f"background-color: {colors.border};")
        self.line2.setStyleSheet(f"background-color: {colors.border};")

        # Windows 下设置标题栏暗色模式（DWM API）
        self._update_title_bar_theme(theme.is_dark)

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

    def _on_theme_applied(self, theme_id: str):
        self._apply_theme()
        self.secretary.show_message(f"已切换主题: {self.theme_engine.get_active_theme().name}")

    # === 插件管理 ===

    def _register_plugin_callbacks(self):
        sandbox = self.plugin_manager._sandbox
        sandbox.set_open_file_callback(self._plugin_open_file)
        sandbox.set_show_message_callback(self._plugin_show_message)
        sandbox.set_register_command_callback(self._plugin_register_command)

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

    def _plugin_register_command(self, command_id: str, handler) -> None:
        get_logger(__name__).info("插件注册命令: %s", command_id)

    def _show_plugin_manager(self):
        from .plugins.plugin_manager_dialog import PluginManagerDialog
        dialog = PluginManagerDialog(self.plugin_manager, self.secretary, self.theme_engine, parent=self)
        dialog.exec()
