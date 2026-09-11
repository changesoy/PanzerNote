# -*- coding: utf-8 -*-
"""C1 验证第 5 项：PDF 导出替代管线（Edge headless --print-to-pdf）。

wryview 的 print() 仅打开系统打印对话框，非静默导出；qtwebview2/wryview
均不暴露 CDP Page.printToPDF。候选替代：复用系统 Edge（与 WebView2
Runtime 同源 Chromium）headless 静默导出 PDF，零额外体积，符合 C 北极星。

用法：
  python c1_probe/pdf_check.py [--src path] [--out path]

依赖 msedge.exe（C:\\Program Files (x86)\\Microsoft\\Edge\\Application）。
需在 TRAE 沙箱外运行（headless 会读系统字体被沙箱拦截）。
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

SRC_HTML = """<!doctype html>
<html>
<head><meta charset="utf-8"><style>
  body { font-family: sans-serif; padding: 24px; }
  h1 { color: #1a6fb0; }
  table { border-collapse: collapse; }
  td, th { border: 1px solid #888; padding: 4px 10px; }
  pre { background: #eef2f7; padding: 8px; border-radius: 4px; }
</style></head>
<body>
  <h1>PDF 导出管线测试</h1>
  <p>中文段落：PanzerNote C 路线 PDF 导出验证。</p>
  <table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>
  <pre><code>def hello():
    return "world"</code></pre>
</body>
</html>
"""


def find_edge() -> Path | None:
    for p in EDGE_CANDIDATES:
        if Path(p).exists():
            return Path(p)
    return None


def main() -> int:
    src = HERE / "_pdf_src.html"
    out = HERE / "_pdf_out.pdf"

    edge = find_edge()
    if edge is None:
        print("FAIL 未找到 msedge.exe")
        return 1

    src.write_text(SRC_HTML, encoding="utf-8")
    if out.exists():
        out.unlink()

    print(f"Edge: {edge}")
    print(f"导出: {src} -> {out}")

    cmd = [
        str(edge),
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={out}",
        src.as_uri(),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL 调用 Edge 异常: {e}")
        return 1

    if out.exists() and out.stat().st_size > 0:
        size = out.stat().st_size
        print(f"PASS PDF 导出成功 size={size} bytes")
        return 0

    print(f"FAIL PDF 未生成 rc={proc.returncode}")
    if proc.stderr:
        print("stderr:", proc.stderr[:500])
    return 1


if __name__ == "__main__":
    sys.exit(main())
