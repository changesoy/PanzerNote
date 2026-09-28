#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线截屏脚本：为 README「截图」一节生成界面图。

运行方式（在仓库根目录）：

    .venv\\Scripts\\python.exe scripts\\make_screenshots.py

- 使用真实 windows 平台构建 MainWindow（不经 main.py，无首跑对话框），
  窗口会短暂出现在屏幕上（约十秒），事件循环用 qasync 驱动——WebView2 预览
  需要真实 HWND，offscreen 平台无法初始化（且缺系统字体，截图全是豆腐块）。
- 输出到 docs/images/*.png；临时数据目录用 tempfile，退出时清理；
  WebView2 用户数据目录同样重定向到临时目录。
- 每张截图独立 try/except：单张失败不影响其余，退出码非 0 提示有失败。
- 截图内容是否正确需人工查看生成的 PNG 确认。

本脚本会改写用户目录下的真实配置吗？不会——Config 以临时目录为 app_dir，
全部读写都落在 tempfile 内，不触碰仓库与用户数据。
"""

import asyncio
import os
import shutil
import sys
import tempfile

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# 不设 offscreen：真实 windows 平台才有系统字体与可用的 WebView2 预览
os.environ.pop("QT_QPA_PLATFORM", None)

OUT_DIR = os.path.join(REPO_ROOT, "docs", "images")

DEMO_MD = """# PanzerNote 演示笔记

一款以《战车少女》为主题的**离线单机记事本**——通过书写获取资源，建造收集角色。

## 高频编辑辅助

- 列表回车自动续写，有序列表序号递增
- [x] 任务勾选：`Ctrl+Alt+T` 在 `[ ]` 与 `[x]` 间切换
- [ ] 表格编辑、行内格式、标题级别一键设置

## 代码块

```python
def greet(name: str) -> str:
    return f"Hello, {name}!"
```

## 表格

| 系统 | 状态 |
| --- | --- |
| 书写资源 | 已上线 |
| 建造 / 图鉴 / 车库 | 规划中 |

> 数学公式与 Mermaid 图表在预览、HTML 与 PDF 导出三处一致渲染。
"""


def log(msg: str) -> None:
    print(msg, flush=True)


async def pump(seconds: float) -> None:
    """qasync 事件循环里 sleep：同时泵 Qt 与 asyncio，给异步后端推进机会。"""
    await asyncio.sleep(seconds)


async def save(window, name: str, results: dict) -> None:
    """屏幕级抓取窗口区域：QWidget.grab() 抓不到 WebView2 的系统合成层，
    窗口真实上屏后用 PIL 按物理像素抓屏才能带出预览内容。
    窗口矩形用 Win32 DWM 扩展边界取（物理像素，不含投影），避免 Qt 逻辑坐标
    与屏幕缩放换算不准。"""
    window.raise_()
    window.activateWindow()
    await pump(0.4)

    import ctypes
    from ctypes import wintypes

    hwnd = int(window.winId())
    # 被最小化（如被用户手动收起）时先还原，否则 DWM 矩形是最小化尺寸 292x50
    if ctypes.windll.user32.IsIconic(hwnd):
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        await pump(0.8)
    rect = wintypes.RECT()
    # DWMWA_EXTENDED_FRAME_BOUNDS=9：可见边界（不含 Win11 隐形缩放边框与投影）
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)
    )
    if rect.right - rect.left < 400 or rect.bottom - rect.top < 300:
        results[name] = False
        log(f"FAIL {name}  窗口矩形异常（疑似最小化/被遮挡）")
        return

    from PIL import ImageGrab

    bbox = (rect.left, rect.top, rect.right, rect.bottom)
    img = ImageGrab.grab(bbox=bbox)
    path = os.path.join(OUT_DIR, name)
    try:
        img.save(path)
        ok = os.path.exists(path) and os.path.getsize(path) > 0
    except Exception:
        ok = False
    results[name] = ok
    log(f"{'OK ' if ok else 'FAIL'} {name}  {img.width}x{img.height}")


async def main_flow(window, results: dict) -> None:
    await pump(6.0)  # 等启动时「每日签到」气泡等临时提示消退
    await pump(1.0)  # 窗口布局沉降

    # 1) 浅色主界面（演示文档 + 预览若可用）
    await save(window, "main_light.png", results)

    # 2) 切深色主题（直接经 manager，触发 F-4 提交回调收尾）
    manager = getattr(window.theme_engine, "theme_manager", None)
    if manager is not None:
        manager.request("default", "dark")
    await pump(5.0)  # 等「已切换主题」气泡消退
    await save(window, "main_dark.png", results)

    # 3) 深色下的命令面板
    window._show_command_palette()
    await pump(0.5)
    await save(window, "command_palette.png", results)
    if window._cmd_palette is not None:
        window._cmd_palette.close()
    await pump(0.3)


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="panzernote_shots_")
    results: dict = {}
    window = None
    try:
        # WebView2 用户数据目录重定向到临时目录（默认落在解释器目录，可能不可写）
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = os.path.join(tmp, "webview2_udf")
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import QApplication
        from qasync import QEventLoop

        app = QApplication(sys.argv)
        app.setApplicationName("PanzerNote")
        app.setFont(QFont("Microsoft YaHei", 10))

        loop = QEventLoop(app)
        asyncio.set_event_loop(loop)

        from src.core.config import Config
        from src.core.app_context import AppContext
        from src.main_window import MainWindow

        cfg = Config(app_dir=tmp)
        cfg.ensure_directories()

        # 镜像真实环境的立绘资源（app_dir 指向临时目录导致默认 secretary.png 缺失，
        # 小秘书会显示「待添加立绘」占位卡）
        src_portraits = os.path.join(REPO_ROOT, "data", "assets", "portraits")
        if os.path.isdir(src_portraits):
            shutil.copytree(
                src_portraits,
                os.path.join(tmp, "data", "assets", "portraits"),
                dirs_exist_ok=True,
            )

        # 演示文档放进数据目录，文件树可见
        ws = os.path.join(tmp, "notes")
        os.makedirs(ws, exist_ok=True)
        demo_path = os.path.join(ws, "演示笔记.md")
        with open(demo_path, "w", encoding="utf-8") as f:
            f.write(DEMO_MD)

        ctx = AppContext(
            path_resolver=cfg.path_resolver,
            settings_store=cfg.settings_store,
            workspace_store=cfg.workspace_store,
            config=cfg,
        )
        window = MainWindow(ctx)
        window.resize(1240, 780)  # 留足任务栏余量，避免窗口底边压到任务栏入镜
        # 截屏期间置顶：activateWindow 抢不过全屏视频/游戏的前台焦点
        from PyQt6.QtCore import Qt

        window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        window.present()

        async def flow():
            await pump(0.5)
            window._open_file(demo_path)
            await pump(3.0)  # 给 WebView2 controller 创建与渲染的时间
            # 只保留演示文档标签，关掉启动时自动新建的空白标签
            window.editor_tabs.close_other_tabs(window.editor_tabs.currentIndex())
            # 把光标移到文档末尾，避免打开时自动补全弹窗入镜
            from PyQt6.QtGui import QTextCursor
            for tabs in [window.editor_tabs, *window.view_coordinator.split_tabs]:
                w = tabs.currentWidget()
                editor = getattr(w, "editor", None)
                if editor is not None:
                    c = editor.textCursor()
                    c.movePosition(QTextCursor.MoveOperation.End)
                    editor.setTextCursor(c)
            await pump(0.5)
            await main_flow(window, results)

        with loop:
            loop.run_until_complete(flow())

    finally:
        if window is not None:
            try:
                window.shutdown_previews()
                window.deleteLater()
            except Exception:
                pass
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [k for k, v in results.items() if not v]
    log(f"完成：{sum(results.values())}/{len(results)} 张，输出目录 {OUT_DIR}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
