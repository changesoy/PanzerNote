# -*- coding: utf-8 -*-
from unittest.mock import patch

import pytest

from src.utils.feature_flags import (
    is_enabled,
    set_enabled,
    get_all_flags,
    init_flags,
    _FLAGS,
)


@pytest.fixture(autouse=True)
def reset_flags():
    original = dict(_FLAGS)
    yield
    _FLAGS.clear()
    _FLAGS.update(original)


class TestIsEnabled:
    def test_registered_flag_true(self):
        set_enabled("virtual_scroll", True)
        assert is_enabled("virtual_scroll") is True

    def test_registered_flag_false(self):
        set_enabled("virtual_scroll", False)
        assert is_enabled("virtual_scroll") is False

    def test_unregistered_flag_returns_false(self):
        assert is_enabled("nonexistent_flag") is False

    def test_unregistered_flag_logs_warning(self):
        with patch('src.utils.feature_flags.get_logger') as mock_logger:
            mock_log_instance = mock_logger.return_value
            is_enabled("typo_flag")
            mock_log_instance.warning.assert_called_once()
            call_args = mock_log_instance.warning.call_args
            assert "未注册的 feature flag" in call_args[0][0]
            assert "typo_flag" in call_args[0][1]

    def test_registered_flag_does_not_log_warning(self):
        with patch('src.utils.feature_flags.get_logger') as mock_logger:
            mock_log_instance = mock_logger.return_value
            is_enabled("virtual_scroll")
            mock_log_instance.warning.assert_not_called()

    def test_all_default_flags_are_false(self):
        for flag_name in _FLAGS:
            assert is_enabled(flag_name) is False


class TestSetEnabled:
    def test_set_registered_flag_true(self):
        set_enabled("virtual_scroll", True)
        assert is_enabled("virtual_scroll") is True

    def test_set_registered_flag_false(self):
        set_enabled("virtual_scroll", True)
        set_enabled("virtual_scroll", False)
        assert is_enabled("virtual_scroll") is False

    def test_set_unregistered_flag_does_not_modify(self):
        set_enabled("nonexistent_flag", True)
        assert "nonexistent_flag" not in _FLAGS

    def test_set_unregistered_flag_logs_warning(self):
        with patch('src.utils.feature_flags.get_logger') as mock_logger:
            mock_log_instance = mock_logger.return_value
            set_enabled("typo_flag", True)
            mock_log_instance.warning.assert_called_once()
            call_args = mock_log_instance.warning.call_args
            assert "未注册的 feature flag" in call_args[0][0]
            assert "typo_flag" in call_args[0][1]

    def test_set_registered_flag_does_not_log_warning(self):
        with patch('src.utils.feature_flags.get_logger') as mock_logger:
            mock_log_instance = mock_logger.return_value
            set_enabled("virtual_scroll", True)
            mock_log_instance.warning.assert_not_called()


class TestGetAllFlags:
    def test_returns_all_flags(self):
        flags = get_all_flags()
        assert isinstance(flags, dict)
        assert "virtual_scroll" in flags
        assert "minimap_block_cache" in flags
        assert "async_highlight" in flags
        assert "markdown_incremental" in flags
        assert "lazy_loading" in flags

    def test_returns_copy(self):
        flags1 = get_all_flags()
        flags1["virtual_scroll"] = True
        flags2 = get_all_flags()
        assert flags2["virtual_scroll"] is False


class TestInitFlags:
    def test_init_flags_without_config_file(self, tmp_path):
        init_flags(str(tmp_path))
        assert is_enabled("virtual_scroll") is False

    def test_init_flags_with_config_file(self, tmp_path):
        config_file = tmp_path / "feature_flags.json"
        config_file.write_text('{"virtual_scroll": true}', encoding="utf-8")
        init_flags(str(tmp_path))
        assert is_enabled("virtual_scroll") is True

    def test_init_flags_with_invalid_json(self, tmp_path):
        config_file = tmp_path / "feature_flags.json"
        config_file.write_text('invalid json', encoding="utf-8")
        init_flags(str(tmp_path))
        assert is_enabled("virtual_scroll") is False
