"""退出期崩溃的原生栈捕获探针。

faulthandler 在本地崩溃中未输出任何内容，说明故障发生在原生层（或非 Python
线程）。本探针直接安装 Windows vectored 异常处理器，在 ACCESS_VIOLATION
发生时：

1. 打印异常地址所属模块与偏移；
2. 回溯栈帧，逐帧解析到「模块 + 偏移」；
3. 打印崩溃线程 ID。

随后放行异常，让进程按原有方式终止，以便仍能观察退出码。

用法：
    .venv\\Scripts\\python.exe c1_probe\\exit_crash_stack.py
"""
from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE = (REPO_ROOT / "main.py").read_text(encoding="utf-8")

# 保持 main.py 的全局命名空间存活到本模块被终结的时刻。
_APP_NAMESPACE: dict | None = None

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL

EXCEPTION_CONTINUE_SEARCH = 0
EXCEPTION_ACCESS_VIOLATION = 0xC0000005
GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS = 0x00000004
GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT = 0x00000002
MAX_FRAMES = 40
WM_CLOSE = 0x0010
WINDOW_TITLE = "PanzerNote"


class EXCEPTION_RECORD(ctypes.Structure):
    pass


EXCEPTION_RECORD._fields_ = [
    ("ExceptionCode", wintypes.DWORD),
    ("ExceptionFlags", wintypes.DWORD),
    ("ExceptionRecord", ctypes.POINTER(EXCEPTION_RECORD)),
    ("ExceptionAddress", ctypes.c_void_p),
    ("NumberParameters", wintypes.DWORD),
    ("ExceptionInformation", ctypes.c_void_p * 15),
]


class EXCEPTION_POINTERS(ctypes.Structure):
    _fields_ = [
        ("ExceptionRecord", ctypes.POINTER(EXCEPTION_RECORD)),
        ("ContextRecord", ctypes.c_void_p),
    ]


kernel32.AddVectoredExceptionHandler.argtypes = [wintypes.ULONG, ctypes.c_void_p]
kernel32.AddVectoredExceptionHandler.restype = ctypes.c_void_p
ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
ntdll.RtlCaptureStackBackTrace.argtypes = [
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.POINTER(wintypes.DWORD),
]
ntdll.RtlCaptureStackBackTrace.restype = wintypes.USHORT
kernel32.GetModuleHandleExW.argtypes = [
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.POINTER(wintypes.HMODULE),
]
kernel32.GetModuleHandleExW.restype = wintypes.BOOL
kernel32.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
kernel32.GetModuleFileNameW.restype = wintypes.DWORD
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def _resolve(address: int | None) -> str:
    """把地址解析为 `模块名+0x偏移`。"""
    if not address:
        return "<空地址>"

    module = wintypes.HMODULE()
    ok = kernel32.GetModuleHandleExW(
        GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        ctypes.c_void_p(address),
        ctypes.byref(module),
    )
    if not ok or not module.value:
        return f"<未知模块>@0x{address:016X}"

    buffer = ctypes.create_unicode_buffer(1024)
    if not kernel32.GetModuleFileNameW(module, buffer, 1024):
        return f"<模块名读取失败>@0x{address:016X}"

    base = int(module.value)
    name = os.path.basename(buffer.value)
    return f"{name}+0x{address - base:X}"


def _emit(lines: list[str]) -> None:
    payload = ("\n".join(lines) + "\n").encode("utf-8", "replace")
    try:
        os.write(2, payload)
    except OSError:
        pass


def _handler(exception_pointers: ctypes.POINTER(EXCEPTION_POINTERS)) -> int:
    try:
        record = exception_pointers.contents.ExceptionRecord.contents
        code = int(record.ExceptionCode)
        if code != EXCEPTION_ACCESS_VIOLATION:
            return EXCEPTION_CONTINUE_SEARCH

        lines = [
            "",
            "=" * 72,
            f"[stack-probe] ACCESS_VIOLATION 线程={int(kernel32.GetCurrentThreadId())}",
            f"[stack-probe] 故障地址: {_resolve(record.ExceptionAddress)}",
        ]

        frames = (ctypes.c_void_p * MAX_FRAMES)()
        hash_out = wintypes.DWORD()
        count = ntdll.RtlCaptureStackBackTrace(0, MAX_FRAMES, frames, ctypes.byref(hash_out))
        for index in range(int(count)):
            lines.append(f"[stack-probe]   #{index:02d} {_resolve(frames[index])}")

        lines.append("=" * 72)
        _emit(lines)
    except Exception:
        pass

    return EXCEPTION_CONTINUE_SEARCH


_HANDLER_REF = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.POINTER(EXCEPTION_POINTERS))(_handler)


def _close_window_when_ready() -> None:
    deadline = time.monotonic() + 90.0
    while time.monotonic() < deadline:
        hwnd = user32.FindWindowW(None, WINDOW_TITLE)
        if hwnd:
            time.sleep(2.0)
            _emit([f"[stack-probe] 发送 WM_CLOSE 到 hwnd={int(hwnd)}"])
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            return
        time.sleep(0.2)
    _emit(["[stack-probe] 未找到主窗口，放弃"])


def main() -> None:
    global _APP_NAMESPACE

    kernel32.AddVectoredExceptionHandler(1, _HANDLER_REF)
    _emit(["[stack-probe] vectored 异常处理器已安装"])

    threading.Thread(target=_close_window_when_ready, daemon=True).start()

    sys.argv = [str(REPO_ROOT / "main.py")]
    os.chdir(REPO_ROOT)
    sys.path.insert(0, str(REPO_ROOT))

    # 刻意用 exec 并把命名空间保留在模块全局中：
    # 这样 main.py 的全局对象直到本模块被终结时才释放，从而让 Qt 对象回到
    # 「解释器终结期销毁」的路径——即直接运行 main.py 时的崩溃路径。
    # 若改用 runpy，命名空间会在异常展开时提前释放，崩溃不复现。
    _APP_NAMESPACE = {"__name__": "__main__", "__file__": str(REPO_ROOT / "main.py")}
    exec(compile(MAIN_SOURCE, str(REPO_ROOT / "main.py"), "exec"), _APP_NAMESPACE)


if __name__ == "__main__":
    main()
