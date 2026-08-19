# -*- coding: utf-8 -*-
"""
配置导入服务

安全导入 JSON 配置文件，逐字段校验类型和值范围，
非法字段跳过并报告，合法字段通过 Config setter 写入。
不再直接 _settings.update() / _workspace.update()。
"""

import json as json_module
from typing import Dict, List, Optional, Tuple

from ..utils.logger import get_logger
from .workspace_store import WorkspaceStore


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

    _SETTINGS_TYPE_RULES: Dict[str, tuple] = {
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

    _SETTINGS_RANGE_RULES: Dict[str, Tuple[Optional[float], Optional[float]]] = {
        "active_tab_index": (0, None),
        "chars_typed_today": (0, None),
        "total_chars": (0, None),
        "total_documents": (0, None),
    }

    _SETTINGS_NESTED_RULES: Dict[str, Dict[str, Tuple[tuple, Optional[Tuple[Optional[float], Optional[float]]]]]] = {
        "editor": {
            "font_family": ((str,), None),
            "font_size": ((int,), (1, 200)),
            "line_spacing": ((int, float), (0.5, 5.0)),
            "show_line_numbers": ((bool,), None),
            "auto_wrap": ((bool,), None),
            "wrap_mode": ((str,), None),
            "highlight_current_line": ((bool,), None),
            "auto_save_interval": ((int,), (0, 3600)),
            "max_history_count": ((int,), (0, 1000)),
            "default_encoding": ((str,), None),
            "line_ending": ((str,), None),
            "code_highlight_theme": ((str,), None),
            "show_minimap": ((bool,), None),
            "auto_minimap": ((bool,), None),
            "auto_pair_brackets": ((bool,), None),
            "indent_size": ((int,), (1, 8)),
            "use_tabs": ((bool,), None),
        },
        "game": {
            "typing_reward_rate": ((int, float), (0, None)),
            "idle_reward_rate": ((int, float), (0, None)),
            "daily_typing_limit": ((int,), (0, None)),
            "construction_time_rate": ((int, float), (0, None)),
            "construction_slots": ((int,), (1, 10)),
        },
        "secretary": {
            "character_id": ((str, type(None)), None),
            "character_name": ((str, type(None)), None),
            "skin_name": ((str, type(None)), None),
            "state": ((str,), None),
            "user_nickname": ((str,), None),
            "secretary_self": ((str,), None),
            "enable_voice": ((bool,), None),
            "show_secretary": ((bool,), None),
            "size_percent": ((int, float), (1, 100)),
        },
        "view": {
            "theme": ((str,), None),
            "sidebar_width": ((int,), (50, 800)),
            "show_file_tree": ((bool,), None),
        },
        "window": {
            "width": ((int,), (100, None)),
            "height": ((int,), (100, None)),
            "x": ((int,), None),
            "y": ((int,), None),
            "maximized": ((bool,), None),
        },
    }

    # 单一来源：直接复用 WorkspaceStore 的白名单（由 DEFAULT_WORKSPACE 派生）
    _KNOWN_WORKSPACE_KEYS = WorkspaceStore._KNOWN_WORKSPACE_KEYS

    _WORKSPACE_TYPE_RULES: Dict[str, tuple] = {
        "last_session": (dict,),
        "bookmarks": (dict,),
        "folds": (dict,),
        "recent_files": (list,),
        "external_files": (list,),
        "closed_tabs_memory": (dict,),
    }

    _WORKSPACE_NESTED_RULES: Dict[str, Dict[str, Tuple[tuple, Optional[Tuple[Optional[float], Optional[float]]]]]] = {
        "last_session": {
            "open_files": ((list,), None),
            "active_tab_index": ((int,), (0, None)),
            "current_view": ((str,), None),
        },
    }

    _NUMERIC_KEYS_REJECT_BOOL: frozenset = frozenset({
        "chars_typed_today",
        "total_chars",
        "total_documents",
        "active_tab_index",
    })

    _NESTED_NUMERIC_REJECT_BOOL: Dict[str, frozenset] = {
        "editor": frozenset({"font_size", "line_spacing", "auto_save_interval", "max_history_count"}),
        "game": frozenset({"typing_reward_rate", "idle_reward_rate", "daily_typing_limit", "construction_time_rate", "construction_slots"}),
        "secretary": frozenset({"size_percent"}),
        "view": frozenset({"sidebar_width"}),
        "window": frozenset({"width", "height", "x", "y"}),
        "last_session": frozenset({"active_tab_index"}),
        "resources": frozenset({"steel", "oil", "ammo", "fuel", "rare_metal"}),
        "cores": frozenset({"total", "available"}),
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

    def _check_type(self, value, expected_types: tuple, reject_bool: bool = False) -> bool:
        if reject_bool and isinstance(value, bool) and bool not in expected_types:
            return False
        return isinstance(value, expected_types)

    def _check_range(self, value, range_rule: Optional[Tuple[Optional[float], Optional[float]]]) -> bool:
        if range_rule is None:
            return True
        lo, hi = range_rule
        if lo is not None and value < lo:
            return False
        if hi is not None and value > hi:
            return False
        return True

    def _validate_setting(self, key: str, value) -> bool:
        expected_types = self._SETTINGS_TYPE_RULES.get(key)
        if expected_types:
            reject_bool = key in self._NUMERIC_KEYS_REJECT_BOOL
            if not self._check_type(value, expected_types, reject_bool=reject_bool):
                self._skip(key, f"期望 {expected_types}，实际: {type(value).__name__}")
                return False

        range_rule = self._SETTINGS_RANGE_RULES.get(key)
        if range_rule and not self._check_range(value, range_rule):
            lo, hi = range_rule
            self._skip(key, f"值 {value} 超出范围 [{lo}, {hi}]")
            return False

        if isinstance(value, dict):
            for sub_key in value:
                if not isinstance(sub_key, str):
                    self._skip(key, "含非字符串键名")
                    return False
            nested_rules = self._SETTINGS_NESTED_RULES.get(key)
            if nested_rules:
                if not self._validate_nested(f"settings.{key}", value, nested_rules):
                    return False

        return True

    def _validate_workspace_field(self, key: str, value) -> bool:
        expected_types = self._WORKSPACE_TYPE_RULES.get(key)
        if expected_types:
            if not self._check_type(value, expected_types):
                self._skip(f"workspace.{key}", f"期望 {expected_types}，实际: {type(value).__name__}")
                return False

        if isinstance(value, dict):
            for sub_key in value:
                if not isinstance(sub_key, str):
                    self._skip(f"workspace.{key}", "含非字符串键名")
                    return False
            nested_rules = self._WORKSPACE_NESTED_RULES.get(key)
            if nested_rules:
                if not self._validate_nested(f"workspace.{key}", value, nested_rules):
                    return False

        return True

    def _validate_nested(
        self,
        prefix: str,
        data: dict,
        rules: Dict[str, Tuple[tuple, Optional[Tuple[Optional[float], Optional[float]]]]],
    ) -> bool:
        valid = True
        section_name = prefix.split(".")[-1]
        numeric_keys = self._NESTED_NUMERIC_REJECT_BOOL.get(section_name, frozenset())

        for sub_key, sub_value in data.items():
            if not isinstance(sub_key, str):
                self._skip(f"{prefix}.{sub_key}", "非字符串键名")
                valid = False
                continue

            rule = rules.get(sub_key)
            if rule is None:
                self._skip(f"{prefix}.{sub_key}", "未知字段")
                valid = False
                continue

            expected_types, range_rule = rule
            reject_bool = sub_key in numeric_keys

            if not self._check_type(sub_value, expected_types, reject_bool=reject_bool):
                self._skip(f"{prefix}.{sub_key}", f"期望 {expected_types}，实际: {type(sub_value).__name__}")
                valid = False
                continue

            if range_rule and not self._check_range(sub_value, range_rule):
                lo, hi = range_rule
                self._skip(f"{prefix}.{sub_key}", f"值 {sub_value} 超出范围 [{lo}, {hi}]")
                valid = False

        return valid

    def _skip(self, key: str, reason: str):
        msg = f"设置项 '{key}' 校验失败: {reason}"
        self._logger.warning(msg)
        self._skipped.append(msg)
