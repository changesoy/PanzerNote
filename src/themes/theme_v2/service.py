# -*- coding: utf-8 -*-
"""Theme v2 运行时服务（Wave 8 B2：Editor Vertical Slice）。

B1 产出契约（loader/validator/types）；B2 提供最小运行时入口：
- 加载默认主题包（themes/default/）→ ThemeSnapshot
- 注册共享 syntax palette（themes/syntax/palettes/*.json）并合并 override
- 组件消费解析：recipe style 值支持 semantic token 引用 / 直接色值
- 双变体选择（B2 阶段由 v1 ThemeEngine 的明暗驱动，B7 起由 ThemeManager 接管）

失败不崩溃：v2 加载失败时 snapshot 为 None，消费方自动回退 v1。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from PyQt6.QtCore import QObject, pyqtSignal

from ...utils.logger import get_logger
from .loader import ThemePackageLoader
from .renderer_registry import RendererRegistry
from .resources import PaletteRegistry, ThemeResourceContract
from .types import (
    ColorValue,
    ComponentRecipe,
    DesignTokens,
    RecipeKey,
    SyntaxTokenKey,
    ThemeSnapshot,
    VariantId,
    VariantSnapshot,
)
from .validator import ThemeValidator

_logger = get_logger(__name__)


class ThemeV2Service(QObject):
    """Theme v2 运行时：default 包加载、palette 注册、双变体选择与消费解析。

    UI 组件只消费 ThemeSnapshot（不可变），不读 raw JSON。
    """

    theme_v2_changed = pyqtSignal()

    def __init__(self, themes_root: str | Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._themes_root = Path(themes_root)
        self._snapshot: ThemeSnapshot | None = None
        self._palettes: dict[str, Mapping[SyntaxTokenKey, ColorValue]] = {}
        self._active_variant: VariantId | None = None

    # ──────────────────────────────────────────────── 加载与变体
    def load_default(self) -> bool:
        """加载 themes/default/ 主题包并注册共享 syntax palette。

        Returns:
            True 成功；False 失败（消费方回退 v1，不抛异常）。
        """
        try:
            root = self._themes_root / "default"
            palette_dir = self._themes_root / "syntax" / "palettes"
            registry = RendererRegistry()
            palettes = PaletteRegistry()
            for filepath in sorted(palette_dir.glob("*.json")):
                palette_id = filepath.stem
                data = json.loads(filepath.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError(f"palette '{palette_id}' 必须是对象")
                self._palettes[palette_id] = dict(data)
                palettes.register(palette_id, data)

            package = ThemePackageLoader().load(root)
            validator = ThemeValidator(
                registry=registry,
                palette_registry=palettes,
                resource_contract=ThemeResourceContract(
                    shared_root=self._themes_root / "syntax"
                ),
            )
            self._snapshot = validator.validate(package)
        except Exception:
            _logger.exception("加载默认 Theme v2 主题失败，回退 v1 主题机制")
            self._snapshot = None
            return False
        return True

    def snapshot(self) -> ThemeSnapshot | None:
        return self._snapshot

    def set_variant(self, variant_id: str) -> None:
        """切换激活变体（B2：仅接受 snapshot 中存在的 variant）。"""
        if self._snapshot is None:
            return
        if variant_id not in self._snapshot.variants:
            _logger.warning("Theme v2 无变体 '%s'（可用: %s）", variant_id, sorted(self._snapshot.variants))
            return
        if variant_id != self._active_variant:
            self._active_variant = variant_id
            self.theme_v2_changed.emit()

    def active_variant(self) -> str | None:
        """当前激活 variant id；未选择时取 snapshot 第一个 variant。"""
        if self._active_variant is not None:
            return self._active_variant
        if self._snapshot is None:
            return None
        return next(iter(self._snapshot.variants))

    def variant_snapshot(self) -> VariantSnapshot | None:
        if self._snapshot is None:
            return None
        vid = self.active_variant()
        if vid is None:
            return None
        return self._snapshot.variants.get(vid)

    # ──────────────────────────────────────────────── 消费解析
    def recipe(self, key: RecipeKey) -> ComponentRecipe | None:
        if self._snapshot is None:
            return None
        return self._snapshot.recipes.get(key)

    def design(self) -> DesignTokens | None:
        if self._snapshot is None:
            return None
        return self._snapshot.design

    def resolve_style_color(
        self,
        recipe_key: RecipeKey,
        style_key: str,
    ) -> ColorValue | None:
        """解析 recipe.style 中一个颜色键。

        值支持两种形式：
          - semantic token 名（如 "surface_primary"）→ variant tokens 中的色值
          - 直接色值 "#RRGGBB[AA]" → 原样返回
        解析失败返回 None（消费方回退 v1）。
        """
        recipe = self.recipe(recipe_key)
        variant = self.variant_snapshot()
        if recipe is None or variant is None:
            return None
        value: Any = recipe.style.get(style_key)
        if isinstance(value, str) and value in variant.tokens:
            return variant.tokens[value]
        if isinstance(value, str) and _is_color_value(value):
            return value
        return None

    def syntax_colors(self) -> Mapping[SyntaxTokenKey, ColorValue]:
        """合并 palette + override 后的完整 syntax 配色（空 dict 表示不可用）。"""
        variant = self.variant_snapshot()
        if variant is None:
            return {}
        palette = self._palettes.get(variant.syntax.palette)
        if palette is None:
            _logger.warning("Theme v2 缺少 syntax palette: %s", variant.syntax.palette)
            return {}
        merged = dict(palette)
        merged.update(variant.syntax.overrides)
        return merged

    # ──────────────────────────────────────────────── 工具
    def variant_for_dark(self, is_dark: bool) -> str:
        """B2 明暗 → variant id 映射（Dark→dark，Light→light，缺失时取首个）。"""
        if self._snapshot is None:
            return ""
        preferred = "dark" if is_dark else "light"
        if preferred in self._snapshot.variants:
            return preferred
        return next(iter(self._snapshot.variants))


def _is_color_value(value: str) -> bool:
    from .constants import COLOR_VALUE_PATTERN

    return bool(COLOR_VALUE_PATTERN.fullmatch(value))
