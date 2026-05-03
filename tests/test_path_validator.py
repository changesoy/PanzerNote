# -*- coding: utf-8 -*-
import os
import tempfile

import pytest

from src.security.path_validator import (
    PathValidator,
    PathSecurityError,
    PathTraversalError,
    PathNotInWhitelistError,
)


class TestPathValidatorNormalize:
    def setup_method(self):
        self.validator = PathValidator()

    def test_normalize_absolute_path(self):
        result = self.validator.normalize("/tmp/test")
        assert result is not None
        assert os.path.isabs(result)

    def test_normalize_relative_path(self):
        result = self.validator.normalize("some/relative/path")
        assert result is not None
        assert os.path.isabs(result)

    def test_normalize_empty_string(self):
        assert self.validator.normalize("") is None

    def test_normalize_none(self):
        assert self.validator.normalize(None) is None

    def test_normalize_non_string(self):
        assert self.validator.normalize(123) is None

    def test_normalize_whitespace_only(self):
        assert self.validator.normalize("   ") is None

    def test_normalize_strips_whitespace(self):
        result = self.validator.normalize("  /tmp/test  ")
        assert result is not None
        assert result == result.strip()


class TestPathTraversal:
    def setup_method(self):
        self.validator = PathValidator()

    def test_unix_traversal(self):
        assert self.validator.is_path_traversal("../../../etc/passwd")

    def test_windows_traversal(self):
        assert self.validator.is_path_traversal("..\\..\\windows\\system32")

    def test_mixed_traversal(self):
        assert self.validator.is_path_traversal("../..\\etc/passwd")

    def test_traversal_at_end(self):
        assert self.validator.is_path_traversal("/some/path/..")

    def test_traversal_at_start(self):
        assert self.validator.is_path_traversal("../safe/path")

    def test_safe_path_no_traversal(self):
        assert not self.validator.is_path_traversal("/safe/normal/path")

    def test_safe_path_with_dots_in_name(self):
        assert not self.validator.is_path_traversal("/path/to/file.test.py")

    def test_empty_path(self):
        assert self.validator.is_path_traversal("")

    def test_none_path(self):
        assert self.validator.is_path_traversal(None)


class TestPathWhitelist:
    def setup_method(self):
        self.validator = PathValidator()
        self.tmp_dir = tempfile.mkdtemp()
        self.validator.add_allowed_root(self.tmp_dir)

    def test_path_in_whitelist(self):
        filepath = os.path.join(self.tmp_dir, "test.txt")
        assert self.validator.is_path_in_whitelist(filepath)

    def test_root_itself_in_whitelist(self):
        assert self.validator.is_path_in_whitelist(self.tmp_dir)

    def test_path_not_in_whitelist(self):
        assert not self.validator.is_path_in_whitelist("/some/other/path")

    def test_empty_whitelist_rejects_all(self):
        empty_validator = PathValidator()
        assert not empty_validator.is_path_in_whitelist("/any/path")

    def test_remove_allowed_root(self):
        self.validator.remove_allowed_root(self.tmp_dir)
        assert not self.validator.is_path_in_whitelist(self.tmp_dir)

    def test_get_allowed_roots(self):
        roots = self.validator.get_allowed_roots()
        assert len(roots) == 1

    def test_case_insensitive_on_windows(self):
        if os.name == 'nt':
            upper = self.tmp_dir.upper()
            lower = self.tmp_dir.lower()
            self.validator.add_allowed_root(lower)
            assert self.validator.is_path_in_whitelist(upper)


class TestPathSafe:
    def setup_method(self):
        self.validator = PathValidator()
        self.tmp_dir = tempfile.mkdtemp()
        self.validator.add_allowed_root(self.tmp_dir)

    def test_safe_path(self):
        filepath = os.path.join(self.tmp_dir, "safe.txt")
        assert self.validator.is_path_safe(filepath)

    def test_traversal_path_unsafe(self):
        filepath = os.path.join(self.tmp_dir, "../../../etc/passwd")
        assert not self.validator.is_path_safe(filepath)

    def test_path_outside_whitelist_unsafe(self):
        assert not self.validator.is_path_safe("/outside/whitelist/path")

    def test_empty_path_unsafe(self):
        assert not self.validator.is_path_safe("")

    def test_none_path_unsafe(self):
        assert not self.validator.is_path_safe(None)

    def test_very_long_path_unsafe(self):
        long_path = "/a" * 200
        assert not self.validator.is_path_safe(long_path)


class TestValidatePath:
    def setup_method(self):
        self.validator = PathValidator()
        self.tmp_dir = tempfile.mkdtemp()
        self.validator.add_allowed_root(self.tmp_dir)

    def test_validate_safe_path_returns_normalized(self):
        filepath = os.path.join(self.tmp_dir, "test.txt")
        result = self.validator.validate_path(filepath)
        assert os.path.isabs(result)

    def test_validate_empty_raises(self):
        with pytest.raises(PathSecurityError):
            self.validator.validate_path("")

    def test_validate_traversal_raises(self):
        with pytest.raises(PathTraversalError):
            self.validator.validate_path("../../../etc/passwd")

    def test_validate_not_in_whitelist_raises(self):
        with pytest.raises(PathNotInWhitelistError):
            self.validator.validate_path("/outside/whitelist")


class TestValidateFilename:
    def setup_method(self):
        self.validator = PathValidator()

    def test_valid_filename(self):
        assert self.validator.validate_filename("test.txt")

    def test_valid_filename_with_spaces(self):
        assert self.validator.validate_filename("my document.txt")

    def test_valid_chinese_filename(self):
        assert self.validator.validate_filename("测试文件.txt")

    def test_empty_filename(self):
        assert not self.validator.validate_filename("")

    def test_filename_with_colon(self):
        assert not self.validator.validate_filename("test:file.txt")

    def test_filename_with_angle_brackets(self):
        assert not self.validator.validate_filename("test<file>.txt")

    def test_filename_with_pipe(self):
        assert not self.validator.validate_filename("test|file.txt")

    def test_filename_with_question_mark(self):
        assert not self.validator.validate_filename("test?file.txt")

    def test_filename_with_asterisk(self):
        assert not self.validator.validate_filename("test*file.txt")

    def test_reserved_name_con(self):
        assert not self.validator.validate_filename("CON")

    def test_reserved_name_aux(self):
        assert not self.validator.validate_filename("AUX")

    def test_reserved_name_com1(self):
        assert not self.validator.validate_filename("COM1")

    def test_filename_starting_with_dot(self):
        assert not self.validator.validate_filename(".hidden")

    def test_filename_ending_with_dot(self):
        assert not self.validator.validate_filename("test.")

    def test_very_long_filename(self):
        assert not self.validator.validate_filename("a" * 256)

    def test_filename_with_control_chars(self):
        assert not self.validator.validate_filename("test\x00file.txt")


class TestLongPathPrefix:
    def setup_method(self):
        self.validator = PathValidator()

    def test_strip_long_path_prefix(self):
        result = PathValidator._strip_long_path_prefix("\\\\?\\C:\\test")
        assert result == "C:\\test"

    def test_no_long_path_prefix(self):
        result = PathValidator._strip_long_path_prefix("C:\\test")
        assert result == "C:\\test"


class TestCaseNormalize:
    def test_case_normalize_windows(self):
        result = PathValidator._case_normalize("C:\\Test")
        if os.name == 'nt':
            assert result == "c:\\test"
        else:
            assert result == "C:\\Test"


class TestPathValidatorEdgeCases:
    def setup_method(self):
        self.validator = PathValidator()

    def test_add_remove_root(self):
        self.validator.add_allowed_root("/tmp")
        roots = self.validator.get_allowed_roots()
        assert len(roots) >= 1
        self.validator.remove_allowed_root("/tmp")
        roots = self.validator.get_allowed_roots()
        assert len(roots) == 0

    def test_is_path_safe_non_string(self):
        assert not self.validator.is_path_safe(123)

    def test_is_path_traversal_with_number(self):
        assert self.validator.is_path_traversal(123)
