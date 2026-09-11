# -*- coding: utf-8 -*-
"""WebView2 后端：WebPreviewAdapter 的 PyWinRT + WebView2 实现

以系统共享的 WebView2 Runtime 承载预览，使 PanzerNote 不必随包分发 Chromium。

为什么依赖 qasync（C1.6 判定性实验结论，非可选）：
  PyWinRT 的 controller 创建既需要「调用线程的消息泵」，又禁止在 STA 上阻塞
  等待（.get() 报 Cannot call blocking method from single-threaded apartment），
  且放到后台 asyncio 循环会永久挂起。故 asyncio 循环与 Qt 循环必须在同一线程
  合并。QEventLoop 就绪前本适配器会初始化失败/挂起——这是设计前提。

与接口的对应关系（8 项能力）：
  widget()            -> 容器 QWidget（WebView2 嵌入其 HWND）
  set_html()          -> navigate_to_string（注入消息 shim 与 <base href>）
  run_javascript()    -> execute_script_async（fire-and-forget）
  set_visible()       -> controller.is_visible
  set_resource_root() -> set_virtual_host_name_to_folder_mapping
  export_pdf()        -> print_to_pdf_async（临时文件中转，回传 bytes）
  load_finished       -> NavigationCompleted 事件
  message_received    -> add_web_message_received

关键实现约束：
  - 创建是异步的，而接口是同步的 → 就绪前的调用入队，就绪后补发。
  - bounds 使用**物理像素**而 Qt 用逻辑像素 → dpr 换算封装在本文件内部，
    且原点取容器自身客户区（容器是独立 HWND），上层不得感知（C1.6 目视检查
    得出的必办项）。
  - 预览模板经 document.title 回传消息，WebView2 无 titleChanged 信号 →
    注入 JS 劫持 title setter 转发到 chrome.webview.postMessage，
    模板与 markdown_preview.py 无需改动。
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import tempfile
from pathlib import Path
from typing import Callable

import webview2.microsoft.web.webview2.core as core
import winrt.windows.foundation as wf
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget

from ..utils.logger import get_logger
from .web_preview import WebPreviewAdapter

_log = get_logger(__name__)

# 虚拟主机名：资源根目录映射用（与 WebEngine 的 base_url 同职责）
VHOST = "pnassets"

# 共享环境对象：create_async 开销大，按进程缓存一份
_ENV: core.CoreWebView2Environment | None = None


def _swallow(task: "asyncio.Task[object]") -> None:
    """fire-and-forget 任务的安全回收：取回异常避免未检索告警。"""
    try:
        task.result()
    except Exception:  # noqa: BLE001
        pass


class _WebView2Host(QWidget):
    """WebView2 的宿主容器控件，负责把尺寸变化转成 bounds 同步。"""

    def __init__(self, owner: "WebView2PreviewAdapter", parent: QWidget | None) -> None:
        super().__init__(parent)
        self._owner = owner
        # 强制原生窗口：controller 需要稳定的 HWND
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setAutoFillBackground(False)

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        self._owner._apply_bounds()

    def showEvent(self, ev) -> None:  # noqa: N802
        super().showEvent(ev)
        self._owner._apply_bounds()


class WebView2PreviewAdapter(WebPreviewAdapter):
    """基于 PyWinRT WebView2 的预览适配器。"""

    # 内部信号：把「环境就绪」从协程世界带回 Qt 世界
    _ready_signal = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._container = _WebView2Host(self, parent)
        self._controller: core.CoreWebView2Controller | None = None
        self._webview: core.CoreWebView2 | None = None
        self._env: core.CoreWebView2Environment | None = None
        self._ready = False

        self._resource_root: str | None = None
        self._pending_html: str | None = None
        self._pending_scripts: list[str] = []
        self._pending_export: tuple[str, Callable[[bytes], None]] | None = None
        self._nav_event: asyncio.Event | None = None

        self._ready_signal.connect(self._flush_pending)
        asyncio.ensure_future(self._init_async())

    # ── 接口实现 ────────────────────────────────────────────────────────
    def widget(self) -> QWidget:
        return self._container

    def set_html(self, html: str) -> None:
        if not self._ready:
            self._pending_html = html
            return
        self._navigate(html)

    def run_javascript(self, script: str) -> None:
        if not self._ready:
            self._pending_scripts.append(script)
            return
        webview = self._webview
        if webview is None:
            return
        task = asyncio.ensure_future(webview.execute_script_async(script))
        task.add_done_callback(_swallow)

    def set_visible(self, visible: bool) -> None:
        if self._controller is not None:
            self._controller.is_visible = visible

    def set_resource_root(self, root: str | None) -> None:
        root = root or None
        if root == self._resource_root:
            return
        self._resource_root = root
        if self._ready and root:
            self._apply_resource_root()

    def export_pdf(self, html: str, on_done: Callable[[bytes], None]) -> None:
        if not self._ready:
            self._pending_export = (html, on_done)
            return
        task = asyncio.ensure_future(self._export_async(html, on_done))
        task.add_done_callback(_swallow)

    # ── 初始化 ──────────────────────────────────────────────────────────
    async def _init_async(self) -> None:
        global _ENV
        try:
            ctypes.windll.ole32.CoInitialize(None)
            if _ENV is None:
                _ENV = await core.CoreWebView2Environment.create_async()
            self._env = _ENV

            hwnd = int(self._container.winId())
            ref = core.CoreWebView2ControllerWindowReference.create_from_window_handle(
                hwnd
            )
            self._controller = await self._env.create_core_webview2_controller_async(ref)
            self._webview = self._controller.core_webview2
            self._controller.is_visible = True
            self._controller.rasterization_scale = self._container.devicePixelRatioF()
            self._controller.should_detect_monitor_scale_changes = True

            self._webview.add_web_message_received(self._on_web_message)
            self._webview.add_navigation_completed(self._on_navigation_completed)

            if self._resource_root:
                self._apply_resource_root()

            self._nav_event = asyncio.Event()
            self._apply_bounds()
            self._ready = True
            _log.info("WebView2 后端已就绪")
            self._ready_signal.emit()
        except Exception:  # noqa: BLE001
            # 初始化失败：预览区留空。必须留日志，否则故障完全不可见
            _log.error("WebView2 初始化失败，预览将留空", exc_info=True)

    def _flush_pending(self) -> None:
        """初始化完成后补发就绪前积压的调用，保持调用顺序。"""
        html, on_done = None, None
        if self._pending_export is not None:
            html, on_done = self._pending_export
            self._pending_export = None
        if html is None and self._pending_html is not None:
            html = self._pending_html
            self._pending_html = None

        if html is not None:
            if on_done is not None:
                self._navigate(html)
                task = asyncio.ensure_future(self._print_current(on_done))
                task.add_done_callback(_swallow)
            else:
                self._navigate(html)

        scripts, self._pending_scripts = self._pending_scripts, []
        for s in scripts:
            self.run_javascript(s)

    # ── 内部机制 ────────────────────────────────────────────────────────
    def _apply_resource_root(self) -> None:
        if self._resource_root and self._webview is not None:
            self._webview.set_virtual_host_name_to_folder_mapping(
                VHOST,
                self._resource_root,
                core.CoreWebView2HostResourceAccessKind.ALLOW,
            )

    def _apply_bounds(self) -> None:
        if self._controller is None:
            return
        # WebView2 bounds = **父 HWND 客户区**的物理像素；Qt geometry() = 逻辑像素。
        # 两个易错点：
        # 1) 尺寸必须乘 dpr，否则只覆盖 1/dpr 的宽高（dpr=2.0 时正好 1/4 面积）；
        # 2) 原点是本容器客户区的 (0,0)，**不能**用 geometry().x()/y() —— 容器带
        #    WA_NativeWindow，已是独立 HWND，而 geometry() 是相对 splitter 的
        #    坐标，把它当原点会把视图整体推出容器外（预览整片空白）。
        dpr = self._container.devicePixelRatioF()
        w = self._container.width()
        h = self._container.height()
        _log.debug("WebView2 bounds: %dx%d dpr=%s", w, h, dpr)
        self._controller.set_bounds_and_zoom_factor(
            wf.Rect(
                0.0,
                0.0,
                float(w) * dpr,
                float(h) * dpr,
            ),
            1.0,
        )

    def _navigate(self, html: str) -> None:
        if self._webview is None:
            return
        if self._nav_event is not None:
            self._nav_event.clear()
        _log.debug("WebView2 导航：html %d 字符，资源根=%s", len(html), self._resource_root)
        self._webview.navigate_to_string(self._inject(html))

    def _inject(self, html: str) -> str:
        """注入消息 shim（必要）与资源根 base 标签（可选）。

        必须插在文档最前，保证先于页面自身脚本执行。
        """
        snippet = _TITLE_SHIM
        if self._resource_root:
            snippet += f'<base href="https://{VHOST}/">'
        lower = html.lower()
        idx = lower.find("<head")
        if idx != -1:
            end = html.find(">", idx)
            if end != -1:
                return html[: end + 1] + snippet + html[end + 1:]
        return snippet + html

    # ── 事件回调（均在创建 controller 的线程上触发）──────────────────────
    def _on_web_message(self, sender, args) -> None:  # noqa: ANN001
        try:
            msg = args.try_get_web_message_as_string()
        except Exception:  # noqa: BLE001
            return
        if msg:
            self.message_received.emit(msg)

    def _on_navigation_completed(self, sender, args) -> None:  # noqa: ANN001
        try:
            ok = bool(args.is_success)
        except Exception:  # noqa: BLE001
            ok = True
        _log.debug("WebView2 导航完成: success=%s", ok)
        if self._nav_event is not None:
            self._nav_event.set()
        self.load_finished.emit(ok)

    # ── PDF 导出 ────────────────────────────────────────────────────────
    async def _export_async(self, html: str, on_done: Callable[[bytes], None]) -> None:
        self._navigate(html)
        await self._print_current(on_done)

    async def _print_current(self, on_done: Callable[[bytes], None]) -> None:
        """等待当前导航完成 → 导出 PDF → 以 bytes 回调 → 释放自身。"""
        env, webview = self._env, self._webview
        if env is None or webview is None:
            on_done(b"")
            self.close()
            return

        path: str | None = None
        try:
            if self._nav_event is not None:
                await self._nav_event.wait()
            fd, path = tempfile.mkstemp(suffix=".pdf", prefix="pn_preview_")
            os.close(fd)
            settings = env.create_print_settings()
            # WebView2 的 PrintSettings 默认**不打印背景**（缺省 False），会让代码块
            # 底色与高亮背景整片丢失。WebEngine 的 printToPdf 默认打印背景，此处对齐。
            settings.should_print_backgrounds = True
            ret = await webview.print_to_pdf_async(path, settings)
            data = b""
            if ret:
                data = Path(path).read_bytes()
                if not data.startswith(b"%PDF"):
                    data = b""
            on_done(data)
        except Exception:  # noqa: BLE001
            on_done(b"")
        finally:
            if path is not None:
                try:
                    os.remove(path)
                except OSError:
                    pass
            self.close()

    # ── 释放 ────────────────────────────────────────────────────────────
    def close(self) -> None:
        """关闭 controller 并释放控件（export_pdf 完成后自动调用）。"""
        if self._controller is not None:
            try:
                self._controller.close()
            except Exception:  # noqa: BLE001
                pass
            self._controller = None
            self._webview = None
        self._container.deleteLater()
        self.deleteLater()


# 消息 shim：劫持 document.title 的 setter，转发到 chrome.webview.postMessage。
# 读值仍返回真实 title，故不改变页面自身对 title 的语义。
_TITLE_SHIM = (
    "<script>(function(){try{"
    "var d=Object.getOwnPropertyDescriptor(Document.prototype,'title');"
    "if(!d)return;"
    "Object.defineProperty(document,'title',{configurable:true,"
    "get:function(){return d.get.call(document);},"
    "set:function(v){d.set.call(document,v);"
    "try{if(window.chrome&&chrome.webview)chrome.webview.postMessage(String(v));}"
    "catch(e){}}"
    "});}catch(e){}})();</script>"
)
