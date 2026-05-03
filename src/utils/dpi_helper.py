# -*- coding: utf-8 -*-
"""
高 DPI 适配工具

提供统一的缩放计算接口，所有视觉元素尺寸应通过本模块获取相对值。
基于 logicalDotsPerInch 或 devicePixelRatio 动态计算缩放系数。

使用方式:
    from src.utils.dpi_helper import DpiHelper

    # 获取缩放后的尺寸
    width = DpiHelper.scale(200)
    height = DpiHelper.scale(300)
    size = DpiHelper.scale_size(800, 600)

    # 获取缩放字体大小
    font_size = DpiHelper.scale_font(12)

    # 获取当前缩放系数
    ratio = DpiHelper.scale_factor()
"""

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QSize

_BASE_DPI = 96.0
_scale_factor = 1.0
_initialized = False


def init_dpi():
    """初始化 DPI 缩放系数

    应在 QApplication 创建后、主窗口显示前调用。

    当 AA_EnableHighDpiScaling 启用时，Qt 已自动处理缩放，
    所有尺寸设置应使用逻辑像素（基准值），scale_factor 应为 1.0。
    仅在未启用 AA_EnableHighDpiScaling 时才需要手动计算缩放系数。
    """
    global _scale_factor, _initialized

    app = QApplication.instance()
    if app is None:
        return

    if app.testAttribute(Qt.AA_EnableHighDpiScaling):
        _scale_factor = 1.0
        _initialized = True
        return

    screen = app.primaryScreen()
    if screen is None:
        _initialized = True
        return

    logical_dpi = screen.logicalDotsPerInch()
    dpi_ratio = logical_dpi / _BASE_DPI

    device_ratio = screen.devicePixelRatio()

    _scale_factor = max(dpi_ratio, device_ratio)

    if _scale_factor < 1.0:
        _scale_factor = 1.0

    _clamp_scale_factor()
    _initialized = True


def _clamp_scale_factor():
    """限制缩放系数在合理范围内，避免极端值"""
    global _scale_factor
    _scale_factor = round(_scale_factor * 4) / 4
    _scale_factor = max(1.0, min(_scale_factor, 3.0))


def scale_factor() -> float:
    """获取当前缩放系数

    Returns:
        缩放系数，1.0 表示 100% 缩放
    """
    if not _initialized:
        init_dpi()
    return _scale_factor


def scale(value: int) -> int:
    """将基准像素值缩放为当前 DPI 对应的像素值

    Args:
        value: 基准像素值（96 DPI 下的值）

    Returns:
        缩放后的像素值
    """
    return max(1, int(value * scale_factor()))


def scale_size(width: int, height: int) -> QSize:
    """缩放 QSize

    Args:
        width: 基准宽度
        height: 基准高度

    Returns:
        缩放后的 QSize
    """
    return QSize(scale(width), scale(height))


def scale_font(point_size: int) -> int:
    """缩放字体大小

    字体使用点阵单位，在 Qt 中已经会根据 DPI 自动缩放，
    但在某些场景下需要额外微调以保持视觉一致性。

    Args:
        point_size: 基准字体大小（点）

    Returns:
        调整后的字体大小
    """
    return max(8, int(point_size * scale_factor()))


def scale_stylesheet(stylesheet: str) -> str:
    """缩放样式表中的 px 值

    将样式表中的 Npx 值按当前缩放系数进行缩放。
    支持正整数和浮点数。

    Args:
        stylesheet: 原始样式表字符串

    Returns:
        缩放后的样式表字符串
    """
    import re

    def replace_px(match):
        value = float(match.group(1))
        scaled = max(1, int(value * scale_factor()))
        return f"{scaled}px"

    return re.sub(r'(\d+(?:\.\d+)?)px', replace_px, stylesheet)


def dp(value: int) -> int:
    """density-independent pixels 的简写

    与 scale() 相同，提供更简短的调用方式。

    Args:
        value: 基准像素值

    Returns:
        缩放后的像素值
    """
    return scale(value)
