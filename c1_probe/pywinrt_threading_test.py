# -*- coding: utf-8 -*-
"""C1.6 判定性实验（无界面）：controller 创建能否在「后台 asyncio 循环」完成。

安全设计：
  - 窗口**只创建不显示**（仅调用 winId() 取 HWND），屏幕上不会出现任何窗口；
  - 20 秒硬超时；
  - 无论结果如何都强制 os._exit()，进程绝不残留。

判定：
  - 成功 → 后台循环方案可行，无需引入 qasync；
  - 超时 → controller 创建强依赖「调用线程自身的循环」，必须用 qasync。

用法：
  python -u c1_probe/pywinrt_threading_test.py
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import sys
import threading
import time
from pathlib import Path

import webview2.microsoft.web.webview2.core as core
from PyQt6.QtWidgets import QApplication, QWidget

LOG = Path(__file__).resolve().parent / "_threading_test.log"
DEADLINE_S = 20


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001
        pass


loop = asyncio.new_event_loop()
ready = threading.Event()


def loop_thread() -> None:
    asyncio.set_event_loop(loop)
    ready.set()
    loop.run_forever()


async def bootstrap(hwnd: int) -> str:
    log("bootstrap: CoInitialize(后台线程)")
    ctypes.windll.ole32.CoInitialize(None)
    log("bootstrap: create_async(environment)")
    env = await core.CoreWebView2Environment.create_async()
    log("bootstrap: environment OK")
    ref = core.CoreWebView2ControllerWindowReference.create_from_window_handle(hwnd)
    log("bootstrap: create_core_webview2_controller_async ... 等待完成")
    ctrl = await env.create_core_webview2_controller_async(ref)
    log("bootstrap: controller OK")
    ctrl.is_visible = True
    wv = ctrl.core_webview2
    log("bootstrap: webview OK")

    # 顺带验证一次 execute_script_async 能否在同一后台循环上完成
    wv.navigate_to_string("<html><head><title>TH</title></head><body>x</body></html>")
    await asyncio.sleep(1.0)
    title = await wv.execute_script_async("document.title")
    log(f"bootstrap: execute_script_async -> {title!r}")
    return str(title)


def main() -> int:
    LOG.write_text("", encoding="utf-8")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    w = QWidget()
    w.resize(600, 400)
    # 关键：不调用 show()，仅 winId() 触发原生 HWND 创建 —— 屏幕上无窗口
    hwnd = int(w.winId())
    log(f"隐藏宿主 HWND = {hwnd:#x}（窗口未显示）")

    threading.Thread(target=loop_thread, daemon=True).start()
    ready.wait(5)
    log("后台 asyncio 循环已启动")

    t0 = time.time()
    fut = asyncio.run_coroutine_threadsafe(bootstrap(hwnd), loop)

    while time.time() - t0 < DEADLINE_S:
        app.processEvents()  # 持续泵 Qt / Win32 消息
        if fut.done():
            break
        time.sleep(0.02)

    if fut.done():
        try:
            res = fut.result()
            log(f"结果：成功（{time.time() - t0:.2f}s），title={res!r} → 后台循环方案可行")
            code = 0
        except Exception as e:  # noqa: BLE001
            log(f"结果：异常 {type(e).__name__}: {e}")
            code = 3
    else:
        log(f"结果：{DEADLINE_S}s 超时 → 后台循环方案不可行，需 qasync")
        code = 1

    sys.stdout.flush()
    os._exit(code)  # 强制退出，确保无残留进程


if __name__ == "__main__":
    main()
