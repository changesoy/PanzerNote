# -*- coding: utf-8 -*-
"""TransitionPlan 数据模型与 planner（Wave 8 B7 Switching）。

兼容性真正比较的是 Resolved Renderer Map（compat.compute_switch_level），
planner 据此生成结构化切换计划；L1 计划中的每个替换步骤都绑定到
HostRegistry 解析出的存活宿主（无宿主 → ThemeSwitchPlanError，见 3.3）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .compat import compute_switch_level
from .errors import ThemeSwitchPlanError
from .hosts import HostRegistry, RendererHost
from .types import (
    CompatibilitySignature,
    RecipeKey,
    ThemeSnapshot,
    ThemeSwitchLevel,
    VariantId,
)


class CommitResult(Enum):
    """request/commit 的返回语义（见 7.2：pending 期间明确区分）。"""

    COMMITTED = "committed"
    PENDING = "pending"
    FAILED = "failed"


@dataclass(frozen=True)
class RendererReplacementStep:
    """单个组件槽位的 renderer 替换步骤（运行期绑定宿主）。"""

    recipe_key: RecipeKey
    old_renderer_id: str
    new_renderer_id: str
    host: RendererHost


@dataclass(frozen=True)
class ThemeTransitionPlan:
    """一次切换的结构化计划：等级 + 目标 + 替换步骤。"""

    level: ThemeSwitchLevel
    package_id: str
    variant_id: VariantId
    replacements: tuple[RendererReplacementStep, ...] = field(default_factory=tuple)

    @property
    def requires_safe_switch(self) -> bool:
        """有 renderer 替换步骤即需 Safe Switch（L0 恒 False）。"""
        return bool(self.replacements)


@dataclass(frozen=True)
class PreparedTheme:
    """manager prepare 产物：已完整校验的快照 + 切换计划。"""

    snapshot: ThemeSnapshot
    plan: ThemeTransitionPlan
    package_id: str
    variant_id: VariantId


def build_plan(
    old_sig: CompatibilitySignature,
    new_sig: CompatibilitySignature,
    hosts: HostRegistry,
    package_id: str,
    variant_id: VariantId,
) -> ThemeTransitionPlan:
    """比较两份签名，生成切换计划。

    - L0（组件级 resolved map 相同，含同包变体切换）→ 空替换步骤；
    - L1 → 对每个 renderer 变化的 recipe key，从 HostRegistry 取全部存活宿主，
      逐宿主生成 step；某 key 无宿主 → 抛 ThemeSwitchPlanError（B7 不允许
      "计划里有替换、实际没人执行"的静默不一致）；
    - L2 → 照常产出 plan（replacements 空），executor 拒绝执行（见 6.4）。
    """
    level = compute_switch_level(old_sig, new_sig)
    if level is not ThemeSwitchLevel.L1:
        return ThemeTransitionPlan(
            level=level, package_id=package_id, variant_id=variant_id
        )

    old_map = old_sig.resolved.mapping
    new_map = new_sig.resolved.mapping
    steps: list[RendererReplacementStep] = []
    for key in sorted(set(old_map) | set(new_map)):
        if old_map.get(key) == new_map.get(key):
            continue
        host_list = hosts.hosts_for(key)
        if not host_list:
            raise ThemeSwitchPlanError(
                f"组件 '{key}' 需要 renderer 替换（{old_map.get(key)} → {new_map[key]}），"
                "但无注册宿主"
            )
        for host in host_list:
            steps.append(
                RendererReplacementStep(
                    recipe_key=key,
                    old_renderer_id=old_map.get(key, ""),
                    new_renderer_id=new_map[key],
                    host=host,
                )
            )
    return ThemeTransitionPlan(
        level=level,
        package_id=package_id,
        variant_id=variant_id,
        replacements=tuple(steps),
    )


def params_for_recipe(snapshot: ThemeSnapshot, recipe_key: RecipeKey) -> Mapping[str, Any]:
    """取新快照中某组件槽位的 renderer_params（供 host.prepare_replacement）。"""
    recipe = snapshot.recipes.get(recipe_key)
    if recipe is None:
        return {}
    return dict(recipe.renderer_params)
