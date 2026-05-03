# -*- coding: utf-8 -*-
from src.utils.dpi_helper import (
    scale, scale_size, scale_font, scale_stylesheet, dp,
    scale_factor, init_dpi
)


class TestDpiHelper:
    def test_scale_factor_default(self):
        factor = scale_factor()
        assert factor >= 1.0
        assert factor <= 3.0

    def test_scale_int(self):
        result = scale(100)
        assert isinstance(result, int)
        assert result >= 100

    def test_scale_minimum(self):
        result = scale(0)
        assert result >= 0

    def test_scale_small_value(self):
        result = scale(1)
        assert result >= 1

    def test_scale_size(self):
        result = scale_size(800, 600)
        assert result.width() >= 800
        assert result.height() >= 600

    def test_scale_font(self):
        result = scale_font(12)
        assert isinstance(result, int)
        assert result >= 8

    def test_scale_font_minimum(self):
        result = scale_font(1)
        assert result >= 8

    def test_dp_alias(self):
        assert dp(100) == scale(100)

    def test_scale_stylesheet_no_px(self):
        result = scale_stylesheet("color: red;")
        assert result == "color: red;"

    def test_scale_stylesheet_with_px(self):
        result = scale_stylesheet("font-size: 12px;")
        assert "px" in result
        assert "12px" not in result or scale_factor() == 1.0

    def test_scale_stylesheet_multiple_px(self):
        result = scale_stylesheet("margin: 10px; padding: 5px;")
        assert "px" in result

    def test_scale_stylesheet_preserves_non_px(self):
        result = scale_stylesheet("border-radius: 4px; color: #333;")
        assert "#333" in result

    def test_init_dpi_idempotent(self):
        init_dpi()
        factor1 = scale_factor()
        init_dpi()
        factor2 = scale_factor()
        assert factor1 == factor2
