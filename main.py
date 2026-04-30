#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PanzerNote - 战车少女主题记事本
主程序入口
"""

import sys
import os

# 获取程序所在目录
if getattr(sys, 'frozen', False):
    # 打包后的exe
    APP_DIR = os.path.dirname(sys.executable)
else:
    # 开发环境
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

# 确保能够导入src模块
sys.path.insert(0, APP_DIR)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIcon

from src.main_window import MainWindow
from src.core.config import Config
from src.ui.first_run_dialog import FirstRunDialog


def main():
    """程序主入口"""
    # 启用高DPI支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setApplicationName("PanzerNote")
    app.setApplicationVersion("1.6.2")
    
    # 设置默认字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    
    # 设置应用图标
    icon_path = os.path.join(APP_DIR, "data", "assets", "icons", "app_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # 尝试从程序目录加载配置
    config = Config(APP_DIR)
    
    # 检查是否首次运行
    if not config.is_initialized():
        dialog = FirstRunDialog(APP_DIR)
        if dialog.exec_() != dialog.Accepted:
            sys.exit(0)
        selected_path = dialog.get_selected_path()
        config.set_base_path(selected_path)
        config.set_initialized(True)
        config.save()
    
    # 确保所有目录存在
    config.ensure_directories()
    
    # 创建主窗口
    window = MainWindow(config)
    window.show()
    
    # 运行应用
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
