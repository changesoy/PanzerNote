# -*- coding: utf-8 -*-
"""
路径安全验证模块

提供路径规范化、白名单校验、目录穿越防护等安全功能。
特别处理 Windows 系统特性：大小写不敏感、长路径前缀等。

用法:
    from src.security.path_validator import PathValidator

    validator = PathValidator()
    validator.add_allowed_root("/path/to/user/data")
    validator.add_allowed_root("/path/to/app/assets")

    if validator.is_path_safe(filepath):
        ...
"""

import os
import re
from typing import Optional, Set

from ..utils.logger import get_logger


class PathSecurityError(Exception):
    pass


class PathTraversalError(PathSecurityError):
    pass


class PathNotInWhitelistError(PathSecurityError):
    pass


class PathValidator:
    MAX_PATH_LENGTH = 4096

    _TRAVERSAL_PATTERNS = [
        re.compile(r'\.\.[/\\]'),
        re.compile(r'[/\\]\.\.[/\\]'),
        re.compile(r'[/\\]\.\.$'),
        re.compile(r'^\.\.[/\\]'),
    ]

    _LONG_PATH_PREFIX = "\\\\?\\"

    def __init__(self):
        self._allowed_roots: Set[str] = set()
        self._logger = get_logger(__name__)

    def add_allowed_root(self, root_path: str) -> None:
        normalized = self.normalize(root_path)
        if normalized:
            self._allowed_roots.add(self._case_normalize(normalized))
            self._logger.debug("添加安全路径白名单: %s", normalized)

    def remove_allowed_root(self, root_path: str) -> None:
        normalized = self.normalize(root_path)
        if normalized:
            self._allowed_roots.discard(self._case_normalize(normalized))

    def get_allowed_roots(self) -> Set[str]:
        return set(self._allowed_roots)

    @staticmethod
    def normalize(path: str) -> Optional[str]:
        if not path or not isinstance(path, str):
            return None
        path = path.strip()
        if not path:
            return None
        path = path.replace('/', os.sep).replace('\\', os.sep)
        try:
            result = os.path.realpath(path)
        except (OSError, ValueError):
            try:
                result = os.path.abspath(path)
            except (OSError, ValueError):
                return None
        return result

    @staticmethod
    def _strip_long_path_prefix(path: str) -> str:
        if path.startswith(PathValidator._LONG_PATH_PREFIX):
            return path[len(PathValidator._LONG_PATH_PREFIX):]
        return path

    @staticmethod
    def _case_normalize(path: str) -> str:
        if os.name == 'nt':
            return path.lower()
        return path

    def is_path_traversal(self, path: str) -> bool:
        if not path or not isinstance(path, str):
            return True
        normalized = path.replace('\\', '/')
        for pattern in self._TRAVERSAL_PATTERNS:
            if pattern.search(normalized):
                return True
        return False

    def is_path_symlink_escape(self, path: str) -> bool:
        """检查符号链接是否逃逸到白名单之外

        不再简单用 realpath != abspath 拒绝所有 symlink。
        改为：解析 realpath → 检查 resolved path 是否仍在 allowed_roots 内。
        在 allowed_roots 内的合法 symlink 允许通过。
        逃逸到 allowed_roots 之外的 symlink 拒绝。
        """
        if not self._allowed_roots:
            return True

        try:
            real = os.path.realpath(path)
        except (OSError, ValueError):
            return True

        if os.path.islink(path):
            try:
                abs_path = os.path.abspath(path)
                if os.path.normcase(real) == os.path.normcase(abs_path):
                    return False
            except (OSError, ValueError):
                pass
        else:
            try:
                abs_path = os.path.abspath(path)
                if os.path.normcase(real) == os.path.normcase(abs_path):
                    return False
            except (OSError, ValueError):
                pass

        clean = self._strip_long_path_prefix(real)
        case_path = self._case_normalize(clean)
        for root in self._allowed_roots:
            if case_path == root or case_path.startswith(root + os.sep):
                return False

        self._logger.warning(
            "符号链接逃逸到白名单之外: %s -> %s", path, real
        )
        return True

    def is_path_in_whitelist(self, path: str) -> bool:
        if not self._allowed_roots:
            self._logger.warning("路径白名单为空，拒绝所有路径访问")
            return False
        normalized = self.normalize(path)
        if not normalized:
            return False
        clean = self._strip_long_path_prefix(normalized)
        case_path = self._case_normalize(clean)
        for root in self._allowed_roots:
            if case_path == root or case_path.startswith(root + os.sep):
                return True
        return False

    def is_path_safe(self, path: str) -> bool:
        if not path or not isinstance(path, str):
            self._logger.warning("路径为空或类型无效: %r", path)
            return False
        if len(path) > self.MAX_PATH_LENGTH:
            self._logger.debug("路径长度超限: %d > %d", len(path), self.MAX_PATH_LENGTH)
            return False
        if self.is_path_traversal(path):
            self._logger.warning("检测到目录穿越攻击: %s", path)
            return False
        if self.is_path_symlink_escape(path):
            self._logger.warning("检测到符号链接逃逸: %s", path)
            return False
        if not self.is_path_in_whitelist(path):
            self._logger.debug("路径不在白名单中: %s", path)
            return False
        return True

    def validate_path(self, path: str) -> str:
        if not path or not isinstance(path, str):
            raise PathSecurityError("路径为空或类型无效")
        if len(path) > self.MAX_PATH_LENGTH:
            raise PathSecurityError(f"路径长度超限: {len(path)} > {self.MAX_PATH_LENGTH}")
        if self.is_path_traversal(path):
            raise PathTraversalError(f"检测到目录穿越攻击: {path}")
        if self.is_path_symlink_escape(path):
            raise PathSecurityError(f"检测到符号链接逃逸: {path}")
        if not self.is_path_in_whitelist(path):
            raise PathNotInWhitelistError(f"路径不在白名单中: {path}")
        normalized = self.normalize(path)
        if not normalized:
            raise PathSecurityError("路径规范化失败")
        return normalized


