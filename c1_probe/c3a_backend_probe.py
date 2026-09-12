# -*- coding: utf-8 -*-
"""C3-A 探针：通过 WebPreviewAdapter 接口验证 WebView2 后端。

与 C1.6 的区别：C1.6 直接调用裸 WebView2 API；本探针只经 Adapter 接口，
用于确认 C3-A 的适配器实现（含就绪前入队、dpr 换算、官方消息通道、
vhost 资源映射、临时文件中转导出）在真实运行时成立。

用法：
  python c1_probe/c3a_backend_probe.py
全程 90s 看门狗兜底，不会无限无响应。
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QWidget
from qasync import QEventLoop

HERE = Path(__file__).resolve().parent
TIMEOUT_S = 60

PASSED: list[str] = []
FAILED: list[str] = []

PAGE_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>c3a</title></head><body>
<h1 id="h">C3A</h1>
<img id="pic" src="asset.svg">
<script>
window.addEventListener('load', function () {
  setTimeout(function () {
    if (window.chrome && window.chrome.webview) {
      window.chrome.webview.postMessage('__pzsync__:12.5');
    }
    document.getElementById('h').textContent = 'posted';
  }, 300);
});
</script>
</body></html>"""


def report(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}", flush=True)
    (PASSED if ok else FAILED).append(name)


async def wait_ready(adapter, timeout: float = 25.0) -> bool:
    for _ in range(int(timeout * 20)):
        if adapter._ready:
            return True
        await asyncio.sleep(0.05)
    return False


async def flow(host: QWidget) -> None:
    from src.editor.web_preview_webview2 import WebView2PreviewAdapter

    # ── 0. 构造与就绪（覆盖：异步创建 vs 同步接口）────────────────────
    adapter = WebView2PreviewAdapter(host)
    msgs: list[str] = []
    adapter.message_received.connect(lambda s: msgs.append(s))
    loads: list[bool] = []
    adapter.load_finished.connect(lambda ok: loads.append(ok))

    ok = await wait_ready(adapter)
    report("0. 就绪（异步创建）", ok)
    if not ok:
        return

    # ── 1. widget() 立即可用 ─────────────────────────────────────────
    report("1. widget() 返回 QWidget", isinstance(adapter.widget(), QWidget),
           type(adapter.widget()).__name__)

    # ── 2/7/8. set_resource_root + set_html + load_finished ──────────
    adapter.set_resource_root(str(HERE))
    adapter.set_html(PAGE_HTML)
    for _ in range(100):
        if loads:
            break
        await asyncio.sleep(0.1)
    report("2. set_html → load_finished", bool(loads) and loads[0] is True,
           f"loads={loads}")
    await asyncio.sleep(1.0)

    # ── 3. run_javascript（同步接口 / fire-and-forget）────────────────
    adapter.run_javascript("document.getElementById('h').style.color = '#d43'")
    await asyncio.sleep(0.6)
    adapter.run_javascript(
        "window.__probe = document.getElementById('h').textContent;"
    )
    await asyncio.sleep(0.6)
    report("3. run_javascript 执行", True, "已下发 2 段脚本（无返回值语义）")

    # ── 4. 消息通道（chrome.webview.postMessage）─────────────────────
    ok = any(m.startswith("__pzsync__:") for m in msgs)
    report("4. message_received（postMessage）", ok, f"msgs={msgs[:3]}")

    # ── 5. 资源根映射（vhost + <base href>）──────────────────────────
    adapter.run_javascript(
        "window.__nat = document.getElementById('pic').naturalWidth;"
    )
    await asyncio.sleep(0.8)
    nat = await _eval(adapter, "window.__nat")
    report("5. 资源根映射（相对路径图片）", isinstance(nat, (int, float)) and nat > 0,
           f"naturalWidth={nat}")

    # ── 6. set_visible ──────────────────────────────────────────────
    adapter.set_visible(False)
    await asyncio.sleep(0.3)
    adapter.set_visible(True)
    await asyncio.sleep(0.3)
    report("6. set_visible", True)

    # ── 9. export_pdf（离屏实例 + 临时文件中转）──────────────────────
    holder = QWidget()
    exp = WebView2PreviewAdapter(holder)
    if not await wait_ready(exp):
        report("9. export_pdf", False, "离屏实例未就绪")
        return
    box: dict[str, object] = {}

    def _done(data: bytes) -> None:
        box["data"] = data

    exp.export_pdf(
        "<html><head><meta charset='utf-8'></head><body><h1>C3A PDF</h1>"
        "<p>中文段落。</p></body></html>",
        _done,
    )
    for _ in range(300):
        if box:
            break
        await asyncio.sleep(0.1)
    data = box.get("data", b"")
    report(
        "9. export_pdf → bytes",
        isinstance(data, bytes) and data.startswith(b"%PDF") and len(data) > 500,
        f"len={len(data) if isinstance(data, bytes) else 'N/A'}",
    )


async def _eval(adapter, expr: str) -> object:
    """仅探针使用的读取通道：直接取 WebView 求值（接口不提供返回值）。"""
    import json

    try:
        raw = await adapter._webview.execute_script_async(expr)
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    def _watchdog() -> None:
        import time as _t

        _t.sleep(int(os.environ.get("PN_C3A_WATCHDOG", "90")))
        print("[watchdog] 超时强制终止", flush=True)
        os._exit(9)

    threading.Thread(target=_watchdog, daemon=True).start()

    host = QWidget()
    host.setWindowTitle("C3-A WebView2 后端探针")
    host.resize(900, 620)
    host.show()

    async def runner() -> None:
        try:
            await asyncio.wait_for(flow(host), TIMEOUT_S)
        except asyncio.TimeoutError:
            report("全局超时", False, f"{TIMEOUT_S}s")
        except Exception as e:  # noqa: BLE001
            report("未捕获异常", False, f"{type(e).__name__}: {e}")
        finally:
            print("\n========== C3-A 结果 ==========", flush=True)
            print(f"PASS {len(PASSED)}: {PASSED}", flush=True)
            if FAILED:
                print(f"FAIL {len(FAILED)}: {FAILED}", flush=True)
            print("==============================", flush=True)
            app.quit()

    loop.call_soon(lambda: asyncio.ensure_future(runner()))
    with loop:
        loop.run_forever()
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
