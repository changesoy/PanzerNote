#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PanzerNote - 战车少女主题记事本
主程序入口
"""

import sys
import os
import shutil
import traceback
from datetime import datetime

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, APP_DIR)

_original_excepthook = sys.excepthook

# crash log 写入目录：excepthook 在 Config 就绪前就要注册（否则 Config 自身崩溃无日志），
# 那时还不知道 base_path，只能回退到 APP_DIR；Config 就绪后由 _activate_crash_log_dir() 切换。
_crash_log_dir = os.path.join(APP_DIR, "data", "logs")
MAX_CRASH_LOGS = 15


def _crash_excepthook(exc_type, exc_value, exc_tb):
    try:
        os.makedirs(_crash_log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        crash_file = os.path.join(_crash_log_dir, f"crash_{timestamp}.log")
        with open(crash_file, "w", encoding="utf-8") as f:
            f.write(f"PanzerNote Crash Log\n")
            f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Version: {globals().get('__version__', 'unknown')}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"OS: {sys.platform}\n")
            f.write(f"\n{'='*60}\n\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
    except Exception:
        pass
    _original_excepthook(exc_type, exc_value, exc_tb)


sys.excepthook = _crash_excepthook


def _migrate_crash_logs(old_dir, new_dir):
    """把早期 crash log 从 old_dir 迁移到 new_dir（跨盘用 copy+delete，同名跳过）"""
    if not os.path.isdir(old_dir):
        return
    os.makedirs(new_dir, exist_ok=True)
    for name in os.listdir(old_dir):
        if name.startswith("crash_") and name.endswith(".log"):
            src = os.path.join(old_dir, name)
            dst = os.path.join(new_dir, name)
            try:
                if not os.path.exists(dst):
                    shutil.move(src, dst)
            except OSError:
                pass


def _cleanup_crash_logs(log_dir, keep=MAX_CRASH_LOGS):
    """仅保留最近 keep 个 crash log，按文件名时间戳倒序删除旧的"""
    if not os.path.isdir(log_dir):
        return
    logs = [f for f in os.listdir(log_dir) if f.startswith("crash_") and f.endswith(".log")]
    logs.sort(reverse=True)
    for name in logs[keep:]:
        try:
            os.remove(os.path.join(log_dir, name))
        except OSError:
            pass


def _clear_crash_logs(log_dir):
    """正常退出时清空 crash log。

    能走到清理说明本次运行无未捕获异常（异常会由 excepthook 写日志后
    直接终止进程，不会返回主循环），因此残留日志只可能来自历史崩溃，
    应一并清除，避免下次启动误报"上次启动异常退出"。
    """
    if not os.path.isdir(log_dir):
        return
    for name in os.listdir(log_dir):
        if name.startswith("crash_") and name.endswith(".log"):
            try:
                os.remove(os.path.join(log_dir, name))
            except OSError:
                pass


def _activate_crash_log_dir(new_dir):
    """切换 crash log 写入目录到用户数据目录：迁移早期日志、清理过期文件、更新 hook 目标"""
    global _crash_log_dir
    if os.path.normpath(_crash_log_dir) != os.path.normpath(new_dir):
        _migrate_crash_logs(_crash_log_dir, new_dir)
    _cleanup_crash_logs(new_dir)
    _crash_log_dir = new_dir

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon

from src import __version__
from src.core.config import Config
from src.core.app_context import AppContext
from src.ui.first_run_dialog import FirstRunDialog
from src.utils.logger import setup_logging, get_logger
from src.utils.feature_flags import init_flags
from src.utils.lazy_loader import get_startup_profiler
from src.utils.dpi_helper import init_dpi


def _verify_version_consistency(logger):
    try:
        from src.plugins.plugin_base import _app_version
        if _app_version != __version__:
            logger.warning(
                "版本不一致: src.__version__=%s, plugin_base._app_version=%s",
                __version__, _app_version,
            )
    except ImportError:
        logger.debug("plugin_base 未导入，跳过版本一致性检查")

    try:
        from src import get_version_tuple
        ver_tuple = get_version_tuple()
        if len(ver_tuple) != 3:
            logger.warning("版本号格式异常: %s (期望 X.Y.Z)", __version__)
    except Exception as e:
        logger.debug("版本号解析检查跳过: %s", e)


def main():
    profiler = get_startup_profiler()

    # ── 关键：必须在创建 QApplication 之前设置 ──────────────────────────────
    # MainWindow（及其依赖 markdown_preview）是延迟导入的（见下方 PHASE_WINDOW_CREATE），
    # 此时 QApplication 已存在。若不预先设置 AA_ShareOpenGLContexts，
    # markdown_preview 里的 `from PyQt6.QtWebEngineWidgets import QWebEngineView`
    # 会抛 ImportError（"must be set before a QCoreApplication instance is created"），
    # 被 except 静默吞掉 → HAS_WEBENGINE=False → 预览回退到 QTextBrowser，
    # 源码行号同步代码全部失效。设置此属性即可让稍后的 WebEngine 导入成功。
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)
    app.setApplicationName("PanzerNote")
    app.setApplicationVersion(__version__)

    init_dpi()

    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    icon_path = os.path.join(APP_DIR, "data", "assets", "icons", "app_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # 集中管理所有 profiler 阶段名称
    PHASE_CONFIG_INIT = "配置初始化"
    PHASE_LOG_INIT = "日志初始化"
    PHASE_WINDOW_CREATE = "主窗口创建"
    PHASE_WINDOW_SHOW = "窗口显示"

    profiler.begin_phase(PHASE_CONFIG_INIT)
    config = Config(APP_DIR)

    if not config.is_initialized():
        dialog = FirstRunDialog(APP_DIR)
        if dialog.exec() != dialog.DialogCode.Accepted:
            sys.exit(0)
        selected_path = dialog.get_selected_path()
        config.set_base_path(selected_path)
        config.set_initialized(True)
        config.save()

    config.ensure_directories()
    init_flags(os.path.join(config.get_base_path(), "data", "config"))
    profiler.end_phase()

    profiler.begin_phase(PHASE_LOG_INIT)
    log_dir = os.path.join(config.get_base_path(), "data", "logs")
    setup_logging(log_dir=log_dir)
    # crash hook 在 Config 就绪前已注册并写 APP_DIR，此处切换到用户数据目录并迁移早期日志
    _activate_crash_log_dir(log_dir)
    logger = get_logger(__name__)
    logger.info("PanzerNote 启动，版本 %s", __version__)

    _verify_version_consistency(logger)
    profiler.end_phase()

    crash_logs = [f for f in os.listdir(log_dir) if f.startswith("crash_") and f.endswith(".log")]
    if crash_logs:
        latest_crash = sorted(crash_logs)[-1]
        crash_path = os.path.join(log_dir, latest_crash)
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            None, "崩溃日志检测",
            f"检测到上次程序异常退出，崩溃日志位于：\n{crash_path}\n\n是否查看？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            import subprocess
            if sys.platform == 'win32':
                os.startfile(crash_path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', crash_path])
            else:
                subprocess.Popen(['xdg-open', crash_path])

    profiler.begin_phase(PHASE_WINDOW_CREATE)
    from src.main_window import MainWindow
    # 阶段 7：AppContext 承载已拆好的子模块，稳定依赖边界；
    # Config 门面仍在 app_context.config 上保留（过渡期共存）
    app_context = AppContext(
        path_resolver=config.path_resolver,
        settings_store=config.settings_store,
        workspace_store=config.workspace_store,
        config=config,
    )
    window = MainWindow(app_context)
    profiler.end_phase()

    profiler.begin_phase(PHASE_WINDOW_SHOW)
    window.present()
    profiler.end_phase()

    logger.info(profiler.get_report())

    exit_code = app.exec()
    # 正常退出：清空 crash 日志，确保下次启动只对真正的异常退出提示
    _clear_crash_logs(log_dir)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
