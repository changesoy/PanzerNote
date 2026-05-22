# -*- coding: utf-8 -*-
"""
配置导入服务

安全导入 JSON 配置文件，逐字段校验类型和值范围，
非法字段跳过并报告，合法字段通过 Config setter 写入。
不再直接 _settings.update() / _workspace.update()。
"""

import json as json_module
from typing import Dict, List

from ..utils.logger import get_logger


class ConfigImportError(Exception):
    pass


class ConfigImportService:
    """配置导入校验服务

    用法：
        service = ConfigImportService(config)
        skipped = service.import_from_json(json_text)
        if skipped:
            show_warning(f"以下字段格式不正确已跳过: {skipped}")
    """

    _KNOWN_SETTINGS_KEYS = frozenset({
        "initialized", "base_path",
        "editor", "game", "secretary", "view", "window", "shortcuts",
        "open_files", "active_tab_index", "recent_files", "external_files",
        "last_login", "chars_typed_today", "total_chars", "total_documents",
    })

    _SETTINGS_TYPE_RULES = {
        "initialized": (bool,),
        "base_path": (str,),
        "open_files": (list,),
        "active_tab_index": (int,),
        "recent_files": (list,),
        "external_files": (list,),
        "last_login": (str,),
        "chars_typed_today": (int, float),
        "total_chars": (int, float),
        "total_documents": (int, float),
        "editor": (dict,),
        "game": (dict,),
        "secretary": (dict,),
        "view": (dict,),
        "window": (dict,),
        "shortcuts": (dict,),
    }

    _KNOWN_WORKSPACE_KEYS = frozenset({
        "last_session", "recent_files", "external_files",
        "editor", "game", "secretary", "view", "window",
        "resources", "cores",
    })

    _WORKSPACE_TYPE_RULES = {
        "last_session": (dict,),
        "recent_files": (list,),
        "external_files": (list,),
        "editor": (dict,),
        "game": (dict,),
        "secretary": (dict,),
        "view": (dict,),
        "window": (dict,),
        "resources": (dict,),
        "cores": (dict,),
    }

    def __init__(self, config):
        self._config = config
        self._logger = get_logger(__name__)
        self._skipped: List[str] = []

    def import_from_json(self, json_text: str) -> List[str]:
        """从 JSON 字符串导入配置

        Returns:
            被跳过的字段描述列表，空列表说明全部校验通过
        """
        self._skipped.clear()
        try:
            data = json_module.loads(json_text)
        except json_module.JSONDecodeError as e:
            raise ConfigImportError(f"JSON 解析失败: {e}")

        if not isinstance(data, dict):
            raise ConfigImportError("无效的设置文件格式，应为 JSON 对象")

        if "settings" not in data:
            raise ConfigImportError("无效的设置文件格式，缺少 settings 字段")

        self._import_settings(data.get("settings", {}))
        self._import_workspace(data.get("workspace", {}))
        self._config.save()

        return list(self._skipped)

    def _import_settings(self, data: dict):
        if not isinstance(data, dict):
            self._skip("settings", "settings 字段不是 JSON 对象")
            return
        for key, value in data.items():
            if not isinstance(key, str):
                self._skip(key, "键名非字符串")
                continue
            if key not in self._KNOWN_SETTINGS_KEYS:
                self._skip(key, "未知设置字段")
                continue
            if not self._validate_setting(key, value):
                continue
            self._config.set_setting(key, value)

    def _import_workspace(self, data: dict):
        if not isinstance(data, dict):
            self._skip("workspace", "workspace 字段不是 JSON 对象")
            return
        for key, value in data.items():
            if not isinstance(key, str):
                self._skip(key, "键名非字符串")
                continue
            if key not in self._KNOWN_WORKSPACE_KEYS:
                self._skip(f"workspace.{key}", "未知 workspace 字段")
                continue
            if not self._validate_workspace_field(key, value):
                continue
            try:
                self._config.update_workspace_field(key, value)
            except KeyError:
                self._skip(f"workspace.{key}", "未知字段")

    def _validate_setting(self, key: str, value) -> bool:
        expected_types = self._SETTINGS_TYPE_RULES.get(key)
        if expected_types and not isinstance(value, expected_types):
            self._skip(key, f"期望 {expected_types}，实际: {type(value).__name__}")
            return False
        if isinstance(value, dict):
            for sub_key in value:
                if not isinstance(sub_key, str):
                    self._skip(key, "含非字符串键名")
                    return False
        return True

    def _validate_workspace_field(self, key: str, value) -> bool:
        expected_types = self._WORKSPACE_TYPE_RULES.get(key)
        if expected_types and not isinstance(value, expected_types):
            self._skip(f"workspace.{key}", f"期望 {expected_types}，实际: {type(value).__name__}")
            return False
        if isinstance(value, dict):
            for sub_key in value:
                if not isinstance(sub_key, str):
                    self._skip(f"workspace.{key}", "含非字符串键名")
                    return False
        return True

    def _skip(self, key: str, reason: str):
        msg = f"设置项 '{key}' 校验失败: {reason}"
        self._logger.warning(msg)
        self._skipped.append(msg)
