# -*- coding: utf-8 -*-
"""Web 预览抽象接口

把预览与导出对具体 Web 控件的依赖（当前为 Qt WebEngine）收敛到本层之后，
使上层只依赖「能力」，而不依赖某一控件的专有 API。

后端实现：
  - WebEngine：web_preview_webengine.WebEnginePreviewAdapter（现存实现）
  - WebView2：C 路线 C3 阶段新增

设计说明：
  - 本层抽象的是「Web 控件 API」，而非「框架」。两个后端都宿主在 Qt 中，
    因此接口直接使用 Qt 信号是合理的，且信号一律在主线程发出。
  - 资源根目录（能力 7）独立成方法而非 set_html 的次要参数：
    WebEngine 侧它是「一次调用时可选的 base_url」，
    WebView2 侧它是「一次映射注册」，二者语义不同，须由后端各自消化。
  - DPI / bounds 不在接口内：WebEngine 后端是普通 QWidget 自动处理；
    WebView2 后端需在自身内部封装 dpr 换算，不让上层感知。
"""

from __future__ import annotations

from abc import ABC, ABCMeta, abstractmethod
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget

from ..utils.feature_flags import is_enabled


class _AdapterMeta(type(QObject), ABCMeta):  # type: ignore[misc]
    """组合 PyQt 的 sip 元类与 ABCMeta。

    QObject 的元类是 sip 的 wrappertype，与 ABCMeta 不兼容，
    直接 `class X(QObject, ABC)` 会抛 metaclass conflict，故显式组合二者。
    """


class WebPreviewAdapter(QObject, ABC, metaclass=_AdapterMeta):
    """Web 预览适配器接口（8 项能力）。"""

    # 能力 6：加载完成（WebEngine loadFinished / WebView2 NavigationCompleted）
    load_finished = pyqtSignal(bool)

    # 能力 8：JS -> Python 消息通道（替代 document.title hack）
    message_received = pyqtSignal(str)

    @abstractmethod
    def widget(self) -> QWidget:
        """返回可挂载到布局中的控件本体。"""

    @abstractmethod
    def set_html(self, html: str) -> None:
        """整页加载 HTML。相对资源的解析根目录见 set_resource_root。"""

    @abstractmethod
    def run_javascript(self, script: str) -> None:
        """执行 JS，不取返回值（现用法均不依赖返回值）。"""

    @abstractmethod
    def set_visible(self, visible: bool) -> None:
        """显示 / 隐藏预览。"""

    @abstractmethod
    def set_resource_root(self, root: str | None) -> None:
        """声明相对资源的解析根目录，通常为当前文档所在目录。

        传 None 表示不使用资源根。
        """

    @abstractmethod
    def export_pdf(self, html: str, on_done: Callable[[bytes], None]) -> None:
        """加载 html 并导出为 PDF，完成时以字节回调（失败回调 b""）。

        时序与既有实现一致：加载完成后才触发导出。

        本方法是**一次性**的：调用后适配器即进入终结流程，回调触发后
        自动释放（控件与适配器本身一并销毁）。因此不要对预览用的实例调用本方法。
        """


def create_preview_adapter(parent: QWidget | None = None) -> WebPreviewAdapter:
    """按 feature flag `webview2_preview` 选择后端并构造适配器。

    上层只应经本函数取得适配器，不得直接构造具体后端 —— 这样切换后端
    不会波及预览与导出两处调用点。

    实现类在此惰性导入：两个后端模块都 import 本模块，模块级导入会成环。
    """
    if is_enabled("webview2_preview"):
        from .web_preview_webview2 import WebView2PreviewAdapter

        return WebView2PreviewAdapter(parent)
    from .web_preview_webengine import WebEnginePreviewAdapter

    return WebEnginePreviewAdapter(parent)
