# -*- coding: utf-8 -*-
"""C1.6 最小验证 2：asyncio await 路径（STA 下允许）。"""

from __future__ import annotations

import asyncio
import ctypes
import time

import webview2.microsoft.web.webview2.core as core

ole32 = ctypes.windll.ole32
print("CoInitialize hr =", ole32.CoInitialize(None))
print("当前线程 apartment: STA（CoInitialize 默认）")


async def main() -> None:
    t0 = time.time()
    print("create_async() -> await ...")
    env = await core.CoreWebView2Environment.create_async()
    print(f"OK 用时 {time.time() - t0:.2f}s  env={env}")

    print("version:", env.get_available_browser_version_string())

    # 验证由异步回调里再次发起异步操作是否可行
    t1 = time.time()
    op = core.CoreWebView2Environment.create_async()
    env2 = await op
    print(f"第二次 create_async 用时 {time.time() - t1:.2f}s  env2={env2}")


print("event loop:", end=" ")
try:
    asyncio.run(main())
    print("\n结论：asyncio await 路径可用")
except Exception as e:
    print(f"\nFAIL: {type(e).__name__}: {e}")
    raise SystemExit(1)
