# -*- coding: utf-8 -*-
"""
共享文档模型（3.5.8 核心 Document）

SharedDocument(QObject)：真正拥有 QTextDocument 的文档模型。
- Document = 内容与持久化状态（content/undo/dirty/save/path/encoding）
- Editor（View）只 attach/detach qdocument，不拥有它
- 保存竞态防护：dirty 与 save_status 两维度 + snapshot 判定 + 单槽合并保存
- 信号源：直接监听共享 QTextDocument，再统一转发给各 View / UI

ViewState：一个标签/视图的展示与交互状态（cursor/selection/scroll/preview…）。
SaveSnapshot：每次异步保存捕获的内容快照。

设计依据：3.5.8-共享文档多视图需求规格.md 2.3 / 2.4。
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QPlainTextDocumentLayout


class SaveStatus(Enum):
    IDLE = "idle"
    SAVING = "saving"
    FAILED = "failed"


@dataclass
class SaveSnapshot:
    """保存开始时捕获的快照（写盘的是这个版本的内容）"""

    content: str
    content_version: int
    filepath: Optional[str]
    encoding: str


@dataclass
class ViewState:
    """一个标签/视图的展示与交互状态（View 侧状态，Document 不持有 View widget）"""

    cursor_position: Optional[int] = None
    scroll_position: Optional[int] = None
    # preview 相关状态（widget / 显示隐藏 / scroll）由 View 层持有，批次 5 细化

    @classmethod
    def new(cls) -> "ViewState":
        return cls()


class SharedDocument(QObject):
    """共享文档模型：拥有 QTextDocument，管理保存状态与 Document-level 信号。

    生命周期：DocumentRegistry 首次打开创建；最后一个 View 关闭时 release。
    不持有 View widget（View 数量与关联由 Registry 的 doc_id → views 管理）。
    """

    contentChanged = pyqtSignal()
    dirtyChanged = pyqtSignal(bool)
    pathChanged = pyqtSignal(str)        # filepath（可为空字符串）
    nameChanged = pyqtSignal(str)        # display_name
    saveStateChanged = pyqtSignal(str)   # SaveStatus.value

    def __init__(
        self,
        document_id: str,
        *,
        display_name: str = "未命名",
        content: str = "",
        filepath: Optional[str] = None,
        encoding: str = "UTF-8",
        eol: str = "LF",
        is_markdown: bool = False,
        untitled_number: Optional[int] = None,
        word_count_fn: Optional[Callable[[str], int]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.document_id = document_id
        self.display_name = display_name
        self.filepath = filepath
        self.encoding = encoding
        self.eol = eol
        self.is_markdown = is_markdown
        # 未命名编号（仅 create_untitled 时分配）：Save As 后 display_name 会变，
        # 编号须独立存储才能在释放时可靠归还，不能从 display_name 反推。
        self.untitled_number: Optional[int] = untitled_number
        # 字数统计：Document 级惰性单一源（规格 2.6 附带收益——两个 View 共享同一
        # QTextDocument，一次输入只统计一次）。core 层不依赖 editor，计算函数注入。
        self._word_count_fn = word_count_fn
        self._word_count = 0
        self._word_count_dirty = True  # 构造后首次访问才重算

        # 语法高亮（3.5.8 R1 收敛）：同 Document 只建一次 highlighter，所有 View
        # 复用。core 层不依赖 editor，仅作为 View 层扩展槽（editor.set_file_type 写入）。
        self._highlighter: Optional[object] = None
        self._highlighter_file_type: str = "Text"

        # 内容本体：SharedDocument 为 parent（QObject ownership 契约）；
        # 必须显式设置 QPlainTextDocumentLayout，否则 QPlainTextEdit.setDocument 静默不绑定。
        # 注意：QTextDocument.setPlainText() 会把 isModified 置 True，须立即复位，
        # 否则 dirty 状态从创建起就错乱。
        self.qdocument = QTextDocument(self)
        self.qdocument.setDocumentLayout(QPlainTextDocumentLayout(self.qdocument))
        self.qdocument.setPlainText(content)
        self.qdocument.setModified(False)

        # 保存状态（两维度：dirty + save_status）
        self._dirty: bool = False
        self._save_status: SaveStatus = SaveStatus.IDLE
        self.pending_save: bool = False
        self.last_saved_snapshot: Optional[SaveSnapshot] = None
        self.content_version: int = 0

        # 信号源：只监听共享 QTextDocument 一次（不监听各 View）
        self.qdocument.contentsChanged.connect(self._on_contents_changed)
        self.qdocument.modificationChanged.connect(self._on_modification_changed)

    # ═══════════════ 内容访问 ═══════════════

    def to_plain_text(self) -> str:
        return self.qdocument.toPlainText()

    def set_word_count_fn(self, fn: Callable[[str], int]) -> None:
        """注册字数统计函数（editor 层 attach 时注入，避免 core 依赖 editor）。"""
        self._word_count_fn = fn
        self._word_count_dirty = True

    @property
    def word_count(self) -> int:
        """Document 级惰性字数统计：内容变化后首次访问才重算，两个 View 共享缓存。"""
        if self._word_count_dirty and self._word_count_fn is not None:
            self._word_count = self._word_count_fn(self.qdocument.toPlainText())
            self._word_count_dirty = False
        return self._word_count

    def _invalidate_word_count(self) -> None:
        self._word_count_dirty = True

    def set_content(self, content: str) -> None:
        """程序化设置内容（打开文件 / 外部 reload），复位修改状态与版本。

        blockSignals 防止 setPlainText（置 modified=True）与复位产生
        中间 dirtyChanged(True) 闪烁信号（reload 时 View 会短暂误标脏）。
        """
        self.qdocument.blockSignals(True)
        try:
            self.qdocument.setPlainText(content)
            self.qdocument.setModified(False)
        finally:
            self.qdocument.blockSignals(False)
        self._dirty = False
        self.content_version = 0
        self._invalidate_word_count()
        self.contentChanged.emit()
        self.dirtyChanged.emit(False)  # reload 后订阅方需收到"变干净"通知

    # ═══════════════ 信号槽（QTextDocument → SharedDocument） ═══════════════

    def _on_contents_changed(self) -> None:
        self.content_version += 1
        self._invalidate_word_count()
        self.contentChanged.emit()

    def _on_modification_changed(self, modified: bool) -> None:
        if self._dirty != modified:
            self._dirty = modified
            self.dirtyChanged.emit(modified)

    # ═══════════════ 保存状态 ═══════════════

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def save_status(self) -> SaveStatus:
        return self._save_status

    def _set_save_status(self, status: SaveStatus) -> None:
        if self._save_status != status:
            self._save_status = status
            self.saveStateChanged.emit(status.value)

    def request_save(self) -> Optional[SaveSnapshot]:
        """请求保存（单槽合并）。

        IDLE / FAILED → 进入 SAVING，返回本次快照（调用方写盘）；
        SAVING       → 仅置 pending_save=True，返回 None（不并发写盘）。
        """
        if self._save_status == SaveStatus.SAVING:
            self.pending_save = True
            return None
        self._set_save_status(SaveStatus.SAVING)
        return SaveSnapshot(
            content=self.to_plain_text(),
            content_version=self.content_version,
            filepath=self.filepath,
            encoding=self.encoding,
        )

    def on_save_succeeded(self, snapshot: SaveSnapshot) -> bool:
        """保存成功回调。返回 True 表示需要立即补保存（pending 且仍 dirty）。

        dirty 最终 authority = saved snapshot：
        current == snapshot → clean；否则保持 dirty（保存成功 ≠ 当前 clean）。
        """
        self.last_saved_snapshot = snapshot
        retry = False
        if self.to_plain_text() == snapshot.content:
            # 先复位 _dirty 再 setModified(False)：槽内 `_dirty != modified` 为 False，
            # 不会与下方手动 emit 重复触发 dirtyChanged(False)。
            self._dirty = False
            self.qdocument.setModified(False)
            self.dirtyChanged.emit(False)
        else:
            self._dirty = True
            if self.pending_save:
                retry = True
        self.pending_save = False
        self._set_save_status(SaveStatus.IDLE)
        return retry

    def on_save_failed(self) -> None:
        """保存失败：不自动补保存（清 pending），保持 dirty，由用户重新触发。"""
        self.pending_save = False
        self._dirty = True
        self.dirtyChanged.emit(True)
        self._set_save_status(SaveStatus.FAILED)

    def reset_save_state(self) -> None:
        """强制回到 IDLE 且 clean（未命名空标签直接关闭等场景）。"""
        self.pending_save = False
        self._dirty = False
        self.qdocument.setModified(False)
        self.last_saved_snapshot = None
        self._set_save_status(SaveStatus.IDLE)
        self.dirtyChanged.emit(False)

    # ═══════════════ 路径 / 名称 ═══════════════

    def bind_path(self, filepath: str, *, encoding: Optional[str] = None,
                  is_markdown: Optional[bool] = None) -> None:
        """Save As（未命名首次保存）成功后 re-key：document_id 不变，path 更新。"""
        self.filepath = filepath
        if encoding is not None:
            self.encoding = encoding
        if is_markdown is not None:
            self.is_markdown = is_markdown
        self.display_name = os.path.basename(filepath)
        self.pathChanged.emit(filepath)
        self.nameChanged.emit(self.display_name)
