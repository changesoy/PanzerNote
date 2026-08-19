# -*- coding: utf-8 -*-
"""
统一输入验证框架

提供文件名验证、搜索内容验证、设置值验证等统一接口。
确保所有用户输入必经验证流程，防止注入攻击和恶意输入。

用法:
    from src.security.input_validator import InputValidator

    validator = InputValidator()

    if validator.validate_filename(name):
        ...

    validator.validate_setting("font_size", 12, int, min_val=1, max_val=72)
"""

import re
from typing import Any, Callable, Dict, List, Optional, Type, Union

from ..utils.logger import get_logger


class ValidationError(ValueError):
    pass


class FilenameValidationError(ValidationError):
    pass


class SearchValidationError(ValidationError):
    pass


class SettingValidationError(ValidationError):
    pass


class InputValidator:
    MAX_FILENAME_LENGTH = 255
    MAX_SEARCH_LENGTH = 10000
    MAX_SETTING_STRING_LENGTH = 1000

    _FILENAME_INVALID_CHARS = re.compile(r'[<>:"|?*\\/\x00-\x1f]')
    _WINDOWS_RESERVED_NAMES = frozenset({
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
    })
    _SEARCH_DANGEROUS_PATTERNS = [
        re.compile(r'<script[^>]*>', re.IGNORECASE),
        re.compile(r'javascript:', re.IGNORECASE),
        re.compile(r'on\w+\s*=', re.IGNORECASE),
        re.compile(r'data:text/html', re.IGNORECASE),
        re.compile(r'vbscript:', re.IGNORECASE),
    ]
    _PATH_INJECTION_PATTERNS = [
        re.compile(r'\.\.[/\\]'),
        re.compile(r'[/\\]\.\.[/\\]'),
        re.compile(r'[/\\]\.\.$'),
        re.compile(r'^\.\.[/\\]'),
    ]

    def __init__(self):
        self._custom_validators: Dict[str, List[Callable]] = {}
        self._logger = get_logger(__name__)

    def validate_filename(self, filename: str) -> bool:
        """验证文件名是否安全

        规则：
        - 非空字符串
        - 长度不超过 255
        - 不包含非法字符 <>:"|?* 及控制字符
        - 不是 Windows 保留名称
        - 不以点号开头或结尾
        - 不包含目录穿越模式
        """
        if not filename or not isinstance(filename, str):
            return False
        if not filename.strip():
            return False
        error = self._check_filename_rules(filename)
        if error is not None:
            self._logger.warning("文件名验证失败: %s", error)
            return False
        return True

    def validate_filename_strict(self, filename: str) -> str:
        """严格验证文件名，失败时抛出异常

        Returns:
            验证通过的文件名
        """
        if not filename or not isinstance(filename, str):
            raise FilenameValidationError("文件名为空或类型无效")
        if not filename.strip():
            raise FilenameValidationError("文件名为空白")
        error = self._check_filename_rules(filename)
        if error is not None:
            raise FilenameValidationError(error)
        return filename

    def _check_filename_rules(self, filename: str) -> Optional[str]:
        """共享文件名规则校验（供 validate_filename / validate_filename_strict 使用）

        Returns:
            首个违规原因；文件名合法时返回 None
        """
        if len(filename) > self.MAX_FILENAME_LENGTH:
            return f"文件名过长: {len(filename)} > {self.MAX_FILENAME_LENGTH}"
        match = self._FILENAME_INVALID_CHARS.search(filename)
        if match:
            return f"文件名包含非法字符: {match.group()!r}"
        name_without_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
        if name_without_ext.upper() in self._WINDOWS_RESERVED_NAMES:
            return f"文件名是 Windows 保留名称: {filename}"
        if filename.startswith('.') or filename.endswith('.'):
            return "文件名不能以点号开头或结尾"
        for pattern in self._PATH_INJECTION_PATTERNS:
            if pattern.search(filename):
                return "文件名包含路径注入模式"
        return None

    def sanitize_filename(self, filename: str) -> str:
        """清理文件名，替换非法字符

        Returns:
            清理后的安全文件名
        """
        if not filename or not isinstance(filename, str):
            return "untitled"
        result = self._FILENAME_INVALID_CHARS.sub('_', filename)
        name_without_ext = result.rsplit('.', 1)[0] if '.' in result else result
        if name_without_ext.upper() in self._WINDOWS_RESERVED_NAMES:
            result = f"_{result}"
        result = result.strip('.')
        if not result:
            return "untitled"
        if len(result) > self.MAX_FILENAME_LENGTH:
            name, ext = result.rsplit('.', 1) if '.' in result else (result, '')
            max_name_len = self.MAX_FILENAME_LENGTH - len(ext) - 1 if ext else self.MAX_FILENAME_LENGTH
            result = name[:max_name_len] + ('.' + ext if ext else '')
        return result

    def validate_search(self, search_text: str) -> bool:
        """验证搜索内容是否安全

        规则：
        - 非空字符串
        - 长度不超过限制
        - 不包含危险 HTML/JS 模式
        """
        if not search_text or not isinstance(search_text, str):
            return False
        if len(search_text) > self.MAX_SEARCH_LENGTH:
            self._logger.warning("搜索内容过长: %d > %d", len(search_text), self.MAX_SEARCH_LENGTH)
            return False
        for pattern in self._SEARCH_DANGEROUS_PATTERNS:
            if pattern.search(search_text):
                self._logger.warning("搜索内容包含危险模式")
                return False
        return True

    def validate_search_strict(self, search_text: str) -> str:
        """严格验证搜索内容，失败时抛出异常"""
        if not search_text or not isinstance(search_text, str):
            raise SearchValidationError("搜索内容为空或类型无效")
        if len(search_text) > self.MAX_SEARCH_LENGTH:
            raise SearchValidationError(f"搜索内容过长: {len(search_text)} > {self.MAX_SEARCH_LENGTH}")
        for pattern in self._SEARCH_DANGEROUS_PATTERNS:
            if pattern.search(search_text):
                raise SearchValidationError("搜索内容包含潜在危险模式")
        return search_text

    def sanitize_search(self, search_text: str) -> str:
        """清理搜索内容，移除危险模式"""
        if not search_text:
            return ""
        result = search_text
        for pattern in self._SEARCH_DANGEROUS_PATTERNS:
            result = pattern.sub('', result)
        if len(result) > self.MAX_SEARCH_LENGTH:
            result = result[:self.MAX_SEARCH_LENGTH]
        return result

    def validate_setting(
        self,
        key: str,
        value: Any,
        expected_type: Type,
        min_val: Optional[Union[int, float]] = None,
        max_val: Optional[Union[int, float]] = None,
        allowed_values: Optional[List[Any]] = None,
        max_length: Optional[int] = None,
    ) -> Any:
        """验证设置值

        Args:
            key: 设置键名
            value: 设置值
            expected_type: 期望类型
            min_val: 最小值（数值类型）
            max_val: 最大值（数值类型）
            allowed_values: 允许的值列表
            max_length: 最大长度（字符串类型）

        Returns:
            验证通过的值

        Raises:
            SettingValidationError: 验证失败
        """
        if not key or not isinstance(key, str):
            raise SettingValidationError("设置键名无效")

        if not isinstance(value, expected_type):
            if expected_type == float and isinstance(value, int):
                value = float(value)
            else:
                raise SettingValidationError(
                    f"设置 '{key}' 类型错误: 期望 {expected_type.__name__}, 实际 {type(value).__name__}"
                )

        if expected_type in (int, float):
            if min_val is not None and value < min_val:
                raise SettingValidationError(
                    f"设置 '{key}' 值过小: {value} < {min_val}"
                )
            if max_val is not None and value > max_val:
                raise SettingValidationError(
                    f"设置 '{key}' 值过大: {value} > {max_val}"
                )

        if expected_type == str:
            if max_length is not None and len(value) > max_length:
                raise SettingValidationError(
                    f"设置 '{key}' 字符串过长: {len(value)} > {max_length}"
                )
            if len(value) > self.MAX_SETTING_STRING_LENGTH:
                raise SettingValidationError(
                    f"设置 '{key}' 字符串超过最大长度限制"
                )

        if allowed_values is not None and value not in allowed_values:
            raise SettingValidationError(
                f"设置 '{key}' 值不在允许列表中: {value!r}"
            )

        return value

    def register_validator(self, key: str, validator: Callable[[Any], bool]) -> None:
        """注册自定义验证器

        Args:
            key: 设置键名
            validator: 验证函数，返回 True 表示通过
        """
        if key not in self._custom_validators:
            self._custom_validators[key] = []
        self._custom_validators[key].append(validator)

    def validate_custom(self, key: str, value: Any) -> bool:
        """使用自定义验证器验证值

        Args:
            key: 设置键名
            value: 待验证值

        Returns:
            是否通过所有自定义验证器
        """
        validators = self._custom_validators.get(key, [])
        if not validators:
            return True
        for validator in validators:
            try:
                if not validator(value):
                    self._logger.warning("自定义验证失败: key=%s, value=%r", key, value)
                    return False
            except Exception as e:
                self._logger.error("自定义验证器异常: key=%s, error=%s", key, e)
                return False
        return True
