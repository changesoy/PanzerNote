# -*- coding: utf-8 -*-
"""Theme v2 契约常量（Wave 8 B1）。

命名遵循 111.md 定稿决策：JSON 字段全部 snake_case；
recipe key 用单段组件语义名（`button` / `input` / `scrollbar`），组件变体经 style 键表达。
"""
from __future__ import annotations

import re

#: 唯一受支持的 theme v2 schema 版本；`> supported` 由 ThemeManager 明确拒绝，不 silent fallback。
SUPPORTED_SCHEMA_VERSION = 2

#: 受支持的 shell_schema（宿主 ABI 契约）。v2 初期仅 `workbench-v1` 合法；
#: 未知 shell_schema 拒绝加载（不触发 L2）。
SUPPORTED_SHELL_SCHEMAS = frozenset({"workbench-v1"})

#: color_identity.strategy 合法值（D27）。
COLOR_IDENTITY_STRATEGIES = ("chromatic", "neutral", "multi")

#: window_chrome.mode 合法枚举（D30，第一版仅 native 稳定实现）。
CHROME_MODES = ("native", "extended-native", "custom")

#: UI 语义 token 白名单（B1 定稿，D26 收敛后）。tokens 键必须是其子集。
TOKEN_WHITELIST = frozenset({
    "surface_primary",
    "surface_secondary",
    "surface_raised",
    "text_primary",
    "text_secondary",
    "text_muted",
    "border_muted",
    "border_strong",
    "accent",
    "focus",
    "danger",
})

#: syntax palette override 白名单（与现有 Pygments → syntax_* 映射保持一致）。
SYNTAX_TOKEN_WHITELIST = frozenset({
    "syntax_keyword",
    "syntax_keyword_type",
    "syntax_builtin",
    "syntax_class",
    "syntax_function",
    "syntax_variable",
    "syntax_tag",
    "syntax_namespace",
    "syntax_string",
    "syntax_string_escape",
    "syntax_string_affix",
    "syntax_string_doc",
    "syntax_number",
    "syntax_comment",
    "syntax_operator",
    "syntax_punctuation",
    "syntax_text",
    "syntax_error",
    "syntax_deleted",
    "syntax_inserted",
    "syntax_heading",
    "syntax_output",
})

#: 内置 default renderer 兜底 id（具体 Renderer 到 B8 再实现）。
DEFAULT_RENDERER_ID = "default-v1"

#: Theme Resource Contract：允许的资源文件扩展名。
ALLOWED_RESOURCE_EXTENSIONS = frozenset({".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif"})

#: variant id 来自 filename stem，允许小写字母/数字/连字符。
VARIANT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")

#: ColorValue 格式：#RRGGBB 或 #RRGGBBAA。
COLOR_VALUE_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")
