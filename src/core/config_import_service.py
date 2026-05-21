# -*- coding: utf-8 -*-
"""
配置导入服务

安全导入 JSON 配置文件，逐字段校验类型和值范围，
非法字段跳过并报告，合法字段通过 Config setter 写入。
不再直接 _settings.update() / _workspace.update()。
"""

import json as json_module
from typing import Dict, List, Tuple

from ..utils.logger import get_logger


class ConfigImportError(Exception):
    """配置导入错误"""
    pass


class ConfigImportService:
    """配置导入校验服务

    用法：
        service = ConfigImportService(config)
        skipped = service.import_from_dict(import_data)
        if skipped:
            show_warning(f"以下字段格式不正确已跳过: {skipped}")
    """

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
        for key, value in data.items():
            if not isinstance(key, str):
                self._skip(key, "键名非字符串")
                continue
            if self._validate_setting(key, value):
                self._config.set_setting(key, value)

    def _import_workspace(self, data: dict):
        if not isinstance(data, dict):
            self._skip("workspace", "workspace 字段不是 JSON 对象")
            return
        for key, value in data.items():
            if not isinstance(key, str):
                self._skip(key, "键名非字符串")
                continue
            if self._validate_workspace_field(key, value):
                self._config.get_workspace()[key] = value

    def _validate_setting(self, key: str, value) -> bool:
        if key in ("open_files", "active_tab_index", "recent_files", "external_files"):
            if not isinstance(value, list):
                self._skip(key, f"期望数组，实际: {type(value).__name__}")
                return False
        elif key in ("last_login",):
            if not isinstance(value, str):
                self._skip(key, f"期望字符串，实际: {type(value).__name__}")
                return False
        elif key in ("chars_typed_today", "total_chars", "total_documents"):
            if not isinstance(value, (int, float)):
                self._skip(key, f"期望数字，实际: {type(value).__name__}")
                return False
        return True

    def _validate_workspace_field(self, key: str, value) -> bool:
        if key in ("editor", "game", "secretary", "view", "window"):
            if not isinstance(value, dict):
                self._skip(f"workspace.{key}", f"期望对象，实际: {type(value).__name__}")
                return False
            for sub_key, sub_value in value.items():
                if not isinstance(sub_key, str):
                    self._skip(f"workspace.{key}", "含非字符串键名")
                    return False
        elif key in ("resources", "cores"):
            if not isinstance(value, dict):
                self._skip(f"workspace.{key}", f"期望对象，实际: {type(value).__name__}")
                return False
        return True

    def _skip(self, key: str, reason: str):
        msg = f"设置项 '{key}' 校验失败: {reason}"
        self._logger.warning(msg)
        self._skipped.append(msg)
