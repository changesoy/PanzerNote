# -*- coding: utf-8 -*-
"""C3-B 退出模式验证：qasync 退出时序本身是否干净。

隔离验证 main.py 的事件循环改造模式（与业务无关）：
  loop = QEventLoop(app); asyncio.set_event_loop(loop)
  app.aboutToQuit.connect(loop.stop)
  with loop: loop.run_forever()

分两步，逐步逼近真实复杂度：
  阶段 1：空窗口自退出
  阶段 2：加一个 WebEngine 视图（模拟应用内既有 WebEngine 预览）
若阶段 1 干净、阶段 2 崩溃 → 问题在 WebEngine 与 asyncio loop.close 的收尾交互；
若两者都干净 → main.py 的收尾问题在别处。

用法：
  python c1_probe/c3b_loop_exit_probe.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QWidget


def run_phase(name: str, with_webengine: bool) -> int:
    # WebEngine 前置条件（必须在 QApplication 之前，与 main.py 一致）
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)

    from qasync import QEventLoop

    win = QWidget()
    win.setWindowTitle(f"C3-B 退出探针 · {name}")
    win.resize(420, 200)

    view = None
    if with_webengine:
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView(win)
        view.setGeometry(10, 10, 400, 180)
        view.setHtml("<html><body><h1>probe</h1></body></html>")

    win.show()

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    app.aboutToQuit.connect(loop.stop)

    if view is not None:

        async def _late_close() -> None:
            await asyncio.sleep(2.0)
            app.quit()

        loop.call_soon(lambda: asyncio.ensure_future(_late_close()))
    else:
        QTimer.singleShot(1200, app.quit)

    with loop:
        loop.run_forever()

    print(f"[phase:{name}] run_forever 已返回（未崩溃到此）", flush=True)
    if view is not None:
        view.deleteLater()
    return 0


def main() -> int:
    phase = os.environ.get("PN_PHASE", "1")
    if phase == "2":
        code = run_phase("webengine", True)
    else:
        code = run_phase("empty", False)
    print(f"[phase:{phase}] 收尾完成，准备 sys.exit({code})", flush=True)
    sys.exit(code)


if __name__ == "__main__":
    main()
