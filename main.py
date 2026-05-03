#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PanzerNote - 战车少女主题记事本
主程序入口
"""

import sys
import os

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, APP_DIR)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIcon

from src.core.config import Config
from src.ui.first_run_dialog import FirstRunDialog
from src.utils.logger import setup_logging, get_logger
from src.utils.feature_flags import init_flags
from src.utils.lazy_loader import get_startup_profiler
from src.utils.dpi_helper import init_dpi


def main():
    profiler = get_startup_profiler()

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("PanzerNote")
    app.setApplicationVersion("1.6.4")

    init_dpi()

    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    icon_path = os.path.join(APP_DIR, "data", "assets", "icons", "app_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    profiler.begin_phase("配置初始化")
    config = Config(APP_DIR)

    if not config.is_initialized():
        dialog = FirstRunDialog(APP_DIR)
        if dialog.exec_() != dialog.Accepted:
            sys.exit(0)
        selected_path = dialog.get_selected_path()
        config.set_base_path(selected_path)
        config.set_initialized(True)
        config.save()

    config.ensure_directories()
    init_flags(os.path.join(config.get_base_path(), "data", "config"))
    profiler.end_phase()

    profiler.begin_phase("日志初始化")
    log_dir = os.path.join(config.get_base_path(), "data", "logs")
    setup_logging(log_dir=log_dir)
    logger = get_logger(__name__)
    logger.info("PanzerNote 启动，版本 1.6.4")
    profiler.end_phase()

    profiler.begin_phase("主窗口创建")
    from src.main_window import MainWindow
    window = MainWindow(config)
    profiler.end_phase()

    profiler.begin_phase("窗口显示")
    window.show()
    profiler.end_phase()

    logger.info(profiler.get_report())

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
