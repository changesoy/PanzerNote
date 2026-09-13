# -*- coding: utf-8 -*-
"""托管图片资源的隐藏恢复索引（Markdown 图片工作流 E6a）。

定位：ledger 只是 PanzerNote 对自己创建 / 管理过的图片留下的「最后已知线索」，
**不取代 Markdown + 文件系统作为真实状态** —— 任何 Move / 恢复判定都必须回到
真实文件与真实引用重新核对。字段刻意不存引用关系（不做 `referenced_by`，也不做
`last_seen_references`）：那是破坏性动作前按可证明范围实时扫描得出的结论，
缓存下来只会产生一份必然过时的数据。

存储：`{base_path}/data/config/image_assets.json`，与 `workspace.json` 同级，
天然不对外显示、不污染笔记目录。

故障域很小：可删除、可重建；文件损坏或版本不符即降级为空；`save()` 写失败只告警
并返回 False，不阻断调用方（插入图片不应因索引写不了而失败）。
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.path_resolver import PathResolver, load_json, save_json
from ..security.file_guard import FileGuard
from ..utils.logger import get_logger

logger = get_logger(__name__)

SCHEMA_VERSION = 1
LEDGER_FILENAME = "image_assets.json"

# origin：图片进入文档的途径
ORIGIN_PASTE = "paste"
ORIGIN_FILE = "file"
ORIGIN_DROP = "drop"


def _location_key(absolute_path: str) -> str:
    """位置比较键：规范化 + 大小写归一（Windows 路径不区分大小写）。"""
    return os.path.normcase(os.path.normpath(absolute_path))


@dataclass(frozen=True)
class ImageAssetRecord:
    """一条托管图片的最后已知线索。"""

    id: str
    name: str
    last_known_abs: str
    sha256: str
    size: int
    added_at: str
    origin: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "last_known_abs": self.last_known_abs,
            "sha256": self.sha256,
            "size": self.size,
            "added_at": self.added_at,
            "origin": self.origin,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["ImageAssetRecord"]:
        """从 dict 还原；缺关键字段时返回 None（跳过该条，不猜）。"""
        asset_id = data.get("id")
        name = data.get("name")
        last_known_abs = data.get("last_known_abs")
        if not (
            isinstance(asset_id, str)
            and asset_id
            and isinstance(name, str)
            and name
            and isinstance(last_known_abs, str)
            and last_known_abs
        ):
            return None
        size = data.get("size")
        return cls(
            id=asset_id,
            name=name,
            last_known_abs=last_known_abs,
            sha256=str(data.get("sha256") or ""),
            size=int(size) if isinstance(size, (int, float)) else 0,
            added_at=str(data.get("added_at") or ""),
            origin=str(data.get("origin") or ""),
        )


class ImageAssetLedger:
    """`image_assets.json` 的读写与查询。"""

    def __init__(self, path_resolver: PathResolver, file_guard: FileGuard) -> None:
        self._path_resolver = path_resolver
        self._file_guard = file_guard
        self._assets: List[ImageAssetRecord] = []

    # ---------- 读写 ----------

    def path(self) -> str:
        """ledger 文件路径（`{config_dir}/image_assets.json`）。"""
        return os.path.join(self._path_resolver.get_config_dir(), LEDGER_FILENAME)

    def load(self) -> None:
        """加载 ledger；文件缺失 / 损坏 / 结构或版本不符时降级为空。"""
        raw = load_json(
            self._file_guard,
            self.path(),
            {"schema_version": SCHEMA_VERSION, "assets": []},
        )
        if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
            logger.warning("图片资源索引结构或版本不符，本次按空处理: %s", self.path())
            self._assets = []
            return
        entries = raw.get("assets")
        if not isinstance(entries, list):
            self._assets = []
            return
        records = [
            ImageAssetRecord.from_dict(entry)
            for entry in entries
            if isinstance(entry, dict)
        ]
        self._assets = [record for record in records if record is not None]

    def save(self) -> bool:
        """原子写回；失败只告警并返回 False（索引可重建，不阻断调用方）。"""
        try:
            os.makedirs(self._path_resolver.get_config_dir(), exist_ok=True)
            save_json(
                self._file_guard,
                self.path(),
                {
                    "schema_version": SCHEMA_VERSION,
                    "assets": [record.to_dict() for record in self._assets],
                },
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("图片资源索引写入失败（不影响笔记内容）: %s", exc)
            return False

    # ---------- 查询 ----------

    def records(self) -> List[ImageAssetRecord]:
        return list(self._assets)

    def find_by_id(self, asset_id: str) -> Optional[ImageAssetRecord]:
        return next((r for r in self._assets if r.id == asset_id), None)

    def find_by_name(self, name: str) -> List[ImageAssetRecord]:
        """按文件名取候选。

        同名多候选是常态（Copy 会产生多条物理 entry）：内容身份由调用方
        **实际重新计算** sha256 后比对——相同即属「多个物理副本、同一内容」，
        不构成内容歧义，可从任一有效副本恢复。
        """
        return [r for r in self._assets if r.name == name]

    def find_by_hash(self, sha256: str) -> List[ImageAssetRecord]:
        return [r for r in self._assets if r.sha256 == sha256]

    def find_by_location(self, absolute_path: str) -> List[ImageAssetRecord]:
        """按「最后已知位置」取候选。

        迁移回写用：位置是**唯一键**（应用自己知道文件从 A 搬到 B），
        不需要靠 hash 猜是哪一条记录。
        """
        target = _location_key(absolute_path)
        return [
            r for r in self._assets if _location_key(r.last_known_abs) == target
        ]

    # ---------- 变更 ----------

    def add(self, record: ImageAssetRecord) -> None:
        self._assets.append(record)

    def update_location(
        self, asset_id: str, absolute_path: str, name: Optional[str] = None
    ) -> bool:
        """迁移后更新某条记录的最后已知位置；`id / added_at / origin` 不变。

        记录是 frozen dataclass：重建一条同身份记录替换原记录。
        未命中返回 False（调用方跳过，不新建记录）。
        """
        for index, record in enumerate(self._assets):
            if record.id != asset_id:
                continue
            self._assets[index] = ImageAssetRecord(
                id=record.id,
                name=name or record.name,
                last_known_abs=absolute_path,
                sha256=record.sha256,
                size=record.size,
                added_at=record.added_at,
                origin=record.origin,
            )
            return True
        return False

    def add_copy(self, record: ImageAssetRecord, absolute_path: str) -> ImageAssetRecord:
        """为同一内容的**新物理副本**补一条记录（Copy 语义：源记录保持有效）。"""
        duplicate = ImageAssetRecord(
            id=uuid.uuid4().hex,
            name=os.path.basename(absolute_path),
            last_known_abs=absolute_path,
            sha256=record.sha256,
            size=record.size,
            added_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            origin=record.origin,
        )
        self._assets.append(duplicate)
        return duplicate

    def remove(self, asset_id: str) -> None:
        self._assets = [r for r in self._assets if r.id != asset_id]

    @staticmethod
    def build_record(
        name: str, absolute_path: str, data: bytes, origin: str
    ) -> ImageAssetRecord:
        """由落盘结果构造记录（sha256 / size 取自实际写入的字节）。"""
        return ImageAssetRecord(
            id=uuid.uuid4().hex,
            name=name,
            last_known_abs=absolute_path,
            sha256=hashlib.sha256(data).hexdigest(),
            size=len(data),
            added_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            origin=origin,
        )
