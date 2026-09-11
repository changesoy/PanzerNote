# -*- coding: utf-8 -*-
"""C1.6 PyWinRT 绑定 spike（qasync 版）：PyQt6 + WebView2。

为什么必须用 qasync：
  经无界面判定性实验确证 —— PyWinRT 的 controller 创建既需要
  「调用线程的消息泵」，又禁止在 STA 上阻塞等待（.get() 报
  "Cannot call blocking method from single-threaded apartment"），
  且放到后台 asyncio 循环会永久挂起（20s 超时）。
  因此 asyncio 循环与 Qt 循环必须**在同一线程合并** → qasync。

验收矩阵：
  0. 初始化            environment + controller
  1. HTML 加载         navigate_to_string + 读 title
  2. Python -> JS      execute_script_async 改 DOM 并读回
  3. JS -> Python      chrome.webview.postMessage + add_web_message_received
  4. 本地资源映射      set_virtual_host_name_to_folder_mapping + 相对路径图片
  5. PDF 静默导出      print_to_pdf_async

用法：
  python c1_probe/pywinrt_demo.py [--auto-close]
全程有 60s 硬超时，超时自动退出，不会无限无响应。
"""

from __future__ import annotations

import asyncio
import ctypes
import json
import os
import sys
import threading
from pathlib import Path

import webview2.microsoft.web.webview2.core as core
import winrt.windows.foundation as wf
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
from qasync import QEventLoop

HERE = Path(__file__).resolve().parent
VHOST = "pnassets"
TIMEOUT_S = 60

PASSED: list[str] = []
FAILED: list[str] = []


def report(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}", flush=True)
    (PASSED if ok else FAILED).append(name)


class Host(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("C1.6 PyWinRT + WebView2 spike (qasync)")
        self.resize(980, 700)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.status = QLabel("初始化 ...")
        self.status.setStyleSheet(
            "padding:4px; background:#eef2f7; border-bottom:1px solid #c8d3e0;"
        )
        lay.addWidget(self.status)
        self.area = QWidget(self)
        self.area.setStyleSheet("background:#fafafa;")
        lay.addWidget(self.area, 1)

        self.env = None
        self.controller = None
        self.webview = None
        self._msgs: list[str] = []

    # ── 工具 ────────────────────────────────────────────────────────────
    def _apply_bounds(self) -> None:
        if self.controller is None:
            return
        # WebView2 的 bounds 使用父窗口客户区的**物理像素**，
        # 而 Qt 的 geometry() 返回**逻辑像素**，必须乘 devicePixelRatio 换算。
        # 漏掉这一步会导致 WebView2 只覆盖 1/dpr 的宽高
        # （本机 dpr=2.0 时正好显示为 1/4 面积）。
        dpr = self.area.devicePixelRatioF()
        g = self.area.geometry()
        self.controller.set_bounds_and_zoom_factor(
            wf.Rect(
                float(g.x()) * dpr,
                float(g.y()) * dpr,
                float(g.width()) * dpr,
                float(g.height()) * dpr,
            ),
            1.0,
        )
        print(
            f"[bounds] dpr={dpr} "
            f"logical=({g.x()},{g.y()},{g.width()},{g.height()}) "
            f"physical=({int(g.x() * dpr)},{int(g.y() * dpr)},"
            f"{int(g.width() * dpr)},{int(g.height() * dpr)})",
            flush=True,
        )

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        self._apply_bounds()

    def _on_wm(self, sender, args) -> None:
        try:
            msg = args.try_get_web_message_as_string()
        except Exception:  # noqa: BLE001
            msg = "<unreadable>"
        print(f"[web_message] {msg[:160]}", flush=True)
        self._msgs.append(msg)

    async def js(self, expr: str) -> str:
        return await self.webview.execute_script_async(expr)

    def _set_status(self, t: str) -> None:
        self.status.setText(t)
        print(f"\n=== {t} ===", flush=True)

    # ── 主流程 ──────────────────────────────────────────────────────────
    async def run_all(self) -> None:
        try:
            await asyncio.wait_for(self._flow(), TIMEOUT_S)
        except asyncio.TimeoutError:
            report("全局超时", False, f"{TIMEOUT_S}s 内未完成")
        except Exception as e:  # noqa: BLE001
            report("未捕获异常", False, f"{type(e).__name__}: {e}")
        finally:
            self._finish()

    async def _flow(self) -> None:
        # ── 0. 初始化 ───────────────────────────────────────────────────
        self._set_status("验收 0：初始化")
        ctypes.windll.ole32.CoInitialize(None)
        self.env = await core.CoreWebView2Environment.create_async()
        hwnd = int(self.winId())
        print(f"[init] HWND = {hwnd:#x}", flush=True)
        ref = core.CoreWebView2ControllerWindowReference.create_from_window_handle(hwnd)
        self.controller = await self.env.create_core_webview2_controller_async(ref)
        self.webview = self.controller.core_webview2
        self.controller.is_visible = True
        # 高 DPI 清晰度：光栅化按设备像素比渲染，并跟随显示器缩放变化。
        dpr = self.area.devicePixelRatioF()
        self.controller.rasterization_scale = dpr
        self.controller.should_detect_monitor_scale_changes = True
        print(f"[init] rasterization_scale = {dpr}", flush=True)
        self.webview.add_web_message_received(self._on_wm)
        self.webview.set_virtual_host_name_to_folder_mapping(
            VHOST, str(HERE), core.CoreWebView2HostResourceAccessKind.ALLOW
        )
        self._apply_bounds()
        report("0. 初始化", True, "environment + controller OK")

        # ── 1. HTML 加载 ────────────────────────────────────────────────
        self._set_status("验收 1：HTML 加载")
        self.webview.navigate_to_string(
            "<html><head><title>C16</title></head>"
            "<body><h1 id='h'>Hello PyWinRT</h1>"
            "<p id='res'>(未调用)</p></body></html>"
        )
        await asyncio.sleep(1.5)
        title = json.loads(await self.js("document.title") or '""')
        report("1. HTML 加载", title == "C16", f"title={title!r}")

        # ── 2. Python -> JS ─────────────────────────────────────────────
        self._set_status("验收 2：Python -> JS")
        await self.js("document.getElementById('h').style.color = '#d43'")
        val = json.loads(await self.js("document.getElementById('h').style.color") or '""')
        report("2. Python -> JS", val in ("#d43", "rgb(221, 68, 51)"), f"h1.color={val!r}")

        # ── 3. JS -> Python ─────────────────────────────────────────────
        self._set_status("验收 3：JS -> Python")
        self._msgs.clear()
        await self.js(
            "chrome.webview.postMessage(JSON.stringify({type:'c16', n: 20+22}))"
        )
        await asyncio.sleep(1.0)
        ok, detail = False, "未收到消息"
        if self._msgs:
            raw = self._msgs[-1]
            detail = f"raw={raw!r}"
            try:
                ok = json.loads(raw).get("n") == 42
            except Exception:  # noqa: BLE001
                pass
        report("3. JS -> Python (postMessage)", ok, detail)

        # ── 4. 本地资源映射 ─────────────────────────────────────────────
        self._set_status("验收 4：本地资源映射")
        self.webview.navigate(f"https://{VHOST}/page.html")
        await asyncio.sleep(2.5)
        w = json.loads(await self.js("document.getElementById('pic').naturalWidth") or "0")
        report("4. 本地资源映射", isinstance(w, (int, float)) and w > 0, f"naturalWidth={w}")

        # ── 5. PDF 静默导出 ─────────────────────────────────────────────
        self._set_status("验收 5：PDF 静默导出")
        out = HERE / "_pywinrt_out.pdf"
        if out.exists():
            out.unlink()
        self.webview.navigate_to_string(
            "<html><head><meta charset='utf-8'><style>"
            "body{font-family:sans-serif;padding:24px}"
            "h1{color:#1a6fb0}table{border-collapse:collapse}"
            "td,th{border:1px solid #888;padding:4px 10px}"
            "pre{background:#eef2f7;padding:8px}</style></head><body>"
            "<h1>PDF 导出管线测试</h1>"
            "<p>中文段落：PanzerNote C 路线 PyWinRT PDF 验证。</p>"
            "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
            "<pre><code>def hello(): return 'world'</code></pre>"
            "</body></html>"
        )
        await asyncio.sleep(2.0)
        settings = self.env.create_print_settings()
        ret = await self.webview.print_to_pdf_async(str(out), settings)
        exists = out.exists()
        size = out.stat().st_size if exists else 0
        head = out.read_bytes()[:5] if exists else b""
        report(
            "5. PDF 静默导出",
            bool(ret) and size > 0 and head.startswith(b"%PDF"),
            f"ret={ret} size={size} head={head!r}",
        )

        # ── 渲染展示页（供目视检查）────────────────────────────────────
        self._set_status("渲染展示页（可目视检查字体 / DPI / 颜色 / 图片）")
        self.webview.navigate(f"https://{VHOST}/showcase.html")

    # ── 汇总 ────────────────────────────────────────────────────────────
    def _finish(self) -> None:
        print("\n========== C1.6 PyWinRT 验证结果 ==========", flush=True)
        print(f"PASS {len(PASSED)}: {PASSED}", flush=True)
        if FAILED:
            print(f"FAIL {len(FAILED)}: {FAILED}", flush=True)
        print("==========================================", flush=True)
        self.status.setText(f"验证完成 PASS {len(PASSED)} / FAIL {len(FAILED)}")
        if "--auto-close" in sys.argv:
            QApplication.instance().quit()


def main() -> None:
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # 硬保险：独立线程看门狗，默认 90s 无条件强退（防止事件循环被卡死时
    # asyncio.wait_for 也无法触发），确保永远不会出现无限无响应窗口。
    # 目视检查时可用 PN_DEMO_WATCHDOG 环境变量放宽（秒）。
    wd = int(os.environ.get("PN_DEMO_WATCHDOG", "90"))

    def _watchdog() -> None:
        import time as _t

        _t.sleep(wd)
        print(f"[watchdog] {wd}s 未退出，强制终止", flush=True)
        sys.stdout.flush()
        os._exit(9)

    threading.Thread(target=_watchdog, daemon=True).start()

    h = Host()
    h.show()
    loop.call_soon(lambda: asyncio.ensure_future(h.run_all()))
    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
