# -*- coding: utf-8 -*-
"""ThemeValidator 校验流水线（Wave 8 B1）。

六阶段（已定稿顺序）：
    parse → schema validation → semantic validation → renderer resolution
    → resource resolution → fallback validation → activate

任何非法主题在 activate 前被拒绝；ThemeSnapshot 只在流水线末尾构造。
"""
from __future__ import annotations

from typing import Any, Mapping

from .compat import resolve_renderer_map, signature_for
from .constants import (
    CHROME_MODES,
    COLOR_IDENTITY_STRATEGIES,
    COLOR_VALUE_PATTERN,
    SUPPORTED_SCHEMA_VERSION,
    SUPPORTED_SHELL_SCHEMAS,
    SYNTAX_TOKEN_WHITELIST,
    TOKEN_WHITELIST,
)
from .errors import (
    ThemeFallbackError,
    ThemeRendererError,
    ThemeResourceError,
    ThemeSchemaError,
    ThemeSemanticError,
)
from .loader import ThemePackage
from .renderer_registry import RendererRegistry
from .resources import PaletteRegistry, ThemeResourceContract
from .types import (
    ColorIdentity,
    ComponentRecipe,
    DesignTokens,
    IconConfig,
    MotionConfig,
    RecipeKey,
    SyntaxConfig,
    ThemeSnapshot,
    TypographyConfig,
    VariantId,
    VariantSnapshot,
    WindowChromeIntent,
)

#: motion.json 缺省时的中性默认值（B1 仅契约，动效语言延后）。
_DEFAULT_MOTION = {"duration_fast": 100, "duration_normal": 200, "easing": "ease-out"}


class ThemeValidator:
    """ThemePackage → ThemeSnapshot（完整校验 + 不可变构造）。"""

    def __init__(
        self,
        registry: RendererRegistry | None = None,
        palette_registry: PaletteRegistry | None = None,
        resource_contract: ThemeResourceContract | None = None,
    ) -> None:
        self._registry = registry or RendererRegistry()
        self._palettes = palette_registry
        self._resources = resource_contract or ThemeResourceContract()

    # ---------------------------------------------------------------- 入口
    def validate(self, package: ThemePackage) -> ThemeSnapshot:
        manifest = self._validate_manifest(package.manifest)

        variants: dict[VariantId, VariantSnapshot] = {}
        for variant_id, data in package.variants.items():
            variants[variant_id] = self._build_variant(variant_id, data)

        self._validate_palette_references(variants)
        recipes = self._validate_recipes(package.recipes)
        icons = self._validate_icons(package.icons, package)
        design = self._build_design(package.design)
        motion = self._build_motion(package.motion)
        self._validate_fallback()

        snapshot = ThemeSnapshot(
            schema_version=manifest["schema_version"],
            name=manifest["name"],
            family=manifest["family"],
            shell_schema=manifest["shell_schema"],
            renderer_profile=manifest["renderer_profile"],
            window_chrome=manifest["window_chrome"],
            design=design,
            recipes=recipes,
            motion=motion,
            icons=icons,
            variants=variants,
        )
        # 构造成功即证明可通过兼容性判定（invariant 7：入口仅在流水线末尾）。
        _ = signature_for(snapshot)
        return snapshot

    # ------------------------------------------------------ schema validation
    def _validate_manifest(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(manifest, dict):
            raise ThemeSchemaError("theme.json 顶层必须是 JSON 对象")

        schema_version = manifest.get("schema_version")
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise ThemeSchemaError(f"schema_version 必须是整数: {schema_version!r}")
        if schema_version != SUPPORTED_SCHEMA_VERSION:
            raise ThemeSchemaError(
                f"不支持的 schema_version {schema_version}（当前支持 {SUPPORTED_SCHEMA_VERSION}）"
            )

        name = manifest.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ThemeSchemaError("name 必须是非空字符串")

        family = manifest.get("family")
        if not isinstance(family, str):
            raise ThemeSchemaError("family 必须是字符串")

        shell_schema = manifest.get("shell_schema")
        if shell_schema not in SUPPORTED_SHELL_SCHEMAS:
            raise ThemeSchemaError(
                f"未知 shell_schema {shell_schema!r}（受支持: {sorted(SUPPORTED_SHELL_SCHEMAS)}）"
                "；未知 schema 拒绝加载，不触发 L2"
            )

        renderer_profile = manifest.get("renderer_profile")
        if not isinstance(renderer_profile, str) or not renderer_profile.strip():
            raise ThemeSchemaError("renderer_profile 必须是非空字符串")

        chrome_raw = manifest.get("window_chrome", {})
        if not isinstance(chrome_raw, dict):
            raise ThemeSchemaError("window_chrome 必须是 JSON 对象")
        mode = chrome_raw.get("mode", "native")
        if mode not in CHROME_MODES:
            raise ThemeSchemaError(f"未知 window_chrome.mode {mode!r}（合法: {CHROME_MODES}）")

        return {
            "schema_version": schema_version,
            "name": name,
            "family": family,
            "shell_schema": shell_schema,
            "renderer_profile": renderer_profile,
            "window_chrome": WindowChromeIntent(mode=mode),
        }

    # ------------------------------------------------ semantic validation 入口
    def _build_variant(self, variant_id: VariantId, data: Mapping[str, Any]) -> VariantSnapshot:
        if not isinstance(data, dict):
            raise ThemeSchemaError(f"variant '{variant_id}' 必须是 JSON 对象")

        identity = self._validate_color_identity(variant_id, data.get("color_identity"))
        tokens = self._validate_tokens(variant_id, data.get("tokens"))
        syntax = self._validate_syntax(variant_id, data.get("syntax"))

        return VariantSnapshot(
            variant_id=variant_id,
            tokens=tokens,
            color_identity=identity,
            syntax=syntax,
        )

    def _validate_color_identity(
        self, variant_id: VariantId, raw: Any
    ) -> ColorIdentity:
        if not isinstance(raw, dict):
            raise ThemeSchemaError(f"variant '{variant_id}' 缺少 color_identity 对象")

        strategy = raw.get("strategy")
        if strategy not in COLOR_IDENTITY_STRATEGIES:
            raise ThemeSemanticError(
                f"variant '{variant_id}' 非法 color_identity.strategy {strategy!r}"
            )

        primary = raw.get("primary")
        accents_raw = raw.get("accents", [])
        if not isinstance(accents_raw, list):
            raise ThemeSemanticError(f"variant '{variant_id}' accents 必须是数组")

        if strategy == "neutral":
            if primary is not None:
                raise ThemeSemanticError(f"neutral 策略下 primary 必须为 null: {variant_id}")
            if accents_raw:
                raise ThemeSemanticError(f"neutral 策略下 accents 必须为空: {variant_id}")
        else:
            if not isinstance(primary, str) or not COLOR_VALUE_PATTERN.fullmatch(primary):
                raise ThemeSemanticError(
                    f"variant '{variant_id}' primary 必须是合法颜色（#RRGGBB[AA]）"
                )

        accents: list[str] = []
        for accent in accents_raw:
            if not isinstance(accent, str) or not COLOR_VALUE_PATTERN.fullmatch(accent):
                raise ThemeSemanticError(
                    f"variant '{variant_id}' accents 含非法颜色: {accent!r}"
                )
            accents.append(accent)

        hue_family = raw.get("hue_family", "neutral")
        if not isinstance(hue_family, str) or not hue_family.strip():
            raise ThemeSemanticError(f"variant '{variant_id}' hue_family 必须是非空字符串")

        return ColorIdentity(
            strategy=strategy,
            primary=primary,
            accents=tuple(accents),
            hue_family=hue_family,
        )

    def _validate_tokens(self, variant_id: VariantId, raw: Any) -> Mapping[str, str]:
        if not isinstance(raw, dict):
            raise ThemeSchemaError(f"variant '{variant_id}' 缺少 tokens 对象")
        if not raw:
            raise ThemeSemanticError(f"variant '{variant_id}' tokens 不能为空")

        tokens: dict[str, str] = {}
        for key, value in raw.items():
            if key not in TOKEN_WHITELIST:
                raise ThemeSemanticError(
                    f"variant '{variant_id}' token '{key}' 不在白名单内"
                    f"（合法: {sorted(TOKEN_WHITELIST)}）"
                )
            if not isinstance(value, str) or not COLOR_VALUE_PATTERN.fullmatch(value):
                raise ThemeSemanticError(
                    f"variant '{variant_id}' token '{key}' 必须是合法颜色"
                )
            tokens[key] = value
        return tokens

    def _validate_syntax(
        self,
        variant_id: VariantId,
        raw: Any,
    ) -> SyntaxConfig:
        if not isinstance(raw, dict):
            raise ThemeSchemaError(f"variant '{variant_id}' 缺少 syntax 对象")

        palette = raw.get("palette")
        if not isinstance(palette, str) or not palette.strip():
            raise ThemeSemanticError(f"variant '{variant_id}' syntax.palette 必须是非空字符串")

        overrides_raw = raw.get("overrides", {})
        if not isinstance(overrides_raw, dict):
            raise ThemeSemanticError(f"variant '{variant_id}' syntax.overrides 必须是对象")

        overrides: dict[str, str] = {}
        for key, value in overrides_raw.items():
            if key not in SYNTAX_TOKEN_WHITELIST:
                raise ThemeSemanticError(
                    f"variant '{variant_id}' syntax override '{key}' 不在白名单内"
                )
            if not isinstance(value, str) or not COLOR_VALUE_PATTERN.fullmatch(value):
                raise ThemeSemanticError(
                    f"variant '{variant_id}' syntax override '{key}' 必须是合法颜色"
                )
            overrides[key] = value

        return SyntaxConfig(palette=palette, overrides=overrides)

    # ------------------------------------------------- renderer resolution
    def _validate_recipes(
        self, raw: Any
    ) -> Mapping[RecipeKey, ComponentRecipe]:
        if not isinstance(raw, dict):
            raise ThemeSchemaError("recipes.json 顶层必须是 JSON 对象")

        recipes: dict[RecipeKey, ComponentRecipe] = {}
        for key, value in raw.items():
            if not isinstance(key, str) or not key.strip():
                raise ThemeSemanticError(f"recipe key 必须是非空字符串: {key!r}")
            if not isinstance(value, dict):
                raise ThemeSemanticError(f"recipe '{key}' 必须是 JSON 对象")

            renderer_id = value.get("renderer")
            if not isinstance(renderer_id, str) or not renderer_id.strip():
                raise ThemeRendererError(f"recipe '{key}' 缺少 renderer id")

            contract = self._registry.resolve(renderer_id)  # ThemeRendererError 若未知

            style = value.get("style", {})
            if not isinstance(style, dict):
                raise ThemeSemanticError(f"recipe '{key}' style 必须是对象")

            renderer_params = value.get("renderer_params", {})
            if not isinstance(renderer_params, dict):
                raise ThemeSemanticError(f"recipe '{key}' renderer_params 必须是对象")
            contract.validate_params(renderer_params)

            recipes[key] = ComponentRecipe(
                renderer=renderer_id,
                style=style,
                renderer_params=renderer_params,
            )
        return recipes

    # ------------------------------------------------- resource resolution
    def _validate_icons(
        self, raw: Any, package: ThemePackage
    ) -> IconConfig:
        if not isinstance(raw, dict):
            raise ThemeSchemaError("icons.json 顶层必须是 JSON 对象")

        icon_set = raw.get("set", "lucide")
        if not isinstance(icon_set, str) or not icon_set.strip():
            raise ThemeSemanticError("icons.set 必须是非空字符串")

        overrides_raw = raw.get("overrides", {})
        if not isinstance(overrides_raw, dict):
            raise ThemeSemanticError("icons.overrides 必须是对象")

        overrides: dict[str, str] = {}
        for key, reference in overrides_raw.items():
            if not isinstance(key, str) or not key.strip():
                raise ThemeSemanticError(f"icon key 必须是非空字符串: {key!r}")
            if not isinstance(reference, str):
                raise ThemeSemanticError(f"icon '{key}' 引用必须是字符串")
            # 资源边界在 activate 前校验（不落到 paint 时）
            self._resources.validate_path(reference, package.root)
            overrides[key] = reference
        return IconConfig(set=icon_set, overrides=overrides)

    def _validate_palette_references(self, variants: Mapping[VariantId, VariantSnapshot]) -> None:
        """resource resolution：palette 存在性校验（仅当提供 PaletteRegistry 时生效）。"""
        if self._palettes is None:
            return
        for variant_id, variant in variants.items():
            if not self._palettes.contains(variant.syntax.palette):
                raise ThemeResourceError(
                    f"variant '{variant_id}' 引用未注册的 syntax palette: "
                    f"{variant.syntax.palette}"
                )

    # ------------------------------------------------- fallback validation
    def _validate_fallback(self) -> None:
        try:
            self._registry.default_renderer()
        except KeyError as exc:
            raise ThemeFallbackError("缺少内置 default renderer 兜底") from exc

    # -------------------------------------------------------- 默认值构造
    def _build_design(self, raw: Any) -> DesignTokens:
        if not isinstance(raw, dict):
            raise ThemeSchemaError("design.json 顶层必须是 JSON 对象")

        spacing = self._int_map(raw.get("spacing", {}), "spacing")
        radius = self._int_map(raw.get("radius", {}), "radius")
        density = self._int_map(raw.get("density", {}), "density")

        typography_raw = raw.get("typography", {})
        if not isinstance(typography_raw, dict):
            raise ThemeSchemaError("design.typography 必须是对象")
        font_ui = typography_raw.get("font_ui", "")
        font_mono = typography_raw.get("font_mono", "")
        font_scale = typography_raw.get("font_scale", 1.0)
        if not isinstance(font_ui, str) or not isinstance(font_mono, str):
            raise ThemeSchemaError("design.typography 字体必须是字符串")
        if not isinstance(font_scale, (int, float)) or isinstance(font_scale, bool):
            raise ThemeSchemaError("design.typography.font_scale 必须是数字")

        return DesignTokens(
            spacing=spacing,
            radius=radius,
            density=density,
            typography=TypographyConfig(
                font_ui=font_ui,
                font_mono=font_mono,
                font_scale=float(font_scale),
            ),
        )

    @staticmethod
    def _int_map(raw: Any, field_name: str) -> dict[str, int]:
        if not isinstance(raw, dict):
            raise ThemeSchemaError(f"design.{field_name} 必须是对象")
        result: dict[str, int] = {}
        for key, value in raw.items():
            if not isinstance(key, str):
                raise ThemeSchemaError(f"design.{field_name} 键必须是字符串")
            if not isinstance(value, int) or isinstance(value, bool):
                raise ThemeSchemaError(
                    f"design.{field_name}.{key} 必须是整数像素值"
                )
            result[key] = value
        return result

    def _build_motion(self, raw: Any) -> MotionConfig:
        if not isinstance(raw, dict):
            raise ThemeSchemaError("motion.json 顶层必须是 JSON 对象")
        if not raw:
            data: dict[str, Any] = dict(_DEFAULT_MOTION)
        else:
            data = raw
        duration_fast = data.get("duration_fast", _DEFAULT_MOTION["duration_fast"])
        duration_normal = data.get("duration_normal", _DEFAULT_MOTION["duration_normal"])
        easing = data.get("easing", _DEFAULT_MOTION["easing"])
        for field_name, value in (("duration_fast", duration_fast), ("duration_normal", duration_normal)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ThemeSchemaError(f"motion.{field_name} 必须是非负整数")
        if not isinstance(easing, str) or not easing.strip():
            raise ThemeSchemaError("motion.easing 必须是非空字符串")
        return MotionConfig(
            duration_fast=duration_fast,
            duration_normal=duration_normal,
            easing=easing,
        )
