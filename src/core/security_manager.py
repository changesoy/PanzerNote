# -*- coding: utf-8 -*-
"""
安全管理器
负责路径验证、文件安全守卫、输入验证等安全相关功能
"""

from typing import Any

from ..security.path_validator import PathValidator
from ..security.file_guard import FileGuard
from ..security.input_validator import InputValidator
from ..utils.logger import get_logger


class SecurityManager:
    """安全管理器

    从 Config 中拆出，集中管理所有安全相关组件。
    """

    def __init__(
        self,
        path_validator: PathValidator,
        file_guard: FileGuard,
        input_validator: InputValidator,
    ):
        self._path_validator = path_validator
        self._file_guard = file_guard
        self._input_validator = input_validator
        self._logger = get_logger(__name__)

    @property
    def path_validator(self) -> PathValidator:
        return self._path_validator

    @property
    def file_guard(self) -> FileGuard:
        return self._file_guard

    @property
    def input_validator(self) -> InputValidator:
        return self._input_validator

    def add_allowed_root(self, root_path: str):
        self._path_validator.add_allowed_root(root_path)

    def validate_setting_value(
        self,
        key: str,
        value: Any,
        expected_type: type,
        min_val=None,
        max_val=None,
        allowed_values=None,
    ) -> Any:
        return self._input_validator.validate_setting(
            key, value, expected_type,
            min_val=min_val,
            max_val=max_val,
            allowed_values=allowed_values,
        )
