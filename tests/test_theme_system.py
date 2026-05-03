# -*- coding: utf-8 -*-
import json
import os
import tempfile

from src.themes.theme_engine import ThemeEngine, ThemeDefinition, ThemeColorScheme, LayoutConfig


class _MockConfig:
    def __init__(self, tmp_dir):
        self._tmp_dir = tmp_dir
        self._settings = {}
        self._view_settings = {"theme": "light"}

    def get_app_dir(self):
        return self._tmp_dir

    def get_setting(self, key, default=None):
        return self._settings.get(key, default)

    def get_view_setting(self, key, default=None):
        return self._view_settings.get(key, default)

    def set_view_setting(self, key, value):
        self._view_settings[key] = value


class TestThemeColorScheme:
    def test_default_colors(self):
        c = ThemeColorScheme()
        assert c.primary == "#2196F3"
        assert c.background == "#FFFFFF"
        assert c.text_primary == "#212121"

    def test_to_dict(self):
        c = ThemeColorScheme()
        d = c.to_dict()
        assert "primary" in d
        assert "background" in d
        assert len(d) > 20

    def test_from_dict(self):
        data = {"primary": "#FF0000", "background": "#000000"}
        c = ThemeColorScheme.from_dict(data)
        assert c.primary == "#FF0000"
        assert c.background == "#000000"
        assert c.text_primary == "#212121"

    def test_from_dict_ignores_unknown(self):
        data = {"primary": "#FF0000", "unknown_field": "#123456"}
        c = ThemeColorScheme.from_dict(data)
        assert c.primary == "#FF0000"


class TestLayoutConfig:
    def test_defaults(self):
        l = LayoutConfig()
        assert l.sidebar_width == 200
        assert l.minimap_width == 80

    def test_from_dict(self):
        data = {"sidebar_width": 300, "minimap_width": 100}
        l = LayoutConfig.from_dict(data)
        assert l.sidebar_width == 300
        assert l.minimap_width == 100

    def test_from_dict_ignores_non_int(self):
        data = {"sidebar_width": "wide"}
        l = LayoutConfig.from_dict(data)
        assert l.sidebar_width == 200


class TestThemeDefinition:
    def test_create(self):
        t = ThemeDefinition(id="test", name="Test Theme")
        assert t.id == "test"
        assert t.name == "Test Theme"
        assert t.is_dark is False

    def test_to_dict(self):
        t = ThemeDefinition(id="test", name="Test")
        d = t.to_dict()
        assert d["id"] == "test"
        assert "colors" in d
        assert "layout" in d

    def test_from_dict(self):
        data = {
            "id": "custom",
            "name": "Custom Theme",
            "is_dark": True,
            "colors": {"primary": "#BB86FC"},
            "layout": {"sidebar_width": 250},
        }
        t = ThemeDefinition.from_dict(data)
        assert t.id == "custom"
        assert t.is_dark is True
        assert t.colors.primary == "#BB86FC"
        assert t.layout.sidebar_width == 250


class TestThemeEngine:
    def test_builtin_themes(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        engine = ThemeEngine(config)
        themes = engine.get_all_themes()
        assert "light" in themes
        assert "dark" in themes

    def test_get_theme(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        engine = ThemeEngine(config)
        light = engine.get_theme("light")
        assert light is not None
        assert light.id == "light"

    def test_get_nonexistent_theme(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        engine = ThemeEngine(config)
        assert engine.get_theme("nonexistent") is None

    def test_set_active_theme(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        engine = ThemeEngine(config)
        result = engine.set_active_theme("dark")
        assert result is True
        active = engine.get_active_theme()
        assert active.id == "dark"

    def test_set_nonexistent_active_theme(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        engine = ThemeEngine(config)
        result = engine.set_active_theme("nonexistent")
        assert result is False

    def test_default_active_theme(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        engine = ThemeEngine(config)
        engine.initialize_active_theme()
        active = engine.get_active_theme()
        assert active.id == "light"

    def test_generate_stylesheet(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        engine = ThemeEngine(config)
        light = engine.get_theme("light")
        stylesheet = engine.generate_stylesheet(light)
        assert "QMainWindow" in stylesheet
        assert "QMenuBar" in stylesheet
        assert "QTabBar" in stylesheet
        assert "QTreeView" in stylesheet
        assert "QStatusBar" in stylesheet
        assert "QPushButton" in stylesheet
        assert "QDialog" in stylesheet

    def test_generate_dark_stylesheet(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        engine = ThemeEngine(config)
        dark = engine.get_theme("dark")
        stylesheet = engine.generate_stylesheet(dark)
        assert "#121212" in stylesheet

    def test_load_external_json_theme(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        themes_dir = os.path.join(str(tmp_path), "themes")
        os.makedirs(themes_dir, exist_ok=True)

        theme_data = {
            "id": "ocean",
            "name": "Ocean Theme",
            "is_dark": True,
            "colors": {
                "primary": "#0077B6",
                "background": "#023E8A",
            },
        }
        with open(os.path.join(themes_dir, "ocean.json"), 'w', encoding='utf-8') as f:
            json.dump(theme_data, f)

        engine = ThemeEngine(config)
        loaded = engine.load_external_themes()
        assert "ocean" in loaded
        ocean = engine.get_theme("ocean")
        assert ocean is not None
        assert ocean.colors.primary == "#0077B6"

    def test_stylesheet_overrides(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        theme = ThemeDefinition(
            id="custom",
            name="Custom",
            stylesheet_overrides={
                "QMainWindow": "border: 2px solid red;",
            },
        )
        engine = ThemeEngine(config)
        stylesheet = engine.generate_stylesheet(theme)
        assert "border: 2px solid red;" in stylesheet
