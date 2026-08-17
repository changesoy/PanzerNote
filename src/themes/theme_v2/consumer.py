# -*- coding: utf-8 -*-
"""Theme v2 消费端辅助（Wave 8 B2）。

B2 编辑器 slice 组件从 ThemeEngine 上取 v2 值：色值 / 带透明通道 QColor / syntax 配色。
v2 不可用（未加载或键缺失）时返回 fallback（通常为 v1 色值），保证回退不崩。
"""
from __future__ import annotations

from typing import Any, Mapping

from PyQt6.QtGui import QColor

from ..theme_engine import ThemeEngine
from .service import ThemeV2Service


def _service(theme_engine: ThemeEngine) -> ThemeV2Service | None:
    """从 ThemeEngine 取 Theme v2 服务（v2 未初始化时为 None）。"""
    return getattr(theme_engine, "theme_v2", None)


def v2_token(
    theme_engine: ThemeEngine,
    token_name: str,
    fallback: str = "",
) -> str:
    """解析 semantic token 色值；不可用返回 fallback。"""
    svc = _service(theme_engine)
    if svc is None:
        return fallback
    variant = svc.variant_snapshot()
    if variant is None:
        return fallback
    value = variant.tokens.get(token_name)
    return value if value is not None else fallback


def v2_color(
    theme_engine: ThemeEngine,
    recipe_key: str,
    style_key: str,
    fallback: str = "",
) -> str:
    """解析 recipe.style 颜色键（token 引用 / 直接色值）；不可用返回 fallback。"""
    svc = _service(theme_engine)
    if svc is None:
        return fallback
    value = svc.resolve_style_color(recipe_key, style_key)
    return value if value is not None else fallback


def v2_style_value(
    theme_engine: ThemeEngine,
    recipe_key: str,
    style_key: str,
    default: object = None,
) -> Any:
    """读取 recipe.style 原始值（数值/字符串等）；不可用返回 default。"""
    svc = _service(theme_engine)
    if svc is None:
        return default
    recipe = svc.recipe(recipe_key)
    if recipe is None:
        return default
    return recipe.style.get(style_key, default)


def v2_color_qcolor(
    theme_engine: ThemeEngine,
    recipe_key: str,
    style_key: str,
    fallback: str = "#000000",
    alpha: int | None = None,
) -> QColor:
    """v2_color 的 QColor 版本，可附加 alpha（0-255）。"""
    color = QColor(v2_color(theme_engine, recipe_key, style_key, fallback))
    if alpha is not None:
        color.setAlpha(alpha)
    return color


def v2_syntax_colors(theme_engine: ThemeEngine) -> Mapping[str, str]:
    """合并 palette + override 后的 syntax 配色（v2 不可用时空 dict）。"""
    svc = _service(theme_engine)
    if svc is None:
        return {}
    return svc.syntax_colors()


def v2_active_variant(theme_engine: ThemeEngine) -> str | None:
    """当前激活 variant id（v2 不可用为 None）。"""
    svc = _service(theme_engine)
    if svc is None:
        return None
    return svc.active_variant()


def v2_export_colors(theme_engine: ThemeEngine) -> dict[str, str]:
    """导出 HTML/PDF 所需的 v2 色值集合（B8：替代 v1 配色对象传参）。"""
    return {
        "text_primary": v2_token(theme_engine, "text_primary", "#212121"),
        "text_secondary": v2_token(theme_engine, "text_secondary", "#757575"),
        "text_disabled": v2_token(theme_engine, "text_muted", "#BDBDBD"),
        "border": v2_token(theme_engine, "border_muted", "#E0E0E0"),
        "divider": v2_token(theme_engine, "border_muted", "#EEEEEE"),
        "surface": v2_token(theme_engine, "surface_secondary", "#F5F5F5"),
        "sidebar_bg": v2_token(theme_engine, "surface_secondary", "#FAFAFA"),
        "primary": v2_token(theme_engine, "accent", "#2196F3"),
        "primary_dark": v2_color(theme_engine, "button", "pressed_background", "#1976D2"),
        "bg_codeblock": v2_token(theme_engine, "md_preview_code_block_bg", "#EDF3FA"),
    }
