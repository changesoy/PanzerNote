# -*- coding: utf-8 -*-
"""
高 DPI 语义标注工具

当高 DPI 缩放启用时（PyQt6 默认启用），
Qt 已自动处理缩放，scale_factor 恒为 1.0，所有函数为恒等函数。

本模块的 scale() 系列函数保留作为语义标注——调用处写 scale(200)
而非硬编码 200，表明"此数值是基准像素值，未来若禁用
PyQt6 默认启用高 DPI 缩放，则会自动缩放"。

使用方式:
    from src.utils.dpi_helper import scale, scale_size

    width = scale(200)   # 语义：200 是基准像素值
    size = scale_size(800, 600)
"""

import re

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSize

_scale_factor = 1.0
_initialized = False


def init_dpi():
    """初始化 DPI 缩放系数

    应在 QApplication 创建后、主窗口显示前调用。

    当高 DPI 缩放启用时（PyQt6 默认），Qt 已自动处理缩放，
    所有尺寸设置应使用逻辑像素（基准值），scale_factor 恒为 1.0。
    """
    global _scale_factor, _initialized

    if QApplication.instance() is None:
        return

    _scale_factor = 1.0
    _initialized = True


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

    当高 DPI 缩放启用时，此函数为恒等函数（直接返回 value）。
    保留调用作为语义标注，表明 value 是基准像素值。

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

    Args:
        point_size: 基准字体大小（点）

    Returns:
        调整后的字体大小
    """
    return max(8, int(point_size * scale_factor()))


def scale_stylesheet(stylesheet: str) -> str:
    """缩放样式表中的 px 值

    Args:
        stylesheet: 原始样式表字符串

    Returns:
        缩放后的样式表字符串
    """

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
