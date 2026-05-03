# -*- coding: utf-8 -*-
import os
import tempfile

import pytest

from src.security.file_guard import (
    FileGuard,
    FileSizeExceededError,
    FileOperationTimeoutError,
    FileSecurityError,
    FileEncodingError,
)
from src.security.path_validator import PathValidator


class TestFileGuardInit:
    def test_default_values(self):
        guard = FileGuard()
        assert guard.max_file_size == 50 * 1024 * 1024
        assert guard.timeout == 30

    def test_custom_values(self):
        guard = FileGuard(max_file_size=1024, timeout=5)
        assert guard.max_file_size == 1024
        assert guard.timeout == 5

    def test_invalid_max_file_size(self):
        with pytest.raises(ValueError):
            guard = FileGuard(max_file_size=1024)
            guard.max_file_size = -1

    def test_invalid_timeout(self):
        with pytest.raises(ValueError):
            guard = FileGuard(timeout=5)
            guard.timeout = 0


class TestFileGuardReadWrite:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.validator = PathValidator()
        self.validator.add_allowed_root(self.tmp_dir)
        self.guard = FileGuard(
            path_validator=self.validator,
            max_file_size=1024 * 1024,
            timeout=10,
        )

    def test_safe_read_write(self):
        filepath = os.path.join(self.tmp_dir, "test.txt")
        self.guard.safe_write(filepath, "hello world")
        content = self.guard.safe_read(filepath)
        assert content == "hello world"

    def test_safe_read_nonexistent(self):
        filepath = os.path.join(self.tmp_dir, "nonexistent.txt")
        with pytest.raises(FileNotFoundError):
            self.guard.safe_read(filepath)

    def test_safe_write_creates_dirs(self):
        filepath = os.path.join(self.tmp_dir, "subdir", "test.txt")
        self.guard.safe_write(filepath, "content")
        assert os.path.exists(filepath)

    def test_safe_read_write_bytes(self):
        filepath = os.path.join(self.tmp_dir, "test.bin")
        data = b"\x00\x01\x02\x03"
        self.guard.safe_write_bytes(filepath, data)
        result = self.guard.safe_read_bytes(filepath)
        assert result == data

    def test_safe_write_content_too_large(self):
        guard = FileGuard(
            path_validator=self.validator,
            max_file_size=10,
            timeout=5,
        )
        filepath = os.path.join(self.tmp_dir, "big.txt")
        with pytest.raises(FileSizeExceededError):
            guard.safe_write(filepath, "a" * 100)

    def test_safe_write_bytes_too_large(self):
        guard = FileGuard(
            path_validator=self.validator,
            max_file_size=10,
            timeout=5,
        )
        filepath = os.path.join(self.tmp_dir, "big.bin")
        with pytest.raises(FileSizeExceededError):
            guard.safe_write_bytes(filepath, b"\x00" * 100)

    def test_path_validation_on_write(self):
        filepath = "/outside/whitelist/test.txt"
        with pytest.raises(Exception):
            self.guard.safe_write(filepath, "content")

    def test_path_validation_on_read(self):
        filepath = "/outside/whitelist/test.txt"
        with pytest.raises(Exception):
            self.guard.safe_read(filepath)

    def test_skip_path_validation(self):
        filepath = os.path.join(self.tmp_dir, "test.txt")
        self.guard.safe_write(filepath, "content", validate_path=False)
        content = self.guard.safe_read(filepath, validate_path=False)
        assert content == "content"

    def test_safe_read_with_encoding(self):
        filepath = os.path.join(self.tmp_dir, "gbk.txt")
        content = "中文测试"
        with open(filepath, 'w', encoding='gbk') as f:
            f.write(content)
        result = self.guard.safe_read(filepath, encoding='gbk')
        assert result == content


class TestFileSizeCheck:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.validator = PathValidator()
        self.validator.add_allowed_root(self.tmp_dir)

    def test_check_file_size_within_limit(self):
        guard = FileGuard(
            path_validator=self.validator,
            max_file_size=1024 * 1024,
        )
        filepath = os.path.join(self.tmp_dir, "small.txt")
        with open(filepath, 'w') as f:
            f.write("small")
        assert guard.check_file_size(filepath)

    def test_check_file_size_exceeds_limit(self):
        guard = FileGuard(
            path_validator=self.validator,
            max_file_size=10,
        )
        filepath = os.path.join(self.tmp_dir, "big.txt")
        with open(filepath, 'w') as f:
            f.write("a" * 100)
        assert not guard.check_file_size(filepath)

    def test_check_nonexistent_file(self):
        guard = FileGuard(path_validator=self.validator)
        assert not guard.check_file_size("/nonexistent/file.txt")


class TestGetRealFileSize:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.validator = PathValidator()
        self.validator.add_allowed_root(self.tmp_dir)
        self.guard = FileGuard(path_validator=self.validator)

    def test_normal_file_size(self):
        filepath = os.path.join(self.tmp_dir, "test.txt")
        content = "hello world"
        with open(filepath, 'w') as f:
            f.write(content)
        size = self.guard.get_real_file_size(filepath)
        assert size > 0

    def test_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            self.guard.get_real_file_size("/nonexistent/file.txt")

    def test_symlink_size(self):
        target = os.path.join(self.tmp_dir, "target.txt")
        with open(target, 'w') as f:
            f.write("target content")

        link = os.path.join(self.tmp_dir, "link.txt")
        try:
            os.symlink(target, link)
            size = self.guard.get_real_file_size(link)
            assert size > 0
        except OSError:
            pass


class TestFileGuardEdgeCases:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.validator = PathValidator()
        self.validator.add_allowed_root(self.tmp_dir)

    def test_broken_symlink_raises_security_error(self):
        target = os.path.join(self.tmp_dir, "target.txt")
        with open(target, 'w') as f:
            f.write("content")

        link = os.path.join(self.tmp_dir, "link.txt")
        try:
            os.symlink(target, link)
            os.remove(target)
            with pytest.raises(FileSecurityError):
                guard = FileGuard(path_validator=self.validator)
                guard.get_real_file_size(link)
        except OSError:
            pass

    def test_get_disk_size_stat_error(self):
        guard = FileGuard(path_validator=self.validator)
        with pytest.raises(FileSecurityError):
            guard._get_disk_size("/nonexistent/path/file.txt")

    def test_max_file_size_property(self):
        guard = FileGuard(max_file_size=100)
        guard.max_file_size = 200
        assert guard.max_file_size == 200

    def test_timeout_property(self):
        guard = FileGuard(timeout=10)
        guard.timeout = 20
        assert guard.timeout == 20

    def test_safe_write_bytes_creates_dirs(self):
        guard = FileGuard(path_validator=self.validator, timeout=10)
        filepath = os.path.join(self.tmp_dir, "sub", "test.bin")
        guard.safe_write_bytes(filepath, b"\x00\x01\x02")
        result = guard.safe_read_bytes(filepath)
        assert result == b"\x00\x01\x02"

    def test_safe_write_bytes_too_large(self):
        guard = FileGuard(path_validator=self.validator, max_file_size=5, timeout=5)
        filepath = os.path.join(self.tmp_dir, "big.bin")
        with pytest.raises(FileSizeExceededError):
            guard.safe_write_bytes(filepath, b"\x00" * 100)

    def test_safe_read_bytes_nonexistent(self):
        guard = FileGuard(path_validator=self.validator, timeout=5)
        filepath = os.path.join(self.tmp_dir, "nonexistent.bin")
        with pytest.raises(FileNotFoundError):
            guard.safe_read_bytes(filepath)

    def test_safe_read_bytes_file_too_large(self):
        guard = FileGuard(path_validator=self.validator, max_file_size=10, timeout=5)
        filepath = os.path.join(self.tmp_dir, "big.bin")
        with open(filepath, 'wb') as f:
            f.write(b"\x00" * 100)
        with pytest.raises(FileSizeExceededError):
            guard.safe_read_bytes(filepath)

    def test_safe_read_existing_file_too_large(self):
        guard = FileGuard(path_validator=self.validator, max_file_size=10, timeout=5)
        filepath = os.path.join(self.tmp_dir, "large.txt")
        with open(filepath, 'w') as f:
            f.write("a" * 100)
        with pytest.raises(FileSizeExceededError):
            guard.safe_read(filepath)

    def test_safe_write_content_size_exceeds_limit(self):
        guard = FileGuard(path_validator=self.validator, max_file_size=10, timeout=5)
        filepath = os.path.join(self.tmp_dir, "big2.txt")
        with pytest.raises(FileSizeExceededError):
            guard.safe_write(filepath, "a" * 100)

    def test_safe_write_bytes_data_exceeds_limit(self):
        guard = FileGuard(path_validator=self.validator, max_file_size=10, timeout=5)
        filepath = os.path.join(self.tmp_dir, "big2.bin")
        with pytest.raises(FileSizeExceededError):
            guard.safe_write_bytes(filepath, b"\x00" * 100)

    def test_safe_write_bytes_creates_parent_dirs(self):
        guard = FileGuard(path_validator=self.validator, max_file_size=1024 * 1024, timeout=10)
        filepath = os.path.join(self.tmp_dir, "deep", "nested", "test.bin")
        guard.safe_write_bytes(filepath, b"\x01\x02\x03")
        assert os.path.exists(filepath)

    def test_safe_read_bytes_with_path_validation(self):
        guard = FileGuard(path_validator=self.validator, max_file_size=1024 * 1024, timeout=10)
        filepath = os.path.join(self.tmp_dir, "test_val.bin")
        guard.safe_write_bytes(filepath, b"\xAA\xBB")
        result = guard.safe_read_bytes(filepath, validate_path=True)
        assert result == b"\xAA\xBB"


class TestCalculateEncodedSize:
    def test_ascii_utf8(self):
        size = FileGuard.calculate_encoded_size("hello", "utf-8")
        assert size == 5

    def test_chinese_utf8(self):
        size = FileGuard.calculate_encoded_size("中文", "utf-8")
        assert size == 6

    def test_chinese_gbk(self):
        size = FileGuard.calculate_encoded_size("中文", "gbk")
        assert size == 4

    def test_empty_string(self):
        size = FileGuard.calculate_encoded_size("", "utf-8")
        assert size == 0

    def test_emoji_utf8(self):
        size = FileGuard.calculate_encoded_size("🎉", "utf-8")
        assert size == 4

    def test_mixed_content_utf8(self):
        size = FileGuard.calculate_encoded_size("Hello世界🎉", "utf-8")
        assert size == 5 + 6 + 4

    def test_unsupported_encoding_raises(self):
        with pytest.raises(FileEncodingError):
            FileGuard.calculate_encoded_size("中文测试", "ascii")

    def test_japanese_shift_jis(self):
        size = FileGuard.calculate_encoded_size("こんにちは", "shift_jis")
        assert size == 10

    def test_default_encoding_is_utf8(self):
        assert FileGuard.calculate_encoded_size("中文") == 6

    def test_size_matches_actual_file(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            validator = PathValidator()
            validator.add_allowed_root(tmp_dir)
            guard = FileGuard(path_validator=validator, max_file_size=1024 * 1024, timeout=5)

            content = "Hello世界🎉"
            filepath = os.path.join(tmp_dir, "size_test.txt")
            guard.safe_write(filepath, content, encoding="utf-8")

            actual_size = os.path.getsize(filepath)
            calculated_size = FileGuard.calculate_encoded_size(content, "utf-8")
            assert actual_size == calculated_size
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestSafeWriteEncoding:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.validator = PathValidator()
        self.validator.add_allowed_root(self.tmp_dir)
        self.guard = FileGuard(
            path_validator=self.validator,
            max_file_size=1024 * 1024,
            timeout=10,
        )

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_write_chinese_utf8(self):
        filepath = os.path.join(self.tmp_dir, "cn_utf8.txt")
        content = "中文测试内容"
        self.guard.safe_write(filepath, content, encoding="utf-8")
        result = self.guard.safe_read(filepath, encoding="utf-8")
        assert result == content

    def test_write_chinese_gbk(self):
        filepath = os.path.join(self.tmp_dir, "cn_gbk.txt")
        content = "中文测试内容"
        self.guard.safe_write(filepath, content, encoding="gbk")
        result = self.guard.safe_read(filepath, encoding="gbk")
        assert result == content

    def test_write_emoji_utf8(self):
        filepath = os.path.join(self.tmp_dir, "emoji.txt")
        content = "🎉🚀💻"
        self.guard.safe_write(filepath, content, encoding="utf-8")
        result = self.guard.safe_read(filepath, encoding="utf-8")
        assert result == content

    def test_write_mixed_content(self):
        filepath = os.path.join(self.tmp_dir, "mixed.txt")
        content = "Hello世界🎉\n第二行"
        self.guard.safe_write(filepath, content, encoding="utf-8")
        result = self.guard.safe_read(filepath, encoding="utf-8")
        assert result == content

    def test_write_unsupported_encoding_raises(self):
        filepath = os.path.join(self.tmp_dir, "bad.txt")
        with pytest.raises(UnicodeEncodeError):
            self.guard.safe_write(filepath, "中文", encoding="ascii")

    def test_write_size_limit_with_multibyte_encoding(self):
        guard = FileGuard(
            path_validator=self.validator,
            max_file_size=10,
            timeout=5,
        )
        filepath = os.path.join(self.tmp_dir, "big_cn.txt")
        with pytest.raises(FileSizeExceededError):
            guard.safe_write(filepath, "中文中文中文中文", encoding="utf-8")

    def test_write_size_exact_limit(self):
        content = "a" * 10
        guard = FileGuard(
            path_validator=self.validator,
            max_file_size=10,
            timeout=5,
        )
        filepath = os.path.join(self.tmp_dir, "exact.txt")
        guard.safe_write(filepath, content, encoding="utf-8")
        result = self.guard.safe_read(filepath)
        assert result == content

    def test_write_size_one_over_limit(self):
        content = "a" * 11
        guard = FileGuard(
            path_validator=self.validator,
            max_file_size=10,
            timeout=5,
        )
        filepath = os.path.join(self.tmp_dir, "over.txt")
        with pytest.raises(FileSizeExceededError):
            guard.safe_write(filepath, content, encoding="utf-8")

    def test_write_chinese_size_boundary(self):
        guard = FileGuard(
            path_validator=self.validator,
            max_file_size=6,
            timeout=5,
        )
        filepath = os.path.join(self.tmp_dir, "cn_exact.txt")
        guard.safe_write(filepath, "中文", encoding="utf-8")
        result = self.guard.safe_read(filepath, encoding="utf-8")
        assert result == "中文"

    def test_write_chinese_size_one_byte_over(self):
        guard = FileGuard(
            path_validator=self.validator,
            max_file_size=5,
            timeout=5,
        )
        filepath = os.path.join(self.tmp_dir, "cn_over.txt")
        with pytest.raises(FileSizeExceededError):
            guard.safe_write(filepath, "中文", encoding="utf-8")

    def test_encoded_size_not_sys_getsizeof(self):
        import sys
        content = "中文测试"
        encoded_size = FileGuard.calculate_encoded_size(content, "utf-8")
        sizeof_size = sys.getsizeof(content)
        assert encoded_size == 12
        assert sizeof_size > encoded_size
        assert encoded_size < sizeof_size
