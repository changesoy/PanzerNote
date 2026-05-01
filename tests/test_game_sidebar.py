# -*- coding: utf-8 -*-
import pytest
from PyQt5.QtWidgets import QApplication

from src.game.game_sidebar import GameIconButton, GameSidebar


class TestGameIconButton:
    def test_init(self, qtbot):
        btn = GameIconButton("back", "返回", "#78909C")
        qtbot.addWidget(btn)
        assert btn.icon_name == "back"
        assert btn._is_current is False

    def test_set_current(self, qtbot):
        btn = GameIconButton("construction", "建造", "#4CAF50")
        qtbot.addWidget(btn)
        btn.set_current(True)
        assert btn._is_current is True
        btn.set_current(False)
        assert btn._is_current is False

    def test_placeholder_char_map(self, qtbot):
        for name in ["back", "construction", "garage", "collection"]:
            btn = GameIconButton(name, name, "#666666")
            qtbot.addWidget(btn)
            assert btn.icon() is not None


class TestGameSidebar:
    def test_init(self, qtbot):
        sidebar = GameSidebar()
        qtbot.addWidget(sidebar)
        assert sidebar is not None
        assert sidebar.back_btn is not None
        assert sidebar.construction_btn is not None

    def test_set_current_view(self, qtbot):
        sidebar = GameSidebar()
        qtbot.addWidget(sidebar)
        sidebar.set_current_view("garage")
        assert sidebar.garage_btn._is_current is True
        assert sidebar.construction_btn._is_current is False

    def test_view_changed_signal(self, qtbot):
        sidebar = GameSidebar()
        qtbot.addWidget(sidebar)
        with qtbot.waitSignal(sidebar.view_changed, timeout=1000) as blocker:
            sidebar.back_btn.click()
        assert blocker.args == ["back"]
