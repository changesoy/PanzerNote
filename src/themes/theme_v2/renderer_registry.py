# -*- coding: utf-8 -*-
"""RendererRegistry（Wave 8 B1）。

具体 Renderer（brutal-v1 / soft-motion-v1）到 B8 再实现；B1 只保证
内置 default renderer 兜底 + 契约可解析。未知 renderer_id 在
renderer resolution 阶段报错，不落到运行时。
"""
from __future__ import annotations

from typing import Mapping

from .constants import DEFAULT_RENDERER_ID
from .errors import ThemeRendererError
from .types import RendererContract


class RendererRegistry:
    """Renderer 契约注册表。构造时预注册内置 default renderer 兜底。"""

    def __init__(self) -> None:
        self._contracts: dict[str, RendererContract] = {}
        self.register(
            RendererContract(
                renderer_id=DEFAULT_RENDERER_ID,
                accepted_params_schema={},
                replaceable=True,
            )
        )

    def register(self, contract: RendererContract) -> None:
        if contract.renderer_id in self._contracts:
            raise ThemeRendererError(f"renderer 已注册: {contract.renderer_id}")
        self._contracts[contract.renderer_id] = contract

    def resolve(self, renderer_id: str) -> RendererContract:
        try:
            return self._contracts[renderer_id]
        except KeyError:
            raise ThemeRendererError(f"未知 renderer id: {renderer_id}") from None

    def default_renderer(self) -> RendererContract:
        return self._contracts[DEFAULT_RENDERER_ID]

    def all(self) -> Mapping[str, RendererContract]:
        return dict(self._contracts)
