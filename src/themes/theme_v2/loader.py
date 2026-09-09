# -*- coding: utf-8 -*-
"""ThemePackage 加载器（Wave 8 B1）。

把主题目录（themes/<name>/）的 JSON 文件读成未校验的 ThemePackage。
JSON 反序列化即校验流水线的 parse 阶段。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .constants import VARIANT_ID_PATTERN
from .errors import ThemeParseError, ThemeSchemaError
from .types import VariantId

OPTIONAL_FILES = ("design.json", "recipes.json", "motion.json", "icons.json")


@dataclass(frozen=True)
class ThemePackage:
    """raw JSON 解析后的 typed 中间层（未校验）。"""

    root: Path
    manifest: dict[str, Any]               # theme.json
    variants: Mapping[VariantId, dict[str, Any]]
    design: dict[str, Any]
    recipes: dict[str, Any]
    motion: dict[str, Any]
    icons: dict[str, Any]


class ThemePackageLoader:
    """读取主题包目录 → ThemePackage。

    目录结构见 B1 设计文档 2.1：theme.json 必填，variants/*.json 至少一个，
    design/recipes/motion/icons 可选（缺省空 dict，校验器给默认值）。
    """

    def load(self, root: Path) -> ThemePackage:
        if not root.is_dir():
            raise ThemeSchemaError(f"主题目录不存在: {root}")

        manifest = self._read_json(root / "theme.json", required=True)

        variants_dir = root / "variants"
        if not variants_dir.is_dir():
            raise ThemeSchemaError(f"主题缺少 variants 目录: {variants_dir}")
        variants: dict[VariantId, dict[str, Any]] = {}
        for path in sorted(variants_dir.glob("*.json")):
            variant_id = path.stem
            if not VARIANT_ID_PATTERN.fullmatch(variant_id):
                raise ThemeSchemaError(
                    f"非法 variant id '{variant_id}'（必须匹配 {VARIANT_ID_PATTERN.pattern}）"
                )
            variants[variant_id] = self._read_json(path, required=True)
        if not variants:
            raise ThemeSchemaError(f"主题至少需要一个变体: {variants_dir}")

        return ThemePackage(
            root=root,
            manifest=manifest,
            variants=variants,
            design=self._read_json(root / "design.json", required=False),
            recipes=self._read_json(root / "recipes.json", required=False),
            motion=self._read_json(root / "motion.json", required=False),
            icons=self._read_json(root / "icons.json", required=False),
        )

    @staticmethod
    def _read_json(path: Path, *, required: bool) -> dict[str, Any]:
        if not path.is_file():
            if required:
                raise ThemeSchemaError(f"缺少必需文件: {path}")
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ThemeParseError(f"JSON 解析失败: {path}: {exc}") from exc
        except OSError as exc:
            raise ThemeParseError(f"读取失败: {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ThemeSchemaError(f"文件顶层必须是 JSON 对象: {path}")
        return data
