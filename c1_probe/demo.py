# -*- coding: utf-8 -*-
"""C1 可行性验证 demo：QtWebViewWidget（wryview / WebView2 后端）五项能力验证。

用法：
  python c1_probe/demo.py                # 可视化 + 自动验证 1-4 项，窗口保持打开
  python c1_probe/demo.py --auto-close   # 验证完自动关闭
  python c1_probe/pdf_check.py           # 单独验证第 5 项 PDF 管线（需沙箱外运行 Edge）

验证项：
  1. HTML 加载（对应 QWebEngineView.setHtml / loadFinished）
  2. Python -> JS 执行（对应 page().runJavaScript）
  3. JS -> Python 消息（对应 titleChanged hack，此处为官方 bridge + raw IPC）
  4. 本地资源加载（对应 setHtml 的 base_url 相对路径解析）
  5. PDF 导出替代管线（wryview 无 printToPdf，见 pdf_check.py）

实测约束（wry 0.57）：IPC 消息仅当文档源为 http(s) 或 about:blank 时送达；
file:// 文档的 IPC 会被 wry 静默丢弃（wry 0.56.1 起的既定行为）。
因此 JS->Python 验证必须在 load_html（about:blank）文档上进行，
本地资源验证（file://）放在最后一步。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from qtwebview2 import QtWebViewWidget
from wryview import PageLoadEvent

HERE = Path(__file__).resolve().parent

PASSED: list[str] = []
FAILED: list[str] = []

# 注意：以 load_html 载入时 document URL 为 about:blank，IPC 可送达。
LOADED_HTML = (
    "<html><head><title>C1-demo</title></head>"
    "<body><h1 id='h'>Hello WebView2</h1><p id='res'>(未调用)</p></body></html>"
)


def report(name: str, ok: bool, detail: str = "") -> None:
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name} {detail}")
    (PASSED if ok else FAILED).append(name)


def python_hello(msg: str) -> str:
    print(f"  [JS→Python] 收到调用 python_hello({msg!r})")
    return f"hello from python: {msg}"


def python_add(a: int, b: int) -> int:
    return a + b


class Demo(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("C1 WebView2 可行性验证")
        self.resize(900, 650)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.status = QLabel("初始化 WebView ...")
        self.status.setStyleSheet(
            "padding:4px; background:#eef2f7; border-bottom:1px solid #c8d3e0;"
        )
        lay.addWidget(self.status)

        self.web = QtWebViewWidget(
            parent=self,
            js_apis={"python_hello": python_hello, "python_add": python_add},
            background_color="#ffffff",
            context_menus=False,
            url="about:blank",
        )
        lay.addWidget(self.web)

        self.bridge = self.web.bridge
        self.bridge.initialization_done.connect(self._on_init_done)
        self.bridge.page_loaded.connect(self._on_page_loaded)
        self.bridge.web_message_received.connect(self._on_web_message)

        self._raw_msg_seen = False

    # ── 事件 ────────────────────────────────────────────────────────────
    def _on_init_done(self) -> None:
        print("[初始化] WebView 创建完成，开始验证 1：HTML 加载")
        self.status.setText("验证 1/4：HTML 加载")
        self.web.load_html(LOADED_HTML)
        QTimer.singleShot(1500, self._check_html_loaded)

    def _on_page_loaded(self, evt: PageLoadEvent, url: str) -> None:
        print(f"[page_loaded] {evt} url={url}")

    def _on_web_message(self, msg: str) -> None:
        self._raw_msg_seen = True
        print(f"[web_message_received] {msg[:120]}")

    # ── 验证 1：HTML 加载 ────────────────────────────────────────────────
    def _check_html_loaded(self) -> None:
        def cb(r: str) -> None:
            title = json.loads(r)
            report("1. HTML 加载", title == "C1-demo", f"title={title!r}")
            self._start_py_to_js()

        self.web.eval_js("document.title", cb)

    # ── 验证 2：Python -> JS ────────────────────────────────────────────
    def _start_py_to_js(self) -> None:
        print("[验证 2] Python -> JS")
        self.status.setText("验证 2/4：Python -> JS")
        self.web.eval_js("document.getElementById('h').style.color = '#d43'")

        def cb(r: str) -> None:
            val = json.loads(r)
            # 浏览器把 #d43 规范化为 rgb(221, 68, 51)
            ok = val in ("#d43", "rgb(221, 68, 51)")
            report("2. Python -> JS", ok, f"h1.color={val!r}")
            self._start_js_to_py()

        self.web.eval_js("document.getElementById('h').style.color", cb)

    # ── 验证 3：JS -> Python（在 about:blank 文档上，IPC 可达）──────────
    def _start_js_to_py(self) -> None:
        print("[验证 3] JS -> Python")
        self.status.setText("验证 3/4：JS -> Python 桥")
        self.web.eval_js(
            "window.qtwebview.api.python_add(20, 22)"
            ".then(r => { document.getElementById('res').textContent = 'sum=' + r; })"
        )
        QTimer.singleShot(900, self._check_bridge_return)

    def _check_bridge_return(self) -> None:
        self.web.eval_js(
            "document.getElementById('res').textContent", self._on_sum_checked
        )

    def _on_sum_checked(self, r: str) -> None:
        val = json.loads(r)
        report("3a. JS -> Python (bridge 返回值)", val == "sum=42", f"res.text={val!r}")

        self.web.eval_js(
            "window.qtwebview.api.python_hello('c1-probe')"
            ".then(r => window.ipc.postMessage(JSON.stringify({type:'c1', result:r})))"
        )
        QTimer.singleShot(900, self._check_raw_message)

    def _check_raw_message(self) -> None:
        report(
            "3b. JS -> Python (raw web_message_received)",
            self._raw_msg_seen,
            "已收到页面 postMessage" if self._raw_msg_seen else "未收到",
        )
        self._start_local_resource()

    # ── 验证 4：本地资源（file:// 相对路径，放最后）──────────────────────
    def _start_local_resource(self) -> None:
        print("[验证 4] 本地资源加载 file://")
        self.status.setText("验证 4/4：本地资源加载")
        self.web.load_url((HERE / "page.html").as_uri())
        QTimer.singleShot(1800, self._check_local_resource)

    def _check_local_resource(self) -> None:
        self.web.eval_js(
            "document.getElementById('pic').naturalWidth", self._on_pic_checked
        )

    def _on_pic_checked(self, r: str) -> None:
        try:
            w = json.loads(r)
            ok = w > 0
        except Exception:
            ok = False
            w = r
        report("4. 本地资源加载", ok, f"img.naturalWidth={w}")
        self._finish()

    # ── 汇总 ─────────────────────────────────────────────────────────────
    def _finish(self) -> None:
        print("\n========== C1 验证结果（1-4 项） ==========")
        print(f"PASS {len(PASSED)}: {PASSED}")
        if FAILED:
            print(f"FAIL {len(FAILED)}: {FAILED}")
        print("==========================================")
        self.status.setText(
            f"验证完成：PASS {len(PASSED)} / FAIL {len(FAILED)}（第 5 项 PDF 见 pdf_check.py）"
        )
        if "--auto-close" in sys.argv:
            QApplication.instance().quit()


def main() -> None:
    app = QApplication(sys.argv)
    d = Demo()
    d.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
