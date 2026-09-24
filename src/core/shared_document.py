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
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, Set

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
    filepath: Optional[str]
    encoding: str
    # 行尾也是本次写盘内容的一部分（_save_file 按它做 normalize_eol），
    # 故必须入快照：否则「切 CRLF → 保存」后无法判定行尾是否已落盘（1.8）。
    eol: str


@dataclass
class EolChange:
    """一次行尾切换的可撤销记录（1.8）。

    行尾是**文档外**元数据（QTextDocument 恒存 \\n，行尾只在保存时施加），
    其变更不产生 Qt 撤销步，故在 Document 上单独记账。

    base_steps = 切换发生时 QTextDocument 的撤销步数，用于判定该变更是否仍是
    「最近一步」——文本编辑越过它时，应由文本撤销先处理，从而让编辑与行尾
    按发生顺序交错撤销。

    不含脏位：行尾脏是派生量（当前 eol ≠ 已落盘行尾），撤销/重做后重算即可。
    """

    old_eol: str
    new_eol: str
    base_steps: int


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
    bookmarksChanged = pyqtSignal()      # Document 级书签集合变化（规格 2.12）

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

        # 折叠（3.5.8 批次 5 收敛）：同 Document 一个 FoldingManager（规格 2.10）。
        # core 层不依赖 editor，由 editor 层首次 attach 时创建并写入（同 _highlighter 模式）。
        self._folding: Optional[object] = None

        # lazy 高亮 Document 级协调器（Wave 4 E2）：分屏多 View 共享同一 Document 时，
        # 各 View 可视区 union 增量高亮。core 层不依赖 editor，由 editor 层首次
        # attach 时惰性创建并写入（同 _folding 模式），无大文件时不创建。
        self._lazy_coordinator: Optional[object] = None

        # 书签（3.5.8 批次 5 收敛）：Document 级（规格 2.12）——两个 View 看同一份。
        self._bookmarks: Set[int] = set()

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

        # 行尾（EOL）变更的记账（1.8）：行尾是文档外元数据，变更不产生 Qt 撤销步，
        # 故可撤销性单独记账。行尾脏是**派生量**——当前 eol ≠ 已落盘行尾
        # （_saved_eol），因此来回切换不会累积脏，切回原行尾即自动回干净。
        self._saved_eol: str = eol
        self._eol_undo: list[EolChange] = []
        self._eol_redo: list[EolChange] = []

        # 保存统计（D3a：迁移至 Document 级——内容共享，字数增量 / 新字数
        # 按 Document 粒度统计，避免跨 View 漏计/重计）。
        # 初始值 = 创建时内容长度（对应构造时的 last_saved_chars）。
        self.last_saved_chars: int = len(content)
        self.last_text_length: int = len(content)

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

    @property
    def bookmarks(self) -> "set[int]":
        """Document 级书签（规格 2.12）：两个 View 看同一份书签。"""
        return self._bookmarks

    def set_content(self, content: str) -> None:
        """程序化设置内容（打开文件 / 外部 reload），复位修改状态。

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
        # 内容重载后行尾即「刚读进来的那份」：以当前 eol 重建已落盘基线，
        # 旧的行尾变更历史一并作废
        self._saved_eol = self.eol
        self.clear_eol_history()
        self.last_saved_chars = len(content)
        self.last_text_length = len(content)
        self._invalidate_word_count()
        self.contentChanged.emit()
        self.dirtyChanged.emit(False)  # reload 后订阅方需收到"变干净"通知

    # ═══════════════ 信号槽（QTextDocument → SharedDocument） ═══════════════

    def _on_contents_changed(self) -> None:
        self._invalidate_word_count()
        self.contentChanged.emit()

    def _on_modification_changed(self, modified: bool) -> None:
        self._refresh_dirty()

    # ═══════════════ 行尾变更的记账与撤销（1.8） ═══════════════

    def _refresh_dirty(self) -> None:
        """dirty = Qt 文本脏 或 行尾偏离已落盘值。

        Qt 的 isModified 由撤销栈干净点推导，覆盖不到文档外元数据（行尾），
        故行尾维度单独比较：当前 eol ≠ 已落盘行尾即意味着「还有变更未落盘」。
        做成派生量而非粘滞标志位，来回切换才不会累积脏（切回原行尾即回干净）。
        """
        dirty = self.qdocument.isModified() or self.eol != self._saved_eol
        if self._dirty != dirty:
            self._dirty = dirty
            self.dirtyChanged.emit(dirty)

    def has_pending_eol_undo(self) -> bool:
        """最近一次行尾切换是否仍可撤销（其间没有新的文本编辑越过它）。"""
        if not self._eol_undo:
            return False
        return self.qdocument.availableUndoSteps() == self._eol_undo[-1].base_steps

    def record_eol_change(self, new_eol: str) -> bool:
        """切换行尾并登记为可撤销的一步。

        行尾未变化时返回 False（不入栈、不置脏、不产生任何撤销步）。
        """
        if new_eol == self.eol:
            return False
        self._eol_undo.append(
            EolChange(
                old_eol=self.eol,
                new_eol=new_eol,
                base_steps=self.qdocument.availableUndoSteps(),
            )
        )
        # 新的变更作废重做历史（与线性撤销语义一致）
        self._eol_redo.clear()
        self.eol = new_eol
        self._refresh_dirty()
        return True

    def undo_eol_if_pending(self) -> bool:
        """回退最近一步行尾变更；无可回退或它不是「最近一步」时返回 False。"""
        if not self.has_pending_eol_undo():
            return False
        entry = self._eol_undo.pop()
        self.eol = entry.old_eol
        self._eol_redo.append(entry)
        self._refresh_dirty()
        return True

    def redo_eol_if_pending(self) -> bool:
        """重做行尾变更。

        redo 与 undo 用同一判据（撤销步数 == 该变更所在位置）：只有当文本的
        撤销/重做都回到该位置时才回放行尾，编辑与行尾才能按发生顺序交错回放。
        """
        if not self._eol_redo:
            return False
        entry = self._eol_redo[-1]
        if self.qdocument.availableUndoSteps() != entry.base_steps:
            return False
        self._eol_redo.pop()
        self.eol = entry.new_eol
        self._eol_undo.append(entry)
        self._refresh_dirty()
        return True

    def clear_eol_history(self) -> None:
        """清空行尾变更历史（内容重载 / 行尾已落盘后调用）。"""
        self._eol_undo.clear()
        self._eol_redo.clear()

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
            filepath=self.filepath,
            encoding=self.encoding,
            eol=self.eol,
        )

    def on_save_succeeded(self, snapshot: SaveSnapshot) -> bool:
        """保存成功回调。返回 True 表示需要立即补保存（pending 且仍 dirty）。

        dirty 最终 authority = saved snapshot：
        current 内容与行尾均 == snapshot → clean；否则保持 dirty
        （保存成功 ≠ 当前 clean）。
        """
        # D3a：保存统计随成功保存更新（对应 mark_saved 语义）
        self.last_saved_chars = len(snapshot.content)
        self.last_text_length = len(snapshot.content)
        # 本次快照的行尾就是磁盘现在的行尾：刷新已落盘基线（行尾脏由
        # eol 与它的比较派生，见 _refresh_dirty）
        self._saved_eol = snapshot.eol
        retry = False
        if self.to_plain_text() == snapshot.content and self.eol == snapshot.eol:
            # 先复位 _dirty 再 setModified(False)：槽内 `_dirty != modified` 为 False，
            # 不会与下方手动 emit 重复触发 dirtyChanged(False)。
            self._dirty = False
            self.qdocument.setModified(False)
            # 已落盘的行尾不再可撤销（撤销已保存的变更需重写文件，超出撤销范畴，
            # 也与「保存是提交点」的既有语义一致）
            self.clear_eol_history()
            # 既有契约：保存成功后无条件发一次「已变干净」（订阅方据此复位保存状态）
            self.dirtyChanged.emit(False)
        else:
            if self.pending_save:
                retry = True
        self.pending_save = False
        self._set_save_status(SaveStatus.IDLE)
        # 幂等补充重算，覆盖不经过 Qt 信号的行尾维度变化 —— 例如「保存途中又切了
        # 行尾」，此时 else 分支必须发出 dirtyChanged(True)，否则标题不会带 *。
        self._refresh_dirty()
        return retry

    def on_save_failed(self) -> None:
        """保存失败：不自动补保存（清 pending），保持 dirty，由用户重新触发。"""
        self.pending_save = False
        self._dirty = True
        self.dirtyChanged.emit(True)
        self._set_save_status(SaveStatus.FAILED)

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
