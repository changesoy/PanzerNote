# -*- coding: utf-8 -*-
"""Theme Resource Contract 与 syntax palette 注册表（Wave 8 B1）。

目标：任何非法主题在 activate 前即被拒绝，不得等到 QWidget paint 时才 KeyError。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from .constants import ALLOWED_RESOURCE_EXTENSIONS
from .errors import ThemeResourceError

_URL_SCHEME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


class PaletteRegistry:
    """syntax palette 注册表：palette id → 数据（B2 起随 palette 文件填充）。"""

    def __init__(self) -> None:
        self._palettes: dict[str, Any] = {}

    def register(self, palette_id: str, data: Any) -> None:
        if not palette_id:
            raise ValueError("palette id 不能为空")
        self._palettes[palette_id] = data

    def contains(self, palette_id: str) -> bool:
        return palette_id in self._palettes

    def all(self) -> Mapping[str, Any]:
        return dict(self._palettes)


class ThemeResourceContract:
    """资源引用边界（4.3）。

    - 禁止 http(s) 等 URL 引用（零运行时网络依赖）
    - 路径 normalize 后必须位于 theme root 或 approved shared registry，不允许 `../` 越界
    - 仅允许白名单扩展名
    """

    def __init__(self, shared_root: Path | None = None) -> None:
        self._shared_root = shared_root

    def validate_path(self, reference: str, theme_root: Path) -> Path:
        """校验资源引用并返回解析后的绝对路径。越界抛 ThemeResourceError。"""
        theme_root = Path(theme_root)
        if not reference:
            raise ThemeResourceError("空资源引用")
        if _URL_SCHEME_PATTERN.match(reference):
            raise ThemeResourceError(f"禁止 URL 资源引用: {reference}")

        try:
            path = Path(reference)
        except ValueError as exc:
            raise ThemeResourceError(f"非法资源路径: {reference}") from exc

        extension = path.suffix.lower()
        if extension not in ALLOWED_RESOURCE_EXTENSIONS:
            raise ThemeResourceError(
                f"资源类型不在白名单内（{sorted(ALLOWED_RESOURCE_EXTENSIONS)}）: {reference}"
            )

        absolute = path if path.is_absolute() else (theme_root / path)
        try:
            resolved = absolute.resolve()
        except OSError as exc:
            raise ThemeResourceError(f"资源路径无法解析: {reference}") from exc

        # B1 4.3：不存在的资源在 activate 前报错，不得拖到 paint/加载时爆发（补漏 D P1-8）。
        if not resolved.is_file():
            raise ThemeResourceError(f"资源文件不存在: {reference}")

        theme_root_resolved = theme_root.resolve()
        if _is_within(resolved, theme_root_resolved):
            return resolved

        if self._shared_root is not None:
            shared_resolved = self._shared_root.resolve()
            if _is_within(resolved, shared_resolved):
                return resolved

        raise ThemeResourceError(f"资源引用越界（不允许 ../ 逃逸）: {reference}")


def _is_within(path: Path, root: Path) -> bool:
    return path.is_relative_to(root)
