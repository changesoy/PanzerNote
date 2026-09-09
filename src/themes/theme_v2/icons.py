# -*- coding: utf-8 -*-
"""IconManager（Wave 8 B1，Lucide Registry 契约）。

语义 key 只覆盖 Productivity UI（`app.save` / `panel.search` / `editor.markdown`），
不用 `game.*`。icons.json 仅声明 `{ "set": "lucide", "overrides": {...} }`，
不复制整套 Lucide。内置 Registry 兜底，override 优先。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

from .types import IconKey, VariantId


@dataclass(frozen=True)
class IconResource:
    """图标解析结果。name 为图标名/资源引用，source 标明来源。"""

    name: str
    source: Literal["builtin", "override"]


class IconManager:
    """语义图标解析：override 优先，内置 Registry 兜底。

    B1 阶段不携带实际图标集；override 来自 ThemeSnapshot.icons.overrides
    （已在 ThemeValidator resource 阶段校验过资源边界）。
    """

    def __init__(self, overrides: Mapping[IconKey, str] | None = None) -> None:
        self._overrides: dict[IconKey, str] = dict(overrides or {})

    def update_overrides(self, overrides: Mapping[IconKey, str] | None) -> None:
        self._overrides = dict(overrides or {})

    def resolve(self, key: IconKey, variant: VariantId = "light") -> IconResource:
        """解析语义图标 key → IconResource。

        variant 参数为契约预留（v2 第一版图标不分 variant，未来可扩展）。
        """
        if key in self._overrides:
            return IconResource(name=self._overrides[key], source="override")
        return IconResource(name=key, source="builtin")
