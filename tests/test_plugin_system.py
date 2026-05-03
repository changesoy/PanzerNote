# -*- coding: utf-8 -*-
import json
import os
import tempfile

from src.plugins.plugin_base import PluginBase, PluginMeta, PluginPermission, PluginState
from src.plugins.plugin_sandbox import PluginAPI, PluginSandbox, SandboxTimeoutError, SandboxViolationError


class TestPluginState:
    def test_state_values(self):
        assert PluginState.UNLOADED.name == "UNLOADED"
        assert PluginState.LOADED.name == "LOADED"
        assert PluginState.ACTIVATED.name == "ACTIVATED"
        assert PluginState.DEACTIVATED.name == "DEACTIVATED"
        assert PluginState.ERROR.name == "ERROR"


class TestPluginPermission:
    def test_permission_values(self):
        assert PluginPermission.READ_SETTINGS.value == "read_settings"
        assert PluginPermission.READ_SAVEGAME.value == "read_savegame"
        assert PluginPermission.READ_WORKSPACE.value == "read_workspace"
        assert PluginPermission.READ_FILE_TREE.value == "read_file_tree"
        assert PluginPermission.ACCESS_EDITOR.value == "access_editor"
        assert PluginPermission.ACCESS_UI.value == "access_ui"
        assert PluginPermission.ACCESS_NETWORK.value == "access_network"
        assert PluginPermission.ACCESS_FILESYSTEM.value == "access_filesystem"


class TestPluginMeta:
    def test_create_meta(self):
        meta = PluginMeta(
            name="test_plugin",
            version="1.0.0",
            description="Test plugin",
            author="Test",
            permissions=[PluginPermission.READ_SETTINGS],
        )
        assert meta.name == "test_plugin"
        assert meta.version == "1.0.0"
        assert len(meta.permissions) == 1

    def test_to_dict(self):
        meta = PluginMeta(
            name="test_plugin",
            version="1.0.0",
            description="Test",
            permissions=[PluginPermission.READ_SETTINGS, PluginPermission.READ_SAVEGAME],
        )
        d = meta.to_dict()
        assert d["name"] == "test_plugin"
        assert d["permissions"] == ["read_settings", "read_savegame"]

    def test_from_dict(self):
        data = {
            "name": "test_plugin",
            "version": "2.0.0",
            "description": "From dict",
            "permissions": ["read_settings"],
            "tags": ["test"],
        }
        meta = PluginMeta.from_dict(data)
        assert meta.name == "test_plugin"
        assert meta.version == "2.0.0"
        assert len(meta.permissions) == 1
        assert meta.tags == ["test"]

    def test_from_dict_invalid_permission(self):
        data = {
            "name": "test",
            "version": "1.0",
            "permissions": ["invalid_perm"],
        }
        meta = PluginMeta.from_dict(data)
        assert len(meta.permissions) == 0


class _DummyPlugin(PluginBase):
    def get_meta(self) -> PluginMeta:
        return PluginMeta(
            name="dummy",
            version="1.0.0",
            description="Dummy",
            permissions=[PluginPermission.READ_SETTINGS],
        )


class TestPluginBase:
    def test_initial_state(self):
        p = _DummyPlugin()
        assert p.state == PluginState.UNLOADED
        assert p.api is None
        assert p.meta is None

    def test_on_load(self):
        p = _DummyPlugin()
        p.on_load("api")
        assert p.state == PluginState.LOADED
        assert p.api == "api"
        assert p.meta is not None
        assert p.meta.name == "dummy"

    def test_on_activate(self):
        p = _DummyPlugin()
        p.on_load("api")
        p.on_activate()
        assert p.state == PluginState.ACTIVATED

    def test_on_deactivate(self):
        p = _DummyPlugin()
        p.on_load("api")
        p.on_activate()
        p.on_deactivate()
        assert p.state == PluginState.DEACTIVATED

    def test_on_unload(self):
        p = _DummyPlugin()
        p.on_load("api")
        p.on_unload()
        assert p.state == PluginState.UNLOADED
        assert p.api is None


class _MockConfig:
    def __init__(self):
        self._settings = {"editor": {"font_size": 12}, "game": {"difficulty": "normal"}}
        self._savegame = {"resources": {"fuel": 3000, "ammo": 2000}}
        self._workspace = {"recent_files": ["/a.txt", "/b.txt"]}

    def get_setting(self, key, default=None):
        return self._settings.get(key, default)

    def get_editor_setting(self, key, default=None):
        return self._settings.get("editor", {}).get(key, default)

    def get_game_setting(self, key, default=None):
        return self._settings.get("game", {}).get(key, default)

    def get_secretary_setting(self, key, default=None):
        return None

    def get_resources(self):
        return self._savegame.get("resources", {})

    def get_savegame(self):
        return self._savegame

    def get_recent_files(self):
        return self._workspace.get("recent_files", [])

    def get_notebooks_path(self):
        return "/notebooks"


class TestPluginAPI:
    def test_get_setting_with_permission(self):
        config = _MockConfig()
        api = PluginAPI(config, [PluginPermission.READ_SETTINGS])
        result = api.get_setting("editor")
        assert result == {"font_size": 12}

    def test_get_setting_without_permission(self):
        config = _MockConfig()
        api = PluginAPI(config, [])
        try:
            api.get_setting("editor")
            assert False, "Should raise SandboxViolationError"
        except SandboxViolationError:
            pass

    def test_get_resources(self):
        config = _MockConfig()
        api = PluginAPI(config, [PluginPermission.READ_SAVEGAME])
        res = api.get_resources()
        assert res["fuel"] == 3000

    def test_get_recent_files(self):
        config = _MockConfig()
        api = PluginAPI(config, [PluginPermission.READ_WORKSPACE])
        files = api.get_recent_files()
        assert len(files) == 2

    def test_mvp_readonly_blocks_filesystem(self):
        config = _MockConfig()
        api = PluginAPI(config, [PluginPermission.ACCESS_FILESYSTEM])
        try:
            api.get_notebooks_path()
            assert False, "Should raise SandboxViolationError"
        except SandboxViolationError:
            pass

    def test_mvp_readonly_blocks_network(self):
        config = _MockConfig()
        api = PluginAPI(config, [PluginPermission.ACCESS_NETWORK])
        try:
            api.get_notebooks_path()
            assert False, "Should raise SandboxViolationError"
        except SandboxViolationError:
            pass


class TestPluginSandbox:
    def test_execute_safe_success(self):
        config = _MockConfig()
        sandbox = PluginSandbox(config, timeout=5)
        result = sandbox.execute_safe(lambda: 1 + 1)
        assert result == 2

    def test_execute_safe_timeout(self):
        import time
        config = _MockConfig()
        sandbox = PluginSandbox(config, timeout=1)
        try:
            sandbox.execute_safe(lambda: time.sleep(10))
            assert False, "Should raise SandboxTimeoutError"
        except SandboxTimeoutError:
            pass

    def test_execute_safe_exception(self):
        config = _MockConfig()
        sandbox = PluginSandbox(config, timeout=5)
        try:
            sandbox.execute_safe(lambda: 1 / 0)
            assert False, "Should raise ZeroDivisionError"
        except ZeroDivisionError:
            pass

    def test_safe_lifecycle(self):
        config = _MockConfig()
        sandbox = PluginSandbox(config, timeout=5)
        plugin = _DummyPlugin()
        api = sandbox.create_api(plugin)
        sandbox.safe_load(plugin, api)
        assert plugin.state == PluginState.LOADED
        sandbox.safe_activate(plugin)
        assert plugin.state == PluginState.ACTIVATED
        sandbox.safe_deactivate(plugin)
        assert plugin.state == PluginState.DEACTIVATED
        sandbox.safe_unload(plugin)
        assert plugin.state == PluginState.UNLOADED
