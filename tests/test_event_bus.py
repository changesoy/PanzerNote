# -*- coding: utf-8 -*-
from unittest.mock import MagicMock

from src.core.event_bus import EventBus


def _make_config() -> MagicMock:
    return MagicMock()


def _make_main_window() -> MagicMock:
    mw = MagicMock()
    mw.game_sidebar = MagicMock()
    mw.file_tree = MagicMock()
    mw.editor_tabs = MagicMock()
    mw.resource_bar = MagicMock()
    mw.secretary = MagicMock()
    mw._current_view = "editor"
    return mw


class TestEventBus:
    def test_connect_signals(self):
        config = _make_config()
        bus = EventBus(config)
        mw = _make_main_window()

        bus.connect_signals(mw)

        mw.game_sidebar.view_changed.connect.assert_called_once()
        mw.file_tree.file_open_requested.connect.assert_called_once()
        mw.editor_tabs.current_changed.connect.assert_called_once()

    def test_handle_view_changed_back_to_editor(self):
        config = _make_config()
        bus = EventBus(config)
        mw = _make_main_window()
        mw._current_view = "construction"

        bus.handle_view_changed(mw, "back")
        mw._switch_view.assert_called_with("editor")

    def test_handle_view_changed_back_undo(self):
        config = _make_config()
        bus = EventBus(config)
        mw = _make_main_window()
        mw._current_view = "editor"

        bus.handle_view_changed(mw, "back")
        mw._undo.assert_called_once()

    def test_handle_view_changed_normal(self):
        config = _make_config()
        bus = EventBus(config)
        mw = _make_main_window()

        bus.handle_view_changed(mw, "garage")
        mw._switch_view.assert_called_with("garage")

    def test_handle_file_saved(self):
        config = _make_config()
        bus = EventBus(config)
        mw = _make_main_window()

        bus.handle_file_saved(mw, 100)
        mw.resource_bar.refresh.assert_called_once()
        mw.secretary.show_message.assert_called_once()

    def test_handle_tab_count_changed_zero(self):
        config = _make_config()
        bus = EventBus(config)
        mw = _make_main_window()

        bus.handle_tab_count_changed(mw, 0)
        mw.secretary.show_event_message.assert_called_with("欢迎")

    def test_handle_tab_count_changed_nonzero(self):
        config = _make_config()
        bus = EventBus(config)
        mw = _make_main_window()

        bus.handle_tab_count_changed(mw, 3)
        mw.secretary.show_event_message.assert_not_called()

    def test_handle_file_move(self):
        config = _make_config()
        bus = EventBus(config)
        mw = _make_main_window()
        mw.editor_tabs.move_file_to_folder.return_value = True

        bus.handle_file_move(mw, "/path/to/file.txt", "/path/to/folder")
        mw.editor_tabs.move_file_to_folder.assert_called_once()
        mw.secretary.show_message.assert_called_once()
