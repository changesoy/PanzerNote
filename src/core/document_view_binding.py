# -*- coding: utf-8 -*-
"""
View ↔ Document 信号接线（3.5.8 规格 2.6）

轻量绑定组件：View 用它订阅 Document-level 信号，生命周期与 View 一致。
- attach()：建立全部登记连接；detach()：断开全部连接
- attach / detach 幂等：同一 View 不能 attach 两次（重复 attach 直接忽略），
  detach 后可再次 attach
- View 销毁时主动 detach()；QObject 自动断连只作第二层保险，不作主要生命周期策略
- 禁止 `signal.connect(lambda: self.xxx(view))` 后无人保存连接关系的写法
  （闭包会让 View/Document 引用链难以清理）——本组件持有 (signal, slot) 对，
  调用方只需传普通可调用对象

设计依据：3.5.8-共享文档多视图需求规格.md 2.6。
"""

from typing import Callable, List, Optional, Tuple

from PyQt6.QtCore import QObject

from .shared_document import SharedDocument


class DocumentViewBinding(QObject):
    """Document 信号 → View 槽 的幂等接线器。"""

    def __init__(self, document: SharedDocument, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._document = document
        self._connections: List[Tuple] = []
        self._attached: bool = False

    def bind(self, signal_name: str, slot: Callable) -> "DocumentViewBinding":
        """登记一条连接（不立即建立）；attach 时才 connect。

        slot 必须是与信号兼容的普通可调用对象（禁止无人持有引用的裸 lambda）。
        """
        signal = getattr(self._document, signal_name)
        if self._attached:
            signal.connect(slot)
        self._connections.append((signal, slot))
        return self

    def attach(self) -> None:
        """建立全部登记连接。幂等：已 attach 时重复调用直接忽略。"""
        if self._attached:
            return
        for signal, slot in self._connections:
            signal.connect(slot)
        self._attached = True

    def detach(self) -> None:
        """断开全部连接。幂等：未 attach 时重复调用直接忽略。"""
        if not self._attached:
            return
        for signal, slot in self._connections:
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                # 槽已在别处断开（View 销毁等）：第二层保险，忽略
                pass
        self._attached = False
