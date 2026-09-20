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
from .image_asset_service import ASSETS_DIRNAME
from .image_reference_scanner import canonical_path_key, find_missing_local_images

logger = get_logger(__name__)

# 恢复决策
RECOVER_MOVE = "recover_move"
RECOVER_COPY = "recover_copy"
NEEDS_USER = "needs_user"

# 兜底扫描的安全阀（与引用扫描同量级）
SCAN_MAX_DIRS = 20000

# 「不猜」的原因（对话框与汇总文案共用）
REASON_NO_LEDGER = "图片索引不可用，取不到恢复线索"
REASON_NO_CANDIDATE = "图片索引与可扫描范围内都找不到这个文件名"
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
        # 兜底扫描只在「完全没有 ledger 线索」时启用：旧图片 / 手动拷贝的图片
        # 从未进过索引，范围资源目录按文件名找仍可能接活。一旦 ledger 有同名记录
        # 但复核不过（文件被删 / 内容已改），说明「这条线索失效」，仍然不猜——
        # 否则会把内容被用户改过的文件误当作同一张图捞回来。
        if ledger is None:
            verified = self._scan_candidates(missing_abs)
            if not verified:
                return AssetRecoveryItem(missing_abs, NEEDS_USER, reason=REASON_NO_LEDGER)
            return self._finalize(missing_abs, verified)

        candidates = ledger.find_by_name(os.path.basename(missing_abs))
        if not candidates:
            verified = self._scan_candidates(missing_abs)
            if not verified:
                return AssetRecoveryItem(
                    missing_abs, NEEDS_USER, reason=REASON_NO_CANDIDATE
                )
            return self._finalize(missing_abs, verified)

        verified = self._verified_candidates(missing_abs, candidates)
        if not verified:
            return AssetRecoveryItem(
                missing_abs, NEEDS_USER, reason=REASON_CANDIDATE_GONE
            )
        return self._finalize(missing_abs, verified)

    def _finalize(
        self, missing_abs: str, verified: List[Tuple[str, str]]
    ) -> AssetRecoveryItem:
        if len({digest for _src, digest in verified}) > 1:
            # 4.7：只有候选实际内容指纹不同，才是真正需要用户判断的歧义
            return AssetRecoveryItem(missing_abs, NEEDS_USER, reason=REASON_AMBIGUOUS)

        source_abs, _digest = verified[0]
        exclusive = not self._migration.is_referenced_elsewhere(
            source_abs, source_abs, missing_abs
        )
        return AssetRecoveryItem(
            missing_abs,
            RECOVER_MOVE if exclusive else RECOVER_COPY,
            source_abs=source_abs,
            reason=REASON_EXCLUSIVE if exclusive else REASON_SHARED,
        )

    def _scan_candidates(
        self, missing_abs: str
    ) -> List[Tuple[str, str]]:
        """ledger 无有效线索时的兜底：在可证明范围内按文件名扫描资源目录。

        命中条件仍保守：只认 `PanzerNote_assets/` 里的同名文件，多个命中时
        内容指纹一致才可用（否则由调用方按歧义交给用户）。无 hash 记录可比对，
        文件名 + 目录约定即身份证据——这正是「索引只是线索，不猜」的兜底延伸。
        """
        name = os.path.basename(missing_abs)
        target_key = canonical_path_key(missing_abs)
        found: List[Tuple[str, str]] = []
        scanned_dirs = 0
        try:
            roots = self._scan_roots(missing_abs)
        except Exception as exc:  # noqa: BLE001
            logger.debug("兜底扫描根目录解析失败: %s", exc)
            return found
        for root_dir in roots:
            if not os.path.isdir(root_dir):
                continue
            for dirpath, dirnames, filenames in os.walk(root_dir):
                scanned_dirs += 1
                if scanned_dirs > SCAN_MAX_DIRS:
                    logger.warning("兜底扫描超出目录数上限，提前终止")
                    return self._dedupe_verified(found)
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                if os.path.basename(dirpath) != ASSETS_DIRNAME:
                    continue
                if name not in filenames:
                    continue
                candidate = os.path.join(dirpath, name)
                if canonical_path_key(candidate) == target_key:
                    continue  # 缺失的期望位置本身
                try:
                    digest = sha256_of(candidate)
                except OSError:
                    continue
                found.append((candidate, digest))
        return self._dedupe_verified(found)

    @staticmethod
    def _dedupe_verified(found: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """同名命中按 canonical 路径去重（os.walk 不会重复，防御大小写差异）。"""
        seen: set[str] = set()
        unique: List[Tuple[str, str]] = []
        for source, digest in found:
            key = canonical_path_key(source)
            if key in seen:
                continue
            seen.add(key)
            unique.append((source, digest))
        return unique

    def _scan_roots(self, missing_abs: str) -> List[str]:
        """兜底扫描范围：workspace 根 + 缺失文档所在目录（可证明范围的同口径）。"""
        roots: List[str] = []
        base = self._config.get_base_path()
        if base:
            roots.append(base)
        doc_dir = os.path.dirname(os.path.dirname(os.path.abspath(missing_abs)))
        if doc_dir and all(canonical_path_key(doc_dir) != canonical_path_key(r) for r in roots):
            roots.append(doc_dir)
        return roots

    @staticmethod
    def _verified_candidates(
        missing_abs: str, candidates: Sequence[ImageAssetRecord]
    ) -> List[Tuple[str, str]]:
        """复核候选：跳过「已在期望位置」的、不存在的、以及内容指纹不符的。"""
        target_key = canonical_path_key(missing_abs)
        verified: List[Tuple[str, str]] = []
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
            verified.append((source_abs, digest))
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
