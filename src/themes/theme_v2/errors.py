# -*- coding: utf-8 -*-
"""Theme v2 错误层次（Wave 8 B1）。

任何非法主题必须在 activate 前被拒绝，不得等到 QWidget paint 时才 KeyError。
"""


class ThemeError(Exception):
    """Theme v2 体系所有错误的基类。"""


class ThemeParseError(ThemeError):
    """JSON 反序列化失败。"""


class ThemeSchemaError(ThemeError):
    """字段存在性 / 类型 / schema_version 门禁失败。"""


class ThemeSemanticError(ThemeError):
    """token 完整性 / recipe key / color_identity 枚举等语义校验失败。"""


class ThemeRendererError(ThemeError):
    """renderer id 无法在 registry 解析，或 renderer_params 不满足 RendererContract。"""


class ThemeResourceError(ThemeError):
    """palette 不存在 / 图标引用不可解析 / 资源边界（http、`../`、类型白名单）越界。"""


class ThemeFallbackError(ThemeError):
    """缺省 renderer / icon fallback 不可达。"""


class ThemeSwitchPlanError(ThemeError):
    """切换计划非法（如 L1 计划中有 renderer 变化但无注册宿主，或提交了非计划内步骤）。"""


class ThemeSwitchUnsupportedError(ThemeError):
    """切换等级不支持执行（L2 Shell rebuild 在 Wave 8 只留 Contract，executor 拒绝）。"""
