# -*- coding: utf-8 -*-
"""旧 `assets/` 目录一次性迁移（分支① 1.5，D8 已决）。

背景：图片落盘早已固定为文档同级 `PanzerNote_assets/`
（`image_asset_service.ASSETS_DIRNAME`），历史遗留的旧 `assets/` 目录不再产生
新文件，但孤儿清理只扫 `PanzerNote_assets/`（`orphan_image_service`），旧目录
里的未引用图片永远清不掉，目录命名也不统一。

本模块提供**显式触发**的一次性迁移（D1 已决：绝不静默迁移）：
`plan()` 预演完整变更清单 → 用户在对话框确认 → `apply()` 执行 → 报告。
D8 已决：未被引用的图片一并迁入（成为孤儿候选，交给既有清理工具反悔式删除）；
预演确认、不做撤销。

安全设计（skill `panzernote-save-file-safety`）：

- MOVE 保底 `copy → sha256 校验 → 删源`（与 `AssetMigrationService` 同一口径），
  任一步失败源文件不动，状态不比迁移前差；
- 引用扫描不可信（篇数截断 / 单篇超限 / 读取失败）→ 整体放弃，绝不猜着搬；
- 引用重写只替换引用目标区间（`rewrite_local_refs`），文档其余内容逐字保留，
  代码块 / 行内代码里的示例不动；
- 每文档走 `decode_document_bytes` 检测编码、**按原编码写回**，不借机转 UTF-8；
- 打开且未保存的文档（`exclude_docs`）不重写；仅被这类文档引用的图片一并跳过
  ——磁盘重写后，编辑器内存里的旧引用一旦保存就会断链；
- 写回用 `FileGuard.safe_write`（临时文件 + `os.replace` 原子替换），不绕过安全层。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from ..core.config import Config
from ..security.file_guard import FileGuard
from ..utils.logger import get_logger
from .file_open_service import decode_document_bytes
from .image_asset_ledger import ImageAssetLedger
from .image_asset_service import ASSETS_DIRNAME
from .image_reference_scanner import (
    SCAN_MAX_BYTES,
    SCAN_MAX_FILES,
    canonical_path_key,
    resolve_document_refs,
    scan_markdown_files,
)
from .orphan_image_service import _IMAGE_EXTS

logger = get_logger(__name__)

# 清理 / 扫描目录数上限（对齐 orphan_image_service 的量级）
_SCAN_MAX_DIRS = 20000

_key = canonical_path_key


@dataclass(frozen=True)
class LegacyAssetsItem:
    """一张旧 `assets/` 图片的迁移决策。

    `copy_needed=False` 表示目标已有同内容文件（同名同 hash），直接复用，
    校验后删源即可；`renamed_from` 非空表示目标同名冲突已改名为 `dest_abs`，
    引用重写映射里的目标一律用 `dest_abs`。
    """

    source_abs: str
    dest_abs: str
    renamed_from: Optional[str]
    referenced: bool
    referencing_docs: Tuple[str, ...]


@dataclass
class LegacyAssetsPlan:
    """预演结果。`untrustworthy` 为真时调用方必须整体放弃（引用面不完整）。"""

    items: List[LegacyAssetsItem] = field(default_factory=list)
    # {文档绝对路径: {引用原绝对路径: 新目标绝对路径}}（仅含需重写的文档）
    rewrite_docs: Dict[str, Dict[str, str]] = field(default_factory=dict)
    # 仅被排除文档（打开未保存）引用而整体跳过的图片
    blocked_images: List[str] = field(default_factory=list)
    untrustworthy: bool = False

    @property
    def ok(self) -> bool:
        return not self.untrustworthy

    @property
    def legacy_dirs(self) -> List[str]:
        return sorted({os.path.dirname(i.source_abs) for i in self.items})

    @property
    def renamed_count(self) -> int:
        return sum(1 for i in self.items if i.renamed_from)


@dataclass
class LegacyAssetsResult:
    """执行结果（供迁移报告展示）。"""

    moved: List[str] = field(default_factory=list)
    renamed: Dict[str, str] = field(default_factory=dict)
    rewritten: Dict[str, int] = field(default_factory=dict)
    failed: List[str] = field(default_factory=list)
    failed_docs: List[Tuple[str, str]] = field(default_factory=list)
    removed_dirs: List[str] = field(default_factory=list)
    ledger_updated: int = 0


class LegacyAssetsMigrationService:
    """旧 `assets/` → `PanzerNote_assets/` 的一次性迁移：预演 → 确认 → 执行。"""

    LEGACY_DIRNAME = "assets"

    def __init__(self, config: Config) -> None:
        self._config = config

    # ---------- 预演 ----------

    def plan(self, exclude_docs: Optional[Set[str]] = None) -> LegacyAssetsPlan:
        """扫描旧 `assets/` 目录并生成完整变更清单。

        `exclude_docs`：打开且未保存的文档路径——不重写这些文档，仅被它们引用
        的图片也整体跳过（见模块 docstring 的断链分析）。
        """
        plan = LegacyAssetsPlan()
        exclude_keys = {_key(d) for d in (exclude_docs or set())}

        legacy_dirs = self._find_legacy_dirs()
        if not legacy_dirs:
            return plan

        referenced, trustworthy = self._collect_referenced_paths()
        if not trustworthy:
            plan.untrustworthy = True
            return plan

        # 逐图决策。同名冲突改名要用「本批已占用目标」做保留集：
        # a.png / a_1.png 同时存在时，前者改名成 a_1.png 不得撞上后者的自然目标。
        claimed: Set[str] = set()
        for legacy_dir in legacy_dirs:
            dest_dir = os.path.normpath(
                os.path.join(os.path.dirname(legacy_dir), ASSETS_DIRNAME)
            )
            for image in self._images_in_dir(legacy_dir):
                refs = referenced.get(_key(image), [])
                excluded_refs = [d for d in refs if _key(d) in exclude_keys]
                if refs and excluded_refs:
                    # 被「打开未保存」的文档引用（哪怕还有干净文档也引用）：
                    # 磁盘重写后，脏文档内存里的旧引用一保存就断链，整体跳过
                    plan.blocked_images.append(image)
                    continue
                active = [d for d in refs if _key(d) not in exclude_keys]

                dest_abs = os.path.join(dest_dir, os.path.basename(image))
                renamed_from: Optional[str] = None
                if os.path.exists(dest_abs):
                    if not _same_content(image, dest_abs):
                        renamed_from = dest_abs
                        dest_abs = _allocate_free_name(
                            dest_abs, taken=claimed
                        ) or os.path.join(dest_dir, _fallback_name(dest_abs))
                claimed.add(_key(dest_abs))

                plan.items.append(
                    LegacyAssetsItem(
                        source_abs=image,
                        dest_abs=dest_abs,
                        renamed_from=renamed_from,
                        referenced=bool(active),
                        referencing_docs=tuple(active),
                    )
                )
                if active:
                    mapping = {image: dest_abs}
                    for doc in active:
                        plan.rewrite_docs.setdefault(doc, {}).update(mapping)
        return plan

    def _find_legacy_dirs(self) -> List[str]:
        """范围内的非空旧 `assets/` 目录（跳过隐藏目录，限目录数）。"""
        dirs: List[str] = []
        scanned = 0
        for root in self._scope_dirs():
            for dirpath, dirnames, filenames in os.walk(root):
                scanned += 1
                if scanned > _SCAN_MAX_DIRS:
                    logger.warning("旧 assets 扫描超出目录数上限，提前终止")
                    return dirs
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                if os.path.basename(dirpath) != self.LEGACY_DIRNAME:
                    continue
                if not self._images_in_dir(dirpath):
                    continue
                # 防重复：external file 目录与 workspace 根可能重叠
                if all(_key(dirpath) != _key(d) for d in dirs):
                    dirs.append(dirpath)
        return dirs

    @staticmethod
    def _images_in_dir(directory: str) -> List[str]:
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            return []
        return [
            os.path.join(directory, n)
            for n in names
            if os.path.splitext(n)[1].lower() in _IMAGE_EXTS
            and os.path.isfile(os.path.join(directory, n))
        ]

    def _collect_referenced_paths(self) -> Tuple[Dict[str, List[str]], bool]:
        """范围内所有 Markdown 的引用索引 {资源 canonical 键: [文档]} + 可信度。"""
        referenced: Dict[str, List[str]] = {}
        trustworthy = True
        count = 0
        for doc_dir in self._scope_dirs():
            remaining = max(1, SCAN_MAX_FILES - count)
            scan = scan_markdown_files(doc_dir, max_files=remaining)
            count += len(scan.paths)
            trustworthy = trustworthy and not scan.truncated
            for md_path in scan.paths:
                outcome = resolve_document_refs(md_path, max_bytes=SCAN_MAX_BYTES)
                trustworthy = trustworthy and outcome.trustworthy
                for asset in outcome.refs:
                    referenced.setdefault(_key(asset), []).append(md_path)
        return referenced, trustworthy

    def _scope_dirs(self) -> List[str]:
        """Markdown 引用扫描范围：workspace 根 + external files 所在目录。"""
        dirs: List[str] = []
        base = self._config.get_base_path()
        if base and os.path.isdir(base):
            dirs.append(base)
        for ext in self._config.get_external_files():
            parent = os.path.dirname(ext)
            if os.path.isdir(parent) and all(
                _key(parent) != _key(d) for d in dirs
            ):
                dirs.append(parent)
        return dirs

    # ---------- 执行 ----------

    def apply(self, plan: LegacyAssetsPlan) -> LegacyAssetsResult:
        """执行迁移；单项失败只记失败，不中断其余项，绝不丢源文件。"""
        result = LegacyAssetsResult()
        if not plan.items:
            return result

        ledger = self._open_ledger()
        for item in plan.items:
            try:
                if not os.path.exists(item.dest_abs):
                    os.makedirs(os.path.dirname(item.dest_abs), exist_ok=True)
                    _copy_verified(item.source_abs, item.dest_abs)
                elif not _same_content(item.source_abs, item.dest_abs):
                    raise OSError("目标文件与源文件内容不一致")
                os.remove(item.source_abs)
            except Exception as exc:  # noqa: BLE001
                logger.warning("旧 assets 迁移失败（源文件保留）%s: %s", item.source_abs, exc)
                result.failed.append(item.source_abs)
                continue
            result.moved.append(item.source_abs)
            if item.renamed_from:
                result.renamed[item.source_abs] = item.dest_abs
            self._write_back_ledger(ledger, item, result)

        # 引用重写：剔除失败项的映射（文件没动成，引用不能改）
        for doc, mapping in plan.rewrite_docs.items():
            effective = {
                old: new
                for old, new in mapping.items()
                if old not in set(result.failed)
            }
            if not effective:
                continue
            try:
                count = self._rewrite_doc(doc, effective)
            except Exception as exc:  # noqa: BLE001
                logger.warning("引用重写失败 %s: %s", doc, exc)
                result.failed_docs.append((doc, str(exc)))
                continue
            if count:
                result.rewritten[doc] = count

        result.removed_dirs = self._cleanup_empty_dirs(plan)
        if ledger is not None and result.ledger_updated:
            ledger.save()
        return result

    def _rewrite_doc(self, doc: str, mapping: Dict[str, str]) -> int:
        """按原编码读 → 只改引用区间 → 原编码原子写回。返回替换处数。"""
        from .image_reference_scanner import rewrite_local_refs

        with open(doc, "rb") as handle:
            raw = handle.read()
        decoded = decode_document_bytes(raw)
        if decoded is None:
            raise OSError("编码检测失败，无法安全重写")
        text, encoding = decoded
        new_text, count = rewrite_local_refs(
            text, os.path.dirname(doc), mapping
        )
        if count and new_text != text:
            self._file_guard().safe_write(doc, new_text, encoding=encoding)
        return count

    def _cleanup_empty_dirs(self, plan: LegacyAssetsPlan) -> List[str]:
        """迁空后删除旧 `assets/` 目录（只清自己的目录名，绝不碰用户目录）。"""
        removed: List[str] = []
        for directory in sorted(plan.legacy_dirs, key=len, reverse=True):
            if os.path.basename(directory) != self.LEGACY_DIRNAME:
                continue
            try:
                if os.path.isdir(directory) and not os.listdir(directory):
                    os.rmdir(directory)
                    removed.append(directory)
            except OSError as exc:  # noqa: BLE001
                logger.debug("清理空旧目录失败 %s: %s", directory, exc)
        return removed

    # ---------- ledger / file guard ----------

    def _open_ledger(self) -> Optional[ImageAssetLedger]:
        try:
            ledger = ImageAssetLedger(
                self._config.get_path_resolver(), self._config.get_file_guard()
            )
            ledger.load()
            return ledger
        except Exception as exc:  # noqa: BLE001
            logger.warning("图片资源索引不可用，本次跳过回写: %s", exc)
            return None

    def _write_back_ledger(
        self,
        ledger: Optional[ImageAssetLedger],
        item: LegacyAssetsItem,
        result: LegacyAssetsResult,
    ) -> None:
        """位置是唯一键（应用自己知道 A → B），不靠 hash 猜。"""
        if ledger is None:
            return
        matches = ledger.find_by_location(item.source_abs)
        for record in matches:
            if ledger.update_location(record.id, item.dest_abs):
                result.ledger_updated += 1

    def _file_guard(self) -> FileGuard:
        return self._config.get_file_guard()


def _same_content(left: str, right: str) -> bool:
    """按字节比较两个文件是否同内容（同名同 hash = 多个物理副本、同一内容）。"""
    from .asset_migration_service import _same_content as impl

    return impl(left, right)


def _allocate_free_name(dest_abs: str, *, taken: Set[str]) -> Optional[str]:
    """为目标目录同名冲突挑空闲名（复用 AssetMigrationService 的实现与语义）。"""
    from .asset_migration_service import _allocate_free_name as impl

    return impl(dest_abs, taken=taken)


def _fallback_name(dest_abs: str) -> str:
    """极端情况下（空闲名分配失败）的兜底名：时间戳前缀保证唯一。"""
    import time

    stem, suffix = os.path.splitext(os.path.basename(dest_abs))
    return f"{stem}_migrated_{int(time.time())}{suffix}"


def _copy_verified(source: str, dest: str) -> None:
    """保底复制：copy2 → sha256 校验，不一致即删除副本并抛错（源文件不动）。"""
    import shutil

    from .asset_migration_service import sha256_of

    shutil.copy2(source, dest)
    if sha256_of(source) != sha256_of(dest):
        try:
            os.remove(dest)
        except OSError:
            pass
        raise OSError("校验失败：复制后的文件与源文件内容不一致")
