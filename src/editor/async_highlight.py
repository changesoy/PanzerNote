# -*- coding: utf-8 -*-
"""
异步代码高亮渲染器
使用QThread实现后台渲染，避免阻塞主线程

核心设计：
1. 渲染工作在后台线程执行，不阻塞UI
2. 主线程与渲染线程间通信采用QueuedConnection信号机制
3. 渲染任务队列管理，支持任务优先级和取消
4. 渲染进度指示和超时处理
"""

import uuid
from typing import Optional, Dict, Callable
from collections import OrderedDict

from PyQt6.QtCore import QThread, pyqtSignal, QObject, QTimer, Qt

from ..utils.logger import get_logger
from ..utils.feature_flags import is_enabled


class HighlightWorker(QThread):
    """后台代码高亮渲染线程"""
    finished = pyqtSignal(str, str, str)
    error = pyqtSignal(str, str)

    def __init__(self, task_id: str, code: str, language: str,
                 theme_name: Optional[str] = None):
        super().__init__()
        self._task_id = task_id
        self._code = code
        self._language = language
        self._theme_name = theme_name
        self._cancelled = False

    def run(self):
        if self._cancelled:
            return

        try:
            from .highlight_themes import highlight_code_html
            result = highlight_code_html(self._code, self._language, self._theme_name)
            if not self._cancelled:
                self.finished.emit(self._task_id, result, self._language)
        except Exception as e:
            if not self._cancelled:
                self.error.emit(self._task_id, str(e))

    def cancel(self):
        self._cancelled = True


class AsyncHighlightRenderer(QObject):
    """异步代码高亮渲染管理器

    管理渲染任务队列，支持优先级和取消。
    当 feature flag "async_highlight" 关闭时，使用同步渲染。
    """

    result_ready = pyqtSignal(str, str, str)
    render_progress = pyqtSignal(str, float)

    MAX_CONCURRENT = 2
    TASK_TIMEOUT_MS = 10000

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._tasks: Dict[str, dict] = {}
        self._active_workers: Dict[str, HighlightWorker] = {}
        self._queue: list = []
        self._results_cache: OrderedDict[str, str] = OrderedDict()
        self._cache_max = 50

        self._timeout_timer = QTimer(self)
        self._timeout_timer.setInterval(1000)
        self._timeout_timer.timeout.connect(self._check_timeouts)
        self._timeout_timer.start()

    def render(self, code: str, language: str,
               theme_name: Optional[str] = None,
               priority: int = 0,
               callback: Optional[Callable] = None) -> Optional[str]:
        if not is_enabled("async_highlight"):
            return self.render_sync(code, language, theme_name)
        return self.render_async(code, language, theme_name, priority, callback)

    def render_sync(self, code: str, language: str,
                    theme_name: Optional[str] = None) -> str:
        from .highlight_themes import highlight_code_html
        return str(highlight_code_html(code, language, theme_name))

    def render_async(self, code: str, language: str,
                     theme_name: Optional[str] = None,
                     priority: int = 0,
                     callback: Optional[Callable] = None) -> Optional[str]:
        cache_key = f"{language}:{hash(code)}:{theme_name}"
        if cache_key in self._results_cache:
            cached = self._results_cache[cache_key]
            if callback:
                callback("", cached, language)
            return cached

        task_id = str(uuid.uuid4())[:8]
        self._tasks[task_id] = {
            "code": code,
            "language": language,
            "theme_name": theme_name,
            "priority": priority,
            "callback": callback,
            "cache_key": cache_key,
            "created_at": self._now_ms(),
        }

        self._queue.append(task_id)
        self._queue.sort(key=lambda tid: self._tasks[tid]["priority"])

        self._process_queue()
        return task_id

    def cancel(self, task_id: str):
        if task_id in self._active_workers:
            self._active_workers[task_id].cancel()
        self._tasks.pop(task_id, None)
        if task_id in self._queue:
            self._queue.remove(task_id)

    def cancel_all(self):
        for task_id in list(self._active_workers.keys()):
            self._active_workers[task_id].cancel()
        self._active_workers.clear()
        self._queue.clear()
        self._tasks.clear()

    def _process_queue(self):
        while self._queue and len(self._active_workers) < self.MAX_CONCURRENT:
            task_id = self._queue.pop(0)
            task = self._tasks.get(task_id)
            if not task:
                continue

            worker = HighlightWorker(
                task_id, task["code"], task["language"], task["theme_name"]
            )
            worker.finished.connect(  # type: ignore[call-arg]
                self._on_worker_finished, Qt.ConnectionType.QueuedConnection
            )
            worker.error.connect(  # type: ignore[call-arg]
                self._on_worker_error, Qt.ConnectionType.QueuedConnection
            )
            worker.finished.connect(worker.deleteLater)

            self._active_workers[task_id] = worker
            worker.start()

    def _on_worker_finished(self, task_id: str, html: str, language: str):
        task = self._tasks.pop(task_id, None)
        self._active_workers.pop(task_id, None)

        if task:
            cache_key = task.get("cache_key")
            if cache_key:
                self._results_cache[cache_key] = html
                if len(self._results_cache) > self._cache_max:
                    self._results_cache.popitem(last=False)

            if task.get("callback"):
                task["callback"](task_id, html, language)

        self.result_ready.emit(task_id, html, language)
        self._process_queue()

    def _on_worker_error(self, task_id: str, error_msg: str):
        self._tasks.pop(task_id, None)
        self._active_workers.pop(task_id, None)
        get_logger(__name__).warning("异步高亮渲染失败: %s", error_msg)
        self._process_queue()

    def _check_timeouts(self):
        now = self._now_ms()
        for task_id in list(self._active_workers.keys()):
            task = self._tasks.get(task_id)
            if task and now - task["created_at"] > self.TASK_TIMEOUT_MS:
                self.cancel(task_id)
                get_logger(__name__).warning("异步高亮渲染超时: %s", task_id)

    @staticmethod
    def _now_ms() -> int:
        import time
        return int(time.time() * 1000)
