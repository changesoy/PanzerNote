# -*- coding: utf-8 -*-
"""外部移动导致的图片断链恢复（Markdown 图片工作流 E6c2）。

定位：用户在 Explorer 里把 `.md` 搬到别处后，文档里的相对引用会指向新目录下并不
存在的 `PanzerNote_assets/x.png`。本模块按 4.2 / 4.5 / 4.7 定的规则给出恢复方案：

1. 缺失的是**文档解析出的期望绝对路径**（`文档目录/PanzerNote_assets/x.png`）；
2. 按文件名到 ledger 取候选（4.7：ledger 只是线索），逐条复核「文件仍在」+
   **实际重算 sha256** 与记录一致；
3. 同名多候选按内容身份判断：内容一致 = 多个物理副本、同一内容，可从任一有效副本
   恢复；内容不一致 = 真歧义，**不猜**；
4. 在**可证明范围**内（4.5 第 1 条）扫描该候选是否仍被别的 Markdown 引用；
5. 决策：可证明独占 → MOVE；仍被引用 → COPY；证据不足 / 内容已变 / 目标已被占用
   → 交给用户。

落位目标就是文档本来期望的路径，**因此恢复不需要改写 Markdown**。执行沿用
`AssetMigrationService.apply`（copy → verify → delete + 空目录清理 + ledger 回写），
不另造一套文件操作；执行前再复核一次目标位置（4.2 / 5.1「破坏性动作前强制重新检查」）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from ..core.config import Config
from ..utils.logger import get_logger
from .asset_migration_service import (
    MODE_COPY,
    MODE_MOVE,
    AssetMigrationItem,
    AssetMigrationPlan,
    AssetMigrationService,
    sha256_of,
)
from .image_asset_ledger import ImageAssetLedger, ImageAssetRecord
from .image_reference_scanner import canonical_path_key, find_missing_local_images

logger = get_logger(__name__)

# 恢复决策
RECOVER_MOVE = "recover_move"
RECOVER_COPY = "recover_copy"
NEEDS_USER = "needs_user"

# 「不猜」的原因（对话框与汇总文案共用）
REASON_NO_LEDGER = "图片索引不可用，取不到恢复线索"
REASON_NO_CANDIDATE = "图片索引里没有这个文件名的记录"
REASON_CANDIDATE_GONE = "索引里的候选文件已不存在或内容已改变"
REASON_AMBIGUOUS = "同名候选内容不一致，需要人工判断"
REASON_EXCLUSIVE = "索引命中的副本没有被其他 Markdown 引用"
REASON_SHARED = "该副本仍被其他 Markdown 引用，只能复制"


@dataclass(frozen=True)
class AssetRecoveryItem:
    """一项缺失引用的恢复决策。

    `missing_abs` 是文档解析出的**期望绝对路径**（缺失的就是它），`source_abs` 是
    选中用于恢复的现有副本；`outcome` 为 `NEEDS_USER` 时两者仅供参考，不做改动。
    """

    missing_abs: str
    outcome: str
    source_abs: Optional[str] = None
    reason: str = ""

    @property
    def recoverable(self) -> bool:
        return self.outcome in (RECOVER_MOVE, RECOVER_COPY)

    @property
    def migration_action(self) -> Optional[str]:
        if self.outcome == RECOVER_MOVE:
            return MODE_MOVE
        if self.outcome == RECOVER_COPY:
            return MODE_COPY
        return None


@dataclass
class AssetRecoveryPlan:
    """恢复预检结果：可恢复项 + 需要人工处理的项。"""

    document: str = ""
    items: List[AssetRecoveryItem] = field(default_factory=list)

    @property
    def recoverable(self) -> List[AssetRecoveryItem]:
        return [item for item in self.items if item.recoverable]

    @property
    def needs_user(self) -> List[AssetRecoveryItem]:
        return [item for item in self.items if not item.recoverable]


@dataclass
class AssetRecoveryResult:
    """执行结果：`moved` = 恢复且旧位置副本已删除；`copied` = 恢复且旧位置保留。"""

    moved: int = 0
    copied: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def recovered(self) -> int:
        return self.moved + self.copied


class AssetRecoveryService:
    """断链恢复：ledger 线索 → 内容核对 → 可证明范围独占判定 → 复用迁移执行。"""

    def __init__(
        self, config: Config, migration: Optional[AssetMigrationService] = None
    ) -> None:
        self._config = config
        self._migration = migration or AssetMigrationService(config)

    # ---------- 预检 ----------

    def plan(self, doc_path: str, markdown_text: str) -> AssetRecoveryPlan:
        """给出逐项恢复决策；不给结论的项一律标 `NEEDS_USER`。"""
        absolute = os.path.abspath(doc_path)
        plan = AssetRecoveryPlan(document=absolute)
        base_dir = os.path.dirname(absolute)
        try:
            missing = find_missing_local_images(base_dir, markdown_text)
        except Exception as exc:  # noqa: BLE001
            logger.debug("缺失检测失败，按无缺失处理: %s", exc)
            return plan
        if not missing:
            return plan

        ledger = self._migration.open_ledger()
        for missing_abs in missing:
            plan.items.append(self._decide(missing_abs, ledger))
        return plan

    def _decide(
        self, missing_abs: str, ledger: Optional[ImageAssetLedger]
    ) -> AssetRecoveryItem:
        if ledger is None:
            return AssetRecoveryItem(missing_abs, NEEDS_USER, reason=REASON_NO_LEDGER)

        candidates = ledger.find_by_name(os.path.basename(missing_abs))
        if not candidates:
            return AssetRecoveryItem(
                missing_abs, NEEDS_USER, reason=REASON_NO_CANDIDATE
            )
        verified = self._verified_candidates(missing_abs, candidates)
        if not verified:
            return AssetRecoveryItem(
                missing_abs, NEEDS_USER, reason=REASON_CANDIDATE_GONE
            )
        if len({digest for _record, _src, digest in verified}) > 1:
            # 4.7：只有候选实际内容指纹不同，才是真正需要用户判断的歧义
            return AssetRecoveryItem(missing_abs, NEEDS_USER, reason=REASON_AMBIGUOUS)

        _record, source_abs, _digest = verified[0]
        exclusive = not self._migration.is_referenced_elsewhere(
            source_abs, source_abs, missing_abs
        )
        return AssetRecoveryItem(
            missing_abs,
            RECOVER_MOVE if exclusive else RECOVER_COPY,
            source_abs=source_abs,
            reason=REASON_EXCLUSIVE if exclusive else REASON_SHARED,
        )

    @staticmethod
    def _verified_candidates(
        missing_abs: str, candidates: Sequence[ImageAssetRecord]
    ) -> List[Tuple[ImageAssetRecord, str, str]]:
        """复核候选：跳过「已在期望位置」的、不存在的、以及内容指纹不符的。"""
        target_key = canonical_path_key(missing_abs)
        verified: List[Tuple[ImageAssetRecord, str, str]] = []
        for record in candidates:
            source_abs = record.last_known_abs
            if canonical_path_key(source_abs) == target_key:
                continue
            if not os.path.isfile(source_abs):
                continue
            try:
                digest = sha256_of(source_abs)
            except OSError as exc:  # noqa: BLE001
                logger.debug("候选文件取指纹失败 %s: %s", source_abs, exc)
                continue
            if record.sha256 and record.sha256 != digest:
                # 文件被用户改过 → 内容身份不再成立，不猜
                continue
            verified.append((record, source_abs, digest))
        return verified

    # ---------- 执行 ----------

    def apply(self, plan: AssetRecoveryPlan) -> AssetRecoveryResult:
        """执行恢复；执行前强制复核目标位置，落位沿用迁移服务的保底流程。"""
        result = AssetRecoveryResult()
        migration_plan = AssetMigrationPlan()
        for item in plan.recoverable:
            if item.source_abs is None:
                continue
            if os.path.exists(item.missing_abs):
                # 计划生成到执行之间目标位置被占用 → 不猜
                result.skipped += 1
                continue
            migration_plan.items.append(
                AssetMigrationItem(
                    source_abs=item.source_abs,
                    dest_abs=item.missing_abs,
                    action=item.migration_action or MODE_COPY,
                    copy_needed=True,
                )
            )
        if not migration_plan.items:
            return result

        try:
            migrated = self._migration.apply(migration_plan)
        except Exception as exc:  # noqa: BLE001
            logger.error("图片资源恢复执行失败: %s", exc)
            result.failed += len(migration_plan.items)
            return result

        result.moved = len(migrated.moved)
        result.copied = len(migrated.copied)
        result.failed += len(migrated.failed)
        return result
