# -*- coding: utf-8 -*-
import json
import os
import tempfile

from src.plugins.plugin_manager import PluginManager, PluginLoadError, PluginValidationError
from src.plugins.plugin_base import PluginBase, PluginMeta, PluginPermission, PluginState


class _MockConfig:
    def __init__(self, tmp_dir):
        self._tmp_dir = tmp_dir
        self._settings = {}

    def get_app_dir(self):
        return self._tmp_dir

    def get_setting(self, key, default=None):
        return self._settings.get(key, default)

    def set_view_setting(self, key, value):
        self._settings[key] = value


def _create_plugin_package(tmp_dir, name, version="1.0.0", entry="main.py",
                           permissions=None, extra_manifest=None):
    plugin_dir = os.path.join(tmp_dir, name)
    os.makedirs(plugin_dir, exist_ok=True)

    manifest = {
        "name": name,
        "version": version,
        "description": f"Test plugin {name}",
        "author": "Test",
        "entry": entry,
        "permissions": permissions or ["read_settings"],
    }
    if extra_manifest:
        manifest.update(extra_manifest)

    with open(os.path.join(plugin_dir, "plugin.json"), 'w', encoding='utf-8') as f:
        json.dump(manifest, f)

    main_code = '''
from src.plugins.plugin_base import PluginBase, PluginMeta, PluginPermission

class Plugin(PluginBase):
    def get_meta(self):
        return PluginMeta(
            name="''' + name + '''",
            version="''' + version + '''",
            description="Test plugin",
            permissions=[PluginPermission.READ_SETTINGS],
        )

    def on_load(self, api):
        super().on_load(api)

    def on_activate(self):
        super().on_activate()

    def on_deactivate(self):
        super().on_deactivate()

    def on_unload(self):
        super().on_unload()
'''
    with open(os.path.join(plugin_dir, entry), 'w', encoding='utf-8') as f:
        f.write(main_code)

    return plugin_dir


class TestPluginManagerScan:
    def test_scan_empty_dir(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        plugins_dir = os.path.join(str(tmp_path), "plugins_empty")
        os.makedirs(plugins_dir, exist_ok=True)
        manager = PluginManager(config, plugins_dir=plugins_dir)
        result = manager.scan_plugins()
        assert result == []

    def test_scan_nonexistent_dir(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        manager = PluginManager(config, plugins_dir="/nonexistent")
        result = manager.scan_plugins()
        assert result == []

    def test_scan_finds_plugin(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        plugins_dir = os.path.join(str(tmp_path), "plugins")
        _create_plugin_package(plugins_dir, "test_plugin")
        manager = PluginManager(config, plugins_dir=plugins_dir)
        result = manager.scan_plugins()
        assert "test_plugin" in result

    def test_scan_skips_no_manifest(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        plugins_dir = os.path.join(str(tmp_path), "plugins")
        no_manifest_dir = os.path.join(plugins_dir, "no_manifest")
        os.makedirs(no_manifest_dir, exist_ok=True)
        manager = PluginManager(config, plugins_dir=plugins_dir)
        result = manager.scan_plugins()
        assert result == []


class TestPluginManagerValidate:
    def test_validate_valid_manifest(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        plugins_dir = os.path.join(str(tmp_path), "plugins")
        _create_plugin_package(plugins_dir, "valid_plugin")
        manager = PluginManager(config, plugins_dir=plugins_dir)
        manager.scan_plugins()
        info = manager.get_plugin_info("valid_plugin")
        assert info is not None
        assert info["name"] == "valid_plugin"

    def test_validate_missing_fields(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        plugins_dir = os.path.join(str(tmp_path), "plugins")
        plugin_dir = os.path.join(plugins_dir, "bad_plugin")
        os.makedirs(plugin_dir, exist_ok=True)
        with open(os.path.join(plugin_dir, "plugin.json"), 'w') as f:
            json.dump({"name": "bad"}, f)
        manager = PluginManager(config, plugins_dir=plugins_dir)
        result = manager.scan_plugins()
        assert "bad_plugin" not in result


class TestPluginManagerLifecycle:
    def test_load_activate_deactivate_unload(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        plugins_dir = os.path.join(str(tmp_path), "plugins")
        _create_plugin_package(plugins_dir, "lifecycle_plugin")
        manager = PluginManager(config, plugins_dir=plugins_dir)
        manager.scan_plugins()

        plugin = manager.load_plugin("lifecycle_plugin")
        assert plugin.state == PluginState.LOADED

        manager.activate_plugin("lifecycle_plugin")
        assert plugin.state == PluginState.ACTIVATED

        manager.deactivate_plugin("lifecycle_plugin")
        assert plugin.state == PluginState.DEACTIVATED

        manager.unload_plugin("lifecycle_plugin")
        assert manager.get_plugin("lifecycle_plugin") is None

    def test_load_nonexistent_plugin(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        plugins_dir = os.path.join(str(tmp_path), "plugins")
        os.makedirs(plugins_dir, exist_ok=True)
        manager = PluginManager(config, plugins_dir=plugins_dir)
        try:
            manager.load_plugin("nonexistent")
            assert False, "Should raise PluginLoadError"
        except PluginLoadError:
            pass

    def test_activate_already_activated(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        plugins_dir = os.path.join(str(tmp_path), "plugins")
        _create_plugin_package(plugins_dir, "double_activate")
        manager = PluginManager(config, plugins_dir=plugins_dir)
        manager.scan_plugins()
        manager.load_plugin("double_activate")
        manager.activate_plugin("double_activate")
        manager.activate_plugin("double_activate")

    def test_deactivate_not_activated(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        plugins_dir = os.path.join(str(tmp_path), "plugins")
        _create_plugin_package(plugins_dir, "deact_test")
        manager = PluginManager(config, plugins_dir=plugins_dir)
        manager.scan_plugins()
        manager.load_plugin("deact_test")
        manager.deactivate_plugin("deact_test")

    def test_get_discovered_plugins(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        plugins_dir = os.path.join(str(tmp_path), "plugins")
        _create_plugin_package(plugins_dir, "disc_plugin")
        manager = PluginManager(config, plugins_dir=plugins_dir)
        manager.scan_plugins()
        discovered = manager.get_discovered_plugins()
        assert len(discovered) >= 1
        names = [p["name"] for p in discovered]
        assert "disc_plugin" in names

    def test_reload_plugin(self, tmp_path):
        config = _MockConfig(str(tmp_path))
        plugins_dir = os.path.join(str(tmp_path), "plugins")
        _create_plugin_package(plugins_dir, "reload_plugin")
        manager = PluginManager(config, plugins_dir=plugins_dir)
        manager.scan_plugins()
        manager.load_plugin("reload_plugin")
        manager.activate_plugin("reload_plugin")

        plugin = manager.reload_plugin("reload_plugin")
        assert plugin.state == PluginState.ACTIVATED
