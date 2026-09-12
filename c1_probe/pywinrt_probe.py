# -*- coding: utf-8 -*-
"""C1.6 探测 4：枚举成员与异步类型形态。"""

from __future__ import annotations

import enum

import webview2.microsoft.web.webview2.core as core

for ename in ("CoreWebView2HostResourceAccessKind", "CoreWebView2PrintOrientation",
              "CoreWebView2PrintStatus", "CoreWebView2PreferredColorScheme"):
    e = getattr(core, ename, None)
    print(f"== {ename}: {e}")
    if e is not None:
        try:
            print("   members:", [(m.name, m.value) for m in e])
        except Exception as ex:
            print("   not iterable:", ex)

print()
print("== IAsyncOperation ==")
try:
    import winrt.windows.foundation as f
    op = f.IAsyncOperation
    print("   type:", op)
    print("   members:", [n for n in dir(op) if not n.startswith("_")])
except Exception as e:
    print("   ERR", e)
