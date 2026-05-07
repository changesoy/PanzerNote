# -*- coding: utf-8 -*-
import os
import pytest
from PyQt5.QtWidgets import QApplication

from src.core.config import Config
from src.game.resource_bar import ResourceItem, ResourceBar


def _make_config(tmp_path):
    config_dir = os.path.join(str(tmp_path), "data", "config")
    gamedata_dir = os.path.join(str(tmp_path), "data", "gamedata")
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs(gamedata_dir, exist_ok=True)
    path_file = os.path.join(str(tmp_path), "user_data_path.txt")
    with open(path_file, "w", encoding="utf-8") as f:
        f.write(str(tmp_path))
    return Config(app_dir=str(tmp_path))


class TestResourceItem:
    def test_init(self, qtbot):
        item = ResourceItem("", "fuel")
        qtbot.addWidget(item)
        assert item.name == "fuel"
        assert item._value == 0

    def test_set_value(self, qtbot):
        item = ResourceItem("", "fuel")
        qtbot.addWidget(item)
        item.set_value(500)
        assert item.get_value() == 500
        assert "500" in item.value_label.text()

    def test_placeholder_colors(self, qtbot):
        fuel = ResourceItem("", "fuel")
        qtbot.addWidget(fuel)
        assert "#4CAF50" in fuel.icon_label.styleSheet()

        ammo = ResourceItem("", "ammo")
        qtbot.addWidget(ammo)
        assert "#FFC107" in ammo.icon_label.styleSheet()


class TestResourceBar:
    def test_init(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        bar = ResourceBar(config)
        qtbot.addWidget(bar)
        assert bar is not None

    def test_refresh(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        config.add_resource("fuel", 100)
        bar = ResourceBar(config)
        qtbot.addWidget(bar)
        bar.refresh()
        assert bar.fuel.get_value() == 3100

    def test_update_typing_stats(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        bar = ResourceBar(config)
        qtbot.addWidget(bar)
        bar.update_typing_stats(500, 10)
        assert "500" in bar.typing_label.text()
        assert "10" in bar.docs_label.text()

    def test_add_resources(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        bar = ResourceBar(config)
        qtbot.addWidget(bar)
        bar.add_resources(fuel=100, ammo=200)
        assert bar.fuel.get_value() == 3100
        assert bar.ammo.get_value() == 3200
