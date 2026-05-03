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
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QMenuBar, QMenu, QAction, QStatusBar,
    QLabel, QMessageBox, QFileDialog, QTabWidget,
    QToolButton, QFrame, QSizePolicy, QApplication, QDialog
)
from PyQt5.QtCore import Qt, QTimer, QEvent, pyqtSignal
from PyQt5.QtGui import QIcon, QCloseEvent

from .core.config import Config
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
from .editor.editor_settings_dialog import EditorSettingsDialog
from .utils.logger import get_logger
from .utils.lazy_loader import get_startup_profiler
from .utils.dpi_helper import scale, scale_size


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self._current_view = "editor"
        self._profiler = get_startup_profiler()

        self._profiler.begin_phase("游戏引擎初始化")
        self.game_engine = GameEngine(config)
        self._profiler.end_phase()

        self._profiler.begin_phase("定时器/事件总线初始化")
        self.timer_manager = TimerManager(config, self)
        self.event_bus = EventBus(config, self)
        self.shortcut_manager = ShortcutManager(config)
        self._profiler.end_phase()

        self._profiler.begin_phase("UI初始化")
        self._init_ui()
        self._profiler.end_phase()

        self._profiler.begin_phase("菜单栏初始化")
        self._init_menubar()
        self._profiler.end_phase()

        self._profiler.begin_phase("状态栏初始化")
        self._init_statusbar()
        self._profiler.end_phase()

        self._init_timers()

        self._profiler.begin_phase("状态恢复")
        self._restore_state()
        self._profiler.end_phase()

        self._connect_signals()

        icon_path = os.path.join(config.get_assets_path(), "icons", "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
    
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
        self.resource_bar = ResourceBar(self.config)
        main_layout.addWidget(self.resource_bar)
        
        # 分隔线
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(line1)
        
        # 内容区域
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # 游戏图标侧边栏
        self.game_sidebar = GameSidebar()
        self.game_sidebar.setFixedWidth(scale(50))
        self.game_sidebar.view_changed.connect(self._on_view_changed)
        content_layout.addWidget(self.game_sidebar)
        
        # 分隔线
        line2 = QFrame()
        line2.setFrameShape(QFrame.VLine)
        line2.setFrameShadow(QFrame.Sunken)
        content_layout.addWidget(line2)
        
        # 分割器
        self.splitter = QSplitter(Qt.Horizontal)
        
        # 文件树
        self.file_tree = FileTreeWidget(self.config)
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
        self.find_replace_bar = FindReplaceBar()
        self.find_replace_bar.hide()
        editor_layout.addWidget(self.find_replace_bar)
        
        # 编辑器标签页
        self.editor_tabs = EditorTabWidget(self.config)
        self.editor_tabs.set_find_bar(self.find_replace_bar)
        self.editor_tabs.current_changed.connect(self._on_tab_changed)
        self.editor_tabs.content_modified.connect(self._on_content_modified)
        self.editor_tabs.tab_count_changed.connect(self._on_tab_count_changed)
        editor_layout.addWidget(self.editor_tabs)
        
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
        main_layout.addWidget(self.game_view_container)
        
        # 小秘书（覆盖在编辑区右下角，自动跟随父容器大小变化）
        self.secretary = SecretaryWidget(self.config, self.editor_container)

        # 快捷键提示面板
        from .ui.shortcut_panel import ShortcutPanel
        self.shortcut_panel = ShortcutPanel(self.shortcut_manager, self)
        self.shortcut_panel.set_edit_callback(self._on_shortcut_edited)
        self.shortcut_panel.hide()
    
    def _init_menubar(self):
        """初始化菜单栏"""
        builder = MenuBuilder(self.config)
        builder.build(self.menuBar(), self)
    
    def _init_statusbar(self):
        """初始化状态栏"""
        self.status_bar_widget = StatusBarWidget()
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

        open_files = self.config.get_open_files()
        if open_files:
            first_file = open_files[0]
            filepath = first_file.get("path")
            if filepath and os.path.exists(filepath):
                self._open_file(filepath)
                remaining = open_files[1:]
            else:
                remaining = open_files[1:]
                if self.editor_tabs.count() == 0:
                    self.editor_tabs.new_file()
        else:
            remaining = []
            self.editor_tabs.new_file()

        if remaining:
            from PyQt5.QtCore import QTimer
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
        if filepath and os.path.exists(filepath):
            self._open_file(filepath)

        if self._pending_files:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, self._open_next_pending_file)
    
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
        
        self.config.save()
    
    def _save_to_temp(self):
        """保存到暂存文件"""
        self.editor_tabs.save_all_to_temp()
    
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
    
    # === 事件处理 ===
    
    def changeEvent(self, event: QEvent):
        """窗口状态变化事件"""
        if event.type() == QEvent.WindowStateChange:
            if self.isMinimized():
                self._save_to_temp()
        super().changeEvent(event)
    
    def closeEvent(self, event: QCloseEvent):
        """关闭窗口事件"""
        self._save_to_temp()
        
        unsaved_files = self.editor_tabs.get_unsaved_files()
        
        if unsaved_files:
            file_list = "\n".join([f"• {f}" for f in unsaved_files[:5]])
            if len(unsaved_files) > 5:
                file_list += f"\n...等{len(unsaved_files)}个文件"
            
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("确认退出")
            msg_box.setText(f"有{len(unsaved_files)}个文件未保存：\n\n{file_list}\n\n是否保存并退出？")
            msg_box.setIcon(QMessageBox.Question)
            
            save_btn = msg_box.addButton("保存", QMessageBox.AcceptRole)
            discard_btn = msg_box.addButton("不保存", QMessageBox.DestructiveRole)
            cancel_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
            
            msg_box.exec_()
            
            clicked = msg_box.clickedButton()
            if clicked == save_btn:
                self.editor_tabs.save_all()
            elif clicked == cancel_btn:
                event.ignore()
                return
        
        self._save_state()
        self.editor_tabs.clear_temp_files()
        
        event.accept()
    
    def keyPressEvent(self, event):
        """键盘事件"""
        if event.key() == Qt.Key_Escape and self._current_view != "editor":
            self._switch_view("editor")
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
        """打开文件"""
        notebooks_path = os.path.normpath(self.config.get_notebooks_path())
        filepath_norm = os.path.normpath(filepath)
        
        if not filepath_norm.startswith(notebooks_path):
            self.config.add_external_file(filepath)
            self.file_tree.refresh_external_files()
        
        self.editor_tabs.open_file(filepath)
        self.config.add_recent_file(filepath)
        self._update_recent_menu()
    
    def _save_current(self):
        """保存当前文件"""
        saved, char_count = self.editor_tabs.save_current()
        if saved and char_count > 0:
            self._on_file_saved(char_count)
    
    def _save_as(self):
        """另存为"""
        self.editor_tabs.save_current_as()
    
    def _save_all(self):
        """保存所有文件"""
        total_chars = self.editor_tabs.save_all()
        if total_chars > 0:
            self._on_file_saved(total_chars)
    
    def _close_current_tab(self):
        """关闭当前标签"""
        self.editor_tabs.close_current_tab()
    
    def _close_all_tabs(self):
        """关闭所有标签"""
        self.editor_tabs.close_all_tabs()
    
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

    # === 视图操作 ===
    
    def _on_view_changed(self, view: str):
        """游戏侧边栏视图切换"""
        self.event_bus.handle_view_changed(self, view)
    
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
        pass
    
    def _import_document(self):
        """导入外部文档"""
        pass
    
    def _show_typing_stats(self):
        """显示打字统计"""
        pass
    
    def _show_construction_stats(self):
        """显示建造记录"""
        pass
    
    def _show_collection_stats(self):
        """显示图鉴完成度"""
        pass
    
    def _on_file_saved(self, char_count: int):
        """文件保存后的处理"""
        self.event_bus.handle_file_saved(self, char_count)

    def _on_tab_count_changed(self, count: int):
        """标签页数量变化"""
        self.event_bus.handle_tab_count_changed(self, count)

    def _on_file_move_from_tree(self, src_filepath: str, dest_folder: str):
        """文件树请求移动文件（标签拖拽到文件夹）"""
        self.event_bus.handle_file_move(self, src_filepath, dest_folder)
    
    # === 设置 ===
    
    def _show_editor_settings(self):
        """显示记事本设置"""
        dialog = EditorSettingsDialog(self.config, self)
        if dialog.exec_() == QDialog.Accepted:
            settings = dialog.get_settings()
            
            # 保存编辑器设置
            editor_keys = {
                "show_line_numbers", "highlight_current_line", "show_minimap",
                "auto_minimap", "font_family", "font_size", "wrap_mode",
                "auto_save_interval", "auto_pair_brackets"
            }
            for key in editor_keys:
                self.config.set_editor_setting(key, settings[key])
            
            # 保存小秘书设置
            self.config.set_secretary_setting("show_secretary", settings["show_secretary"])
            self.config.set_secretary_setting("size_percent", settings["secretary_size_percent"])
            
            self.config.save_settings()
            
            # 应用设置
            # 显示行号
            self.editor_tabs.set_line_numbers_all(settings["show_line_numbers"])
            
            # 高亮当前行
            self.editor_tabs.set_highlight_current_line_all(settings["highlight_current_line"])
            
            # 字体和字体大小
            self.editor_tabs.set_font_all(settings["font_family"], settings["font_size"])
            
            # 行宽模式
            self.editor_tabs.set_wrap_mode_all(settings["wrap_mode"])
            self._wrap_no_wrap_action.setChecked(settings["wrap_mode"] == "no_wrap")
            self._wrap_limit_action.setChecked(settings["wrap_mode"] == "limit_width")
            
            # 自动缩略图
            self.editor_tabs.apply_auto_minimap_all()
            
            # 自动保存间隔
            self.timer_manager.update_auto_save_interval(settings["auto_save_interval"])
            
            # 小秘书设置
            if settings["show_secretary"]:
                self.secretary.show()
                self.secretary.set_size_percent(settings["secretary_size_percent"])
            else:
                self.secretary.hide()
            
            self.secretary.show_message("设置已保存并应用")
    
    def _show_game_settings(self):
        """显示游戏设置"""
        pass
    
    def _save_settings(self):
        """保存设置"""
        self.config.save_settings()
        self.secretary.show_message("设置已保存")
    
    def _reset_settings(self):
        """恢复默认设置"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("确认")
        msg_box.setText("确定要恢复所有设置为默认值吗？")
        msg_box.setIcon(QMessageBox.Question)
        
        yes_btn = msg_box.addButton("确定", QMessageBox.AcceptRole)
        no_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
        
        msg_box.exec_()
        
        if msg_box.clickedButton() == yes_btn:
            pass
    
    # === 帮助 ===
    
    def _show_guide(self):
        """显示新手攻略"""
        pass
    
    def _show_manual(self):
        """显示使用说明"""
        pass
    
    def _show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "关于 PanzerNote",
            "PanzerNote v1.5.5\n\n"
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
        """更新统计信息"""
        editor = self.editor_tabs.current_editor()
        if editor:
            char_count = editor.get_char_count()
            line = editor.get_current_line()
            col = editor.get_current_column()
            file_type = editor.get_file_type()
            encoding = self.editor_tabs.get_current_encoding()
            
            self.status_bar_widget.update_stats(char_count, line, col, encoding, file_type)
        
        today_chars = self.config.get_today_chars_typed()
        total_docs = self.config.get_total_documents()
        self.resource_bar.update_typing_stats(today_chars, total_docs)
    
    def _on_tab_changed(self, index: int):
        """标签页切换"""
        self._update_stats()
    
    def _on_content_modified(self):
        """内容修改"""
        self._update_stats()
