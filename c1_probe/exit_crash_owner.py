"""定位「谁把 Qt 控件持有到解释器终结阶段」的探针。

思路：main.py 在退出前会调用 sys.exit(0)。本探针替换 sys.exit，在它被调用的
瞬间（此时 main() 帧仍存活、Python 运行时健康）枚举所有顶层 Qt 控件的引用者，
并按引用者类型分类打印：

- module-dict<模块名>  → 某个模块的全局变量持有（解释器终结时才清空，就是元凶）
- frame<函数名>        → 某个仍在执行的函数栈持有
- cell                → 闭包变量
- instance-dict       → 某个对象的属性持有

若某个控件被 module-dict 持有，则该控件会活到解释器终结阶段，其析构过程经 sip
回调 Python 时运行时已不可用 → ACCESS_VIOLATION。

用法：
    .venv\\Scripts\\python.exe c1_probe\\exit_crash_owner.py
"""
from __future__ import annotations

import ctypes
import gc
import os
import sys
import threading
import time
import types
from ctypes import wintypes
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE = (REPO_ROOT / "main.py").read_text(encoding="utf-8")

_APP_NAMESPACE: dict | None = None

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL

WINDOW_TITLE = "PanzerNote"
WM_CLOSE = 0x0010
MAX_REPORTED_REFERRERS = 12


def _emit(lines: list[str]) -> None:
    try:
        os.write(2, ("\n".join(lines) + "\n").encode("utf-8", "replace"))
    except OSError:
        pass


def _describe(obj: object) -> str:
    if isinstance(obj, types.FrameType):
        return f"frame<{obj.f_code.co_name}> ({obj.f_code.co_filename}:{obj.f_lineno})"
    if isinstance(obj, types.CellType):
        return "cell（闭包变量）"
    if isinstance(obj, dict):
        module_name = obj.get("__name__")
        if isinstance(module_name, str):
            return f"module-dict<{module_name}>"
        if "__qualname__" in obj or "__module__" in obj:
            return "class-dict"
        return "instance-dict"
    if isinstance(obj, type):
        return f"class<{obj.__name__}>"
    if isinstance(obj, (list, tuple, set)):
        return type(obj).__name__
    return f"{type(obj).__module__}.{type(obj).__name__}"


def _dump_owners() -> None:
    from PyQt6.QtWidgets import QApplication

    current_frame = sys._getframe(1)
    main_locals = {id(value) for value in current_frame.f_locals.values()}

    app = QApplication.instance()
    if app is None:
        _emit(["[owner-probe] QApplication 已不存在"])
        return

    widgets = app.topLevelWidgets()
    _emit(
        [
            "",
            "=" * 72,
            f"[owner-probe] 退出时刻顶层控件数={len(widgets)}，"
            f"gc 中全部对象数={len(gc.get_objects())}",
        ]
    )

    for widget in widgets:
        name = widget.objectName() or widget.metaObject().className()
        lines = [f"[owner-probe] 控件 {widget.metaObject().className()} ({name}) 的引用者:"]

        referrers = gc.get_referrers(widget)
        shown = 0
        for referrer in referrers:
            if id(referrer) in main_locals:
                continue
            if isinstance(referrer, list) and len(referrer) > 100_000:
                continue
            lines.append(f"[owner-probe]     - {_describe(referrer)}")
            shown += 1
            if shown >= MAX_REPORTED_REFERRERS:
                lines.append("[owner-probe]     - ...（省略）")
                break

        if shown == 0:
            lines.append("[owner-probe]     （无外部引用者）")
        _emit(lines)

    _emit(["=" * 72])


def _close_window_when_ready() -> None:
    deadline = time.monotonic() + 90.0
    while time.monotonic() < deadline:
        hwnd = user32.FindWindowW(None, WINDOW_TITLE)
        if hwnd:
            time.sleep(2.0)
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            return
        time.sleep(0.2)


def main() -> None:
    global _APP_NAMESPACE

    real_exit = sys.exit

    def exit_with_report(code: object = None) -> None:
        try:
            _dump_owners()
        except Exception as error:  # 诊断失败不能影响原有退出
            _emit([f"[owner-probe] 诊断失败: {error!r}"])
        real_exit(code)

    sys.exit = exit_with_report  # type: ignore[assignment]

    threading.Thread(target=_close_window_when_ready, daemon=True).start()

    sys.argv = [str(REPO_ROOT / "main.py")]
    os.chdir(REPO_ROOT)
    sys.path.insert(0, str(REPO_ROOT))

    _APP_NAMESPACE = {"__name__": "__main__", "__file__": str(REPO_ROOT / "main.py")}
    exec(compile(MAIN_SOURCE, str(REPO_ROOT / "main.py"), "exec"), _APP_NAMESPACE)


if __name__ == "__main__":
    main()
