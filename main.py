#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PanzerNote - 战车少女主题记事本
主程序入口
"""

import sys
import os
import traceback
from datetime import datetime

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, APP_DIR)

_original_excepthook = sys.excepthook


def _crash_excepthook(exc_type, exc_value, exc_tb):
    try:
        logs_dir = os.path.join(APP_DIR, "data", "logs")
        os.makedirs(logs_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        crash_file = os.path.join(logs_dir, f"crash_{timestamp}.log")
        with open(crash_file, "w", encoding="utf-8") as f:
            f.write(f"PanzerNote Crash Log\n")
            f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Version: {__version__ if '__version__' in dir() else 'unknown'}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"OS: {sys.platform}\n")
            f.write(f"\n{'='*60}\n\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
    except Exception:
        pass
    _original_excepthook(exc_type, exc_value, exc_tb)


sys.excepthook = _crash_excepthook

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon

from src import __version__
from src.core.config import Config
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
    window = MainWindow(config)
    profiler.end_phase()

    profiler.begin_phase(PHASE_WINDOW_SHOW)
    window.show()
    profiler.end_phase()

    logger.info(profiler.get_report())

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
