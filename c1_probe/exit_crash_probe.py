"""退出行为自动复现探针。

以子进程方式启动 main.py，等主窗口出现后向它发送 WM_CLOSE，然后读取退出码。
用途：不必人工关窗即可反复测量应用退出行为，用于定位退出期崩溃。

用法：
    .venv\\Scripts\\python.exe c1_probe\\exit_crash_probe.py

退出码约定（探针自身的退出码）：
    0  被测应用退出码为 0
    1  被测应用退出码非 0（真实结果打印在 stdout）
    2  未能找到主窗口（超时）
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL

WINDOW_TITLE = "PanzerNote"
WM_CLOSE = 0x0010

APP_START_TIMEOUT = 60.0
CLOSE_SETTLE_SECONDS = 2.0
APP_EXIT_TIMEOUT = 60.0


def wait_for_window(timeout: float) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hwnd = user32.FindWindowW(None, WINDOW_TITLE)
        if hwnd:
            return int(hwnd)
        time.sleep(0.2)
    return 0


def main() -> int:
    proc = subprocess.Popen([sys.executable, "main.py"], cwd=str(REPO_ROOT))
    try:
        hwnd = wait_for_window(APP_START_TIMEOUT)
        if not hwnd:
            print("[probe] 未找到主窗口，启动超时")
            return 2

        print(f"[probe] 已找到主窗口 hwnd={hwnd}，{CLOSE_SETTLE_SECONDS:.0f}s 后发送 WM_CLOSE")
        time.sleep(CLOSE_SETTLE_SECONDS)
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

        code = proc.wait(timeout=APP_EXIT_TIMEOUT)
        print(f"[probe] 应用退出码 = {code} (0x{code & 0xFFFFFFFF:08X})")
        return 0 if code == 0 else 1
    except subprocess.TimeoutExpired:
        print("[probe] 应用在超时内未退出（疑似挂起）")
        return 2
    finally:
        if proc.poll() is None:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
