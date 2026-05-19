# -*- coding: utf-8 -*-
"""
菜单构建器模块
将主窗口菜单栏的构建逻辑从 MainWindow 中抽离
"""

from typing import Any, Callable, Optional, Union

from PyQt6.QtGui import QKeySequence, QAction
from PyQt6.QtWidgets import QMenu, QMenuBar, QMessageBox

from ..core.config import Config
from ..core.shortcut_manager import ShortcutManager


class MenuBuilder:
    """菜单栏构建器"""

    def __init__(self, config: Config, shortcut_manager: Optional[ShortcutManager] = None) -> None:
        self._config = config
        self._shortcut_manager = shortcut_manager

    def build(self, menubar: QMenuBar, main_window: Any) -> None:
        """构建完整菜单栏

        Args:
            menubar: QMainWindow 的 menuBar()
            main_window: MainWindow 实例，用于绑定回调
        """
        self._build_file_menu(menubar, main_window)
        self._build_edit_menu(menubar, main_window)
        self._build_game_menu(menubar, main_window)
        self._build_view_menu(menubar, main_window)
        self._build_settings_menu(menubar, main_window)
        self._build_help_menu(menubar, main_window)

    def _build_file_menu(self, menubar: QMenuBar, mw: Any) -> None:
        menu = menubar.addMenu("文件")
        if menu is None:
            return

        self._add_action(menu, "新建文件", QKeySequence.StandardKey.New, mw._new_file, "file.new", "文件")
        self._add_action(menu, "新建文件夹", None, mw._new_folder, "file.new_folder", "文件")
        self._add_action(menu, "打开文件", QKeySequence.StandardKey.Open, mw._open_file_dialog, "file.open", "文件")
        menu.addSeparator()
        self._add_action(menu, "保存", QKeySequence.StandardKey.Save, mw._save_current, "file.save", "文件")
        self._add_action(menu, "另存为", QKeySequence("Ctrl+Shift+S"), mw._save_as, "file.save_as", "文件")
        self._add_action(menu, "全部保存", None, mw._save_all)
        menu.addSeparator()
        export_menu = menu.addMenu("导出")
        if export_menu is not None:
            self._add_action(export_menu, "导出为PDF", None, mw._export_pdf, "file.export_pdf", "文件")
            self._add_action(export_menu, "导出为HTML", None, mw._export_html, "file.export_html", "文件")
        menu.addSeparator()
        self._add_action(menu, "关闭当前标签", QKeySequence("Ctrl+W"), mw._close_current_tab, "file.close_tab", "文件")
        self._add_action(menu, "关闭所有标签", None, mw._close_all_tabs)
        self._add_action(menu, "重新打开关闭的标签", QKeySequence("Ctrl+Shift+T"), mw._reopen_closed_tab, "file.reopen_closed", "文件")
        menu.addSeparator()
        self._add_action(menu, "释放占用内存", None, mw._release_memory)
        menu.addSeparator()

        mw.recent_menu = menu.addMenu("最近打开")
        mw._update_recent_menu()

        menu.addSeparator()
        self._add_action(menu, "退出", QKeySequence("Alt+F4"), mw.close, "file.exit", "文件")

    def _build_edit_menu(self, menubar: QMenuBar, mw: Any) -> None:
        menu = menubar.addMenu("编辑")
        if menu is None:
            return

        self._add_action(menu, "撤销", QKeySequence.StandardKey.Undo, mw._undo, "edit.undo", "编辑")
        self._add_action(menu, "重做", QKeySequence.StandardKey.Redo, mw._redo, "edit.redo", "编辑")
        menu.addSeparator()
        self._add_action(menu, "剪切", QKeySequence.StandardKey.Cut, mw._cut, "edit.cut", "编辑")
        self._add_action(menu, "复制", QKeySequence.StandardKey.Copy, mw._copy, "edit.copy", "编辑")
        self._add_action(menu, "粘贴", QKeySequence.StandardKey.Paste, mw._paste, "edit.paste", "编辑")
        self._add_action(menu, "全选", QKeySequence.StandardKey.SelectAll, mw._select_all, "edit.select_all", "编辑")
        menu.addSeparator()
        self._add_action(menu, "查找", QKeySequence.StandardKey.Find, mw._find, "edit.find", "编辑")
        self._add_action(menu, "替换", QKeySequence("Ctrl+H"), mw._replace, "edit.replace", "编辑")
        menu.addSeparator()

        line_menu = menu.addMenu("行操作")
        if line_menu is not None:
            self._add_action(line_menu, "删除当前行", QKeySequence("Ctrl+Shift+K"), mw._delete_current_line, "edit.delete_line", "编辑")
            self._add_action(line_menu, "上移当前行", QKeySequence("Alt+Up"), mw._move_line_up, "edit.move_line_up", "编辑")
            self._add_action(line_menu, "下移当前行", QKeySequence("Alt+Down"), mw._move_line_down, "edit.move_line_down", "编辑")
            self._add_action(line_menu, "复制当前行", QKeySequence("Ctrl+Shift+D"), mw._duplicate_line, "edit.duplicate_line", "编辑")

        self._add_action(menu, "转到行...", QKeySequence("Ctrl+G"), mw._goto_line, "edit.goto_line", "编辑")
        menu.addSeparator()
        self._add_action(menu, "添加/移除书签", QKeySequence("Ctrl+F2"), mw._toggle_bookmark, "edit.toggle_bookmark", "编辑")
        self._add_action(menu, "下一个书签", QKeySequence("F2"), mw._next_bookmark, "edit.next_bookmark", "编辑")
        self._add_action(menu, "上一个书签", QKeySequence("Shift+F2"), mw._prev_bookmark, "edit.prev_bookmark", "编辑")
        menu.addSeparator()

        case_menu = menu.addMenu("大小写转换")
        if case_menu is not None:
            self._add_action(case_menu, "转为大写", None, mw._to_uppercase)
            self._add_action(case_menu, "转为小写", None, mw._to_lowercase)
            self._add_action(case_menu, "首字母大写", None, mw._to_titlecase)
            self._add_action(case_menu, "切换大小写", QKeySequence("Ctrl+Shift+U"), mw._toggle_case, "edit.toggle_case", "编辑")

    def _build_game_menu(self, menubar: QMenuBar, mw: Any) -> None:
        menu = menubar.addMenu("游戏")
        if menu is None:
            return

        self._add_action(menu, "导入角色数据...", None, mw._import_characters)
        self._add_action(menu, "导入外部文档...", None, mw._import_document)
        menu.addSeparator()

        stats_menu = menu.addMenu("数据统计")
        if stats_menu is not None:
            self._add_action(stats_menu, "打字统计", None, mw._show_typing_stats)
            self._add_action(stats_menu, "建造记录", None, mw._show_construction_stats)
            self._add_action(stats_menu, "图鉴完成度", None, mw._show_collection_stats)

    def _build_view_menu(self, menubar: QMenuBar, mw: Any) -> None:
        menu = menubar.addMenu("视图")
        if menu is None:
            return

        self._add_action(menu, "切换到记事本", QKeySequence("Ctrl+1"),
                         lambda: mw._switch_view("editor"), "view.editor", "视图")
        self._add_action(menu, "切换到建造", QKeySequence("Ctrl+2"),
                         lambda: mw._switch_view("construction"), "view.construction", "视图")
        self._add_action(menu, "切换到车库", QKeySequence("Ctrl+3"),
                         lambda: mw._switch_view("garage"), "view.garage", "视图")
        self._add_action(menu, "切换到图鉴", QKeySequence("Ctrl+4"),
                         lambda: mw._switch_view("collection"), "view.collection", "视图")
        menu.addSeparator()

        wrap_menu = menu.addMenu("行宽模式")
        if wrap_menu is not None:
            mw._wrap_no_wrap_action = self._add_check_action(
                wrap_menu, "不换行", lambda: mw._set_wrap_mode("no_wrap"))
            mw._wrap_limit_action = self._add_check_action(
                wrap_menu, "限制行宽", lambda: mw._set_wrap_mode("limit_width"))

            current_mode = self._config.get_editor_setting("wrap_mode", "no_wrap")
            mw._wrap_no_wrap_action.setChecked(current_mode == "no_wrap")
            mw._wrap_limit_action.setChecked(current_mode == "limit_width")

        self._add_action(menu, "切换Markdown预览", QKeySequence("Ctrl+Shift+P"), mw._toggle_md_preview, "view.md_preview", "视图")
        self._add_action(menu, "显示/隐藏代码缩略图", QKeySequence("Ctrl+M"), mw._toggle_minimap, "view.minimap", "视图")
        menu.addSeparator()
        self._add_action(menu, "水平分屏（独立编辑）", None, mw._split_editor_horizontal, "view.split_horizontal", "视图")
        self._add_action(menu, "垂直分屏（独立编辑）", None, mw._split_editor_vertical, "view.split_vertical", "视图")
        self._add_action(menu, "关闭分屏", None, mw._close_split, "view.close_split", "视图")
        menu.addSeparator()
        self._add_action(menu, "折叠/展开文件树", QKeySequence("Ctrl+B"), mw._toggle_file_tree, "view.file_tree", "视图")
        self._add_action(menu, "显示/隐藏小秘书", None, mw._toggle_secretary)
        menu.addSeparator()
        self._add_action(menu, "全屏模式", QKeySequence("F11"), mw._toggle_fullscreen, "view.fullscreen", "视图")
        menu.addSeparator()

        zoom_menu = menu.addMenu("缩放")
        if zoom_menu is not None:
            self._add_action(zoom_menu, "放大", QKeySequence("Ctrl++"), mw._zoom_in, "view.zoom_in", "视图")
            self._add_action(zoom_menu, "缩小", QKeySequence("Ctrl+-"), mw._zoom_out, "view.zoom_out", "视图")
            self._add_action(zoom_menu, "重置", QKeySequence("Ctrl+0"), mw._zoom_reset, "view.zoom_reset", "视图")

    def _build_settings_menu(self, menubar: QMenuBar, mw: Any) -> None:
        menu = menubar.addMenu("设置")
        if menu is None:
            return

        self._add_action(menu, "记事本设置", None, mw._show_editor_settings)
        self._add_action(menu, "游戏设置", None, mw._show_game_settings)
        menu.addSeparator()
        self._add_action(menu, "主题管理", None, mw._show_theme_dialog)
        self._add_action(menu, "插件管理", None, mw._show_plugin_manager)
        menu.addSeparator()
        self._add_action(menu, "保存设置", None, mw._save_settings)
        self._add_action(menu, "恢复默认", None, mw._reset_settings)
        menu.addSeparator()
        self._add_action(menu, "导出设置", None, mw._export_settings, "settings.export", "设置")
        self._add_action(menu, "导入设置", None, mw._import_settings, "settings.import", "设置")

    def _build_help_menu(self, menubar: QMenuBar, mw: Any) -> None:
        menu = menubar.addMenu("帮助")
        if menu is None:
            return

        self._add_action(menu, "快捷键列表", QKeySequence("Ctrl+/"),
                         mw._toggle_shortcut_panel, "shortcut_panel", "帮助")
        menu.addSeparator()
        self._add_action(menu, "新手攻略", None, mw._show_guide)
        self._add_action(menu, "使用说明", None, mw._show_manual)
        menu.addSeparator()
        self._add_action(menu, "关于", None, mw._show_about)

    def _add_action(
        self,
        menu: QMenu,
        text: str,
        shortcut: Optional[Union[QKeySequence, int]],
        callback: Callable,
        action_id: Optional[str] = None,
        category: str = "通用",
    ) -> QAction:
        if self._shortcut_manager and action_id:
            default_key = ""
            if shortcut:
                ks = QKeySequence(shortcut)
                default_key = ks.toString() if not ks.isEmpty() else ""
            action = self._shortcut_manager.register(
                action_id, text, default_key, callback, category
            )
            if action is None:
                action = QAction(text, menu)
                if shortcut:
                    action.setShortcut(shortcut)
                action.triggered.connect(callback)
        else:
            action = QAction(text, menu)
            if shortcut:
                action.setShortcut(shortcut)
            action.triggered.connect(callback)
        menu.addAction(action)
        return action

    @staticmethod
    def _add_check_action(
        menu: QMenu,
        text: str,
        callback: Callable,
    ) -> QAction:
        action = QAction(text, menu)
        action.setCheckable(True)
        action.triggered.connect(callback)
        menu.addAction(action)
        return action
