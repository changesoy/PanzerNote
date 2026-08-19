# -*- coding: utf-8 -*-
"""
DocumentRegistry：全局文档注册表（3.5.8 核心 Document）

跨面板共享的 Document 生命周期与查找入口：
- documents_by_id：document_id → SharedDocument（生命周期管理）
- path_index：canonical(path) → document_id（打开文件时查找既有 Document）
- views：document_id → 该 Document 当前关联的所有 View
- pending_path_index：Save As 期间的路径预留（成功后 pending → path_index）

规则：
- path 用来查找 Document，但 path 不是 identity（document_id 永不变）。
- 路径 key 统一 canonical：绝对路径 + realpath + Windows normcase。
- Save As 目标已被另一个 Document 占用 → 拒绝（不允许两个不同 Document 指向同一路径）。
- 只有最后一个 View 关闭才 release Document。

设计依据：3.5.8-共享文档多视图需求规格.md 2.2 / 2.3。
"""

import os
import uuid
from typing import Any, Dict, List, Optional

from .shared_document import SharedDocument


class DocumentRegistry:
    """管理共享 Document 的注册、查找与生命周期。"""

    def __init__(self) -> None:
        self._documents: Dict[str, SharedDocument] = {}
        self._path_index: Dict[str, str] = {}
        self._pending_path_index: Dict[str, str] = {}
        self._views: Dict[str, List[Any]] = {}
        self._used_untitled_numbers: set[int] = set()

    # ═══════════════ 路径规范化 ═══════════════

    @staticmethod
    def canonical(path: str) -> str:
        """规范化路径 key：绝对路径 + realpath + Windows normcase。"""
        abs_path = os.path.abspath(path)
        try:
            real = os.path.realpath(abs_path)
        except OSError:
            real = abs_path
        if os.name == "nt":
            return os.path.normcase(real)
        return real

    # ═══════════════ 创建 ═══════════════

    @staticmethod
    def _new_document_id() -> str:
        return uuid.uuid4().hex

    def create_untitled(
        self,
        untitled_number: Optional[int] = None,
        display_name: Optional[str] = None,
    ) -> SharedDocument:
        """创建未命名 Document。

        untitled_number / display_name 由调用方（View 层编号池）指定时沿用；
        缺省时 Document 自分配编号（独立使用场景）。编号池以 View 层为准，
        Document 仅记录编号供 release 时归还（3.5.8 R4 未命名共享入口）。
        """
        num = untitled_number if untitled_number is not None else self._next_untitled_number()
        name = display_name or f"未命名-{num}"
        doc = SharedDocument(
            self._new_document_id(),
            display_name=name,
            filepath=None,
            untitled_number=num,
        )
        self._documents[doc.document_id] = doc
        self._views[doc.document_id] = []
        return doc

    def create_from_path(
        self,
        filepath: str,
        content: str = "",
        *,
        encoding: str = "UTF-8",
        eol: str = "LF",
        is_markdown: bool = False,
    ) -> SharedDocument:
        """创建具名 Document 并注册 path_index（打开文件首次加载）。

        仅在调用方已确认该路径未被任何 Document 占用（get_by_path 未命中）时调用；
        否则路径索引会被静默覆盖（两个 Document 指向同一路径的非法形态）。
        """
        key = self.canonical(filepath)
        if key in self._path_index or key in self._pending_path_index:
            raise ValueError(f"path already owned by a Document: {filepath}")
        doc = SharedDocument(
            self._new_document_id(),
            display_name=os.path.basename(filepath),
            content=content,
            filepath=filepath,
            encoding=encoding,
            eol=eol,
            is_markdown=is_markdown,
        )
        self._documents[doc.document_id] = doc
        self._path_index[key] = doc.document_id
        self._views[doc.document_id] = []
        return doc

    # ═══════════════ 未命名编号 ═══════════════

    def _next_untitled_number(self) -> int:
        num = 1
        while num in self._used_untitled_numbers:
            num += 1
        self._used_untitled_numbers.add(num)
        return num

    def release_untitled_number(self, document: SharedDocument) -> None:
        """释放未命名编号（标签关闭 / Save As 成功后）。

        直接使用 document.untitled_number 字段——display_name 在 Save As 后
        变为文件名，不能从它反推编号。
        """
        if document.untitled_number is not None:
            self._used_untitled_numbers.discard(document.untitled_number)

    # ═══════════════ 查找 ═══════════════

    def get_by_id(self, document_id: str) -> Optional[SharedDocument]:
        return self._documents.get(document_id)

    def get_by_path(self, filepath: str) -> Optional[SharedDocument]:
        doc_id = self._path_index.get(self.canonical(filepath))
        if doc_id is None:
            return None
        return self._documents.get(doc_id)

    def all_documents(self) -> List[SharedDocument]:
        return list(self._documents.values())

    # ═══════════════ 路径占用 / re-key ═══════════════

    def is_path_owned_by_other(self, document_id: str, filepath: str) -> bool:
        """目标路径是否被另一个 Document 占用（Save As 拒绝判定，含 pending 预留）。"""
        key = self.canonical(filepath)
        owner = self._path_index.get(key)
        if owner is not None and owner != document_id:
            return True
        pending = self._pending_path_index.get(key)
        return pending is not None and pending != document_id

    def reserve_path(self, document_id: str, filepath: str) -> bool:
        """Save As 期间路径预留（pending）。被其他 Document 占用则返回 False。"""
        if self.is_path_owned_by_other(document_id, filepath):
            return False
        self._pending_path_index[self.canonical(filepath)] = document_id
        return True

    def commit_path(self, document: SharedDocument, filepath: str) -> bool:
        """Save As 成功后 commit：pending → path_index，并更新 Document.path。"""
        if self.is_path_owned_by_other(document.document_id, filepath):
            return False
        key = self.canonical(filepath)
        old_key = self.canonical(document.filepath) if document.filepath else None
        if old_key and self._path_index.get(old_key) == document.document_id:
            del self._path_index[old_key]
        self._pending_path_index.pop(key, None)
        self._path_index[key] = document.document_id
        document.bind_path(filepath)
        return True

    def cancel_reservation(self, document_id: str, filepath: str) -> None:
        """保存失败时释放 pending 预留。"""
        key = self.canonical(filepath)
        if self._pending_path_index.get(key) == document_id:
            del self._pending_path_index[key]

    def move_path(self, document: SharedDocument, filepath: str) -> bool:
        """文件树移动文件后 re-key：path_index 换键 + Document 绑定新路径。

        与 commit_path（Save As 语义）不同：无 pending 预留流程，仅换路径键。
        目标路径被其它 Document 占用时拒绝（与 Save As 同规则，避免两个
        Document 指向同一路径的非法形态）。成功后 bind_path 广播 pathChanged /
        nameChanged，所有 View 的路径/标题随 Document 同步。
        """
        if self.is_path_owned_by_other(document.document_id, filepath):
            return False
        key = self.canonical(filepath)
        old_key = self.canonical(document.filepath) if document.filepath else None
        if old_key and self._path_index.get(old_key) == document.document_id:
            del self._path_index[old_key]
        self._path_index[key] = document.document_id
        document.bind_path(filepath)
        return True

    def unregister_path(self, document: SharedDocument) -> None:
        """移除 Document 当前路径的索引（关闭 / 换路径前）。"""
        if not document.filepath:
            return
        key = self.canonical(document.filepath)
        if self._path_index.get(key) == document.document_id:
            del self._path_index[key]
        if self._pending_path_index.get(key) == document.document_id:
            del self._pending_path_index[key]

    # ═══════════════ View 关联 ═══════════════

    def attach_view(self, document_id: str, view: Any) -> None:
        if document_id not in self._views:
            self._views[document_id] = []
        if view not in self._views[document_id]:
            self._views[document_id].append(view)

    def detach_view(self, document_id: str, view: Any) -> None:
        views = self._views.get(document_id)
        if views and view in views:
            views.remove(view)

    def view_count(self, document_id: str) -> int:
        return len(self._views.get(document_id, []))

    def has_views(self, document_id: str) -> bool:
        return len(self._views.get(document_id, [])) > 0

    # ═══════════════ 生命周期 ═══════════════

    def release(self, document_id: str) -> None:
        """最后一个 View 关闭：销毁 Document（移除所有索引与 View 关联）。"""
        doc = self._documents.pop(document_id, None)
        if doc is None:
            return
        self.unregister_path(doc)
        self.release_untitled_number(doc)
        self._views.pop(document_id, None)
        # 清理该文档遗留的 pending 预留
        for key in [k for k, v in self._pending_path_index.items() if v == document_id]:
            del self._pending_path_index[key]
        doc.qdocument.deleteLater()
        doc.deleteLater()
