# -*- coding: utf-8 -*-
import os
import json
import pytest
from PyQt5.QtWidgets import QApplication, QWidget

from src.core.config import Config
from src.core.shortcut_manager import ShortcutManager, _DEFAULT_SHORTCUTS, _SYSTEM_SHORTCUTS


def _make_config(tmp_path):
    config_dir = os.path.join(str(tmp_path), "data", "config")
    gamedata_dir = os.path.join(str(tmp_path), "data", "gamedata")
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs(gamedata_dir, exist_ok=True)
    path_file = os.path.join(str(tmp_path), "user_data_path.txt")
    with open(path_file, "w", encoding="utf-8") as f:
        f.write(str(tmp_path))
    return Config(app_dir=str(tmp_path))


class TestShortcutManager:
    def test_init(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        assert manager is not None

    def test_default_shortcuts_loaded(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        all_shortcuts = manager.get_all_shortcuts()
        assert len(all_shortcuts) > 0

    def test_get_shortcut(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        shortcut = manager.get_shortcut("file.new")
        assert shortcut == "Ctrl+N"

    def test_get_shortcut_unknown(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        shortcut = manager.get_shortcut("nonexistent.action")
        assert shortcut is None

    def test_register(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        called = []
        action = manager.register("test.action", "测试操作", "Ctrl+T", lambda: called.append(1))
        assert action is not None
        assert action.text() == "测试操作"

    def test_register_triggers_callback(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        called = []
        action = manager.register("test.action2", "测试", "Ctrl+Shift+T", lambda: called.append(1))
        action.trigger()
        assert len(called) == 1

    def test_get_action(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        manager.register("test.get_action", "测试", "F2", lambda: None)
        action = manager.get_action("test.get_action")
        assert action is not None

    def test_get_action_unknown(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        action = manager.get_action("nonexistent")
        assert action is None

    def test_check_conflicts_empty(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        conflicts = manager.check_conflicts("")
        assert conflicts == []

    def test_check_conflicts_system(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        conflicts = manager.check_conflicts("Ctrl+C")
        assert len(conflicts) > 0
        assert any(c["type"] == "system" for c in conflicts)

    def test_check_conflicts_application(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        conflicts = manager.check_conflicts("Ctrl+N")
        assert len(conflicts) > 0
        assert any(c["type"] == "application" for c in conflicts)

    def test_check_conflicts_exclude_self(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        conflicts = manager.check_conflicts("Ctrl+N", exclude="file.new")
        app_conflicts = [c for c in conflicts if c["type"] == "application"]
        assert len(app_conflicts) == 0

    def test_check_conflicts_no_conflict(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        conflicts = manager.check_conflicts("Ctrl+Shift+F12")
        assert len(conflicts) == 0

    def test_set_shortcut(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        success, conflicts = manager.set_shortcut("file.new", "Ctrl+Shift+N")
        assert success is True
        assert conflicts == []
        assert manager.get_shortcut("file.new") == "Ctrl+Shift+N"

    def test_set_shortcut_conflict(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        success, conflicts = manager.set_shortcut("file.new", "Ctrl+S")
        assert success is False
        assert len(conflicts) > 0

    def test_set_shortcut_unknown(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        success, conflicts = manager.set_shortcut("nonexistent", "Ctrl+X")
        assert success is False

    def test_reset_shortcut(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        manager.set_shortcut("file.new", "Ctrl+Shift+N")
        result = manager.reset_shortcut("file.new")
        assert result is True
        assert manager.get_shortcut("file.new") == "Ctrl+N"

    def test_reset_shortcut_unknown(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        result = manager.reset_shortcut("nonexistent")
        assert result is False

    def test_reset_all(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        manager.set_shortcut("file.new", "Ctrl+Shift+N")
        manager.reset_all()
        assert manager.get_shortcut("file.new") == "Ctrl+N"

    def test_get_categories(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        categories = manager.get_categories()
        assert "文件" in categories
        assert "编辑" in categories
        assert "视图" in categories

    def test_get_all_shortcuts_structure(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        all_shortcuts = manager.get_all_shortcuts()
        for category, items in all_shortcuts.items():
            for action_id, info in items.items():
                assert "name" in info
                assert "shortcut" in info

    def test_custom_shortcuts_persisted(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        manager.set_shortcut("file.new", "Ctrl+Shift+N")

        manager2 = ShortcutManager(config)
        assert manager2.get_shortcut("file.new") == "Ctrl+Shift+N"

    def test_normalize_key(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        assert manager._normalize_key("Ctrl+N") == manager._normalize_key("ctrl+n")
        assert manager._normalize_key("Ctrl+Shift+S") == manager._normalize_key("shift+ctrl+s")

    def test_normalize_key_order(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        assert manager._normalize_key("Ctrl+Shift+N") == manager._normalize_key("Shift+Ctrl+N")

    def test_register_with_existing_id(self, tmp_path):
        config = _make_config(tmp_path)
        manager = ShortcutManager(config)
        called = []
        manager.register("file.new", "新建文件", "Ctrl+N", lambda: called.append(1))
        assert manager.get_shortcut("file.new") == "Ctrl+N"


class TestSystemShortcuts:
    def test_common_shortcuts_defined(self):
        assert "Ctrl+C" in _SYSTEM_SHORTCUTS
        assert "Ctrl+V" in _SYSTEM_SHORTCUTS
        assert "Ctrl+X" in _SYSTEM_SHORTCUTS
        assert "Ctrl+S" in _SYSTEM_SHORTCUTS
        assert "Alt+F4" in _SYSTEM_SHORTCUTS

    def test_all_have_descriptions(self):
        for key, desc in _SYSTEM_SHORTCUTS.items():
            assert desc != ""


class TestDefaultShortcuts:
    def test_all_have_three_elements(self):
        for action_id, value in _DEFAULT_SHORTCUTS.items():
            assert len(value) == 3, f"{action_id} should have (name, shortcut, category)"

    def test_all_categories_non_empty(self):
        for action_id, (name, shortcut, category) in _DEFAULT_SHORTCUTS.items():
            assert category != "", f"{action_id} has empty category"
