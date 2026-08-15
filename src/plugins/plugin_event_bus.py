# -*- coding: utf-8 -*-
"""
插件事件总线（Wave 5 Batch 4）

插件事件订阅的宿主侧实现：白名单 + 无状态节流 + 订阅数上限 + 卸载自动解绑。

设计 §6：
- 白名单 7 个事件；cursor.changed / content.changed 为高频事件，
  合并到 100ms 窗口后派发（仅保留最新 payload）。
- 单插件单事件订阅数上限（默认 5）。
- 回调异常 → 仅 log，不自动禁插件（D7/D8）。
- 不做「异常频发 → 节流降级」（D11）——防护只保留时间维度节流与数量上限。
"""

from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import QObject, QTimer

from ..utils.logger import get_logger
from .capability_registry import PluginCapabilityError


# 事件白名单（第一版，§6.1）
EVENT_WHITELIST: frozenset[str] = frozenset({
    "document.opened",
    "document.saved",
    "document.closed",
    "cursor.changed",    # 高频
    "content.changed",   # 高频
    "theme.changed",
    "file_tree.changed",
})

# 高频事件 → 100ms 窗口合并节流（§6.2）
HIGH_FREQUENCY_EVENTS: frozenset[str] = frozenset({"cursor.changed", "content.changed"})
THROTTLE_WINDOW_MS = 100

# 单插件单事件订阅数上限（§6.2）
MAX_SUBSCRIPTIONS_PER_EVENT = 5


class PluginEventBus(QObject):
    """插件事件总线：订阅登记 + 白名单/上限校验 + 高频节流 + 异常隔离"""

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._logger = get_logger(__name__)
        # event_name -> plugin_id -> [handler, ...]
        self._subs: Dict[str, Dict[str, List[Callable[[Any], Any]]]] = {}
        # 高频事件节流：event_name -> 最新 pending payload
        self._throttle_pending: Dict[str, Any] = {}
        self._throttle_timer: Optional[QTimer] = None

    # === 订阅管理 ===

    def subscribe(self, plugin_id: str, event_name: str, handler: Callable[[Any], Any]) -> None:
        """登记插件订阅；白名单校验 + 订阅数上限校验。

        Raises:
            PluginCapabilityError: 事件不在白名单 / 订阅数超上限
        """
        if event_name not in EVENT_WHITELIST:
            raise PluginCapabilityError(
                f"事件不在白名单: {event_name}（可用: {', '.join(sorted(EVENT_WHITELIST))}）"
            )
        handlers = self._subs.setdefault(event_name, {}).setdefault(plugin_id, [])
        if handler in handlers:
            return  # 同一处理器重复订阅 → 幂等，不计入上限
        if len(handlers) >= MAX_SUBSCRIPTIONS_PER_EVENT:
            raise PluginCapabilityError(
                f"插件 {plugin_id} 对事件 {event_name} 的订阅数已达上限 "
                f"({MAX_SUBSCRIPTIONS_PER_EVENT})"
            )
        handlers.append(handler)

    def unsubscribe_all(self, plugin_id: str) -> None:
        """卸载自动解绑：清除该插件全部订阅"""
        for handlers_map in self._subs.values():
            handlers_map.pop(plugin_id, None)

    # === 事件派发 ===

    def emit(self, event_name: str, payload: Any = None) -> None:
        """宿主触发事件；高频事件经 100ms 窗口合并后派发。

        白名单外事件仅记 debug 日志并跳过；无订阅者时直接返回。
        """
        if event_name not in EVENT_WHITELIST:
            self._logger.debug("忽略白名单外事件: %s", event_name)
            return
        if not self._subs.get(event_name):
            return
        if event_name in HIGH_FREQUENCY_EVENTS:
            self._throttle_pending[event_name] = payload
            self._ensure_timer()
            timer = self._throttle_timer
            assert timer is not None
            timer.start(THROTTLE_WINDOW_MS)
            return
        self._dispatch(event_name, payload)

    def has_subscribers(self, event_name: str) -> bool:
        return bool(self._subs.get(event_name))

    # === 内部 ===

    def _ensure_timer(self) -> None:
        if self._throttle_timer is None:
            self._throttle_timer = QTimer(self)
            self._throttle_timer.setSingleShot(True)
            self._throttle_timer.timeout.connect(self._flush_throttled)

    def _flush_throttled(self) -> None:
        for event_name, payload in self._throttle_pending.items():
            self._dispatch(event_name, payload)
        self._throttle_pending.clear()

    def _dispatch(self, event_name: str, payload: Any) -> None:
        handlers_map = self._subs.get(event_name)
        if not handlers_map:
            return
        for plugin_id, handlers in list(handlers_map.items()):
            for handler in list(handlers):
                try:
                    handler(payload)
                except Exception:
                    self._logger.exception(
                        "插件事件回调异常: plugin=%s event=%s", plugin_id, event_name
                    )
