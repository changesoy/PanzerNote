# -*- coding: utf-8 -*-
"""
Theme v2 契约层（Wave 8 B1）。

Theme v2 将「主题」升级为视觉语言包。本包只定义契约与基础设施：

- ThemeSnapshot（不可变运行时主题对象）与全部子结构
- ThemeValidator 六阶段校验流水线 + Theme Resource Contract
- RendererRegistry / RendererContract / Compatibility Signature
- IconManager / TypographyLoader

不包含：具体 Renderer 实现（B8）、L0/L1 executor（B7）、Window Chrome 实现（见 src/platform）。
"""
from .compat import compute_switch_level, resolve_renderer_map, signature_for
from .constants import (
    DEFAULT_RENDERER_ID,
    SUPPORTED_SCHEMA_VERSION,
    SUPPORTED_SHELL_SCHEMAS,
    SYNTAX_TOKEN_WHITELIST,
    TOKEN_WHITELIST,
)
from .errors import (
    ThemeError,
    ThemeFallbackError,
    ThemeParseError,
    ThemeRendererError,
    ThemeResourceError,
    ThemeSchemaError,
    ThemeSemanticError,
)
from .icons import IconManager, IconResource
from .loader import ThemePackage, ThemePackageLoader
from .renderer_registry import RendererRegistry
from .resources import PaletteRegistry, ThemeResourceContract
from .typography import TypographyLoader
from .types import (
    ColorIdentity,
    ColorValue,
    CompatibilitySignature,
    ComponentRecipe,
    DesignTokens,
    IconConfig,
    IconKey,
    MotionConfig,
    RecipeKey,
    RendererContract,
    ResolvedRendererMap,
    SyntaxConfig,
    SyntaxTokenKey,
    ThemeSnapshot,
    ThemeSwitchLevel,
    TokenKey,
    TypographyConfig,
    VariantId,
    VariantSnapshot,
    WindowChromeIntent,
)
from .validator import ThemeValidator

__all__ = [
    "ColorIdentity",
    "ColorValue",
    "CompatibilitySignature",
    "ComponentRecipe",
    "DEFAULT_RENDERER_ID",
    "DesignTokens",
    "IconConfig",
    "IconKey",
    "IconManager",
    "IconResource",
    "MotionConfig",
    "PaletteRegistry",
    "RecipeKey",
    "RendererContract",
    "RendererRegistry",
    "ResolvedRendererMap",
    "SUPPORTED_SCHEMA_VERSION",
    "SUPPORTED_SHELL_SCHEMAS",
    "SYNTAX_TOKEN_WHITELIST",
    "SyntaxConfig",
    "SyntaxTokenKey",
    "ThemeError",
    "ThemeFallbackError",
    "ThemePackage",
    "ThemePackageLoader",
    "ThemeParseError",
    "ThemeRendererError",
    "ThemeResourceContract",
    "ThemeResourceError",
    "ThemeSchemaError",
    "ThemeSemanticError",
    "ThemeSnapshot",
    "ThemeSwitchLevel",
    "ThemeValidator",
    "TOKEN_WHITELIST",
    "TokenKey",
    "TypographyConfig",
    "TypographyLoader",
    "VariantId",
    "VariantSnapshot",
    "WindowChromeIntent",
    "compute_switch_level",
    "resolve_renderer_map",
    "signature_for",
]
