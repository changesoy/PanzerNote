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
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QMenuBar, QMenu, QStatusBar,
    QLabel, QMessageBox, QFileDialog, QTabWidget,
    QToolButton, QFrame, QSizePolicy, QApplication, QDialog,
    QLineEdit
)
from PyQt6.QtCore import Qt, QTimer, QEvent, pyqtSignal, QPoint
from PyQt6.QtGui import QIcon, QCloseEvent, QAction, QTextCursor
from typing import List, Optional

from . import __version__
from .core.config import Config
from .core.config_import_service import ConfigImportService, ConfigImportError
from .core.timer_manager import TimerManager
from .core.event_bus import EventBus
from .core.menu_builder import MenuBuilder
from .core.shortcut_manager import ShortcutManager
from .game.game_engine import GameEngine
from .game.resource_bar import ResourceBar
from .game.game_sidebar import GameSidebar
from .editor.file_tree import FileTreeWidget
from .editor.editor_tabs import EditorTabWidget
from .game.secretary_widget import SecretaryWidget
from .editor.status_bar import StatusBarWidget
from .editor.find_replace import FindReplaceBar
from .editor.outline_panel import OutlinePanel
from .editor.editor_settings_dialog import EditorSettingsDialog
from .editor.file_open_service import FileOpenService, FileOpenSource, FileOpenSecurityError, _is_inside_root
from .plugins.plugin_manager import PluginManager
from .themes.theme_engine import ThemeEngine
from .themes.theme_preview import ThemePreviewDialog
from .ui.command_palette import CommandPalette
from .utils.logger import get_logger
from .utils.error_handler import ErrorHandler, ErrorCategory
from .utils.feature_flags import is_enabled
from .utils.dpi_helper import scale, scale_size


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        # 预声明由 MenuBuilder 动态挂载的属性
        self.recent_menu: QMenu
        self._wrap_no_wrap_action: QAction
        self._wrap_limit_action: QAction
        self._file_open_service = FileOpenService(
            config.get_path_validator(),
            config.get_notebooks_path(),
        )
        self._current_view = "editor"
        self._closing = False
        self._closing_pending_save = False
        self.setAcceptDrops(True)

        self.game_engine = GameEngine(config)
        self.timer_manager = TimerManager(config, self)
        self.event_bus = EventBus(config, self)
        self.shortcut_manager = ShortcutManager(config)
        self._cmd_palette: Optional[CommandPalette] = None
        self.theme_engine = ThemeEngine(config)
        self.theme_engine.load_external_themes()
        self.theme_engine.initialize_active_theme()
        self.plugin_manager = PluginManager(config)
        self.plugin_manager.scan_plugins()
        self._register_plugin_callbacks()

        self._save_notify_timer = QTimer(self)
        self._save_notify_timer.setSingleShot(True)
        self._save_notify_timer.timeout.connect(self._do_save_notify)

        self._init_ui()
        self._init_menubar()
        self._init_statusbar()
        self._init_timers()
        self._register_command_palette()
        self._restore_state()
        self._connect_signals()
        self._apply_theme()

        icon_path = os.path.join(config.get_assets_path(), "icons", "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        QTimer.singleShot(0, self._check_session_recovery)

    def _init_ui(self):
        """初始化UI"""
        self.setWindowTitle("PanzerNote")
        self.setMinimumSize(scale(800), scale(600))

        # 中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 资源栏
        self.resource_bar = ResourceBar(self.config, theme_engine=self.theme_engine)
        main_layout.addWidget(self.resource_bar)

        # 分隔线
        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.HLine)
        line1.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(line1)

        # 内容区域
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # 游戏图标侧边栏
        self.game_sidebar = GameSidebar(theme_engine=self.theme_engine)
        self.game_sidebar.setFixedWidth(scale(50))
        self.game_sidebar.view_changed.connect(self._on_view_changed)
        content_layout.addWidget(self.game_sidebar)

        # 分隔线
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.VLine)
        line2.setFrameShadow(QFrame.Shadow.Sunken)
        content_layout.addWidget(line2)

        # 分割器
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # 文件树
        self.file_tree = FileTreeWidget(self.config, theme_engine=self.theme_engine)
        self.file_tree.file_open_requested.connect(self._open_file)
        self.file_tree.file_move_requested.connect(self._on_file_move_from_tree)
        self.file_tree.setMinimumWidth(scale(100))
        self.splitter.addWidget(self.file_tree)

        # 编辑区容器
        self.editor_container = QWidget()
        editor_layout = QVBoxLayout(self.editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        # v1.5.4: 查找替换栏（嵌入在编辑器标签页上方）
        self.find_replace_bar = FindReplaceBar(theme_engine=self.theme_engine)
        self.find_replace_bar.hide()
        editor_layout.addWidget(self.find_replace_bar)

        # 编辑器分屏容器
        self.editor_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.editor_splitter.setChildrenCollapsible(False)

        # 编辑器标签页
        self.editor_tabs = EditorTabWidget(self.config, theme_engine=self.theme_engine)
        self.editor_tabs.set_find_bar(self.find_replace_bar)
        self.editor_tabs.current_changed.connect(self._on_tab_changed)
        self.editor_tabs.content_modified.connect(self._on_content_modified)
        self.editor_tabs.tab_count_changed.connect(self._on_tab_count_changed)
        self.editor_tabs.chars_typed.connect(self._on_chars_typed)
        self.editor_tabs.cursor_position_changed.connect(self._update_stats)
        self.editor_tabs.word_count_updated.connect(self._update_stats)
        self.editor_tabs.file_saved.connect(self._on_file_saved)
        self.editor_splitter.addWidget(self.editor_tabs)

        self._split_tabs: List[EditorTabWidget] = []

        # 大纲面板
        self.outline_panel = OutlinePanel()
        self.outline_panel.hide()
        self.outline_panel.heading_clicked.connect(self._on_outline_heading_clicked)

        # 编辑器+大纲容器（用 splitter 包裹，支持拖拽调整宽度）
        self._editor_outline_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._editor_outline_splitter.addWidget(self.editor_splitter)
        self._editor_outline_splitter.addWidget(self.outline_panel)
        self._editor_outline_splitter.setSizes([800, 200])

        editor_layout.addWidget(self._editor_outline_splitter)

        self.splitter.addWidget(self.editor_container)

        # 设置分割器初始大小
        sidebar_width = self.config.get_view_setting("sidebar_width", 200)
        editor_width = self.config.get_view_setting("editor_area_width", 800)
        self.splitter.setSizes([sidebar_width, editor_width])

        content_layout.addWidget(self.splitter)

        # 内容容器
        content_widget = QWidget()
        content_widget.setLayout(content_layout)
        main_layout.addWidget(content_widget, 1)

        # 游戏界面容器
        self.game_view_container = QWidget()
        self.game_view_container.hide()
        _game_layout = QVBoxLayout(self.game_view_container)
        _game_layout.setContentsMargins(0, 0, 0, 0)
        self._game_placeholder = QLabel("该功能尚在开发中")
        self._game_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._game_placeholder.setStyleSheet(f"color: {self.theme_engine.get_active_theme().colors.text_disabled}; font-size: 18px;")
        _game_layout.addWidget(self._game_placeholder)
        main_layout.addWidget(self.game_view_container)

        # 小秘书（覆盖在编辑区右下角，自动跟随父容器大小变化）
        self.secretary = SecretaryWidget(self.config, theme_engine=self.theme_engine, parent=self.editor_container)

        # 快捷键提示面板
        from .ui.shortcut_panel import ShortcutPanel
        self.shortcut_panel = ShortcutPanel(self.shortcut_manager, theme_engine=self.theme_engine, parent=self)
        self.shortcut_panel.set_edit_callback(self._on_shortcut_edited)
        self.shortcut_panel.hide()

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

    def _restore_state(self):
        """恢复窗口状态"""
        width = self.config.get_window_setting("width", 1200)
        height = self.config.get_window_setting("height", 800)
        x = self.config.get_window_setting("x", 100)
        y = self.config.get_window_setting("y", 100)
        maximized = self.config.get_window_setting("maximized", False)

        self.resize(width, height)
        self.move(x, y)

        if maximized:
            self.showMaximized()

        self._calculate_offline_rewards()
        self._check_daily_checkin()

        open_files = self.config.get_open_files()
        if open_files:
            first_file = open_files[0]
            filepath = first_file.get("path")
            if filepath and os.path.exists(filepath):
                self._open_file(filepath)
                self._restore_cursor_for_current_tab(first_file)
                remaining = open_files[1:]
            else:
                remaining = open_files[1:]
                if self.editor_tabs.count() == 0:
                    self.editor_tabs.new_file()
        else:
            remaining = []
            self.editor_tabs.new_file()

        if remaining:
            from PyQt6.QtCore import QTimer
            self._pending_files = remaining
            QTimer.singleShot(0, self._open_next_pending_file)
        else:
            active_index = self.config.get_active_tab_index()
            if active_index < self.editor_tabs.count():
                self.editor_tabs.setCurrentIndex(active_index)

        current_view = self.config.get_current_view()
        if current_view != "editor":
            self._switch_view(current_view)

        self.file_tree.refresh_external_files()

        self.config.update_last_login()
        self.config.save_savegame()

    def _open_next_pending_file(self):
        if not hasattr(self, '_pending_files') or not self._pending_files:
            active_index = self.config.get_active_tab_index()
            if active_index < self.editor_tabs.count():
                self.editor_tabs.setCurrentIndex(active_index)
            return

        file_info = self._pending_files.pop(0)
        filepath = file_info.get("path")
        cursor_pos = file_info.get("cursor_position")
        scroll_pos = file_info.get("scroll_position")
        if filepath and os.path.exists(filepath):
            self._open_file(filepath)
            if cursor_pos is not None or scroll_pos is not None:
                from .editor.editor import Editor
                from .editor.markdown_preview import MarkdownPreviewWidget
                widget = self.editor_tabs.currentWidget()
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
                    if scroll_pos is not None:
                        from PyQt6.QtCore import QTimer
                        vbar = editor.verticalScrollBar()
                        if vbar is not None:
                            QTimer.singleShot(0, lambda v=scroll_pos, sb=vbar: sb.setValue(v))

        if self._pending_files:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self._open_next_pending_file)

    def _restore_cursor_for_current_tab(self, file_info: dict):
        cursor_pos = file_info.get("cursor_position")
        scroll_pos = file_info.get("scroll_position")
        if cursor_pos is None and scroll_pos is None:
            return
        from .editor.editor import Editor
        from .editor.markdown_preview import MarkdownPreviewWidget
        widget = self.editor_tabs.currentWidget()
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
            if scroll_pos is not None:
                vbar = editor.verticalScrollBar()
                if vbar is not None:
                    QTimer.singleShot(0, lambda v=scroll_pos, sb=vbar: sb.setValue(v))

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
        self.config.set_current_view(self._current_view)

        sizes = self.splitter.sizes()
        if len(sizes) >= 2:
            self.config.set_view_setting("sidebar_width", sizes[0])
            self.config.set_view_setting("editor_area_width", sizes[1])

        self.config.update_last_login()

        self.config.save_settings()
        self.config.save_workspace()
        self.config._save_user_data_path()

        from .core.savegame_manager import SavegameSaveResult
        result = self.config.save_savegame()
        if result == SavegameSaveResult.SKIPPED_ENCRYPTED_UNREAD:
            self._prompt_encrypted_savegame_save()

    def _prompt_encrypted_savegame_save(self):
        from .core.savegame_manager import SavegameSaveResult
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("存档已加密")
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setText("游戏存档已加密但未解锁，本次游戏进度无法保存。")
        msg_box.setInformativeText("请输入密码解锁存档，或放弃本次进度。")
        unlock_btn = msg_box.addButton("输入密码解锁", QMessageBox.ButtonRole.AcceptRole)
        discard_btn = msg_box.addButton("放弃进度", QMessageBox.ButtonRole.DestructiveRole)
        msg_box.exec()

        if msg_box.clickedButton() == unlock_btn:
            from PyQt6.QtWidgets import QInputDialog
            password, ok = QInputDialog.getText(
                self, "解锁存档", "请输入存档加密密码：",
                QLineEdit.EchoMode.Password, ""
            )
            if ok and password:
                if self.config.verify_encryption_password(password):
                    self.config.set_encryption_password(password)
                    result = self.config.save_savegame()
                    if result == SavegameSaveResult.SUCCESS:
                        QMessageBox.information(self, "成功", "存档已保存。")
                    else:
                        QMessageBox.warning(self, "保存失败", "存档保存时发生错误。")
                else:
                    QMessageBox.warning(self, "密码错误", "密码不正确，存档未保存。")

    def _save_to_temp(self):
        """保存到暂存文件"""
        self.editor_tabs.save_all_to_temp()

    def _check_session_recovery(self):
        """检查是否有可恢复的异常退出会话

        在 window.show() 之后由 QTimer.singleShot(0, ...) 触发，
        不在 __init__ 中直接弹窗。

        创建者：MainWindow.__init__（通过 QTimer.singleShot 延迟）
        持有者：TempSessionManager
        完成通知：同步完成
        失败通知：日志记录，不中断启动
        关闭时行为：恢复的会话在关闭时走正常保存流程
        """
        session_mgr = self.editor_tabs.session_manager
        recoverable = session_mgr.find_recoverable_sessions()

        if not recoverable:
            session_mgr.cleanup_all_clean_sessions()
            return

        session = recoverable[0]
        files = session.get("files", [])
        if not files:
            return

        file_names = []
        for f in files:
            original = f.get("original_path", "")
            if original:
                file_names.append(os.path.basename(original))
            else:
                file_names.append("未命名文件")

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
        """恢复指定会话的文件"""
        session_mgr = self.editor_tabs.session_manager
        session_dir = session.get("session_dir", "")
        files = session.get("files", [])

        for f in files:
            original_path = f.get("original_path", "")
            autosave_name = f.get("autosave_path", "")
            encoding = f.get("encoding", "UTF-8")
            is_new = f.get("is_new", False)

            content = session_mgr.read_autosave_content(session_dir, autosave_name, encoding)
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
                index = self.editor_tabs.open_file(validated)
                if index >= 0:
                    widget = self.editor_tabs.widget(index)
                    editor = self.editor_tabs._get_editor_from_widget(widget)
                    if editor:
                        cursor = editor.textCursor()
                        cursor.select(QTextCursor.SelectionType.Document)
                        cursor.insertText(content)
                        tab_id = getattr(widget, 'tab_id', None)
                        if tab_id is not None:
                            self.editor_tabs._save_manager.mark_dirty(tab_id)
            else:
                index = self.editor_tabs.new_file()
                if index >= 0:
                    widget = self.editor_tabs.widget(index)
                    if hasattr(widget, 'tab_id'):
                        editor = self.editor_tabs._get_editor_from_widget(widget)
                        if editor:
                            cursor = editor.textCursor()
                            cursor.select(QTextCursor.SelectionType.Document)
                            cursor.insertText(content)
                            tab_id = getattr(widget, 'tab_id', None)
                            if tab_id is not None:
                                self.editor_tabs._save_manager.mark_dirty(tab_id)

        session_mgr.remove_recovered_session(session_dir)

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
        if self.config.savegame_manager.check_daily_checkin():
            QTimer.singleShot(3000, lambda: self.secretary.show_message(
                "每日签到成功！\n燃料+100 弹药+100\n钢材+100 铝材+100",
                5000
            ))
            self.resource_bar.refresh()

    # === 事件处理 ===

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
        self.editor_tabs.clear_temp_files()
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
            failed_files = []
            for tab_id in failed_tabs:
                info = self.editor_tabs._tab_info.get(tab_id, {})
                filepath = info.get("filepath", "")
                if filepath:
                    failed_files.append(os.path.basename(filepath))
                else:
                    failed_files.append("未知文件")
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
        if event.key() == Qt.Key.Key_Escape and self._current_view != "editor":
            self._switch_view("editor")
            return
        if event.key() == Qt.Key.Key_F1:
            self._show_command_palette()
            return
        super().keyPressEvent(event)

    # === 文件操作 ===

    def _new_file(self):
        """新建文件"""
        self.editor_tabs.new_file()

    def _new_folder(self):
        """新建文件夹"""
        self.file_tree.create_new_folder()

    def _open_file_dialog(self):
        """打开文件对话框"""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "打开文件",
            self.config.get_notebooks_path(),
            "所有支持的文件 (*.txt *.md *.py *.c *.cpp *.h *.java *.js *.json *.html *.css *.xml);;"
            "文本文件 (*.txt);;"
            "Markdown (*.md);;"
            "Python (*.py);;"
            "C/C++ (*.c *.cpp *.h);;"
            "Java (*.java);;"
            "Web (*.html *.css *.js);;"
            "所有文件 (*.*)"
        )
        if filepath:
            self._open_file(filepath)

    def _open_file(self, filepath: str):
        """打开文件（统一走 FileOpenService 安全入口）"""
        try:
            validated = self._file_open_service.validate_open_request(
                filepath, FileOpenSource.USER_DIALOG
            )
        except FileOpenSecurityError as e:
            QMessageBox.warning(self, "无法打开文件", str(e))
            return

        notebooks_path = os.path.normpath(self.config.get_notebooks_path())
        filepath_norm = os.path.normpath(validated)

        if not _is_inside_root(filepath_norm, notebooks_path):
            self.config.add_external_file(validated)
            self.file_tree.refresh_external_files()

        self.editor_tabs.open_file(validated)
        self.config.add_recent_file(validated)
        self._update_recent_menu()

    def _open_file_bypass_service(self, filepath: str):
        """由拖放等已通过 FileOpenService 校验后调用，不再重复校验"""
        notebooks_path = os.path.normpath(self.config.get_notebooks_path())
        filepath_norm = os.path.normpath(filepath)

        if not _is_inside_root(filepath_norm, notebooks_path):
            self.config.add_external_file(filepath)
            self.file_tree.refresh_external_files()

        self.editor_tabs.open_file(filepath)
        self.config.add_recent_file(filepath)
        self._update_recent_menu()

    def _save_current(self):
        """保存当前文件"""
        self.editor_tabs.save_current()

    def _save_as(self):
        """另存为"""
        self.editor_tabs.save_current_as()

    def _save_all(self):
        """保存所有文件"""
        self.editor_tabs.save_all()

    def _export_pdf(self):
        from .editor.export_service import ExportService
        try:
            editor = self.editor_tabs.current_editor()
            if not editor:
                return
            filepath, _ = QFileDialog.getSaveFileName(
                self, "导出PDF", "", "PDF文件 (*.pdf)"
            )
            if not filepath:
                return

            content = editor.toPlainText()
            widget = self.editor_tabs.currentWidget()
            widget_type = type(widget).__name__ if widget else ""
            is_md = ExportService.is_markdown_content(content, widget_type)

            def on_pdf_ready(pdf_data):
                self._on_pdf_generated(pdf_data, filepath)

            ExportService.export_pdf(content, is_md, self, on_pdf_ready)
        except RuntimeError as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _on_pdf_generated(self, pdf_data, filepath):
        if pdf_data:
            try:
                with open(filepath, 'wb') as f:
                    f.write(pdf_data)
                self.secretary.show_message(f"已导出PDF: {os.path.basename(filepath)}")
            except Exception as e:
                ErrorHandler.show_from_exception(e, ErrorCategory.FILE, f"写入PDF文件失败：{os.path.basename(filepath)}")
        else:
            QMessageBox.warning(self, "导出失败", "PDF生成失败")

    def _export_html(self):
        from .editor.export_service import ExportService
        editor = self.editor_tabs.current_editor()
        if not editor:
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出HTML", "", "HTML文件 (*.html)"
        )
        if not filepath:
            return

        content = editor.toPlainText()
        widget = self.editor_tabs.currentWidget()
        widget_type = type(widget).__name__ if widget else ""
        is_md = ExportService.is_markdown_content(content, widget_type)

        try:
            ExportService.export_html(content, is_md, filepath)
            self.secretary.show_message(f"已导出HTML: {os.path.basename(filepath)}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

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
        """更新最近打开菜单"""
        self.recent_menu.clear()
        recent_files = self.config.get_recent_files()

        valid_files = [f for f in recent_files if os.path.exists(f)]
        if valid_files != recent_files:
            self.config._workspace["recent_files"] = valid_files
            recent_files = valid_files

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
        if not self.editor_tabs.undo():
            self.secretary.show_message("当前没有可撤销的操作")

    def _redo(self):
        """重做"""
        self.editor_tabs.redo()

    def _cut(self):
        """剪切"""
        self.editor_tabs.cut()

    def _copy(self):
        """复制"""
        self.editor_tabs.copy()

    def _paste(self):
        """粘贴"""
        self.editor_tabs.paste()

    def _select_all(self):
        """全选"""
        self.editor_tabs.select_all()

    def _find(self):
        """查找"""
        self.editor_tabs.show_find_dialog()

    def _replace(self):
        """替换"""
        self.editor_tabs.show_replace_dialog()

    # === 行操作 ===

    def _delete_current_line(self):
        self.editor_tabs.delete_current_line()

    def _move_line_up(self):
        self.editor_tabs.move_line_up()

    def _move_line_down(self):
        self.editor_tabs.move_line_down()

    def _duplicate_line(self):
        self.editor_tabs.duplicate_line()

    def _goto_line(self):
        self.editor_tabs.show_goto_line_dialog()

    # === 大小写转换 ===

    def _toggle_case(self):
        self.editor_tabs.toggle_case()

    def _to_uppercase(self):
        self.editor_tabs.to_uppercase()

    def _to_lowercase(self):
        self.editor_tabs.to_lowercase()

    def _to_titlecase(self):
        self.editor_tabs.to_titlecase()

    def _toggle_bookmark(self):
        editor = self.editor_tabs.current_editor()
        if editor:
            editor.toggle_bookmark()

    def _next_bookmark(self):
        editor = self.editor_tabs.current_editor()
        if editor:
            editor.next_bookmark()

    def _prev_bookmark(self):
        editor = self.editor_tabs.current_editor()
        if editor:
            editor.prev_bookmark()

    # === 视图操作 ===

    def _on_view_changed(self, view: str):
        """游戏侧边栏视图切换"""
        if view == "back":
            if self._current_view != "editor":
                self._switch_view("editor")
            else:
                self._undo()
        else:
            self._switch_view(view)

    def _switch_view(self, view: str):
        """切换视图"""
        if view == self._current_view:
            return

        if view == "editor":
            self.file_tree.show()
            self.splitter.show()
            self.game_view_container.hide()
            self.game_sidebar.set_current_view(None)
        else:
            self.file_tree.hide()
            self.splitter.hide()
            self.game_view_container.show()
            self.game_sidebar.set_current_view(view)

        self._current_view = view

    def _set_wrap_mode(self, mode: str):
        """设置行宽模式"""
        self.config.set_editor_setting("wrap_mode", mode)
        self.editor_tabs.set_wrap_mode_all(mode)

        # 更新菜单选中状态
        self._wrap_no_wrap_action.setChecked(mode == "no_wrap")
        self._wrap_limit_action.setChecked(mode == "limit_width")

    def _toggle_md_preview(self):
        """切换Markdown预览"""
        self.editor_tabs.toggle_md_preview()

    def _toggle_minimap(self):
        """切换代码缩略图"""
        self.editor_tabs.toggle_minimap()

    def _split_editor_horizontal(self):
        """水平分屏"""
        self._split_editor(Qt.Orientation.Horizontal)

    def _split_editor_vertical(self):
        """垂直分屏"""
        self._split_editor(Qt.Orientation.Vertical)

    def _split_editor(self, orientation):
        if self._split_tabs:
            return
        self.editor_splitter.setOrientation(orientation)
        split_tabs = EditorTabWidget(self.config, theme_engine=self.theme_engine)
        split_tabs.set_find_bar(self.find_replace_bar)
        split_tabs.current_changed.connect(self._on_tab_changed)
        split_tabs.content_modified.connect(self._on_content_modified)
        split_tabs.tab_count_changed.connect(self._on_tab_count_changed)
        split_tabs.chars_typed.connect(self._on_chars_typed)
        split_tabs.cursor_position_changed.connect(self._update_stats)
        split_tabs.word_count_updated.connect(self._update_stats)
        self.editor_splitter.addWidget(split_tabs)
        self._split_tabs.append(split_tabs)
        split_tabs.new_file()
        total = self.editor_splitter.width()
        self.editor_splitter.setSizes([total // 2, total // 2])
        self.secretary.show_message("已启用分屏。注意：分屏中编辑的是独立文件，与主面板不同步。")

    def _close_split(self):
        """关闭分屏"""
        if not self._split_tabs:
            return
        split_tabs = self._split_tabs.pop()
        unsaved = split_tabs.get_unsaved_files()
        if unsaved:
            reply = QMessageBox.question(
                self, "关闭分屏",
                "分屏中有未保存的文件，是否关闭？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                self._split_tabs.append(split_tabs)
                return
        split_tabs.save_all_to_temp()
        split_tabs.close_all_tabs()
        split_tabs.setParent(None)
        split_tabs.deleteLater()

    def _toggle_file_tree(self):
        """切换文件树显示/隐藏"""
        if self.file_tree.isVisible():
            self.file_tree.hide()
        else:
            self.file_tree.show()

    def _toggle_secretary(self):
        """切换小秘书显示/隐藏"""
        self.secretary.setVisible(not self.secretary.isVisible())
        self.config.set_secretary_setting("show_secretary", self.secretary.isVisible())

    def _toggle_shortcut_panel(self):
        """切换快捷键提示面板"""
        if self.shortcut_panel.isVisible():
            self.shortcut_panel.hide()
        else:
            self.shortcut_panel.refresh()
            self.shortcut_panel.show()
            self.shortcut_panel.raise_()

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

        palette = CommandPalette(commands, shortcut=actual_shortcut, parent=self)
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

    def _on_tab_count_changed(self, count: int):
        """标签页数量变化"""
        if count == 0:
            self.secretary.show_event_message("欢迎")

    def _on_file_move_from_tree(self, src_filepath: str, dest_folder: str):
        """文件树请求移动文件（标签拖拽到文件夹）"""
        import os
        success = self.editor_tabs.move_file_to_folder(src_filepath, dest_folder)
        if success:
            self.secretary.show_message(
                f"已将 {os.path.basename(src_filepath)} 移动到 {os.path.basename(dest_folder)}/"
            )

    # === 设置 ===

    def _show_editor_settings(self):
        """显示记事本设置"""
        dialog = EditorSettingsDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            settings = dialog.get_settings()
            editor = settings["editor"]
            secretary = settings["secretary"]

            # 保存编辑器设置
            for key, value in editor.items():
                self.config.set_editor_setting(key, value)

            # 保存小秘书设置
            for key, value in secretary.items():
                self.config.set_secretary_setting(key, value)

            self.config.save_settings()

            # 应用设置
            # 显示行号
            self.editor_tabs.set_line_numbers_all(editor["show_line_numbers"])

            # 高亮当前行
            self.editor_tabs.set_highlight_current_line_all(editor["highlight_current_line"])

            # 字体和字体大小
            self.editor_tabs.set_font_all(editor["font_family"], editor["font_size"])

            # 行宽模式
            self.editor_tabs.set_wrap_mode_all(editor["wrap_mode"])
            self._wrap_no_wrap_action.setChecked(editor["wrap_mode"] == "no_wrap")
            self._wrap_limit_action.setChecked(editor["wrap_mode"] == "limit_width")

            # 自动缩略图
            self.editor_tabs.apply_auto_minimap_all()

            # 缩进配置
            self.editor_tabs.update_indent_settings_all()

            # 自动保存间隔
            self.timer_manager.update_auto_save_interval(editor["auto_save_interval"])

            # 小秘书设置
            if secretary["show_secretary"]:
                self.secretary.show()
                self.secretary.set_size_percent(secretary["size_percent"])
            else:
                self.secretary.hide()

            self.secretary.show_message("设置已保存并应用")

    def _show_game_settings(self):
        """显示游戏设置"""
        QMessageBox.information(self, "提示", "该功能尚在开发中")

    def _export_settings(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出设置", "panzernote_settings.json", "JSON文件 (*.json)"
        )
        if not filepath:
            return
        import json as json_module
        try:
            export_data = {
                "version": __version__,
                "settings": self.config._settings,
                "workspace": self.config._workspace,
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json_module.dump(export_data, f, ensure_ascii=False, indent=2)
            self.secretary.show_message(f"设置已导出到 {os.path.basename(filepath)}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _import_settings(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "导入设置", "", "JSON文件 (*.json)"
        )
        if not filepath:
            return
        import json as json_module
        try:
            validated = self._file_open_service.validate_open_request(
                filepath, FileOpenSource.SETTINGS_IMPORT
            )
        except FileOpenSecurityError as e:
            QMessageBox.warning(self, "导入失败", str(e))
            return

        try:
            content = self.config.get_file_guard().safe_read(
                validated, encoding='utf-8',
                context=self.config.INTERNAL_CONFIG_CTX
            )
            data = json_module.loads(content)
            if not isinstance(data, dict) or "settings" not in data:
                QMessageBox.warning(self, "导入失败", "无效的设置文件格式")
                return
            reply = QMessageBox.question(
                self, "确认导入",
                "导入设置将覆盖当前所有设置，是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
            service = ConfigImportService(self.config)
            skipped = service.import_from_json(content)
            if skipped:
                QMessageBox.warning(
                    self, "导入完成（部分跳过）",
                    "以下字段因格式不正确已跳过：\n" + "\n".join(skipped[:10])
                )
            self._apply_editor_settings()
            self.secretary.show_message("设置已导入，部分设置将在重启后生效")
        except ConfigImportError as e:
            QMessageBox.warning(self, "导入失败", str(e))
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))

    def _save_settings(self):
        """保存设置"""
        self.config.save_settings()
        self.secretary.show_message("设置已保存")

    def _apply_editor_settings(self):
        """从 config 读取当前设置并应用到 UI"""
        self.editor_tabs.set_line_numbers_all(self.config.get_editor_setting("show_line_numbers", True))
        self.editor_tabs.set_highlight_current_line_all(self.config.get_editor_setting("highlight_current_line", True))
        self.editor_tabs.set_font_all(
            self.config.get_editor_setting("font_family", "Microsoft YaHei"),
            self.config.get_editor_setting("font_size", 12)
        )
        self.editor_tabs.set_wrap_mode_all(self.config.get_editor_setting("wrap_mode", "no_wrap"))
        wrap_mode = self.config.get_editor_setting("wrap_mode", "no_wrap")
        self._wrap_no_wrap_action.setChecked(wrap_mode == "no_wrap")
        self._wrap_limit_action.setChecked(wrap_mode == "limit_width")
        self.editor_tabs.apply_auto_minimap_all()
        self.timer_manager.update_auto_save_interval(self.config.get_editor_setting("auto_save_interval", 30))
        if self.config.get_secretary_setting("show_secretary", True):
            self.secretary.show()
            self.secretary.set_size_percent(self.config.get_secretary_setting("size_percent", 7))
        else:
            self.secretary.hide()

    def _reset_settings(self):
        """恢复默认设置"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("确认")
        msg_box.setText("确定要恢复所有设置为默认值吗？")
        msg_box.setIcon(QMessageBox.Icon.Question)

        yes_btn = msg_box.addButton("确定", QMessageBox.ButtonRole.AcceptRole)
        no_btn = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)

        msg_box.exec()

        if msg_box.clickedButton() == yes_btn:
            self.config.reset_to_defaults()
            self._apply_editor_settings()
            self.secretary.show_message("设置已恢复为默认值")

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
        if self.editor_tabs.has_modified_files():
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
        for tw in [self.editor_tabs] + self._split_tabs:
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
            self.outline_panel.show()
        else:
            self.outline_panel.set_editor(None)
            self.outline_panel.hide()

    def _on_outline_heading_clicked(self, line_num: int):
        """大纲面板点击标题 → 跳转到对应行"""
        editor = self.editor_tabs.current_editor()
        if editor is not None and editor.get_file_type() == "Markdown":
            editor.goto_line(line_num)

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
        colors = self.theme_engine.get_active_theme().colors
        self._game_placeholder.setStyleSheet(f"color: {colors.text_disabled}; font-size: 18px;")

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
        dialog = PluginManagerDialog(self.plugin_manager, self.secretary, parent=self)
        dialog.exec()
