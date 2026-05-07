# -*- coding: utf-8 -*-
import json
import os
import tempfile
from datetime import datetime

from src.core.config import Config


def _make_config(tmp_path):
    config_dir = os.path.join(str(tmp_path), "data", "config")
    gamedata_dir = os.path.join(str(tmp_path), "data", "gamedata")
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs(gamedata_dir, exist_ok=True)

    path_file = os.path.join(str(tmp_path), "user_data_path.txt")
    with open(path_file, "w", encoding="utf-8") as f:
        f.write(str(tmp_path))

    return Config(app_dir=str(tmp_path))


class TestConfigInit:
    def test_init_creates_config(self, tmp_path):
        config = _make_config(tmp_path)
        assert config is not None

    def test_get_base_path(self, tmp_path):
        config = _make_config(tmp_path)
        assert config.get_base_path() == str(tmp_path)

    def test_get_app_dir(self, tmp_path):
        config = _make_config(tmp_path)
        assert config.get_app_dir() == str(tmp_path)


class TestConfigEditorSettings:
    def test_get_default_font_size(self, tmp_path):
        config = _make_config(tmp_path)
        assert config.get_editor_setting("font_size") == 12

    def test_set_and_get_editor_setting(self, tmp_path):
        config = _make_config(tmp_path)
        config.set_editor_setting("font_size", 20)
        assert config.get_editor_setting("font_size") == 20

    def test_get_nonexistent_default(self, tmp_path):
        config = _make_config(tmp_path)
        assert config.get_editor_setting("nonexistent", "default") == "default"

    def test_auto_pair_default(self, tmp_path):
        config = _make_config(tmp_path)
        assert config.get_editor_setting("auto_pair_brackets") is True


class TestConfigGameSettings:
    def test_get_default_idle_rate(self, tmp_path):
        config = _make_config(tmp_path)
        assert config.get_game_setting("idle_reward_rate") == 1.0

    def test_set_and_get_game_setting(self, tmp_path):
        config = _make_config(tmp_path)
        config.set_game_setting("idle_reward_rate", 2.5)
        assert config.get_game_setting("idle_reward_rate") == 2.5

    def test_get_nonexistent_default(self, tmp_path):
        config = _make_config(tmp_path)
        assert config.get_game_setting("nonexistent", 42) == 42


class TestConfigResources:
    def test_get_default_resources(self, tmp_path):
        config = _make_config(tmp_path)
        res = config.get_resources()
        assert res["fuel"] == 3000
        assert res["ammo"] == 3000
        assert res["steel"] == 3000
        assert res["bauxite"] == 1000

    def test_add_resource(self, tmp_path):
        config = _make_config(tmp_path)
        config.add_resource("fuel", 100)
        assert config.get_resources()["fuel"] == 3100

    def test_add_resource_accumulates(self, tmp_path):
        config = _make_config(tmp_path)
        config.add_resource("fuel", 50)
        config.add_resource("fuel", 30)
        assert config.get_resources()["fuel"] == 3080

    def test_add_resource_no_negative(self, tmp_path):
        config = _make_config(tmp_path)
        config.add_resource("fuel", -99999)
        assert config.get_resources()["fuel"] == 0

    def test_set_resources(self, tmp_path):
        config = _make_config(tmp_path)
        config.set_resources({"fuel": 100, "ammo": 200, "steel": 300, "bauxite": 400})
        assert config.get_resources()["fuel"] == 100


class TestConfigCores:
    def test_default_cores(self, tmp_path):
        config = _make_config(tmp_path)
        assert config.get_cores() == 0

    def test_set_cores(self, tmp_path):
        config = _make_config(tmp_path)
        config.set_cores(10)
        assert config.get_cores() == 10

    def test_add_cores(self, tmp_path):
        config = _make_config(tmp_path)
        config.add_cores(5)
        assert config.get_cores() == 5

    def test_cores_no_negative(self, tmp_path):
        config = _make_config(tmp_path)
        config.set_cores(-5)
        assert config.get_cores() == 0


class TestConfigRecentFiles:
    def test_add_recent_file(self, tmp_path):
        config = _make_config(tmp_path)
        config.add_recent_file("/path/to/file.txt")
        recent = config.get_recent_files()
        assert "/path/to/file.txt" in recent

    def test_recent_files_limit(self, tmp_path):
        config = _make_config(tmp_path)
        for i in range(25):
            config.add_recent_file(f"/path/file_{i}.txt")
        recent = config.get_recent_files()
        assert len(recent) <= 20

    def test_recent_files_no_duplicates(self, tmp_path):
        config = _make_config(tmp_path)
        config.add_recent_file("/path/to/file.txt")
        config.add_recent_file("/path/to/file.txt")
        recent = config.get_recent_files()
        assert recent.count("/path/to/file.txt") == 1

    def test_recent_files_most_recent_first(self, tmp_path):
        config = _make_config(tmp_path)
        config.add_recent_file("/first.txt")
        config.add_recent_file("/second.txt")
        recent = config.get_recent_files()
        assert recent[0] == "/second.txt"


class TestConfigWorkspace:
    def test_get_open_files_default(self, tmp_path):
        config = _make_config(tmp_path)
        assert config.get_open_files() == []

    def test_set_and_get_open_files(self, tmp_path):
        config = _make_config(tmp_path)
        config.set_open_files([{"path": "/test.txt"}])
        assert len(config.get_open_files()) == 1

    def test_active_tab_index(self, tmp_path):
        config = _make_config(tmp_path)
        config.set_active_tab_index(3)
        assert config.get_active_tab_index() == 3

    def test_current_view(self, tmp_path):
        config = _make_config(tmp_path)
        config.set_current_view("garage")
        assert config.get_current_view() == "garage"


class TestConfigSaveLoad:
    def test_save_and_reload_settings(self, tmp_path):
        config = _make_config(tmp_path)
        config.set_editor_setting("font_size", 20)
        config.save_settings()

        config2 = Config(app_dir=str(tmp_path))
        assert config2.get_editor_setting("font_size") == 20

    def test_save_and_reload_savegame(self, tmp_path):
        config = _make_config(tmp_path)
        config.add_resource("fuel", 500)
        config.save_savegame()

        config2 = Config(app_dir=str(tmp_path))
        assert config2.get_resources()["fuel"] == 3500


class TestConfigLastLogin:
    def test_update_and_get_last_login(self, tmp_path):
        config = _make_config(tmp_path)
        config.update_last_login()
        last = config.get_last_login()
        assert last is not None
        assert datetime.now().strftime("%Y-%m-%d") in last

    def test_get_last_login_none(self, tmp_path):
        config = _make_config(tmp_path)
        assert config.get_last_login() is None


class TestConfigCharsTyped:
    def test_add_chars_typed(self, tmp_path):
        config = _make_config(tmp_path)
        config.add_chars_typed(100)
        assert config.get_today_chars_typed() == 100

    def test_add_chars_accumulates(self, tmp_path):
        config = _make_config(tmp_path)
        config.add_chars_typed(50)
        config.add_chars_typed(30)
        assert config.get_today_chars_typed() == 80


class TestConfigDirectories:
    def test_ensure_directories(self, tmp_path):
        config = _make_config(tmp_path)
        config.ensure_directories()
        assert os.path.isdir(os.path.join(str(tmp_path), "notebooks"))

    def test_get_notebooks_path(self, tmp_path):
        config = _make_config(tmp_path)
        assert "notebooks" in config.get_notebooks_path()

    def test_get_assets_path(self, tmp_path):
        config = _make_config(tmp_path)
        assert "assets" in config.get_assets_path()


class TestConfigExternalFiles:
    def test_add_and_get_external_file(self, tmp_path):
        config = _make_config(tmp_path)
        config.add_external_file("/external/file.txt")
        assert "/external/file.txt" in config.get_external_files()

    def test_remove_external_file(self, tmp_path):
        config = _make_config(tmp_path)
        config.add_external_file("/external/file.txt")
        config.remove_external_file("/external/file.txt")
        assert "/external/file.txt" not in config.get_external_files()
