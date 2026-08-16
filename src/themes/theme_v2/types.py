# -*- coding: utf-8 -*-
"""Theme v2 不可变运行时数据结构（Wave 8 B1）。

UI 永远只消费 ThemeSnapshot，不读 raw JSON。全部 dataclass 均 frozen，
Mapping 字段在构造后被替换为只读视图（不变量 6）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Literal, Mapping, TypeVar

VariantId = str      # "light" / "dark"，来自 filename stem
RecipeKey = str      # "button" / "tab" / "input" / "scrollbar" / ...（单段组件语义名）
TokenKey = str       # "surface_primary" / "text_primary" / ...（UI 语义 token 白名单）
SyntaxTokenKey = str  # "syntax_keyword" / "syntax_string" / ...（Pygments 语义 token）
ColorValue = str     # "#RRGGBB" / "#RRGGBBAA"
IconKey = str        # "app.save" / "panel.search" / ...

#: renderer_params 允许的参数值类型（RendererContract.accepted_params_schema 使用）。
ParamType = Literal["string", "number", "boolean", "list"]

_K = TypeVar("_K")
_V = TypeVar("_V")


def _freeze(value: Any) -> Any:
    """递归冻结：dict/Mapping → MappingProxyType，list → tuple，其余原样。"""
    if isinstance(value, Mapping):
        return MappingProxyType({_freeze(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def _frozen_mapping(data: Mapping[_K, _V]) -> MappingProxyType[_K, _V]:
    """将可变映射递归冻结为只读视图（构造后只读，不变量 6）。"""
    return MappingProxyType({_freeze(k): _freeze(v) for k, v in data.items()})


def _frozen_mapping_any(data: Mapping[str, Any]) -> MappingProxyType[str, Any]:
    return _frozen_mapping(data)


@dataclass(frozen=True)
class ColorIdentity:
    """主题色彩身份（D27，归属 variant）。"""

    strategy: Literal["chromatic", "neutral", "multi"]
    primary: ColorValue | None        # neutral 时为 None
    accents: tuple[ColorValue, ...]   # neutral 时为空元组
    hue_family: str                    # "purple" / "neutral" / ...（描述性，不渲染）


@dataclass(frozen=True)
class SyntaxConfig:
    """共享 palette + theme override 浅继承（D18，归属 variant）。"""

    palette: str
    overrides: Mapping[SyntaxTokenKey, ColorValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "overrides", _frozen_mapping(self.overrides))


@dataclass(frozen=True)
class VariantSnapshot:
    """单个视觉变体（tokens / colorIdentity / syntax 天然属于变体）。"""

    variant_id: VariantId
    tokens: Mapping[TokenKey, ColorValue]
    color_identity: ColorIdentity
    syntax: SyntaxConfig

    def __post_init__(self) -> None:
        object.__setattr__(self, "tokens", _frozen_mapping(self.tokens))


@dataclass(frozen=True)
class TypographyConfig:
    font_ui: str
    font_mono: str
    font_scale: float


@dataclass(frozen=True)
class DesignTokens:
    """design.json（变体共享）：spacing/radius/density/typography。"""

    spacing: Mapping[str, int]       # "space_1".."space_8" → px
    radius: Mapping[str, int]        # "radius_sm"/"radius_md"/"radius_lg"/"radius_full" → px
    density: Mapping[str, int]       # "density_compact"/"density_default"/"density_comfortable" → px
    typography: TypographyConfig

    def __post_init__(self) -> None:
        object.__setattr__(self, "spacing", _frozen_mapping_any(self.spacing))
        object.__setattr__(self, "radius", _frozen_mapping_any(self.radius))
        object.__setattr__(self, "density", _frozen_mapping_any(self.density))


@dataclass(frozen=True)
class MotionConfig:
    """motion.json：动效时长与缓动。"""

    duration_fast: int
    duration_normal: int
    easing: str


@dataclass(frozen=True)
class IconConfig:
    """icons.json：图标集声明 + 语义 key 覆盖。"""

    set: str
    overrides: Mapping[IconKey, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "overrides", _frozen_mapping(self.overrides))


@dataclass(frozen=True)
class ComponentRecipe:
    """组件配方（3.2 两层结构）：style 跨 renderer 通用，renderer_params 仅 renderer 认识。"""

    renderer: str
    style: Mapping[str, Any]
    renderer_params: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "style", _frozen_mapping_any(self.style))
        object.__setattr__(self, "renderer_params", _frozen_mapping_any(self.renderer_params))


@dataclass(frozen=True)
class WindowChromeIntent:
    """主题声明的 Window Chrome 视觉意图（D30，主题不写平台细节）。"""

    mode: Literal["native", "extended-native", "custom"]
    profile: str | None = None    # 未来 C1/C2 才用


@dataclass(frozen=True)
class ThemeSnapshot:
    """完整校验后的不可变运行时主题对象（activate 的唯一产物）。"""

    schema_version: int
    name: str
    family: str
    shell_schema: str
    renderer_profile: str
    window_chrome: WindowChromeIntent
    design: DesignTokens
    recipes: Mapping[RecipeKey, ComponentRecipe]
    motion: MotionConfig
    icons: IconConfig
    variants: Mapping[VariantId, VariantSnapshot]

    def __post_init__(self) -> None:
        object.__setattr__(self, "recipes", _frozen_mapping(self.recipes))
        object.__setattr__(self, "variants", _frozen_mapping(self.variants))


class ThemeSwitchLevel(Enum):
    """三级切换概念模型。v2 初期 L2 不可达（shell_schema 唯一）。"""

    L0 = "hot-reload"
    L1 = "renderer-replacement"
    L2 = "shell-migration"


@dataclass(frozen=True)
class ResolvedRendererMap:
    """组件 → 实际 renderer id 的解析结果（兼容性比较对象）。"""

    mapping: Mapping[RecipeKey, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "mapping", _frozen_mapping(self.mapping))


@dataclass(frozen=True)
class CompatibilitySignature:
    """主题切换兼容性签名：Resolved Renderer Map + shell_schema。"""

    resolved: ResolvedRendererMap
    shell_schema: str


@dataclass(frozen=True)
class RendererContract:
    """Renderer 契约：renderer_params schema + 是否只替换 visual implementation。"""

    renderer_id: str
    accepted_params_schema: Mapping[str, ParamType]
    replaceable: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "accepted_params_schema", _frozen_mapping(self.accepted_params_schema))

    def validate_params(self, params: Mapping[str, Any]) -> None:
        """校验 renderer_params 与契约（未知参数或类型不匹配 → ValueError）。"""
        from .errors import ThemeRendererError

        unknown = [k for k in params if k not in self.accepted_params_schema]
        if unknown:
            raise ThemeRendererError(
                f"renderer '{self.renderer_id}' 收到未知参数: {sorted(unknown)}"
            )
        for key, expected in self.accepted_params_schema.items():
            if key not in params:
                continue
            value = params[key]
            ok = _matches_type(value, expected)
            if not ok:
                raise ThemeRendererError(
                    f"renderer '{self.renderer_id}' 参数 '{key}' 类型错误: "
                    f"期望 {expected}，实际 {type(value).__name__}"
                )


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "list":
        return isinstance(value, list)
    return False
