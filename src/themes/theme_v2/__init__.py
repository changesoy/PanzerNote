# -*- coding: utf-8 -*-
"""
Theme v2 契约层（Wave 8 B1）+ 切换执行器（B7）。

Theme v2 将「主题」升级为视觉语言包。本包定义契约与基础设施：

- ThemeSnapshot（不可变运行时主题对象）与全部子结构
- ThemeValidator 六阶段校验流水线 + Theme Resource Contract
- RendererRegistry / RendererContract / Compatibility Signature
- IconManager / TypographyLoader
- B7：RendererHost 薄契约 + HostRegistry + TransitionPlan planner + ThemeManager

不包含：具体 Renderer 实现（B8）、L2 Shell rebuild executor（B7 只留 Contract）、
Window Chrome 实现（见 src/platform）。
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
    ThemeSwitchPlanError,
    ThemeSwitchUnsupportedError,
)
from .hosts import HostRegistry, RendererHost, ReplacementSafety
from .icons import IconManager, IconResource
from .loader import ThemePackage, ThemePackageLoader
from .manager import ThemeManager, ThemeManagerState
from .renderer_registry import RendererRegistry
from .resources import PaletteRegistry, ThemeResourceContract
from .transition import (
    CommitResult,
    PreparedTheme,
    RendererReplacementStep,
    ThemeTransitionPlan,
    build_plan,
    params_for_recipe,
)
from .transition_controller import (
    ThemeTransitionController,
    duration_for,
    easing_for,
)
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
    "CommitResult",
    "CompatibilitySignature",
    "ComponentRecipe",
    "DEFAULT_RENDERER_ID",
    "DesignTokens",
    "HostRegistry",
    "IconConfig",
    "IconKey",
    "IconManager",
    "IconResource",
    "MotionConfig",
    "PaletteRegistry",
    "PreparedTheme",
    "RecipeKey",
    "RendererContract",
    "RendererHost",
    "RendererRegistry",
    "ReplacementSafety",
    "RendererReplacementStep",
    "ResolvedRendererMap",
    "SUPPORTED_SCHEMA_VERSION",
    "SUPPORTED_SHELL_SCHEMAS",
    "SYNTAX_TOKEN_WHITELIST",
    "SyntaxConfig",
    "SyntaxTokenKey",
    "ThemeError",
    "ThemeFallbackError",
    "ThemeManager",
    "ThemeManagerState",
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
    "ThemeSwitchPlanError",
    "ThemeSwitchUnsupportedError",
    "ThemeTransitionController",
    "ThemeTransitionPlan",
    "ThemeValidator",
    "TOKEN_WHITELIST",
    "TokenKey",
    "TypographyConfig",
    "TypographyLoader",
    "VariantId",
    "VariantSnapshot",
    "WindowChromeIntent",
    "build_plan",
    "compute_switch_level",
    "duration_for",
    "easing_for",
    "params_for_recipe",
    "resolve_renderer_map",
    "signature_for",
]
