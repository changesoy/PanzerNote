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
import tempfile
import time
from typing import Optional

from ..utils.logger import get_logger
from .path_validator import PathValidator, PathSecurityError
from .file_access_context import FileAccessContext


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
            blocks = getattr(result, "st_blocks", None)
            if blocks is not None:
                return int(blocks) * 512
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

    @staticmethod
    def _should_validate(validate_path: bool, context: Optional[FileAccessContext]) -> bool:
        """根据访问上下文决定是否需要路径白名单校验

        明确上下文的调用已通过 FileOpenService 或内部路径校验，
        无需重复走 PathValidator 白名单。仅未指定上下文时按 validate_path 决定。
        """
        if context is not None:
            return False
        return validate_path

    def safe_read(
        self,
        filepath: str,
        encoding: str = 'utf-8',
        validate_path: bool = True,
        context: Optional[FileAccessContext] = None,
    ) -> str:
        """安全读取文件内容（分块读取 + 超时检测）

        Args:
            filepath: 文件路径
            encoding: 文件编码
            validate_path: 是否验证路径安全性
            context: 文件访问上下文（优先级高于 validate_path）

        Returns:
            文件内容字符串

        Raises:
            PathSecurityError: 路径不安全
            FileSizeExceededError: 文件大小超限
            FileOperationTimeoutError: 操作超时
        """
        if self._should_validate(validate_path, context):
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
        context: Optional[FileAccessContext] = None,
    ) -> None:
        """安全写入文件内容（原子写入）

        先写同目录临时文件再 os.replace 原子替换目标：
        写入中途崩溃/断电时目标保持完整旧版本，不会半写损坏；
        并发写同一文件时目标始终是某个完整版本（last-write-wins），
        不会出现字节交错。临时文件前缀 .pn_tmp_ 便于识别残留。

        Args:
            filepath: 文件路径
            content: 写入内容
            encoding: 文件编码
            validate_path: 是否验证路径安全性
            context: 文件访问上下文（优先级高于 validate_path）

        Raises:
            PathSecurityError: 路径不安全
            FileSizeExceededError: 内容大小超限
            FileEncodingError: 编码失败
        """
        if self._should_validate(validate_path, context):
            self._validator.validate_path(filepath)

        encoded_content = content.encode(encoding)
        content_size = len(encoded_content)
        if content_size > self._max_file_size:
            raise FileSizeExceededError(
                f"写入内容大小超过限制 ({self._max_file_size} 字节)"
            )

        self._atomic_write(filepath, encoded_content)

    def _atomic_write(self, filepath: str, data: bytes) -> None:
        """原子写入：同目录临时文件 + os.replace 原子替换目标。

        临时文件与目标同目录（同一文件系统）保证 os.replace 原子性；
        失败时清理临时文件并重新抛出异常，不留下半写目标文件。
        """
        target_dir = os.path.dirname(os.path.abspath(filepath))
        os.makedirs(target_dir, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(dir=target_dir, prefix=".pn_tmp_", suffix=".tmp")
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
            # 保留原文件权限（mkstemp 默认 0600）：Unix 下避免替换后丢失 0644 等
            try:
                st = os.stat(filepath)
                os.chmod(temp_path, st.st_mode)
            except OSError:
                pass
            os.replace(temp_path, filepath)
        except BaseException:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
        self._logger.debug("原子写入文件: %s (%d 字节)", filepath, len(data))

    def safe_read_bytes(
        self,
        filepath: str,
        validate_path: bool = True,
        context: Optional[FileAccessContext] = None,
    ) -> bytes:
        """安全读取二进制文件（分块读取 + 超时检测）

        Args:
            filepath: 文件路径
            validate_path: 是否验证路径安全性
            context: 文件访问上下文（优先级高于 validate_path）

        Returns:
            文件二进制内容
        """
        if self._should_validate(validate_path, context):
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
        context: Optional[FileAccessContext] = None,
    ) -> None:
        """安全写入二进制文件（原子写入，见 _atomic_write）

        Args:
            filepath: 文件路径
            data: 二进制数据
            validate_path: 是否验证路径安全性
            context: 文件访问上下文（优先级高于 validate_path）
        """
        if self._should_validate(validate_path, context):
            self._validator.validate_path(filepath)

        if len(data) > self._max_file_size:
            raise FileSizeExceededError(
                f"写入数据大小超过限制 ({self._max_file_size} 字节)"
            )

        self._atomic_write(filepath, data)
