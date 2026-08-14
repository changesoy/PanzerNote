# -*- coding: utf-8 -*-
"""
保存任务管理器
统一管理所有异步保存任务的生命周期，提供保存状态。

3.5.8 改造（规格 2.4）：
- dirty 与 saving 解耦为两个维度，不再共用互斥枚举（原 DIRTY → SAVING → CLEAN 单状态机
  在保存期间继续编辑时会丢 dirty，成功回调又无条件进 CLEAN——竞态根因）。
- SaveState 枚举保留为「派生状态」，供 UI / 调用方消费：
    status=saving            → SAVING   （优先级最高）
    status=failed            → SAVE_FAILED
    dirty                    → DIRTY
    否则                     → CLEAN
- 保存成功时按「当前内容 == 保存快照」判定 dirty（保存成功 ≠ 当前 Document clean）。
- 单槽合并：同一 tab 同时最多一个实际保存任务；保存中再次请求 → 仅置 pending，
  成功且仍 dirty 时通过 on_resave 回调通知调用方以最新内容补保存一次。
"""

from enum import Enum
from typing import Optional, Dict, Callable

from PyQt6.QtCore import QObject, pyqtSignal

from ..utils.logger import get_logger


class SaveState(Enum):
    CLEAN = "clean"
    DIRTY = "dirty"
    SAVING = "saving"
    SAVE_FAILED = "save_failed"


class SaveTaskManager(QObject):
    """管理所有异步保存任务

    职责：
    1. 持有所有活跃的 SaveTask 引用，防止被 GC 回收
    2. 两维度保存状态：_dirty + _status（IDLE/SAVING/FAILED）
    3. 保存成功后按 snapshot 判定 dirty，不无条件 CLEAN
    4. 单槽合并保存：保存中再次请求 → pending，成功后补保存一次
    5. 提供查询接口：是否有任务进行中、是否全部完成
    """

    save_state_changed = pyqtSignal(int, str)
    save_failed = pyqtSignal(int, str, object)
    all_tasks_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: Dict[int, object] = {}
        self._dirty: Dict[int, bool] = {}
        self._status: Dict[int, str] = {}          # "idle" / "saving" / "failed"
        self._pending_save: Dict[int, bool] = {}
        self._snapshots: Dict[int, str] = {}       # 保存时写盘的内容快照（已 EOL 规范化）
        self._providers: Dict[int, Callable[[], str]] = {}
        self._on_resave: Dict[int, Callable[[], None]] = {}
        self._last_states: Dict[int, SaveState] = {}
        # 3.5.8 多 View（R3）：document_key → 正在保存该 Document 的 owner tab_id。
        # 同一 Document 的多个 View（不同 tab_id）共享内容，保存任务按 Document
        # 合并——同 Document 同时最多一个实际写盘任务，禁止并发写同一文件。
        self._doc_owner: Dict[str, int] = {}

    # ═══════════════ 生命周期 ═══════════════

    def register_tab(self, tab_id: int) -> None:
        self._dirty[tab_id] = False
        self._status[tab_id] = "idle"

    def unregister_tab(self, tab_id: int) -> None:
        # 若该 tab 是某个 Document 的保存 owner，注销时释放 doc 级保存锁
        for key, owner in list(self._doc_owner.items()):
            if owner == tab_id:
                del self._doc_owner[key]
        self._tasks.pop(tab_id, None)
        self._dirty.pop(tab_id, None)
        self._status.pop(tab_id, None)
        self._pending_save.pop(tab_id, None)
        self._snapshots.pop(tab_id, None)
        self._providers.pop(tab_id, None)
        self._on_resave.pop(tab_id, None)
        self._last_states.pop(tab_id, None)

    # ═══════════════ 派生状态 ═══════════════

    def get_state(self, tab_id: int) -> SaveState:
        status = self._status.get(tab_id, "idle")
        if status == "saving":
            return SaveState.SAVING
        if status == "failed":
            return SaveState.SAVE_FAILED
        if self._dirty.get(tab_id, False):
            return SaveState.DIRTY
        return SaveState.CLEAN

    def _set_state(self, tab_id: int, state: SaveState) -> None:
        """直接设置派生状态（保留给旧调用/测试使用）。"""
        if state == SaveState.CLEAN:
            self._dirty[tab_id] = False
            self._status[tab_id] = "idle"
        elif state == SaveState.DIRTY:
            self._dirty[tab_id] = True
        elif state == SaveState.SAVING:
            self._status[tab_id] = "saving"
        elif state == SaveState.SAVE_FAILED:
            self._status[tab_id] = "failed"
            self._dirty[tab_id] = True
        self._emit_if_changed(tab_id)

    def _emit_if_changed(self, tab_id: int) -> None:
        state = self.get_state(tab_id)
        if self._last_states.get(tab_id) != state:
            self._last_states[tab_id] = state
            self.save_state_changed.emit(tab_id, state.value)

    def mark_dirty(self, tab_id: int) -> None:
        """标记 dirty。不再被 SAVING 状态忽略（3.5.8：dirty 与 saving 解耦）。"""
        self._dirty[tab_id] = True
        self._emit_if_changed(tab_id)

    # ═══════════════ 保存任务 ═══════════════

    def submit_task(self, tab_id: int, task, snapshot: Optional[str] = None,
                    provider: Optional[Callable[[], str]] = None,
                    on_resave: Optional[Callable[[], None]] = None,
                    document_key: Optional[str] = None) -> bool:
        """提交保存任务。

        snapshot：本次写盘的内容快照；provider：返回当前内容（成功时判定 dirty 用）。
        on_resave：保存成功但内容已变且保存期间有 pending 请求时，通知调用方补保存。
        document_key：所属 Document 标识（3.5.8 多 View）。同一 Document 的多个 View
        共享内容，传此参数后保存任务按 Document 合并——该 Document 已由其他 View
        发起保存时不再并发提交，仅置 pending（单槽合并），返回 False。
        传 snapshot/provider 后成功判定走「当前 == 快照」，否则保持旧行为（直接 CLEAN）。
        已在 SAVING 中 → 不并发提交，仅置 pending（单槽合并），返回 False。
        """
        if document_key is not None:
            owner = self._doc_owner.get(document_key)
            if owner is not None and self._status.get(owner) == "saving":
                # 同一 Document 已有 View 在保存 → 合并到该 owner，不并发写同一文件
                self._pending_save[owner] = True
                return False
        if self._status.get(tab_id) == "saving":
            self._pending_save[tab_id] = True
            return False

        self._tasks[tab_id] = task
        self._status[tab_id] = "saving"
        if document_key is not None:
            self._doc_owner[document_key] = tab_id
        if snapshot is not None:
            self._snapshots[tab_id] = snapshot
        if provider is not None:
            self._providers[tab_id] = provider
        if on_resave is not None:
            self._on_resave[tab_id] = on_resave
        task.signals.finished.connect(
            lambda success, fp, exc, tid=tab_id: self._on_task_finished(tid, success, fp, exc)
        )
        self._emit_if_changed(tab_id)
        return True

    def request_resave(self, tab_id: int, document_key: Optional[str] = None) -> bool:
        """保存中再次收到显式保存请求 → 仅置 pending（单槽合并），返回 True。

        document_key：同一 Document 已由其他 View 在保存时，请求合并到该 owner。
        """
        if document_key is not None:
            owner = self._doc_owner.get(document_key)
            if owner is not None and self._status.get(owner) == "saving":
                self._pending_save[owner] = True
                return True
        if self._status.get(tab_id) == "saving":
            self._pending_save[tab_id] = True
            return True
        return False

    def has_pending_tasks(self) -> bool:
        return len(self._tasks) > 0

    def is_saving(self, tab_id: int) -> bool:
        return self._status.get(tab_id) == "saving"

    def any_saving(self) -> bool:
        return any(s == "saving" for s in self._status.values())

    def has_unsaved_work(self) -> bool:
        return any(
            self._dirty.get(tid, False) or s == "failed"
            for tid, s in self._status.items()
        )

    def get_dirty_tab_ids(self) -> list:
        return [tid for tid in self._status
                if self._dirty.get(tid, False) or self._status[tid] == "failed"]

    def get_saving_tab_ids(self) -> list:
        return [tid for tid, s in self._status.items() if s == "saving"]

    def get_failed_tab_ids(self) -> list:
        return [tid for tid, s in self._status.items() if s == "failed"]

    # ═══════════════ 任务完成 ═══════════════

    def _on_task_finished(self, tab_id: int, success: bool, filepath: str,
                          exc: Optional[Exception]) -> None:
        # 守卫：tab 已注销（unregister 后任务才完成）→ 忽略迟到回调，避免幽灵状态重建
        if tab_id not in self._status:
            return
        # 该 tab 是某 Document 的保存 owner → 任务结束释放 doc 级保存锁
        for key, owner in list(self._doc_owner.items()):
            if owner == tab_id:
                del self._doc_owner[key]
        self._tasks.pop(tab_id, None)
        snapshot = self._snapshots.pop(tab_id, None)
        provider = self._providers.pop(tab_id, None)
        on_resave = self._on_resave.pop(tab_id, None)

        if success:
            self._status[tab_id] = "idle"
            if snapshot is not None and provider is not None:
                try:
                    current = provider()
                except Exception:
                    # widget 已不可用（销毁/异常）：按内容未变化处理，
                    # 避免异常从 Qt 信号回调冒出、也避免误触发 resave
                    current = snapshot
                if current == snapshot:
                    self._dirty[tab_id] = False
                    # pending 请求已被兑现（当前内容 == 已落盘内容），清掉避免泄漏
                    self._pending_save.pop(tab_id, None)
                else:
                    # 保存期间继续编辑：保存成功 ≠ 当前 clean
                    self._dirty[tab_id] = True
                    if self._pending_save.pop(tab_id, False) and on_resave is not None:
                        # 单槽合并：以最新内容补保存一次
                        self._emit_if_changed(tab_id)
                        on_resave()
                        if not self._tasks:
                            self.all_tasks_finished.emit()
                        return
            else:
                # 未提供快照（旧路径）：保持旧行为
                self._dirty[tab_id] = False
                self._pending_save.pop(tab_id, None)
        else:
            self._status[tab_id] = "failed"
            self._dirty[tab_id] = True
            self._pending_save.pop(tab_id, None)  # 失败不自动补保存
            get_logger(__name__).error("保存文件失败 [tab_id=%s]: %s", tab_id, exc)
            self.save_failed.emit(tab_id, filepath, exc)

        self._emit_if_changed(tab_id)
        if not self._tasks:
            self.all_tasks_finished.emit()
