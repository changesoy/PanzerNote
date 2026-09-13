# -*- coding: utf-8 -*-
"""PanzerNote 内文档移动 / 复制时的图片资源迁移（Markdown 图片工作流 E6c1a）。

规则见 hotfix 4.2 / 4.5：

- 逐项判定：**确认独占 → MOVE；确认共享 → COPY**（不是"永远 Copy / 永远 Move"）；
- 「确认独占」必须落在**可证明范围**内：
  workspace 内资产扫整个 workspace + 已登记 external files；
  workspace 外资产扫源 / 目标文档目录 + 已登记 external files；
- 引用判定一律基于**真实 Markdown** 与 URL decode / 规范化后的 canonical path（D13，
  `../` 跨目录引用同样计入），**绝不拿 ledger 当真相**；
- 执行必须保底安全：`copy target → verify sha256 → delete source`；
  任一步失败都不丢原资源，也不让状态比迁移前更差。

调用顺序由接线方保证：**先 plan() 预检（不可解冲突可整体中止）→ 搬 .md → 再
apply()**；有改名项（`plan.renames()`）时，最后按 span 改写目标文档里的引用。
"""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set

from ..core.config import Config
from ..utils.logger import get_logger
from .image_asset_ledger import ImageAssetLedger
from .image_reference_scanner import (
    canonical_path_key,
    iter_markdown_files,
    resolve_document_refs,
    resolve_refs_in_text,
)

logger = get_logger(__name__)

MODE_MOVE = "move"
MODE_COPY = "copy"

# 迁移后可清理的空目录名：只清我们自己的资源目录，绝不碰用户目录
_CLEANABLE_DIRNAMES = frozenset({"PanzerNote_assets", "assets"})
_HASH_CHUNK = 1024 * 1024

# canonical 路径键与引用解析共用同一实现：口径一致才谈得上「同一路径」
_key = canonical_path_key


def sha256_of(path: str) -> str:
    """文件内容指纹（分块读，避免大图整块进内存）。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(_HASH_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _same_content(left: str, right: str) -> bool:
    """按实际字节比较两个文件是否同内容（同名同 hash = 多个物理副本、同一内容）。"""
    try:
        if os.path.getsize(left) != os.path.getsize(right):
            return False
        return sha256_of(left) == sha256_of(right)
    except OSError:
        return False


def _is_within(path: str, root: str) -> bool:
    if not root:
        return False
    root_key = _key(root)
    path_key = _key(path)
    return path_key == root_key or path_key.startswith(root_key + os.sep)


def _allocate_free_name(dest_abs: str, *, limit: int = 999) -> Optional[str]:
    """为目标目录里的同名冲突挑一个空闲名：`stem_1.ext`、`stem_2.ext`…

    只给**这一份新副本**改名，目标目录里已存在的同名文件保持原样不动。
    分配不出空闲名（极端情况）返回 None，由调用方按冲突整体中止。
    """
    directory = os.path.dirname(dest_abs)
    stem, suffix = os.path.splitext(os.path.basename(dest_abs))
    for index in range(1, limit + 1):
        candidate = os.path.join(directory, f"{stem}_{index}{suffix}")
        if not os.path.exists(candidate):
            return candidate
    return None


@dataclass(frozen=True)
class AssetMigrationItem:
    """单项资源迁移决策。

    `action` 决定源文件是否删除；`copy_needed` 决定是否需要真正复制
    （目标已存在同内容文件时为 False，直接复用）。`renamed_from` 非空表示目标
    同名冲突已改名为 `dest_abs`，调用方必须据此改写目标文档里的引用。
    """

    source_abs: str
    dest_abs: str
    action: str
    copy_needed: bool
    renamed_from: Optional[str] = None


@dataclass
class AssetMigrationPlan:
    """迁移预检结果。`conflicts` 非空时调用方必须整体中止，不动任何文件。

    同名但内容不同不再进 `conflicts`（E6c1b2 起改为改名 + 改写引用），只有连空闲
    名都分配不出来这种极端情况才判为冲突。
    """

    items: List[AssetMigrationItem] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.conflicts

    def renames(self) -> Dict[str, str]:
        """{原目标绝对路径: 改名后的目标绝对路径}；无改名时为空字典。"""
        return {
            item.renamed_from: item.dest_abs
            for item in self.items
            if item.renamed_from
        }


@dataclass
class AssetMigrationResult:
    """执行结果。

    `moved` = 源文件已删除（资源实际位置落到目标）；
    `copied` = 新复制了一份副本（源保留，Copy 语义）；
    `reused` = 目标已有同内容文件、未复制（仅 Copy 语义下会出现，因为
    MOVE + 复用同样算 `moved`）。
    """

    moved: List[str] = field(default_factory=list)
    copied: List[str] = field(default_factory=list)
    reused: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    removed_dirs: List[str] = field(default_factory=list)
    ledger_updated: int = 0


class _ReferenceIndex:
    """可证明范围内「资源 canonical 路径 → 引用它的文档」索引。

    一次扫描、多次查询：让同一批资产的独占判定不必反复读遍整个范围。
    """

    def __init__(
        self,
        roots: Sequence[str],
        external_files: Sequence[str],
        exclude_docs: Set[str],
    ) -> None:
        self._refs: Dict[str, List[str]] = {}
        for doc in self._iter_documents(roots, external_files):
            if _key(doc) in exclude_docs:
                continue
            for asset in resolve_document_refs(doc):
                self._refs.setdefault(_key(asset), []).append(doc)

    @staticmethod
    def _iter_documents(
        roots: Sequence[str], external_files: Sequence[str]
    ) -> List[str]:
        documents: List[str] = []
        seen: Set[str] = set()
        for root in roots:
            for doc in iter_markdown_files(root):
                if _key(doc) not in seen:
                    seen.add(_key(doc))
                    documents.append(doc)
        for extra in external_files:
            if os.path.isfile(extra) and _key(extra) not in seen:
                seen.add(_key(extra))
                documents.append(extra)
        return documents

    def is_referenced_elsewhere(self, asset_abs: str) -> bool:
        return bool(self._refs.get(_key(asset_abs)))


class AssetMigrationService:
    """文档移动 / 复制时的资源迁移：预检 → 执行 → ledger 回写。"""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._indexes: Dict[frozenset, _ReferenceIndex] = {}

    # ---------- 预检 ----------

    def plan(
        self,
        source_md: str,
        dest_md: str,
        mode: str,
        *,
        markdown_text: Optional[str] = None,
    ) -> AssetMigrationPlan:
        """给出逐项 MOVE / COPY 决策；目标同名冲突会改名为空闲名并记入 item。

        `markdown_text` 传入编辑器里的**当前内容**时以它为准——文档有未保存改动
        时磁盘内容不是真相（保存是异步的，预检读盘会漏掉刚插入的引用）。
        """
        plan = AssetMigrationPlan()
        source_md = os.path.abspath(source_md)
        dest_md = os.path.abspath(dest_md)
        source_dir = os.path.dirname(source_md)
        dest_dir = os.path.dirname(dest_md)

        # 排除集合：目标文档始终排除；Move 时源文档即将不存在，一并排除。
        # 于是 Copy 模式（源文档保留且仍引用）自然得出 COPY，不需要单独分支。
        exclude = {_key(dest_md)}
        if mode == MODE_MOVE:
            exclude.add(_key(source_md))

        if markdown_text is not None:
            assets = resolve_refs_in_text(source_dir, markdown_text)
        else:
            assets = resolve_document_refs(source_md)

        for asset in assets:
            # 已断链的引用无从迁移（交由缺失检测 / E6c2），也不该算冲突
            if not os.path.isfile(asset):
                plan.skipped.append(asset)
                continue
            relative = os.path.relpath(asset, source_dir)
            if relative.startswith(".."):
                # 跨出源目录树（如 ../other/x.png）：复制文档无法保持该相对关系，
                # 不动文件，留给缺失检测 / E6c2 处理。
                plan.skipped.append(asset)
                continue
            dest_abs = os.path.normpath(os.path.join(dest_dir, relative))
            if _key(asset) == _key(dest_abs):
                plan.skipped.append(asset)
                continue

            copy_needed = True
            renamed_from: Optional[str] = None
            if os.path.exists(dest_abs):
                if _same_content(asset, dest_abs):
                    copy_needed = False  # 同名同 hash：多个物理副本、同一内容，直接复用
                else:
                    # 同名不同内容：绝不覆盖目标目录里的现有文件，给这一份挑个空闲名
                    # （x_1.png / x_2.png…），由调用方把新文档里的引用改写到新名字。
                    free_name = _allocate_free_name(dest_abs)
                    if free_name is None:
                        plan.conflicts.append(asset)
                        continue
                    renamed_from = dest_abs
                    dest_abs = free_name

            exclusive = not self.is_referenced_elsewhere(
                asset, source_md, dest_md, exclude
            )
            plan.items.append(
                AssetMigrationItem(
                    source_abs=asset,
                    dest_abs=dest_abs,
                    action=MODE_MOVE if exclusive else MODE_COPY,
                    copy_needed=copy_needed,
                    renamed_from=renamed_from,
                )
            )
        return plan

    def is_referenced_elsewhere(
        self,
        asset_abs: str,
        source_md: str,
        dest_md: str,
        exclude: Optional[Set[str]] = None,
    ) -> bool:
        """可证明范围内是否还有别的文档引用该路径（排除 `exclude` 中的文档）。

        范围口径见 4.5 第 1 条：资产在 workspace 内 → 扫整个 workspace + 已登记
        external files；在 workspace 外 → 扫 `source_md` / `dest_md` 所在目录 +
        external files。恢复链路复用同一口径（传入候选资产与期望落位路径）。
        """
        exclude_docs = {_key(doc) for doc in (exclude or set())}
        key = self._index_key(asset_abs, source_md, dest_md)
        index = self._indexes.get(key)
        if index is None:
            index = _ReferenceIndex(
                roots=self._scope_roots(asset_abs, source_md, dest_md),
                external_files=self._external_files(),
                exclude_docs=exclude_docs,
            )
            self._indexes[key] = index
        return index.is_referenced_elsewhere(asset_abs)

    def _scope_roots(
        self, asset_abs: str, source_md: str, dest_md: str
    ) -> List[str]:
        base = self._config.get_base_path()
        if base and _is_within(asset_abs, base):
            return [base]
        return [os.path.dirname(source_md), os.path.dirname(dest_md)]

    def _index_key(
        self, asset_abs: str, source_md: str, dest_md: str
    ) -> frozenset:
        return frozenset(self._scope_roots(asset_abs, source_md, dest_md))

    def _external_files(self) -> List[str]:
        try:
            return list(self._config.get_external_files())
        except Exception as exc:  # noqa: BLE001
            logger.debug("读取 external files 失败，按空处理: %s", exc)
            return []

    # ---------- 执行 ----------

    def apply(self, plan: AssetMigrationPlan) -> AssetMigrationResult:
        """执行迁移；单项失败只记失败，不中断其余项，也绝不丢源文件。"""
        result = AssetMigrationResult()
        if not plan.items:
            return result

        ledger = self.open_ledger()
        for item in plan.items:
            created_dest = False
            try:
                if item.copy_needed:
                    os.makedirs(os.path.dirname(item.dest_abs), exist_ok=True)
                    shutil.copy2(item.source_abs, item.dest_abs)
                    created_dest = True
                if not _same_content(item.source_abs, item.dest_abs):
                    raise OSError("校验失败：目标文件与源文件内容不一致")
                if item.action == MODE_MOVE:
                    os.remove(item.source_abs)
                    result.moved.append(item.source_abs)
                elif item.copy_needed:
                    result.copied.append(item.source_abs)
                else:
                    result.reused.append(item.source_abs)
            except Exception as exc:  # noqa: BLE001
                logger.warning("资源迁移失败（源文件保留）%s: %s", item.source_abs, exc)
                result.failed.append(item.source_abs)
                if created_dest:
                    try:
                        os.remove(item.dest_abs)
                    except OSError:
                        pass
                continue

            if item.action == MODE_MOVE or item.copy_needed:
                self._write_back_ledger(ledger, item, result)

        result.removed_dirs = self._cleanup_empty_dirs(plan)
        if ledger is not None and result.ledger_updated:
            ledger.save()
        return result

    def _cleanup_empty_dirs(self, plan: AssetMigrationPlan) -> List[str]:
        """MOVE 后旧资源目录已空则删除（只清 PanzerNote_assets / assets）。"""
        candidates = {
            os.path.dirname(item.source_abs)
            for item in plan.items
            if item.action == MODE_MOVE
        }
        removed: List[str] = []
        for directory in sorted(candidates, key=len, reverse=True):
            if os.path.basename(directory) not in _CLEANABLE_DIRNAMES:
                continue
            if not os.path.isdir(directory):
                continue
            try:
                if not os.listdir(directory):
                    os.rmdir(directory)
                    removed.append(directory)
            except OSError as exc:  # noqa: BLE001
                logger.debug("清理空资源目录失败 %s: %s", directory, exc)
        return removed

    # ---------- ledger ----------

    def open_ledger(self) -> Optional[ImageAssetLedger]:
        """打开并加载 ledger；不可用时返回 None（调用方跳过回写，不阻断文件操作）。"""
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
        item: AssetMigrationItem,
        result: AssetMigrationResult,
    ) -> None:
        """回写最后已知位置：位置是唯一键（应用自己知道 A → B），不靠 hash 猜。"""
        if ledger is None:
            return
        matches = ledger.find_by_location(item.source_abs)
        if not matches:
            return
        name = os.path.basename(item.dest_abs)
        for record in matches:
            if item.action == MODE_MOVE:
                if ledger.update_location(record.id, item.dest_abs, name=name):
                    result.ledger_updated += 1
            else:
                # COPY：源记录仍有效，为新副本补一条（Copy 产生两个物理 entry）
                ledger.add_copy(record, item.dest_abs)
                result.ledger_updated += 1
