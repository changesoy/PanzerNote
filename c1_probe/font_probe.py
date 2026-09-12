# -*- coding: utf-8 -*-
"""临时探针：确认预览代码块的实际渲染字体（WebView2 vs WebEngine）。

回答的问题：`.code-block { font-family: Consolas, "Courier New", monospace }`
在两个后端下究竟解析成了哪个字体。

用法：
  python c1_probe/font_probe.py webview2
  python c1_probe/font_probe.py webengine
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QCoreApplication, Qt  # noqa: E402

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402
from qasync import QEventLoop  # noqa: E402

SAMPLE = "0123456789abcdefghijklmnop"

PAGE = f"""<!doctype html><html><head><meta charset="utf-8">
<style>
body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
        font-size: 14px; }}
.code-block {{ font-family: Consolas, "Courier New", monospace; font-size: 14px;
        line-height: 1.55; white-space: pre; }}
</style></head><body>
<span id="t" class="code-block">{SAMPLE}</span>
</body></html>"""

PROBE_JS = """
(function () {
  var el = document.getElementById('t');
  var c = document.createElement('canvas').getContext('2d');
  function w(spec) { c.font = spec; return c.measureText(%s).width; }
  var refs = {};
  ['Consolas', 'Courier New', 'monospace', 'Microsoft YaHei', 'SimSun',
   'Fixedsys', 'Lucida Console', 'NSimSun'].forEach(function (f) {
    refs[f] = w('14px "' + f + '"');
  });
  return JSON.stringify({
    actual_width: el.getBoundingClientRect().width,
    css_family: getComputedStyle(el).fontFamily,
    available: {
      Consolas: document.fonts.check('14px Consolas'),
      'Courier New': document.fonts.check('14px "Courier New"'),
      Fixedsys: document.fonts.check('14px Fixedsys'),
      SimSun: document.fonts.check('14px SimSun')
    },
    refs: refs
  });
})()
""" % json.dumps(SAMPLE)


def main() -> int:
    backend = sys.argv[1] if len(sys.argv) > 1 else "webview2"
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    def _watchdog() -> None:
        import time as _t

        _t.sleep(60)
        print("[watchdog] 超时", flush=True)
        os._exit(9)

    threading.Thread(target=_watchdog, daemon=True).start()

    host = QWidget()
    host.resize(900, 620)
    host.show()

    async def runner() -> None:
        try:
            if backend == "webview2":
                from src.editor.web_preview_webview2 import WebView2PreviewAdapter

                adapter = WebView2PreviewAdapter(host)
                for _ in range(600):
                    if adapter._ready:
                        break
                    await asyncio.sleep(0.05)
                adapter.set_html(PAGE)
                await asyncio.sleep(2.0)
                raw = await adapter._webview.execute_script_async(PROBE_JS)
            else:
                from PyQt6.QtWebEngineWidgets import QWebEngineView
                from PyQt6.QtCore import QUrl

                view = QWebEngineView(host)
                view.resize(900, 620)
                view.setHtml(PAGE, QUrl("https://local/"))
                await asyncio.sleep(3.0)
                box: dict[str, str] = {}
                view.page().runJavaScript(
                    PROBE_JS, lambda r: box.__setitem__("r", r)
                )
                for _ in range(100):
                    if box:
                        break
                    await asyncio.sleep(0.1)
                raw = box.get("r", "")

            print(f"===== {backend} =====", flush=True)
            print(json.dumps(json.loads(raw), indent=2, ensure_ascii=False), flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] {type(e).__name__}: {e}", flush=True)
        finally:
            app.quit()

    loop.call_soon(lambda: asyncio.ensure_future(runner()))
    with loop:
        loop.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
