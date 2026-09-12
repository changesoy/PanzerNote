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
  set_html()          -> navigate_to_string（注入 <base href>）
  run_javascript()    -> execute_script_async（fire-and-forget）
  set_visible()       -> controller.is_visible
  set_resource_root() -> set_virtual_host_name_to_folder_mapping
  export_pdf()        -> print_to_pdf_async（临时文件中转，回传 bytes）
  load_finished       -> NavigationCompleted 事件
  message_received    -> add_web_message_received

关键实现约束：
  - 创建是异步的，而接口是同步的 → 就绪前的调用入队，就绪后补发。
  - 协程必须有运行中的事件循环（qasync）；循环缺失或运行时缺失/初始化失败
    一律转入失败态并在预览区显示可读提示，不做构造期崩溃、不留空白。
  - bounds 使用**物理像素**而 Qt 用逻辑像素 → dpr 换算封装在本文件内部，
    且原点取容器自身客户区（容器是独立 HWND），上层不得感知（C1.6 目视检查
    得出的必办项）。
  - 页面 → 宿主的消息走 WebView2 官方通道：页面调用
    ``chrome.webview.postMessage``，本后端经 add_web_message_received 转成
    message_received 信号；协议（消息前缀）见 markdown_preview 的预览模板。
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import tempfile
from pathlib import Path
from typing import Callable, Coroutine

import webview2.microsoft.web.webview2.core as core
import winrt.windows.foundation as wf
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..utils.logger import get_logger
from . import mermaid_render, webview2_runtime
from .mermaid_render import READY_MESSAGE, needs_async_render, needs_vendor_injection
from .web_preview import WebPreviewAdapter

_log = get_logger(__name__)

# 虚拟主机名：资源根目录映射用（与 WebEngine 的 base_url 同职责）
VHOST = "pnassets"

# NavigateToString 官方文档上限 2 MB；留余量（预览模板恒内联 KaTeX 约 645 KB）
_MAX_NAVIGATE_BYTES = 1_800_000

# 图表等异步渲染的就绪等待上限（秒）
_ASYNC_RENDER_TIMEOUT_S = 8.0
_ASYNC_POLL_INTERVAL_S = 0.05

# 打印渲染视口：Chromium 的打印排版与 CSS 一样按 1in = 96px 换算
_CSS_PX_PER_INCH = 96.0
# 取不到打印设置时的退化视口（A4 纸面）
_FALLBACK_PRINT_SIZE = (794, 1123)

# 共享环境对象：create_async 开销大，按进程缓存一份
_ENV: core.CoreWebView2Environment | None = None


def _safe_remove(path: str | None) -> None:
    """尽力删除临时文件（Windows 下文件句柄占用是常态，忽略一切失败）。"""
    if path is None:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _swallow(task: "asyncio.Task[object]") -> None:
    """fire-and-forget 任务的安全回收：取回异常避免未检索告警，并留下日志。

    这里不能静默丢弃：``_execute_script`` 的失败（JS 报错、脚本未执行）
    没有别的地方能看到。
    """
    try:
        task.result()
    except Exception as exc:  # noqa: BLE001
        _log.warning("WebView2 后台任务失败: %s", exc)


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
        # 初始化失败（含运行时缺失 / 无事件循环）：预览区转为可见提示
        self._failed = False
        self._hint_label: QLabel | None = None

        self._resource_root: str | None = None
        self._pending_html: str | None = None
        self._pending_scripts: list[str] = []
        self._pending_export: tuple[str, Callable[[bytes], None]] | None = None
        self._nav_event: asyncio.Event | None = None
        # 页面异步渲染（图表）就绪标志：本轮导航的文档是否声明了 pn-async，
        # 以及页面是否已回传就绪信号
        self._await_async_render = False
        self._async_ready = False

        # 事件处理器注册 token：close 时显式摘除，打破跨 Python/WinRT 的引用环
        self._webmsg_token: object | None = None
        self._nav_token: object | None = None
        # close() 幂等标志：导出完成后与预览 teardown 都可能触发释放
        self._closed = False

        self._ready_signal.connect(self._flush_pending)
        self._schedule(self._init_async())

    # ── 接口实现 ────────────────────────────────────────────────────────
    def widget(self) -> QWidget:
        return self._container

    def set_html(self, html: str) -> None:
        if not self._ready:
            self._pending_html = html
            return
        try:
            self._navigate(html)
        except Exception as exc:  # noqa: BLE001
            # 同步路径上的 WinRT 调用异常若从这里逃逸（PyQt6 槽 → abort）
            # 会直接终止进程，与模块「失败可见、不崩溃」的承诺相反。
            self._fail(f"预览加载失败：{exc}")

    def run_javascript(self, script: str) -> None:
        if not self._ready:
            self._pending_scripts.append(script)
            return
        self._schedule(self._execute_script(script))

    def set_visible(self, visible: bool) -> None:
        if self._controller is None:
            return
        try:
            self._controller.is_visible = visible
        except Exception as exc:  # noqa: BLE001
            self._fail(f"预览显示控制失败：{exc}")

    def set_resource_root(self, root: str | None) -> None:
        root = root or None
        if root == self._resource_root:
            return
        self._resource_root = root
        if self._ready and root:
            self._apply_resource_root()

    def export_pdf(self, html: str, on_done: Callable[[bytes], None]) -> None:
        if self._failed:
            # 已定失败：按接口约定立即回调 b""，不让调用方空等
            on_done(b"")
            return
        if not self._ready:
            # 同一实例只服务一次导出。前一次尚未补发时先把它按失败兑现，
            # 否则会被静默覆盖、那个调用方永远收不到回调。
            if self._pending_export is not None:
                self._pending_export[1](b"")
            self._pending_export = (html, on_done)
            return
        self._schedule(self._export_async(html, on_done))

    # ── 协程调度 ────────────────────────────────────────────────────────
    async def _execute_script(self, script: str) -> None:
        """执行 JS。

        ``execute_script_async`` 返回 WinRT 的 IAsyncOperation（可等待对象，
        不是协程），故必须包在协程里 await —— ``loop.create_task`` 只接受协程。
        """
        webview = self._webview
        if webview is None:
            return
        await webview.execute_script_async(script)

    def _schedule(self, coro: "Coroutine[object, object, None]") -> None:
        """把协程投递到当前事件循环。

        用 ``get_event_loop()`` 而非 ``get_running_loop()``：主窗口是在
        ``loop.run_forever()`` **之前**构造的（见 main.py），此时循环已 set
        但尚未 run，任务仍应正常入队、待循环启动后执行。

        完全没有循环时**不抛异常**：适配器可能被构造在循环之外（测试宿主、
        非 qasync 启动路径），此时转入失败态并给出可见提示，
        避免把「后端不可用」表现为构造期崩溃。
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            coro.close()
            self._fail(
                "当前没有事件循环，无法初始化 WebView2 预览。\n"
                "应用需经 qasync 事件循环启动（见 main.py）。"
            )
            return
        task = loop.create_task(coro)
        task.add_done_callback(_swallow)

    def _fail(self, message: str) -> None:
        """转入失败态：清理 controller、显示可读提示，并兑掉排队中的导出回调。

        导出是一次性调用，调用方靠 on_done 收尾；若失败时丢弃回调，用户点
        导出会毫无反应（连「PDF生成失败」提示都看不到），故此处也必须回调 b""。

        先清理 controller 再显示提示：WebView2 是独立 HWND 的原生子窗口，
        Windows 下永远绘制在非原生 Qt 控件之上——不隐藏/关闭它，失败提示
        QLabel 会被盖成一片白板（M1）。
        """
        self._failed = True
        _log.error("WebView2 预览不可用：%s", message.replace("\n", " "))
        if self._controller is not None:
            try:
                self._controller.is_visible = False
            except Exception:  # noqa: BLE001
                pass
            try:
                self._controller.close()
            except Exception:  # noqa: BLE001
                pass
            self._controller = None
            self._webview = None
        self._show_hint(message)
        pending, self._pending_export = self._pending_export, None
        if pending is not None:
            pending[1](b"")

    def _show_hint(self, message: str) -> None:
        if self._hint_label is not None:
            return
        label = QLabel(message, self._container)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 允许选中 / 点开安装地址，便于用户自助恢复
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        label.setOpenExternalLinks(True)
        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(label)
        label.show()
        self._hint_label = label

    # ── 初始化 ──────────────────────────────────────────────────────────
    async def _init_async(self) -> None:
        global _ENV
        if not webview2_runtime.is_available():
            # 运行时缺失：先失败退出，不进入 create_async 的晦涩报错
            self._fail(webview2_runtime.INSTALL_HINT)
            return
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

            self._webmsg_token = self._webview.add_web_message_received(
                self._on_web_message
            )
            self._nav_token = self._webview.add_navigation_completed(
                self._on_navigation_completed
            )

            if self._resource_root:
                self._apply_resource_root()

            self._nav_event = asyncio.Event()
            self._apply_bounds()
            self._ready = True
            _log.info("WebView2 后端已就绪")
            self._ready_signal.emit()
        except Exception as exc:  # noqa: BLE001
            # 初始化失败：必须留日志 + 可见提示，否则故障完全不可见
            _log.error("WebView2 初始化失败", exc_info=True)
            self._fail(f"WebView2 初始化失败：{exc}")

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
                # 必须复用 _export_async（而非直接 _navigate）：导出前的资源准备
                # （图表库注入）都在那里。export_pdf 几乎总在适配器就绪前被调用，
                # 因此这条补发路径才是常规路径，绕过它会让注入静默失效。
                self._schedule(self._export_async(html, on_done))
            else:
                self._navigate(html)

        scripts, self._pending_scripts = self._pending_scripts, []
        for s in scripts:
            self.run_javascript(s)

    # ── 内部机制 ────────────────────────────────────────────────────────
    def _apply_resource_root(self) -> None:
        if self._resource_root and self._webview is not None:
            try:
                self._webview.set_virtual_host_name_to_folder_mapping(
                    VHOST,
                    self._resource_root,
                    core.CoreWebView2HostResourceAccessKind.ALLOW,
                )
            except Exception as exc:  # noqa: BLE001
                self._fail(f"资源目录映射失败：{exc}")

    def _apply_bounds(self) -> None:
        if self._controller is None:
            return
        # WebView2 bounds = **父 HWND 客户区**的物理像素；Qt geometry() = 逻辑像素。
        # 两个易错点：
        # 1) 尺寸必须乘 dpr，否则只覆盖 1/dpr 的宽高（dpr=2.0 时正好 1/4 面积）；
        # 2) 原点是本容器客户区的 (0,0)，**不能**用 geometry().x()/y() —— 容器带
        #    WA_NativeWindow，已是独立 HWND，而 geometry() 是相对 splitter 的
        #    坐标，把它当原点会把视图整体推出容器外（预览整片空白）。
        try:
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
        except Exception:  # noqa: BLE001
            # 由 _WebView2Host.resizeEvent/showEvent 调用：PyQt6 虚函数回调里
            # 抛异常是致命的（abort），且销毁过程中容器尺寸已无意义，只记日志。
            _log.debug("同步 WebView2 bounds 失败（控件可能正在销毁）", exc_info=True)

    def _navigate(self, html: str) -> None:
        if self._webview is None:
            return
        # NavigateToString 有 2 MB 文档上限（官方文档 + 真机 E_INVALIDARG 复现）。
        # 超限文档若直接导航会抛异常：预览侧由 set_html 转 _fail，导出侧由
        # _export_async 的 try/except 兜住 —— 都不能让 E_INVALIDARG 裸奔。
        if len(html) > _MAX_NAVIGATE_BYTES:
            size_mb = len(html) / 1024 / 1024
            raise RuntimeError(
                f"文档过大（{size_mb:.1f} MB，上限约 1.7 MB）："
                "WebView2 单次加载的文档不能超过 2 MB，请精简内容后重试。"
            )
        if self._nav_event is not None:
            self._nav_event.clear()
        # 每轮导航重置异步就绪门：图表文档要等页面回传就绪信号才打印
        self._async_ready = False
        self._await_async_render = needs_async_render(html)
        _log.debug("WebView2 导航：html %d 字符，资源根=%s", len(html), self._resource_root)
        self._webview.navigate_to_string(self._inject(html))

    def _inject(self, html: str) -> str:
        """注入资源根 base 标签（可选；未声明资源根时原样返回）。

        必须插在文档最前，保证先于页面自身脚本执行。
        """
        if not self._resource_root:
            return html
        snippet = f'<base href="https://{VHOST}/">'
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
        if msg == READY_MESSAGE:
            # 页面异步渲染就绪（仅图表导出文档会发），不向 Qt 侧转发
            self._async_ready = True
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
        """导出全程：前置准备（视口 / 图表库 / 导航）→ 打印。

        前置阶段失败也必须兑现 on_done，否则本次导出会静默卡死（打印阶段由
        ``_print_current`` 自己兜底，这里补上前置阶段）。
        """
        try:
            self._size_viewport_for_print()
            await self._provide_external_vendor(html)
            self._navigate(html)
        except Exception:  # noqa: BLE001
            _log.error("PDF 导出前置阶段失败", exc_info=True)
            on_done(b"")
            self.close()
            return
        await self._print_current(on_done)

    def _size_viewport_for_print(self) -> None:
        """打印前把离屏视口调成纸面内容框尺寸。

        离屏容器从不进入布局，尺寸停留在 Qt 的默认值；正文类内容在打印时按纸面
        重新排版，故此前无需过问。但**按容器宽度计算自身宽度**的图表会因此失准：
        Mermaid 甘特图取 ``parentElement.offsetWidth`` 作 viewBox 宽度，袖珍视口
        下算出的宽度只有纸面的约 1/10，导出后整张图挤在纸面左侧。

        视口取「纸面宽 - 左右页边距」：打印排版用的就是这个内容框宽度，图表据此
        得到与纸面一致的宽度。``resize`` 后须显式同步 bounds —— 隐藏控件不派发
        resizeEvent（见 _WebView2Host.resizeEvent）。
        """
        width, height = _FALLBACK_PRINT_SIZE
        env = self._env
        if env is not None:
            try:
                settings = env.create_print_settings()
                w = (
                    float(settings.page_width)
                    - float(settings.margin_left)
                    - float(settings.margin_right)
                )
                h = (
                    float(settings.page_height)
                    - float(settings.margin_top)
                    - float(settings.margin_bottom)
                )
                if w > 0 and h > 0:
                    width = int(w * _CSS_PX_PER_INCH)
                    height = int(h * _CSS_PX_PER_INCH)
            except Exception:  # noqa: BLE001
                _log.debug("读取打印设置失败，视口退化为 A4", exc_info=True)
        _log.debug("打印视口：%dx%d CSS px", width, height)
        self._container.resize(width, height)
        self._apply_bounds()

    async def _provide_external_vendor(self, html: str) -> None:
        """文档声明「图表库外置」时，经文档级脚本注入提供 vendor。

        为什么不内联进文档：NavigateToString 对文档有 2 MB 上限（官方文档
        "may not be larger than 2 MB"），内联 Mermaid（约 5.6 MB）会以
        E_INVALIDARG 直接失败。文档级注入没有该上限（实测 5.6 MB 可用），
        且脚本在页面自身脚本之前执行，页面里的 pnMermaidBoot 照常工作。

        注入失败不致命：脚本缺失时页面渲染无产出，就绪门等超时后降级打印，
        图表位置留空但正文照常导出（见 _await_page_render 的超时兜底）。
        """
        webview = self._webview
        if webview is None or not needs_vendor_injection(html):
            return
        vendor = mermaid_render.vendor_js()
        if not vendor:
            return
        try:
            await webview.add_script_to_execute_on_document_created_async(vendor)
        except Exception:  # noqa: BLE001
            _log.warning("图表库注入失败，导出的 PDF 可能缺少图表", exc_info=True)

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
            await self._await_page_render()
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
                _safe_remove(path)
            self.close()

    async def _await_page_render(self) -> None:
        """等待页面声明的异步渲染（图表）就绪后再打印。

        NavigationCompleted 只代表文档装载完成：Mermaid 渲染是异步的，此刻 SVG
        可能尚未生成，直接打印会把图表位置印成源码文本。页面渲染结束后经 title
        shim 回传 READY_MESSAGE，此处轮询该标志（页面声明了 pn-async 时才等）。

        用轮询而非 asyncio.Event.wait：消息回调不保证在事件循环线程上触发，
        跨线程 set asyncio.Event 并不安全，而布尔标志的赋值是原子的。

        超时兜底：超时后照常打印 —— 宁可少一张图，也不让整个导出失败。
        """
        if not self._await_async_render:
            return
        attempts = int(_ASYNC_RENDER_TIMEOUT_S / _ASYNC_POLL_INTERVAL_S)
        for _ in range(attempts):
            if self._async_ready:
                return
            await asyncio.sleep(_ASYNC_POLL_INTERVAL_S)
        _log.warning(
            "图表渲染未在 %.1fs 内就绪，本次导出可能缺少图表", _ASYNC_RENDER_TIMEOUT_S
        )

    # ── 释放 ────────────────────────────────────────────────────────────
    def close(self) -> None:
        """通用 teardown：摘除事件处理器、关闭 controller、销毁控件。幂等。

        预览与导出共用：导出完成后（_export_async / _print_current）自动调用；
        预览侧在标签关闭 / 窗口退出时由上层显式调用（接口 close 契约，见
        web_preview.py）。QTabWidget.removeTab 不删除页面控件也不触发
        closeEvent，若不经本方法，每个标签页的 controller 与一组
        msedgewebview2 进程会随标签累积、永不回收。

        显式摘除事件处理器：add_web_message_received / add_navigation_completed
        注册的处理器持有本适配器的绑定方法，形成跨 Python/WinRT 的引用环，
        controller.close() 之外还需 remove 掉注册才能彻底断开。
        """
        if self._closed:
            return
        self._closed = True
        webview = self._webview
        if webview is not None:
            if self._webmsg_token is not None:
                try:
                    webview.remove_web_message_received(self._webmsg_token)
                except Exception:  # noqa: BLE001
                    pass
            if self._nav_token is not None:
                try:
                    webview.remove_navigation_completed(self._nav_token)
                except Exception:  # noqa: BLE001
                    pass
        if self._controller is not None:
            try:
                self._controller.close()
            except Exception:  # noqa: BLE001
                pass
            self._controller = None
            self._webview = None
        self._container.deleteLater()
        self.deleteLater()
