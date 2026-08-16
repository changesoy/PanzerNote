# -*- coding: utf-8 -*-
"""ThemeManager：v2 激活态唯一所有者与切换事务执行器（Wave 8 B7）。

落地 Wave8-B7-Switching 设计文档：
- 四节：prepare → commit 生命周期状态机、4.4 commit 事务边界表（回滚语义）
- 五节：L0 executor（同包变体切换复用当前 snapshot，恒 L0）
- 六节：L1 executor 两阶段替换 + L2 防线
- 七节：Safe Switch pending（latest-wins、interaction_finished 一次性唤醒）

headless：不持有任何 QWidget 引用；全局 QSS 重涂与视觉包装留在调用点
（main_window），经信号/回调衔接。
"""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from PyQt6.QtCore import QMetaObject, QObject, pyqtSignal

from ...utils.logger import get_logger
from .compat import signature_for
from .errors import ThemeError, ThemeSchemaError, ThemeSwitchPlanError, ThemeSwitchUnsupportedError
from .hosts import HostRegistry, ReplacementSafety, RendererHost
from .loader import ThemePackageLoader
from .renderer_registry import RendererRegistry
from .resources import PaletteRegistry, ThemeResourceContract
from .service import ThemeV2Service
from .transition import (
    CommitResult,
    PreparedTheme,
    ThemeTransitionPlan,
    build_plan,
    params_for_recipe,
)
from .types import (
    ColorValue,
    SyntaxTokenKey,
    ThemeSnapshot,
    ThemeSwitchLevel,
    VariantId,
)
from .validator import ThemeValidator

_logger = get_logger(__name__)


class ThemeManagerState(Enum):
    """ThemeManager 生命周期状态（设计 4.2）。

    pending 挂起态不单独设状态：L1 unsafe → 回 IDLE 但 pending 槽非空。
    """

    IDLE = "idle"
    PREPARING = "preparing"
    PREPARED = "prepared"
    COMMITTING = "committing"


class ThemeManager(QObject):
    """v2 激活态唯一所有者：包发现、prepare、commit、回滚、pending、HostRegistry。"""

    #: 切换成功（package_id, variant_id）。signal 发布即 active 态已生效（4.4 步骤 4）。
    theme_committed = pyqtSignal(str, str)
    #: 切换失败（package_id, error 字符串）。失败后 active 态回滚为旧值（4.4）。
    theme_commit_failed = pyqtSignal(str, str)

    def __init__(
        self,
        themes_root: str | Path,
        service: ThemeV2Service,
        registry: RendererRegistry | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._themes_root = Path(themes_root)
        self._service = service
        self._registry = registry or RendererRegistry()
        self._host_registry = HostRegistry()
        self._state = ThemeManagerState.IDLE
        self._prepared: PreparedTheme | None = None
        self._pending: tuple[str, VariantId] | None = None
        self._pending_conns: list[QMetaObject.Connection] = []
        self._active_package_id: str | None = None
        #: 本次 prepare 缓存的新 palette 集合（commit 步骤 2 传给 activate）。
        self._prepared_palettes: Mapping[str, Mapping[SyntaxTokenKey, ColorValue]] | None = None

    # ──────────────────────────────────────────────── 只读属性
    @property
    def state(self) -> ThemeManagerState:
        return self._state

    @property
    def host_registry(self) -> HostRegistry:
        """宿主注册表（B7 产品代码注册 0 个；测试与 B8 注册）。"""
        return self._host_registry

    @property
    def pending(self) -> tuple[str, VariantId] | None:
        """当前 pending 槽（(package_id, variant_id)），latest-wins。"""
        return self._pending

    @property
    def active_package_id(self) -> str | None:
        """当前激活包 id（commit 成功后才更新）。"""
        return self._active_package_id

    # ──────────────────────────────────────────────── 入口
    def request(self, package_id: str, variant_id: VariantId) -> CommitResult:
        """prepare + 尝试 commit 的便捷入口（生产路径用）。

        prepare 失败（ThemeError）→ 发射 theme_commit_failed 并返回 FAILED；
        其余结果见 ``CommitResult``（7.2：pending 期间明确区分）。
        """
        try:
            prepared = self.prepare(package_id, variant_id)
        except ThemeError as exc:
            self.theme_commit_failed.emit(package_id, str(exc))
            return CommitResult.FAILED
        return self._commit_now(prepared)

    def request_variant_for_dark(self, is_dark: bool) -> CommitResult:
        """B7 接管：v1 明暗 → 激活对应变体（theme_engine 委托入口，设计 9.1）。"""
        service = self._service
        snapshot = service.snapshot()
        if snapshot is None:
            return CommitResult.FAILED  # v2 不可用，消费方回退 v1
        variant_id = service.variant_for_dark(is_dark)
        if not variant_id:
            return CommitResult.FAILED
        package_id = self._active_package_id or "default"
        return self.request(package_id, variant_id)

    def prepare(self, package_id: str, variant_id: VariantId) -> PreparedTheme:
        """准备一次切换（全部无 QWidget 副作用，设计 4.3）。

        任何一步失败 → 抛对应 ThemeError 子类并回 IDLE，active 态未动。
        同包变体切换复用当前 snapshot（恒 L0）；跨包走 loader/validator 流水线。
        """
        if self._state in (ThemeManagerState.PREPARING, ThemeManagerState.COMMITTING):
            raise ThemeSwitchPlanError("切换进行中，禁止重入 prepare")
        self._state = ThemeManagerState.PREPARING
        try:
            prepared = self._prepare_impl(package_id, variant_id)
        except Exception:
            self._state = ThemeManagerState.IDLE
            raise
        self._prepared = prepared
        self._state = ThemeManagerState.PREPARED
        return prepared

    def commit(self) -> CommitResult:
        """对最近一次 prepare 的产物执行事务 commit（4.4）。"""
        if self._prepared is None or self._state is not ThemeManagerState.PREPARED:
            raise ThemeSwitchPlanError("无已准备的主题（先调用 prepare）")
        return self._commit_now(self._prepared)

    # ──────────────────────────────────────────────── prepare 实现
    def _prepare_impl(self, package_id: str, variant_id: VariantId) -> PreparedTheme:
        service = self._service
        current = service.snapshot()
        if current is not None and package_id == self._active_package_id:
            # 同包变体切换（5 节）：复用当前 snapshot，仅校验 variant 存在；
            # resolved map 不变 → 恒 L0。palette 沿用现有集合。
            if variant_id not in current.variants:
                raise ThemeSchemaError(
                    f"Theme v2 包 '{package_id}' 无变体 '{variant_id}'"
                    f"（可用: {sorted(current.variants)}）"
                )
            self._prepared_palettes = service.syntax_palettes()
            plan = ThemeTransitionPlan(
                level=ThemeSwitchLevel.L0, package_id=package_id, variant_id=variant_id
            )
            return PreparedTheme(
                snapshot=current, plan=plan, package_id=package_id, variant_id=variant_id
            )
        return self._prepare_package(package_id, variant_id)

    def _prepare_package(self, package_id: str, variant_id: VariantId) -> PreparedTheme:
        root = self._themes_root / package_id
        palettes, palette_registry = self._load_palettes()
        self._prepared_palettes = palettes
        package = ThemePackageLoader().load(root)
        validator = ThemeValidator(
            registry=self._registry,
            palette_registry=palette_registry,
            resource_contract=ThemeResourceContract(
                shared_root=self._themes_root / "syntax"
            ),
        )
        snapshot = validator.validate(package)
        if variant_id not in snapshot.variants:
            raise ThemeSchemaError(
                f"Theme v2 包 '{package_id}' 无变体 '{variant_id}'"
                f"（可用: {sorted(snapshot.variants)}）"
            )

        old = self._service.snapshot()
        if old is None:
            # 首次激活：无 renderer 可替换，恒 L0（避免 build_plan 误判为 L1 且无宿主）
            plan = ThemeTransitionPlan(
                level=ThemeSwitchLevel.L0, package_id=package_id, variant_id=variant_id
            )
        else:
            plan = build_plan(
                signature_for(old),
                signature_for(snapshot),
                self._host_registry,
                package_id,
                variant_id,
            )
        return PreparedTheme(
            snapshot=snapshot, plan=plan, package_id=package_id, variant_id=variant_id
        )

    def _load_palettes(
        self,
    ) -> tuple[dict[str, Mapping[SyntaxTokenKey, ColorValue]], PaletteRegistry]:
        """加载共享 syntax palette 目录（9.1：palette 注册在 prepare 内完成）。"""
        palette_dir = self._themes_root / "syntax" / "palettes"
        palettes: dict[str, Mapping[SyntaxTokenKey, ColorValue]] = {}
        registry = PaletteRegistry()
        for filepath in sorted(palette_dir.glob("*.json")):
            palette_id = filepath.stem
            data = json.loads(filepath.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ThemeSchemaError(f"palette '{palette_id}' 必须是对象")
            palettes[palette_id] = dict(data)
            registry.register(palette_id, data)
        return palettes, registry

    # ──────────────────────────────────────────────── commit 事务（4.4）
    def _commit_now(self, prepared: PreparedTheme) -> CommitResult:
        plan = prepared.plan
        if plan.level is ThemeSwitchLevel.L2:
            raise ThemeSwitchUnsupportedError("Wave 8 不实现 L2 Shell rebuild（仅留 Contract）")

        # 7.1 Safe Switch：L1 且任一宿主 TRANSIENT_INTERACTION → 不执行，置 pending。
        if plan.requires_safe_switch:
            unsafe = self._unsafe_hosts(plan)
            if unsafe:
                self._arm_pending(prepared.package_id, prepared.variant_id, unsafe)
                self._state = ThemeManagerState.IDLE
                return CommitResult.PENDING

        # 4.4：旧 snapshot/变体/palette 对象保留到成功（回滚用）。
        old_snapshot = self._service.snapshot()
        old_variant = self._service.active_variant()
        old_palettes = self._service.syntax_palettes()

        self._state = ThemeManagerState.COMMITTING
        try:
            # 步骤 1：L1 全部预创建（失败 → 下方统一 abort）
            self._prepare_hosts(plan, prepared)
            # 步骤 2：数据先行（activate 不发信号）
            self._service.activate(
                prepared.snapshot, prepared.variant_id, self._prepared_palettes
            )
        except Exception as exc:
            # 步骤 1/2 失败：清理已 prepare 未 commit 的宿主（abort 幂等）
            for step in plan.replacements:
                step.host.abort_replacement()
            self._restore_activation(old_snapshot, old_variant, old_palettes)
            return self._fail(prepared.package_id, exc)

        # 步骤 3：逐宿主 swap（失败 → 逆序 rollback + abort + 快照回滚）
        done: list[RendererHost] = []
        try:
            for step in plan.replacements:
                step.host.commit_replacement()
                done.append(step.host)
        except Exception as exc:
            for host in reversed(done):
                host.rollback_replacement()
            for step in plan.replacements:
                step.host.abort_replacement()
            self._restore_activation(old_snapshot, old_variant, old_palettes)
            return self._fail(prepared.package_id, exc)

        # 步骤 4：发布（成功路径信号唯一发布点）
        self._active_package_id = prepared.package_id
        self._service.notify_changed()
        self.theme_committed.emit(prepared.package_id, prepared.variant_id)
        self._state = ThemeManagerState.IDLE
        return CommitResult.COMMITTED

    @staticmethod
    def _prepare_hosts(plan: ThemeTransitionPlan, prepared: PreparedTheme) -> None:
        for step in plan.replacements:
            params = params_for_recipe(prepared.snapshot, step.recipe_key)
            step.host.prepare_replacement(step.new_renderer_id, params)

    @staticmethod
    def _unsafe_hosts(plan: ThemeTransitionPlan) -> list[RendererHost]:
        return [
            step.host
            for step in plan.replacements
            if step.host.replacement_safety_state() is ReplacementSafety.TRANSIENT_INTERACTION
        ]

    def _restore_activation(
        self,
        old_snapshot: ThemeSnapshot | None,
        old_variant: str | None,
        old_palettes: Mapping[str, Mapping[SyntaxTokenKey, ColorValue]],
    ) -> None:
        """回滚 active 态到旧值（4.4 步骤 2 回滚；失败路径不发信号）。"""
        if old_snapshot is None:
            self._service.deactivate()
        else:
            self._service.activate(old_snapshot, old_variant or "", old_palettes)

    def _fail(self, package_id: str, exc: Exception) -> CommitResult:
        self._state = ThemeManagerState.IDLE
        _logger.warning("Theme v2 切换失败（%s）: %s", package_id, exc)
        self.theme_commit_failed.emit(package_id, str(exc))
        return CommitResult.FAILED

    # ──────────────────────────────────────────────── Safe Switch pending（七节）
    def _arm_pending(
        self, package_id: str, variant_id: VariantId, unsafe: list[RendererHost]
    ) -> None:
        """置 pending + 对 unsafe 宿主逐个建立到 interaction_finished 的一次性连接。

        latest-wins：旧 pending 的连接先断开；重试时重新 prepare + 全量复查。
        """
        self._clear_pending()
        self._pending = (package_id, variant_id)
        for host in unsafe:
            conn = host.interaction_finished.connect(
                lambda pkg=package_id, vid=variant_id: self._retry_pending(pkg, vid)
            )
            self._pending_conns.append(conn)

    def _clear_pending(self) -> None:
        for conn in self._pending_conns:
            QObject.disconnect(conn)
        self._pending_conns = []
        self._pending = None

    def _retry_pending(self, package_id: str, variant_id: VariantId) -> None:
        """interaction_finished 唤醒：重新 prepare + 全量安全性复查。

        仍 unsafe → 重新挂起并重连；latest-wins 已覆盖的旧唤醒直接忽略。
        """
        if self._pending != (package_id, variant_id):
            return
        self._clear_pending()
        try:
            prepared = self.prepare(package_id, variant_id)
            self._commit_now(prepared)
        except ThemeError as exc:
            self._state = ThemeManagerState.IDLE
            self.theme_commit_failed.emit(package_id, str(exc))
