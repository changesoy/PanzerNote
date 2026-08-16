# -*- coding: utf-8 -*-
"""RendererHost 薄契约与 HostRegistry（Wave 8 B7 Switching）。

主设计 4.3「RendererHost 薄契约」：替换是否安全由真正拥有 interaction 状态的
Host 报告，ThemeManager 不自己去全局猜。B7 交付契约 + registry；
产品侧注册 0 个宿主（B8 按真实 renderer 需要补齐），仅测试 fixture 注册。

状态所有权铁律（主设计 3.2）：checked/selection/text/focus/drag 语义状态归 Host；
renderer 只持 disposable visual state。commit_replacement 前后 host object identity、
business signals、业务状态不变。
"""
from __future__ import annotations

import weakref
from abc import ABCMeta, abstractmethod
from enum import Enum

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.sip import wrappertype

from .types import RecipeKey


class _RendererHostMeta(wrappertype, ABCMeta):
    """QObject（sip wrappertype）与 abc.ABCMeta 的组合元类。

    PyQt6 QObject 的元类是 ``PyQt6.sip.wrappertype``，与 ``abc.ABCMeta``
    不构成继承关系，直接 ``class X(QObject, ABC)`` 会触发 metaclass conflict；
    因此以组合元类承载抽象方法检查（设计文档 6.1 的抽象协议语义落地）。
    """


class ReplacementSafety(Enum):
    """当前替换是否安全（判定权在 Host，只有两态，见 3.1）。

    宿主无法给出确定答案时按 TRANSIENT_INTERACTION 处理（保守侧）。
    """

    SAFE = "safe"
    TRANSIENT_INTERACTION = "transient-interaction"


class RendererHost(QObject, metaclass=_RendererHostMeta):
    """稳定组件宿主薄契约：renderer 可替换，业务状态与活动交互归 Host。

    宿主通常是 QWidget（但不强制）；继承 QObject 以声明 interaction_finished 信号。
    """

    #: 具体类提供；pending 唤醒用。交互结束（拖拽返回 / 模态关闭 / IME 提交）必须发射。
    interaction_finished = pyqtSignal()

    @abstractmethod
    def renderer_host_key(self) -> RecipeKey:
        """本宿主绑定的组件槽位（与 recipe key 同命名空间）。"""

    @abstractmethod
    def current_renderer_id(self) -> str:
        """当前生效 renderer id（executor 校验与测试断言用）。"""

    # ── 两阶段替换（"先建新 renderer 再 swap"，D20/4.4）──

    @abstractmethod
    def prepare_replacement(self, new_renderer_id: str, params: object) -> None:
        """预创建新 renderer（不生效）。失败抛异常，不留半成品。"""

    @abstractmethod
    def commit_replacement(self) -> None:
        """原子 swap 到已 prepare 的新 renderer；旧 renderer 入栈供回滚。"""

    @abstractmethod
    def abort_replacement(self) -> None:
        """放弃已 prepare 未 commit 的替换（清理预创建物）。"""

    @abstractmethod
    def rollback_replacement(self) -> bool:
        """恢复最近一次 commit 前的 renderer。无可恢复 → False。"""

    # ── Safe Switch ──

    @abstractmethod
    def replacement_safety_state(self) -> ReplacementSafety:
        """当前替换是否安全（判定权在 Host，见 3.1）。"""


class HostRegistry:
    """宿主注册表：按 recipe key 索引，容器内弱引用。

    宿主 widget 被 Qt 销毁后自动出局（不延长生命周期，见 T13）。
    """

    def __init__(self) -> None:
        self._hosts: dict[RecipeKey, list[weakref.ReferenceType]] = {}

    def register(self, host: RendererHost) -> None:
        """注册一个宿主（重复注册同一宿主：幂等覆盖为最新引用）。"""
        key = host.renderer_host_key()
        refs = self._hosts.setdefault(key, [])
        for ref in list(refs):
            if ref() is host:
                return  # 已注册，幂等
        refs.append(weakref.ref(host))

    def hosts_for(self, recipe_key: RecipeKey) -> list[RendererHost]:
        """返回该槽位的全部存活宿主；顺带清理已失效弱引用。"""
        refs = self._hosts.get(recipe_key, [])
        alive: list[RendererHost] = []
        for ref in list(refs):
            host = ref()
            if host is not None:
                alive.append(host)
            else:
                refs.remove(ref)
        if not refs:
            self._hosts.pop(recipe_key, None)
        return alive

    def all_hosts(self) -> list[RendererHost]:
        """全部存活宿主（测试用；生产代码不消费）。"""
        result: list[RendererHost] = []
        for key in list(self._hosts):
            result.extend(self.hosts_for(key))
        return result

    def unregister(self, host: RendererHost) -> None:
        """显式注销（测试与未来动态宿主用）。"""
        key = host.renderer_host_key()
        refs = self._hosts.get(key, [])
        for ref in list(refs):
            if ref() is host:
                refs.remove(ref)
        if not refs:
            self._hosts.pop(key, None)
