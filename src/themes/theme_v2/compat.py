# -*- coding: utf-8 -*-
"""Compatibility Signature（Wave 8 B1）。

兼容性真正比较的是 Resolved Renderer Map（组件 → 实际 renderer），
不是 'classic-v1' / 'soft-v1' 这样的字符串 profile 名。
"""
from __future__ import annotations

from typing import Mapping

from .types import (
    ComponentRecipe,
    CompatibilitySignature,
    RecipeKey,
    ResolvedRendererMap,
    ThemeSnapshot,
    ThemeSwitchLevel,
)


def resolve_renderer_map(
    recipes: Mapping[RecipeKey, ComponentRecipe],
) -> ResolvedRendererMap:
    """组件级 Recipe override 解析为 renderer 映射（缺省 renderer 由 profile 负责，不在此处展开）。"""
    return ResolvedRendererMap(mapping={key: recipe.renderer for key, recipe in recipes.items()})


def signature_for(snapshot: ThemeSnapshot) -> CompatibilitySignature:
    """从 ThemeSnapshot 构建兼容性签名。"""
    return CompatibilitySignature(
        resolved=resolve_renderer_map(snapshot.recipes),
        shell_schema=snapshot.shell_schema,
    )


def compute_switch_level(
    old: CompatibilitySignature,
    new: CompatibilitySignature,
) -> ThemeSwitchLevel:
    """判定切换等级。

    - shell_schema 不同（且均受支持）→ L2（v2 初期不存在，仅保留判定）
    - resolved map 组件级相同 → L0
    - 存在组件级不同 → L1 局部替换计划
    """
    if old.shell_schema != new.shell_schema:
        return ThemeSwitchLevel.L2
    if old.resolved.mapping == new.resolved.mapping:
        return ThemeSwitchLevel.L0
    return ThemeSwitchLevel.L1
