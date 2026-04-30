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
import math
from datetime import datetime
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QMenuBar, QMenu, QAction, QStatusBar,
    QLabel, QMessageBox, QFileDialog, QTabWidget,
    QToolButton, QFrame, QSizePolicy, QApplication, QDialog
)
from PyQt5.QtCore import Qt, QTimer, QEvent, pyqtSignal
from PyQt5.QtGui import QIcon, QKeySequence, QCloseEvent

from .core.config import Config
from .game.resource_bar import ResourceBar
from .game.game_sidebar import GameSidebar
from .editor.file_tree import FileTreeWidget
from .editor.editor_tabs import EditorTabWidget
from .game.secretary_widget import SecretaryWidget
from .editor.status_bar import StatusBarWidget
from .editor.find_replace import FindReplaceBar
from .editor.editor_settings_dialog import EditorSettingsDialog


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self._current_view = "editor"
        
        self._init_ui()
        self._init_menubar()
        self._init_statusbar()
        self._init_timers()
        self._restore_state()
        self._connect_signals()
        
        # 设置窗口图标
        icon_path = os.path.join(config.get_assets_path(), "icons", "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
    
    def _init_ui(self):
        """初始化UI"""
        self.setWindowTitle("PanzerNote")
        self.setMinimumSize(800, 600)
        
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
        self.game_sidebar.setFixedWidth(50)
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
        self.file_tree.setMinimumWidth(100)
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
    
    def _init_menubar(self):
        """初始化菜单栏"""
        menubar = self.menuBar()
        
        # === 文件菜单 ===
        file_menu = menubar.addMenu("文件")
        
        new_file_action = QAction("新建文件", self)
        new_file_action.setShortcut(QKeySequence.New)
        new_file_action.triggered.connect(self._new_file)
        file_menu.addAction(new_file_action)
        
        new_folder_action = QAction("新建文件夹", self)
        new_folder_action.triggered.connect(self._new_folder)
        file_menu.addAction(new_folder_action)
        
        open_action = QAction("打开文件", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._open_file_dialog)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        save_action = QAction("保存", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self._save_current)
        file_menu.addAction(save_action)
        
        save_as_action = QAction("另存为", self)
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(self._save_as)
        file_menu.addAction(save_as_action)
        
        save_all_action = QAction("全部保存", self)
        save_all_action.triggered.connect(self._save_all)
        file_menu.addAction(save_all_action)
        
        file_menu.addSeparator()
        
        close_tab_action = QAction("关闭当前标签", self)
        close_tab_action.setShortcut(QKeySequence("Ctrl+W"))
        close_tab_action.triggered.connect(self._close_current_tab)
        file_menu.addAction(close_tab_action)
        
        close_all_action = QAction("关闭所有标签", self)
        close_all_action.triggered.connect(self._close_all_tabs)
        file_menu.addAction(close_all_action)
        
        file_menu.addSeparator()
        
        release_memory_action = QAction("释放占用内存", self)
        release_memory_action.triggered.connect(self._release_memory)
        file_menu.addAction(release_memory_action)
        
        file_menu.addSeparator()
        
        self.recent_menu = file_menu.addMenu("最近打开")
        self._update_recent_menu()
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出", self)
        exit_action.setShortcut(QKeySequence("Alt+F4"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # === 编辑菜单 ===
        edit_menu = menubar.addMenu("编辑")
        
        undo_action = QAction("撤销", self)
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.triggered.connect(self._undo)
        edit_menu.addAction(undo_action)
        
        redo_action = QAction("重做", self)
        redo_action.setShortcut(QKeySequence.Redo)
        redo_action.triggered.connect(self._redo)
        edit_menu.addAction(redo_action)
        
        edit_menu.addSeparator()
        
        cut_action = QAction("剪切", self)
        cut_action.setShortcut(QKeySequence.Cut)
        cut_action.triggered.connect(self._cut)
        edit_menu.addAction(cut_action)
        
        copy_action = QAction("复制", self)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.triggered.connect(self._copy)
        edit_menu.addAction(copy_action)
        
        paste_action = QAction("粘贴", self)
        paste_action.setShortcut(QKeySequence.Paste)
        paste_action.triggered.connect(self._paste)
        edit_menu.addAction(paste_action)
        
        select_all_action = QAction("全选", self)
        select_all_action.setShortcut(QKeySequence.SelectAll)
        select_all_action.triggered.connect(self._select_all)
        edit_menu.addAction(select_all_action)
        
        edit_menu.addSeparator()
        
        find_action = QAction("查找", self)
        find_action.setShortcut(QKeySequence.Find)
        find_action.triggered.connect(self._find)
        edit_menu.addAction(find_action)
        
        replace_action = QAction("替换", self)
        replace_action.setShortcut(QKeySequence("Ctrl+H"))
        replace_action.triggered.connect(self._replace)
        edit_menu.addAction(replace_action)


        edit_menu.addSeparator()

        # 行操作子菜单
        line_menu = edit_menu.addMenu("行操作")

        delete_line_action = QAction("删除当前行", self)
        delete_line_action.setShortcut(QKeySequence("Ctrl+Shift+K"))
        delete_line_action.triggered.connect(self._delete_current_line)
        line_menu.addAction(delete_line_action)

        move_up_action = QAction("上移当前行", self)
        move_up_action.setShortcut(QKeySequence("Alt+Up"))
        move_up_action.triggered.connect(self._move_line_up)
        line_menu.addAction(move_up_action)

        move_down_action = QAction("下移当前行", self)
        move_down_action.setShortcut(QKeySequence("Alt+Down"))
        move_down_action.triggered.connect(self._move_line_down)
        line_menu.addAction(move_down_action)

        duplicate_line_action = QAction("复制当前行", self)
        duplicate_line_action.setShortcut(QKeySequence("Ctrl+Shift+D"))
        duplicate_line_action.triggered.connect(self._duplicate_line)
        line_menu.addAction(duplicate_line_action)

        # 转到行
        goto_line_action = QAction("转到行...", self)
        goto_line_action.setShortcut(QKeySequence("Ctrl+G"))
        goto_line_action.triggered.connect(self._goto_line)
        edit_menu.addAction(goto_line_action)

        edit_menu.addSeparator()

        # 大小写子菜单
        case_menu = edit_menu.addMenu("大小写转换")

        to_upper_action = QAction("转为大写", self)
        to_upper_action.triggered.connect(self._to_uppercase)
        case_menu.addAction(to_upper_action)

        to_lower_action = QAction("转为小写", self)
        to_lower_action.triggered.connect(self._to_lowercase)
        case_menu.addAction(to_lower_action)

        to_title_action = QAction("首字母大写", self)
        to_title_action.triggered.connect(self._to_titlecase)
        case_menu.addAction(to_title_action)

        toggle_case_action = QAction("切换大小写", self)
        toggle_case_action.setShortcut(QKeySequence("Ctrl+Shift+U"))
        toggle_case_action.triggered.connect(self._toggle_case)
        case_menu.addAction(toggle_case_action)


        # === 游戏菜单 ===
        game_menu = menubar.addMenu("游戏")
        
        import_chars_action = QAction("导入角色数据...", self)
        import_chars_action.triggered.connect(self._import_characters)
        game_menu.addAction(import_chars_action)
        
        import_doc_action = QAction("导入外部文档...", self)
        import_doc_action.triggered.connect(self._import_document)
        game_menu.addAction(import_doc_action)
        
        game_menu.addSeparator()
        
        stats_menu = game_menu.addMenu("数据统计")
        
        typing_stats_action = QAction("打字统计", self)
        typing_stats_action.triggered.connect(self._show_typing_stats)
        stats_menu.addAction(typing_stats_action)
        
        construction_stats_action = QAction("建造记录", self)
        construction_stats_action.triggered.connect(self._show_construction_stats)
        stats_menu.addAction(construction_stats_action)
        
        collection_stats_action = QAction("图鉴完成度", self)
        collection_stats_action.triggered.connect(self._show_collection_stats)
        stats_menu.addAction(collection_stats_action)
        
        # === 视图菜单 ===
        view_menu = menubar.addMenu("视图")
        
        view_editor_action = QAction("切换到记事本", self)
        view_editor_action.setShortcut(QKeySequence("Ctrl+1"))
        view_editor_action.triggered.connect(lambda: self._switch_view("editor"))
        view_menu.addAction(view_editor_action)
        
        view_construction_action = QAction("切换到建造", self)
        view_construction_action.setShortcut(QKeySequence("Ctrl+2"))
        view_construction_action.triggered.connect(lambda: self._switch_view("construction"))
        view_menu.addAction(view_construction_action)
        
        view_garage_action = QAction("切换到车库", self)
        view_garage_action.setShortcut(QKeySequence("Ctrl+3"))
        view_garage_action.triggered.connect(lambda: self._switch_view("garage"))
        view_menu.addAction(view_garage_action)
        
        view_collection_action = QAction("切换到图鉴", self)
        view_collection_action.setShortcut(QKeySequence("Ctrl+4"))
        view_collection_action.triggered.connect(lambda: self._switch_view("collection"))
        view_menu.addAction(view_collection_action)
        
        view_menu.addSeparator()
        
        # 行宽模式子菜单
        wrap_menu = view_menu.addMenu("行宽模式")
        
        self._wrap_no_wrap_action = QAction("不换行", self)
        self._wrap_no_wrap_action.setCheckable(True)
        self._wrap_no_wrap_action.triggered.connect(lambda: self._set_wrap_mode("no_wrap"))
        wrap_menu.addAction(self._wrap_no_wrap_action)
        
        self._wrap_limit_action = QAction("限制行宽", self)
        self._wrap_limit_action.setCheckable(True)
        self._wrap_limit_action.triggered.connect(lambda: self._set_wrap_mode("limit_width"))
        wrap_menu.addAction(self._wrap_limit_action)
        
        # 初始化选中状态
        current_mode = self.config.get_editor_setting("wrap_mode", "no_wrap")
        self._wrap_no_wrap_action.setChecked(current_mode == "no_wrap")
        self._wrap_limit_action.setChecked(current_mode == "limit_width")
        
        # MD预览切换
        toggle_preview_action = QAction("切换Markdown预览", self)
        toggle_preview_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        toggle_preview_action.triggered.connect(self._toggle_md_preview)
        view_menu.addAction(toggle_preview_action)

        # 缩略图切换
        toggle_minimap_action = QAction("显示/隐藏代码缩略图", self)
        toggle_minimap_action.setShortcut(QKeySequence("Ctrl+M"))
        toggle_minimap_action.triggered.connect(self._toggle_minimap)
        view_menu.addAction(toggle_minimap_action)
        
        view_menu.addSeparator()
        
        toggle_tree_action = QAction("折叠/展开文件树", self)
        toggle_tree_action.setShortcut(QKeySequence("Ctrl+B"))
        toggle_tree_action.triggered.connect(self._toggle_file_tree)
        view_menu.addAction(toggle_tree_action)
        
        toggle_secretary_action = QAction("显示/隐藏小秘书", self)
        toggle_secretary_action.triggered.connect(self._toggle_secretary)
        view_menu.addAction(toggle_secretary_action)
        
        view_menu.addSeparator()
        
        fullscreen_action = QAction("全屏模式", self)
        fullscreen_action.setShortcut(QKeySequence("F11"))
        fullscreen_action.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(fullscreen_action)
        
        view_menu.addSeparator()
        
        zoom_menu = view_menu.addMenu("缩放")
        
        zoom_in_action = QAction("放大", self)
        zoom_in_action.setShortcut(QKeySequence("Ctrl++"))
        zoom_in_action.triggered.connect(self._zoom_in)
        zoom_menu.addAction(zoom_in_action)
        
        zoom_out_action = QAction("缩小", self)
        zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        zoom_out_action.triggered.connect(self._zoom_out)
        zoom_menu.addAction(zoom_out_action)
        
        zoom_reset_action = QAction("重置", self)
        zoom_reset_action.setShortcut(QKeySequence("Ctrl+0"))
        zoom_reset_action.triggered.connect(self._zoom_reset)
        zoom_menu.addAction(zoom_reset_action)
        
        # === 设置菜单 ===
        settings_menu = menubar.addMenu("设置")
        
        editor_settings_action = QAction("记事本设置", self)
        editor_settings_action.triggered.connect(self._show_editor_settings)
        settings_menu.addAction(editor_settings_action)
        
        game_settings_action = QAction("游戏设置", self)
        game_settings_action.triggered.connect(self._show_game_settings)
        settings_menu.addAction(game_settings_action)
        
        settings_menu.addSeparator()
        
        save_settings_action = QAction("保存设置", self)
        save_settings_action.triggered.connect(self._save_settings)
        settings_menu.addAction(save_settings_action)
        
        reset_settings_action = QAction("恢复默认", self)
        reset_settings_action.triggered.connect(self._reset_settings)
        settings_menu.addAction(reset_settings_action)
        
        # === 帮助菜单 ===
        help_menu = menubar.addMenu("帮助")
        
        guide_action = QAction("新手攻略", self)
        guide_action.triggered.connect(self._show_guide)
        help_menu.addAction(guide_action)
        
        manual_action = QAction("使用说明", self)
        manual_action.triggered.connect(self._show_manual)
        help_menu.addAction(manual_action)
        
        help_menu.addSeparator()
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _init_statusbar(self):
        """初始化状态栏"""
        self.status_bar_widget = StatusBarWidget()
        self.setStatusBar(self.status_bar_widget)
    
    def _init_timers(self):
        """初始化定时器"""
        self.auto_save_timer = QTimer(self)
        interval = self.config.get_editor_setting("auto_save_interval", 30) * 1000
        self.auto_save_timer.setInterval(interval)
        self.auto_save_timer.timeout.connect(self._auto_save)
        self.auto_save_timer.start()
        
        self.stats_timer = QTimer(self)
        self.stats_timer.setInterval(500)
        self.stats_timer.timeout.connect(self._update_stats)
        self.stats_timer.start()
        
        # 在线挂机奖励定时器（每分钟触发）
        self.idle_reward_timer = QTimer(self)
        self.idle_reward_timer.setInterval(60000)  # 60秒
        self.idle_reward_timer.timeout.connect(self._on_idle_reward)
        self.idle_reward_timer.start()
    
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
        for file_info in open_files:
            filepath = file_info.get("path")
            if filepath and os.path.exists(filepath):
                self._open_file(filepath)
        
        if self.editor_tabs.count() == 0:
            self.editor_tabs.new_file()
        
        active_index = self.config.get_active_tab_index()
        if active_index < self.editor_tabs.count():
            self.editor_tabs.setCurrentIndex(active_index)
        
        current_view = self.config.get_current_view()
        if current_view != "editor":
            self._switch_view(current_view)
        
        self.file_tree.refresh_external_files()
        
        self.config.update_last_login()
        self.config.save_savegame()
    
    def _connect_signals(self):
        """连接信号"""
        pass
    
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
        """在线挂机奖励（每分钟触发）
        
        资源平衡：
        - 燃料、弹药、钢材：每分钟 +5
        - 铝材：每3分钟 +5（使用计数器）
        """
        rate = self.config.get_game_setting("idle_reward_rate", 1.0)
        
        # 前三项每分钟固定+5
        fuel = int(5 * rate)
        ammo = int(5 * rate)
        steel = int(5 * rate)
        
        # 铝材：每3分钟+5（使用计数器）
        bauxite_counter = self.config.get_game_setting("bauxite_counter", 0)
        bauxite_counter += 1
        
        if bauxite_counter >= 3:
            bauxite = int(5 * rate)
            self.config.set_game_setting("bauxite_counter", 0)
        else:
            bauxite = 0
            self.config.set_game_setting("bauxite_counter", bauxite_counter)
        
        # 添加资源
        self.config.add_resource("fuel", fuel)
        self.config.add_resource("ammo", ammo)
        self.config.add_resource("steel", steel)
        if bauxite > 0:
            self.config.add_resource("bauxite", bauxite)
        
        # 刷新资源显示
        self.resource_bar.refresh()
    
    def _calculate_offline_rewards(self):
        """计算离线挂机收益
        
        离线收益 = 在线的1/3，全部向大取整
        - 燃料、弹药、钢材：ceil(分钟数 × 5/3)
        - 铝材：ceil(分钟数 × 5/9)
        """
        last_login = self.config.get_last_login()
        
        if not last_login:
            return
        
        try:
            last_time = datetime.fromisoformat(last_login)
            now = datetime.now()
            
            # 计算离线时间（分钟）
            offline_seconds = (now - last_time).total_seconds()
            offline_minutes = offline_seconds / 60
            
            # 最少5分钟才计算离线收益
            if offline_minutes < 5:
                return
            
            # 离线最多计算24小时（1440分钟）
            offline_minutes = min(offline_minutes, 1440)
            
            rate = self.config.get_game_setting("idle_reward_rate", 1.0)
            
            # 离线收益 = 在线的1/3，向大取整
            # 在线：燃料/弹药/钢材 = 5/分钟，铝材 = 5/3分钟
            # 离线：燃料/弹药/钢材 = 5/3/分钟，铝材 = 5/9/分钟
            fuel = math.ceil(offline_minutes * 5 / 3 * rate)
            ammo = math.ceil(offline_minutes * 5 / 3 * rate)
            steel = math.ceil(offline_minutes * 5 / 3 * rate)
            bauxite = math.ceil(offline_minutes * 5 / 9 * rate)
            
            # 添加资源
            self.config.add_resource("fuel", fuel)
            self.config.add_resource("ammo", ammo)
            self.config.add_resource("steel", steel)
            self.config.add_resource("bauxite", bauxite)
            
            # 显示提示
            hours = int(offline_minutes // 60)
            mins = int(offline_minutes % 60)
            
            if hours > 0:
                time_str = f"{hours}小时{mins}分钟"
            else:
                time_str = f"{mins}分钟"
            
            # 延迟显示，等待UI初始化完成
            QTimer.singleShot(2000, lambda: self.secretary.show_message(
                f"离线{time_str}，获得资源！\n燃料+{fuel} 弹药+{ammo}\n钢材+{steel} 铝材+{bauxite}",
                5000
            ))
            
        except Exception as e:
            print(f"计算离线收益失败: {e}")
    
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
        self.resource_bar.refresh()
        self.secretary.show_message("文件已保存！")
    
    def _on_tab_count_changed(self, count: int):
        """标签页数量变化"""
        if count == 0:
            self.secretary.show_event_message("欢迎")

    def _on_file_move_from_tree(self, src_filepath: str, dest_folder: str):
        """文件树请求移动文件（标签拖拽到文件夹）"""
        success = self.editor_tabs.move_file_to_folder(src_filepath, dest_folder)
        if success:
            self.secretary.show_message(
                f"已将 {os.path.basename(src_filepath)} 移动到 {os.path.basename(dest_folder)}/"
            )
    
    # === 设置 ===
    
    def _show_editor_settings(self):
        """显示记事本设置"""
        dialog = EditorSettingsDialog(self.config, self)
        if dialog.exec_() == QDialog.Accepted:
            settings = dialog.get_settings()
            
            # 保存设置
            for key, value in settings.items():
                self.config.set_editor_setting(key, value)
            
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
            self.auto_save_timer.setInterval(settings["auto_save_interval"] * 1000)
            
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
