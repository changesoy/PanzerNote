# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

from PyQt5.QtWidgets import QMenuBar, QMenu

from src.core.menu_builder import MenuBuilder


def _make_config() -> MagicMock:
    config = MagicMock()
    config.get_editor_setting = MagicMock(return_value="no_wrap")
    return config


def _make_main_window() -> MagicMock:
    mw = MagicMock()
    mw._new_file = MagicMock()
    mw._new_folder = MagicMock()
    mw._open_file_dialog = MagicMock()
    mw._save_current = MagicMock()
    mw._save_as = MagicMock()
    mw._save_all = MagicMock()
    mw._close_current_tab = MagicMock()
    mw._close_all_tabs = MagicMock()
    mw._release_memory = MagicMock()
    mw._update_recent_menu = MagicMock()
    mw._undo = MagicMock()
    mw._redo = MagicMock()
    mw._cut = MagicMock()
    mw._copy = MagicMock()
    mw._paste = MagicMock()
    mw._select_all = MagicMock()
    mw._find = MagicMock()
    mw._replace = MagicMock()
    mw._delete_current_line = MagicMock()
    mw._move_line_up = MagicMock()
    mw._move_line_down = MagicMock()
    mw._duplicate_line = MagicMock()
    mw._goto_line = MagicMock()
    mw._to_uppercase = MagicMock()
    mw._to_lowercase = MagicMock()
    mw._to_titlecase = MagicMock()
    mw._toggle_case = MagicMock()
    mw._import_characters = MagicMock()
    mw._import_document = MagicMock()
    mw._show_typing_stats = MagicMock()
    mw._show_construction_stats = MagicMock()
    mw._show_collection_stats = MagicMock()
    mw._switch_view = MagicMock()
    mw._set_wrap_mode = MagicMock()
    mw._toggle_md_preview = MagicMock()
    mw._toggle_minimap = MagicMock()
    mw._toggle_file_tree = MagicMock()
    mw._toggle_secretary = MagicMock()
    mw._toggle_fullscreen = MagicMock()
    mw._zoom_in = MagicMock()
    mw._zoom_out = MagicMock()
    mw._zoom_reset = MagicMock()
    mw._show_editor_settings = MagicMock()
    mw._show_game_settings = MagicMock()
    mw._save_settings = MagicMock()
    mw._reset_settings = MagicMock()
    mw._show_guide = MagicMock()
    mw._show_manual = MagicMock()
    mw._show_about = MagicMock()
    mw.close = MagicMock()
    return mw


class TestMenuBuilderBuild:
    def test_build_creates_six_menus(self, qtbot):
        config = _make_config()
        builder = MenuBuilder(config)
        mw = _make_main_window()

        menubar = QMenuBar()
        builder.build(menubar, mw)

        actions = menubar.actions()
        menu_titles = [a.text() for a in actions]
        assert "文件" in menu_titles
        assert "编辑" in menu_titles
        assert "游戏" in menu_titles
        assert "视图" in menu_titles
        assert "设置" in menu_titles
        assert "帮助" in menu_titles

    def test_file_menu_has_new_action(self, qtbot):
        config = _make_config()
        builder = MenuBuilder(config)
        mw = _make_main_window()

        menubar = QMenuBar()
        builder.build(menubar, mw)

        file_menu = menubar.actions()[0].menu()
        action_texts = [a.text() for a in file_menu.actions() if a.text()]
        assert "新建文件" in action_texts

    def test_edit_menu_has_line_operations(self, qtbot):
        config = _make_config()
        builder = MenuBuilder(config)
        mw = _make_main_window()

        menubar = QMenuBar()
        builder.build(menubar, mw)

        edit_menu = menubar.actions()[1].menu()
        all_texts = []
        for action in edit_menu.actions():
            if action.menu():
                all_texts.extend(
                    [a.text() for a in action.menu().actions() if a.text()]
                )
            elif action.text():
                all_texts.append(action.text())

        assert "删除当前行" in all_texts
        assert "转为大写" in all_texts

    def test_recent_menu_created(self, qtbot):
        config = _make_config()
        builder = MenuBuilder(config)
        mw = _make_main_window()

        menubar = QMenuBar()
        builder.build(menubar, mw)

        mw._update_recent_menu.assert_called_once()

    def test_wrap_mode_actions_created(self, qtbot):
        config = _make_config()
        builder = MenuBuilder(config)
        mw = _make_main_window()

        menubar = QMenuBar()
        builder.build(menubar, mw)

        assert hasattr(mw, "_wrap_no_wrap_action")
        assert hasattr(mw, "_wrap_limit_action")
        assert mw._wrap_no_wrap_action.isChecked()


class TestMenuBuilderAddAction:
    def test_add_action_with_shortcut(self, qtbot):
        config = _make_config()
        builder = MenuBuilder(config)

        menu = QMenu()
        callback = MagicMock()

        action = MenuBuilder._add_action(menu, "测试", 0, callback)
        assert action.text() == "测试"

    def test_add_check_action(self, qtbot):
        config = _make_config()
        builder = MenuBuilder(config)

        menu = QMenu()
        callback = MagicMock()

        action = MenuBuilder._add_check_action(menu, "可选项", callback)
        assert action.isCheckable()
        assert action.text() == "可选项"
