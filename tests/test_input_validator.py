# -*- coding: utf-8 -*-
import pytest

from src.security.input_validator import (
    InputValidator,
    ValidationError,
    FilenameValidationError,
    SearchValidationError,
    SettingValidationError,
)


class TestFilenameValidation:
    def setup_method(self):
        self.validator = InputValidator()

    def test_valid_filename(self):
        assert self.validator.validate_filename("test.txt")

    def test_valid_filename_no_ext(self):
        assert self.validator.validate_filename("README")

    def test_valid_filename_multiple_dots(self):
        assert self.validator.validate_filename("test.backup.txt")

    def test_valid_filename_with_spaces(self):
        assert self.validator.validate_filename("my document.txt")

    def test_valid_chinese_filename(self):
        assert self.validator.validate_filename("测试文件.txt")

    def test_valid_filename_with_hyphen_underscore(self):
        assert self.validator.validate_filename("my-test_file.txt")

    def test_empty_filename(self):
        assert not self.validator.validate_filename("")

    def test_whitespace_only_filename(self):
        assert not self.validator.validate_filename("   ")

    def test_none_filename(self):
        assert not self.validator.validate_filename(None)

    def test_non_string_filename(self):
        assert not self.validator.validate_filename(123)

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

    def test_filename_with_double_quotes(self):
        assert not self.validator.validate_filename('test"file.txt')

    def test_filename_with_control_chars(self):
        assert not self.validator.validate_filename("test\x00file.txt")

    def test_reserved_name_con(self):
        assert not self.validator.validate_filename("CON")

    def test_reserved_name_prn(self):
        assert not self.validator.validate_filename("PRN")

    def test_reserved_name_aux(self):
        assert not self.validator.validate_filename("AUX")

    def test_reserved_name_nul(self):
        assert not self.validator.validate_filename("NUL")

    def test_reserved_name_com1(self):
        assert not self.validator.validate_filename("COM1")

    def test_reserved_name_lpt1(self):
        assert not self.validator.validate_filename("LPT1")

    def test_filename_starting_with_dot(self):
        assert not self.validator.validate_filename(".hidden")

    def test_filename_ending_with_dot(self):
        assert not self.validator.validate_filename("test.")

    def test_very_long_filename(self):
        assert not self.validator.validate_filename("a" * 256)

    def test_filename_with_traversal(self):
        assert not self.validator.validate_filename("../../../etc/passwd")

    def test_filename_with_backslash_traversal(self):
        assert not self.validator.validate_filename("..\\..\\windows")


class TestFilenameStrict:
    def setup_method(self):
        self.validator = InputValidator()

    def test_valid_returns_filename(self):
        result = self.validator.validate_filename_strict("test.txt")
        assert result == "test.txt"

    def test_empty_raises(self):
        with pytest.raises(FilenameValidationError):
            self.validator.validate_filename_strict("")

    def test_invalid_chars_raises(self):
        with pytest.raises(FilenameValidationError):
            self.validator.validate_filename_strict("test:file.txt")

    def test_reserved_name_raises(self):
        with pytest.raises(FilenameValidationError):
            self.validator.validate_filename_strict("CON")

    def test_dot_start_raises(self):
        with pytest.raises(FilenameValidationError):
            self.validator.validate_filename_strict(".hidden")


class TestSanitizeFilename:
    def setup_method(self):
        self.validator = InputValidator()

    def test_sanitize_replaces_invalid_chars(self):
        result = self.validator.sanitize_filename("test:file?.txt")
        assert ":" not in result
        assert "?" not in result

    def test_sanitize_empty_returns_untitled(self):
        result = self.validator.sanitize_filename("")
        assert result == "untitled"

    def test_sanitize_reserved_name_prefix(self):
        result = self.validator.sanitize_filename("CON")
        assert result.startswith("_")

    def test_sanitize_strips_dots(self):
        result = self.validator.sanitize_filename(".test.")
        assert not result.startswith(".")
        assert not result.endswith(".")

    def test_sanitize_preserves_valid_chars(self):
        result = self.validator.sanitize_filename("valid-file_name.txt")
        assert result == "valid-file_name.txt"

    def test_sanitize_truncates_long_filename(self):
        long_name = "a" * 300 + ".txt"
        result = self.validator.sanitize_filename(long_name)
        assert len(result) <= 255


class TestSearchValidation:
    def setup_method(self):
        self.validator = InputValidator()

    def test_valid_search(self):
        assert self.validator.validate_search("hello world")

    def test_valid_search_with_regex_chars(self):
        assert self.validator.validate_search(r"\d+\.\w+")

    def test_empty_search(self):
        assert not self.validator.validate_search("")

    def test_none_search(self):
        assert not self.validator.validate_search(None)

    def test_script_tag_rejected(self):
        assert not self.validator.validate_search("<script>alert('xss')</script>")

    def test_javascript_protocol_rejected(self):
        assert not self.validator.validate_search("javascript:alert(1)")

    def test_event_handler_rejected(self):
        assert not self.validator.validate_search("onclick=alert(1)")

    def test_data_uri_rejected(self):
        assert not self.validator.validate_search("data:text/html,<h1>test</h1>")

    def test_vbscript_rejected(self):
        assert not self.validator.validate_search("vbscript:msgbox")

    def test_very_long_search(self):
        assert not self.validator.validate_search("a" * 10001)

    def test_search_strict_valid(self):
        result = self.validator.validate_search_strict("hello")
        assert result == "hello"

    def test_search_strict_dangerous_raises(self):
        with pytest.raises(SearchValidationError):
            self.validator.validate_search_strict("<script>alert(1)</script>")


class TestSanitizeSearch:
    def setup_method(self):
        self.validator = InputValidator()

    def test_sanitize_removes_script_tags(self):
        result = self.validator.sanitize_search("<script>alert(1)</script> hello")
        assert "<script>" not in result
        assert "hello" in result

    def test_sanitize_empty(self):
        assert self.validator.sanitize_search("") == ""

    def test_sanitize_none(self):
        assert self.validator.sanitize_search(None) == ""

    def test_sanitize_truncates_long(self):
        result = self.validator.sanitize_search("a" * 20000)
        assert len(result) <= 10000


class TestSettingValidation:
    def setup_method(self):
        self.validator = InputValidator()

    def test_valid_int_setting(self):
        result = self.validator.validate_setting("font_size", 12, int, min_val=1, max_val=72)
        assert result == 12

    def test_valid_float_setting(self):
        result = self.validator.validate_setting("line_spacing", 1.5, float, min_val=0.5, max_val=3.0)
        assert result == 1.5

    def test_valid_string_setting(self):
        result = self.validator.validate_setting("font_family", "YaHei", str, max_length=100)
        assert result == "YaHei"

    def test_valid_bool_setting(self):
        result = self.validator.validate_setting("show_line_numbers", True, bool)
        assert result is True

    def test_invalid_type_raises(self):
        with pytest.raises(SettingValidationError):
            self.validator.validate_setting("font_size", "not_a_number", int)

    def test_int_coerced_to_float(self):
        result = self.validator.validate_setting("line_spacing", 2, float, min_val=0.5, max_val=3.0)
        assert result == 2.0
        assert isinstance(result, float)

    def test_value_below_min_raises(self):
        with pytest.raises(SettingValidationError):
            self.validator.validate_setting("font_size", 0, int, min_val=1)

    def test_value_above_max_raises(self):
        with pytest.raises(SettingValidationError):
            self.validator.validate_setting("font_size", 100, int, max_val=72)

    def test_string_too_long_raises(self):
        with pytest.raises(SettingValidationError):
            self.validator.validate_setting("name", "a" * 2000, str)

    def test_allowed_values(self):
        result = self.validator.validate_setting(
            "wrap_mode", "no_wrap", str,
            allowed_values=["no_wrap", "wrap_at_edge"]
        )
        assert result == "no_wrap"

    def test_disallowed_value_raises(self):
        with pytest.raises(SettingValidationError):
            self.validator.validate_setting(
                "wrap_mode", "invalid", str,
                allowed_values=["no_wrap", "wrap_at_edge"]
            )

    def test_empty_key_raises(self):
        with pytest.raises(SettingValidationError):
            self.validator.validate_setting("", 12, int)


class TestCustomValidator:
    def setup_method(self):
        self.validator = InputValidator()

    def test_register_and_validate(self):
        self.validator.register_validator("custom_key", lambda v: v > 0)
        assert self.validator.validate_custom("custom_key", 5)

    def test_custom_validator_fails(self):
        self.validator.register_validator("custom_key", lambda v: v > 0)
        assert not self.validator.validate_custom("custom_key", -1)

    def test_no_custom_validator_passes(self):
        assert self.validator.validate_custom("unknown_key", "any_value")

    def test_custom_validator_exception_fails(self):
        def bad_validator(v):
            raise RuntimeError("oops")

        self.validator.register_validator("bad_key", bad_validator)
        assert not self.validator.validate_custom("bad_key", "value")

    def test_multiple_validators(self):
        self.validator.register_validator("multi", lambda v: v > 0)
        self.validator.register_validator("multi", lambda v: v < 100)
        assert self.validator.validate_custom("multi", 50)
        assert not self.validator.validate_custom("multi", -1)
        assert not self.validator.validate_custom("multi", 200)


class TestInputValidatorEdgeCases:
    def setup_method(self):
        self.validator = InputValidator()

    def test_filename_with_backslash(self):
        assert not self.validator.validate_filename("test\\file.txt")

    def test_filename_with_forward_slash(self):
        assert not self.validator.validate_filename("test/file.txt")

    def test_search_strict_empty_raises(self):
        with pytest.raises(SearchValidationError):
            self.validator.validate_search_strict("")

    def test_search_strict_none_raises(self):
        with pytest.raises(SearchValidationError):
            self.validator.validate_search_strict(None)

    def test_search_strict_too_long_raises(self):
        with pytest.raises(SearchValidationError):
            self.validator.validate_search_strict("a" * 10001)

    def test_setting_non_string_key_raises(self):
        with pytest.raises(SettingValidationError):
            self.validator.validate_setting(123, "value", str)

    def test_setting_string_max_length_param(self):
        result = self.validator.validate_setting("name", "short", str, max_length=10)
        assert result == "short"

    def test_setting_string_exceeds_param_max_length(self):
        with pytest.raises(SettingValidationError):
            self.validator.validate_setting("name", "a" * 11, str, max_length=10)

    def test_sanitize_filename_none(self):
        result = self.validator.sanitize_filename(None)
        assert result == "untitled"

    def test_sanitize_filename_non_string(self):
        result = self.validator.sanitize_filename(123)
        assert result == "untitled"

    def test_sanitize_filename_with_backslash(self):
        result = self.validator.sanitize_filename("test\\file.txt")
        assert "\\" not in result

    def test_sanitize_filename_with_slash(self):
        result = self.validator.sanitize_filename("test/file.txt")
        assert "/" not in result
