# -*- coding: utf-8 -*-
"""清理未使用的图片（Markdown 图片工作流收尾）。

定位：删除文档 / 删除文档中的图片引用后，落盘的 `PanzerNote_assets/` 图片不会被
自动删除——本模块提供**手动触发的**孤儿图片检测与清理：

1. 收集引用面：workspace + external files 范围内所有 Markdown 的本地图片引用
   （复用 `image_reference_scanner`，与恢复 / 迁移同一口径）；
2. 扫描范围：workspace 根 + external files 所在目录里的 `PanzerNote_assets/`
   目录中的图片文件；
3. 未被任何 Markdown 引用 → 孤儿候选。删除动作不在本模块执行，交给对话框
   勾选确认后由调用方 send2trash 进回收站（可反悔）。

安全边界：只清理「可证明未被引用」的图片；不触碰目录里其它文件；清理可反悔。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Set

from ..core.config import Config
from ..utils.logger import get_logger
from .image_asset_ledger import ImageAssetLedger
from .image_asset_service import ASSETS_DIRNAME
from .image_reference_scanner import (
    SCAN_MAX_FILES,
    canonical_path_key,
    iter_markdown_files,
    resolve_document_refs,
)

logger = get_logger(__name__)

# 清理扫描目录数上限（与恢复兜底同量级）
_SCAN_MAX_DIRS = 20000


@dataclass(frozen=True)
class OrphanImage:
    """一个未被任何 Markdown 引用的托管图片候选。"""

    abs_path: str
    size: int

    @property
    def name(self) -> str:
        return os.path.basename(self.abs_path)

    @property
    def dirname(self) -> str:
        return os.path.dirname(self.abs_path)

    @property
    def human_size(self) -> str:
        if self.size >= 1024 * 1024:
            return f"{self.size / (1024 * 1024):.1f} MB"
        return f"{max(1, self.size // 1024)} KB"


class OrphanImageService:
    """发现未被引用的图片；删除由调用方确认后执行（进回收站）。"""

    def __init__(self, config: Config) -> None:
        self._config = config

    # ---------- 扫描 ----------

    def find_orphans(self) -> List[OrphanImage]:
        """返回范围内所有未被 Markdown 引用的图片文件（按目录分组保序）。"""
        referenced = self._collect_referenced_paths()
        candidates = self._scan_asset_images()
        orphans: List[OrphanImage] = []
        seen: Set[str] = set()
        for candidate in candidates:
            key = canonical_path_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            if key in referenced:
                continue
            try:
                size = os.path.getsize(candidate)
            except OSError:
                continue
            orphans.append(OrphanImage(candidate, size))
        orphans.sort(key=lambda o: (o.dirname, o.name))
        return orphans

    def _collect_referenced_paths(self) -> Set[str]:
        """范围内所有 Markdown 引用的本地图片 canonical 键集合。"""
        referenced: Set[str] = set()
        base = self._config.get_base_path()
        doc_dirs = self._doc_scan_dirs()
        count = 0
        for doc_dir in doc_dirs:
            remaining = max(1, SCAN_MAX_FILES - count)
            for md_path in iter_markdown_files(doc_dir, max_files=remaining):
                count += 1
                for ref in resolve_document_refs(md_path):
                    referenced.add(canonical_path_key(ref))
        return referenced

    def _doc_scan_dirs(self) -> List[str]:
        """Markdown 引用扫描范围：workspace 根 + external files 所在目录。"""
        dirs: List[str] = []
        base = self._config.get_base_path()
        if base and os.path.isdir(base):
            dirs.append(base)
        for ext in self._config.get_external_files():
            parent = os.path.dirname(ext)
            if os.path.isdir(parent) and all(
                canonical_path_key(parent) != canonical_path_key(d) for d in dirs
            ):
                dirs.append(parent)
        return dirs

    def _scan_asset_images(self) -> List[str]:
        """扫描范围内所有 `PanzerNote_assets/` 目录下的图片文件。"""
        images: List[str] = []
        roots = self._doc_scan_dirs()
        scanned_dirs = 0
        for root_dir in roots:
            for dirpath, dirnames, filenames in os.walk(root_dir):
                scanned_dirs += 1
                if scanned_dirs > _SCAN_MAX_DIRS:
                    logger.warning("清理扫描超出目录数上限，提前终止")
                    return images
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                if os.path.basename(dirpath) != ASSETS_DIRNAME:
                    continue
                for filename in filenames:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in _IMAGE_EXTS:
                        images.append(os.path.join(dirpath, filename))
        return images

    # ---------- ledger 同步 ----------

    def open_ledger(self) -> Optional[ImageAssetLedger]:
        """打开 ledger；不可用时返回 None（清理不阻断）。"""
        try:
            ledger = ImageAssetLedger(
                self._config.get_path_resolver(), self._config.get_file_guard()
            )
            ledger.load()
            return ledger
        except Exception as exc:  # noqa: BLE001
            logger.debug("图片索引不可用，跳过 ledger 同步: %s", exc)
            return None

    def remove_from_ledger(self, removed: List[str]) -> None:
        """从 ledger 移除已清理文件的记录（匹配 last_known_abs 或 name）。"""
        ledger = self.open_ledger()
        if ledger is None:
            return
        removed_keys = {canonical_path_key(p) for p in removed}
        for record in ledger.records():
            if canonical_path_key(record.last_known_abs) in removed_keys:
                ledger.remove(record.id)
        ledger.save()


_IMAGE_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg",
    ".webp", ".ico", ".tif", ".tiff",
}
