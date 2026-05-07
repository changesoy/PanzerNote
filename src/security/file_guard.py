# -*- coding: utf-8 -*-
"""
文件操作安全控制模块

提供文件大小限制、分块读取超时控制、安全文件读写等功能。
正确处理符号链接、稀疏文件等特殊文件类型。

超时机制说明：
  safe_read / safe_read_bytes 采用分块读取 + 累计时间检测。
  每读取一个 chunk 后检查累计耗时，超过 timeout 则中断读取。
  优点：在主线程中执行，可真正中断；无需 daemon 线程。
  限制：单次 read(chunk_size) 本身若阻塞（如 NFS 挂载），
  无法在 Python 层面中断，此时超时精度取决于 chunk 读取耗时。
  对于本地 SSD/HDD，chunk 读取通常在毫秒级，超时精度足够。

用法:
    from src.security.file_guard import FileGuard

    guard = FileGuard(max_file_size=50 * 1024 * 1024, timeout=30)

    content = guard.safe_read(filepath)
    guard.safe_write(filepath, content)
"""

import os
import time
from typing import Optional

from ..utils.logger import get_logger
from .path_validator import PathValidator, PathSecurityError


class FileSizeExceededError(Exception):
    pass


class FileOperationTimeoutError(Exception):
    pass


class FileSecurityError(Exception):
    pass


class FileEncodingError(Exception):
    pass


_READ_CHUNK_SIZE = 64 * 1024


class FileGuard:
    DEFAULT_MAX_FILE_SIZE = 50 * 1024 * 1024
    DEFAULT_TIMEOUT = 30

    def __init__(
        self,
        path_validator: Optional[PathValidator] = None,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self._validator = path_validator or PathValidator()
        self._max_file_size = max_file_size
        self._timeout = timeout
        self._logger = get_logger(__name__)

    @property
    def max_file_size(self) -> int:
        return self._max_file_size

    @max_file_size.setter
    def max_file_size(self, value: int) -> None:
        if value <= 0:
            raise ValueError("最大文件大小必须为正数")
        self._max_file_size = value

    @property
    def timeout(self) -> int:
        return self._timeout

    @timeout.setter
    def timeout(self, value: int) -> None:
        if value <= 0:
            raise ValueError("超时时间必须为正数")
        self._timeout = value

    def get_real_file_size(self, filepath: str) -> int:
        """获取文件真实大小（处理符号链接、稀疏文件等）

        不使用 os.path.getsize，而是通过低级 API 获取真实磁盘占用。
        对于符号链接，获取链接目标的大小而非链接本身。
        对于稀疏文件，返回实际磁盘分配大小。
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"文件不存在: {filepath}")

        if os.path.islink(filepath):
            link_target = os.path.realpath(filepath)
            if not os.path.exists(link_target):
                raise FileSecurityError(f"符号链接目标不存在: {link_target}")
            return self._get_disk_size(link_target)

        return self._get_disk_size(filepath)

    @staticmethod
    def _get_disk_size(filepath: str) -> int:
        """获取文件实际磁盘占用大小"""
        try:
            result = os.stat(filepath)
            if hasattr(result, 'st_blocks'):
                return result.st_blocks * 512
            return result.st_size
        except OSError as e:
            raise FileSecurityError(f"无法获取文件大小: {e}")

    @staticmethod
    def calculate_encoded_size(content: str, encoding: str = 'utf-8') -> int:
        """计算字符串在指定编码下的实际字节大小

        使用 len(content.encode(encoding)) 而非 sys.getsizeof(content)，
        因为前者返回实际写入文件的字节数，后者返回 Python 对象的内存占用
        （包含 49-108 字节的对象头开销），与文件大小无关。

        Args:
            content: 待计算内容
            encoding: 目标编码

        Returns:
            编码后的字节大小

        Raises:
            FileEncodingError: 编码失败（如目标编码不支持内容中的字符）
        """
        try:
            return len(content.encode(encoding))
        except UnicodeEncodeError as e:
            raise FileEncodingError(
                f"内容无法使用 {encoding} 编码: {e}"
            )

    def check_file_size(self, filepath: str) -> bool:
        """检查文件大小是否在允许范围内"""
        try:
            size = self.get_real_file_size(filepath)
            if size > self._max_file_size:
                self._logger.warning(
                    "文件大小超限: %s (%d > %d)",
                    filepath, size, self._max_file_size
                )
                return False
            return True
        except (FileNotFoundError, FileSecurityError):
            return False

    def safe_read(
        self,
        filepath: str,
        encoding: str = 'utf-8',
        validate_path: bool = True,
    ) -> str:
        """安全读取文件内容（分块读取 + 超时检测）

        Args:
            filepath: 文件路径
            encoding: 文件编码
            validate_path: 是否验证路径安全性

        Returns:
            文件内容字符串

        Raises:
            PathSecurityError: 路径不安全
            FileSizeExceededError: 文件大小超限
            FileOperationTimeoutError: 操作超时
        """
        if validate_path:
            self._validator.validate_path(filepath)

        if os.path.exists(filepath):
            if not self.check_file_size(filepath):
                raise FileSizeExceededError(
                    f"文件大小超过限制 ({self._max_file_size} 字节): {filepath}"
                )

        chunks = []
        start = time.monotonic()
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                while True:
                    chunk = f.read(_READ_CHUNK_SIZE)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    if time.monotonic() - start > self._timeout:
                        raise FileOperationTimeoutError(
                            f"文件读取超时 ({self._timeout}秒): {filepath}"
                        )
        except FileOperationTimeoutError:
            raise
        except Exception as e:
            raise e

        return ''.join(chunks)

    def safe_write(
        self,
        filepath: str,
        content: str,
        encoding: str = 'utf-8',
        validate_path: bool = True,
    ) -> None:
        """安全写入文件内容

        Args:
            filepath: 文件路径
            content: 写入内容
            encoding: 文件编码
            validate_path: 是否验证路径安全性

        Raises:
            PathSecurityError: 路径不安全
            FileSizeExceededError: 内容大小超限
            FileEncodingError: 编码失败
        """
        if validate_path:
            self._validator.validate_path(filepath)

        encoded_content = content.encode(encoding)
        content_size = len(encoded_content)
        if content_size > self._max_file_size:
            raise FileSizeExceededError(
                f"写入内容大小超过限制 ({self._max_file_size} 字节)"
            )

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'wb') as f:
            f.write(encoded_content)

        self._logger.debug("安全写入文件: %s (%d 字节)", filepath, content_size)

    def safe_read_bytes(
        self,
        filepath: str,
        validate_path: bool = True,
    ) -> bytes:
        """安全读取二进制文件（分块读取 + 超时检测）

        Args:
            filepath: 文件路径
            validate_path: 是否验证路径安全性

        Returns:
            文件二进制内容
        """
        if validate_path:
            self._validator.validate_path(filepath)

        if os.path.exists(filepath):
            if not self.check_file_size(filepath):
                raise FileSizeExceededError(
                    f"文件大小超过限制 ({self._max_file_size} 字节): {filepath}"
                )

        chunks = []
        start = time.monotonic()
        try:
            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(_READ_CHUNK_SIZE)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    if time.monotonic() - start > self._timeout:
                        raise FileOperationTimeoutError(
                            f"文件读取超时 ({self._timeout}秒): {filepath}"
                        )
        except FileOperationTimeoutError:
            raise
        except Exception as e:
            raise e

        return b''.join(chunks)

    def safe_write_bytes(
        self,
        filepath: str,
        data: bytes,
        validate_path: bool = True,
    ) -> None:
        """安全写入二进制文件

        Args:
            filepath: 文件路径
            data: 二进制数据
            validate_path: 是否验证路径安全性
        """
        if validate_path:
            self._validator.validate_path(filepath)

        if len(data) > self._max_file_size:
            raise FileSizeExceededError(
                f"写入数据大小超过限制 ({self._max_file_size} 字节)"
            )

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'wb') as f:
            f.write(data)

        self._logger.debug("安全写入二进制文件: %s (%d 字节)", filepath, len(data))
