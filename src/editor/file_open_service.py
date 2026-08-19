# -*- coding: utf-8 -*-
"""
文件打开服务
统一文件打开入口，所有用户打开、拖放、插件、会话恢复、设置导入
文件访问都走本服务，不再由各调用方各自绕开安全逻辑。

创建者：MainWindow / PluginContext / FileTree / EditorTabWidget
持有者：MainWindow（单例生命周期）
完成通知：同步返回
失败通知：抛出 FileOpenSecurityError / 返回 False
关闭时行为：同步服务，无异步清理
"""

import os
from enum import Enum
from typing import Set

from ..utils.logger import get_logger
from ..security.path_validator import PathValidator, PathSecurityError


class FileOpenSource(Enum):
    USER_DIALOG = "user_dialog"
    DRAG_DROP = "drag_drop"
    PLUGIN = "plugin"
    SESSION_RESTORE = "session_restore"
    SETTINGS_IMPORT = "settings_import"
    INTERNAL = "internal"


class FileOpenSecurityError(Exception):
    pass


_TEXT_EXTENSIONS: Set[str] = {
    '.txt', '.md', '.py', '.json', '.xml', '.html', '.htm',
    '.css', '.js', '.ts', '.jsx', '.tsx', '.yaml', '.yml',
    '.toml', '.cfg', '.ini', '.conf', '.properties',
    '.c', '.cpp', '.h', '.hpp', '.java', '.go', '.rs',
    '.swift', '.kt', '.rb', '.lua', '.sh', '.bat', '.ps1',
    '.sql', '.r', '.m', '.mm', '.pl', '.php', '.scala',
    '.cs', '.vb', '.f90', '.f95', '.log', '.csv', '.rst',
    '.tex', '.bib', '.makefile', '.cmake', '.dockerfile',
    '.gitignore', '.gitattributes', '.editorconfig',
    '.env', '.envrc', '.markdown',
}

_DANGEROUS_EXTENSIONS: Set[str] = {
    '.exe', '.dll', '.so', '.dylib', '.sys', '.drv',
    '.bin', '.dat', '.db', '.sqlite', '.mdb',
    '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz',
    '.iso', '.dmg', '.img',
    '.class', '.pyc', '.pyd', '.o', '.obj', '.a', '.lib',
    '.woff', '.woff2', '.ttf', '.otf', '.eot',
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg', '.webp',
    '.mp3', '.mp4', '.avi', '.mkv', '.mov', '.wav', '.flac',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
}

_MAX_PLUGIN_FILE_SIZE = 10 * 1024 * 1024
_MAX_SETTINGS_IMPORT_SIZE = 5 * 1024 * 1024
_MAX_USER_FILE_SIZE = 100 * 1024 * 1024


def _is_inside_root(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


def _is_dangerous_extension(filepath: str) -> bool:
    ext = os.path.splitext(filepath)[1].lower()
    return ext in _DANGEROUS_EXTENSIONS


def _is_known_text_extension(filepath: str) -> bool:
    ext = os.path.splitext(filepath)[1].lower()
    return ext in _TEXT_EXTENSIONS


def _is_binary_file(filepath: str) -> bool:
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(8192)
        if b'\x00' in chunk:
            return True
        return False
    except Exception:
        return True


class FileOpenService:
    """统一文件打开安全服务"""

    ALL_USER_SOURCES = {FileOpenSource.USER_DIALOG, FileOpenSource.DRAG_DROP}

    def __init__(self, path_validator: PathValidator, notebooks_path: str):
        self._validator = path_validator
        self._notebooks_path = os.path.normpath(notebooks_path)
        self._logger = get_logger(__name__)

    @property
    def notebooks_path(self) -> str:
        return self._notebooks_path

    def validate_open_request(
        self,
        filepath: str,
        source: FileOpenSource,
    ) -> str:
        """验证文件打开请求，返回规范化路径

        参数：
          filepath：文件路径
          source：打开来源

        返回：规范化后的安全路径

        异常：FileOpenSecurityError
        """
        if not filepath or not isinstance(filepath, str):
            raise FileOpenSecurityError("文件路径为空或类型无效")

        normalized = self._norm(filepath)

        if source in self.ALL_USER_SOURCES:
            return self._validate_user_open(normalized, source)
        elif source == FileOpenSource.PLUGIN:
            return self._validate_plugin_open(normalized)
        elif source == FileOpenSource.SESSION_RESTORE:
            return self._validate_session_restore(normalized)
        elif source == FileOpenSource.SETTINGS_IMPORT:
            return self._validate_settings_import(normalized)
        elif source == FileOpenSource.INTERNAL:
            return normalized
        else:
            raise FileOpenSecurityError(f"未知的文件打开来源: {source}")

    def _norm(self, filepath: str) -> str:
        try:
            return os.path.realpath(filepath)
        except (OSError, ValueError):
            try:
                return os.path.abspath(filepath)
            except (OSError, ValueError):
                raise FileOpenSecurityError(f"无法解析文件路径: {filepath}")

    def _validate_user_open(self, filepath: str, source: FileOpenSource) -> str:
        if not os.path.isfile(filepath):
            raise FileOpenSecurityError(f"文件不存在: {filepath}")

        if _is_dangerous_extension(filepath):
            raise FileOpenSecurityError(
                f"不支持的文件类型: {os.path.splitext(filepath)[1]}"
            )

        if not _is_known_text_extension(filepath):
            if _is_binary_file(filepath):
                raise FileOpenSecurityError("不支持二进制文件")

        size = os.path.getsize(filepath)
        if size > _MAX_USER_FILE_SIZE:
            raise FileOpenSecurityError(
                f"文件过大 ({size} > {_MAX_USER_FILE_SIZE} 字节)"
            )

        try:
            return self._validator.validate_path(filepath)
        except PathSecurityError:
            normalized = os.path.normpath(filepath)
            if not _is_inside_root(normalized, self._notebooks_path):
                self._logger.warning(
                    "文件不在 notebooks 白名单中，允许外部打开: %s", filepath
                )
            return normalized

    def _validate_plugin_open(self, filepath: str) -> str:
        if not os.path.isfile(filepath):
            raise FileOpenSecurityError(f"文件不存在: {filepath}")

        normalized = os.path.normpath(filepath)

        if not _is_inside_root(normalized, self._notebooks_path):
            raise FileOpenSecurityError(
                "插件只能打开 notebooks 目录内的文件"
            )

        if _is_dangerous_extension(filepath):
            raise FileOpenSecurityError(
                f"不支持的文件类型: {os.path.splitext(filepath)[1]}"
            )

        size = os.path.getsize(filepath)
        if size > _MAX_PLUGIN_FILE_SIZE:
            raise FileOpenSecurityError(
                f"文件过大 ({size} > {_MAX_PLUGIN_FILE_SIZE} 字节)"
            )

        if not _is_known_text_extension(filepath):
            if _is_binary_file(filepath):
                raise FileOpenSecurityError("不支持二进制文件")

        return normalized

    def _validate_session_restore(self, filepath: str) -> str:
        if not os.path.isfile(filepath):
            raise FileOpenSecurityError(f"会话恢复文件不存在: {filepath}")

        try:
            return self._validator.validate_path(filepath)
        except PathSecurityError:
            normalized = os.path.normpath(filepath)
            if _is_inside_root(normalized, self._notebooks_path):
                return normalized
            raise FileOpenSecurityError(
                f"会话恢复路径不在允许范围内: {filepath}"
            )

    def _validate_settings_import(self, filepath: str) -> str:
        ext = os.path.splitext(filepath)[1].lower()
        if ext != '.json':
            raise FileOpenSecurityError("设置导入只支持 .json 文件")

        if not os.path.isfile(filepath):
            raise FileOpenSecurityError(f"文件不存在: {filepath}")

        size = os.path.getsize(filepath)
        if size > _MAX_SETTINGS_IMPORT_SIZE:
            raise FileOpenSecurityError(
                f"设置文件过大 ({size} > {_MAX_SETTINGS_IMPORT_SIZE} 字节)"
            )

        return os.path.abspath(filepath)
