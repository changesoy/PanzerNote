# -*- coding: utf-8 -*-
"""
保存任务管理器
统一管理所有异步保存任务的生命周期，提供保存状态机。

状态转换：
    DIRTY → SAVING → CLEAN         保存成功
    DIRTY → SAVING → SAVE_FAILED   保存失败
    SAVE_FAILED → SAVING → CLEAN   重试成功
    CLEAN → DIRTY                  内容修改
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
    2. 跟踪每个 tab 的保存状态
    3. 保存成功后才标记 CLEAN，失败后标记 SAVE_FAILED
    4. 提供查询接口：是否有任务进行中、是否全部完成
    """

    save_state_changed = pyqtSignal(int, str)
    save_failed = pyqtSignal(int, str, object)
    all_tasks_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: Dict[int, object] = {}
        self._states: Dict[int, SaveState] = {}

    def register_tab(self, tab_id: int) -> None:
        self._states[tab_id] = SaveState.CLEAN

    def unregister_tab(self, tab_id: int) -> None:
        self._tasks.pop(tab_id, None)
        self._states.pop(tab_id, None)

    def get_state(self, tab_id: int) -> SaveState:
        return self._states.get(tab_id, SaveState.CLEAN)

    def mark_dirty(self, tab_id: int) -> None:
        if self.get_state(tab_id) != SaveState.SAVING:
            self._set_state(tab_id, SaveState.DIRTY)

    def submit_task(self, tab_id: int, task) -> None:
        self._tasks[tab_id] = task
        self._set_state(tab_id, SaveState.SAVING)
        task.signals.finished.connect(
            lambda success, fp, exc, tid=tab_id: self._on_task_finished(tid, success, fp, exc)
        )

    def has_pending_tasks(self) -> bool:
        return len(self._tasks) > 0

    def is_saving(self, tab_id: int) -> bool:
        return self.get_state(tab_id) == SaveState.SAVING

    def any_saving(self) -> bool:
        return any(s == SaveState.SAVING for s in self._states.values())

    def get_dirty_tab_ids(self) -> list:
        return [tid for tid, s in self._states.items() if s in (SaveState.DIRTY, SaveState.SAVE_FAILED)]

    def get_saving_tab_ids(self) -> list:
        return [tid for tid, s in self._states.items() if s == SaveState.SAVING]

    def get_failed_tab_ids(self) -> list:
        return [tid for tid, s in self._states.items() if s == SaveState.SAVE_FAILED]

    def _on_task_finished(self, tab_id: int, success: bool, filepath: str, exc: Optional[Exception]) -> None:
        self._tasks.pop(tab_id, None)

        if success:
            self._set_state(tab_id, SaveState.CLEAN)
        else:
            self._set_state(tab_id, SaveState.SAVE_FAILED)
            get_logger(__name__).error("保存文件失败 [tab_id=%s]: %s", tab_id, exc)
            self.save_failed.emit(tab_id, filepath, exc)

        if not self._tasks:
            self.all_tasks_finished.emit()

    def _set_state(self, tab_id: int, state: SaveState) -> None:
        old = self._states.get(tab_id)
        self._states[tab_id] = state
        if old != state:
            self.save_state_changed.emit(tab_id, state.value)
