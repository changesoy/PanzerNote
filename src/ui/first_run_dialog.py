# -*- coding: utf-8 -*-
"""
首次运行对话框
用于设置程序安装位置
"""

import os
import shutil
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class FirstRunDialog(QDialog):
    """首次运行对话框"""
    
    def __init__(self, app_dir: str = None, parent=None):
        super().__init__(parent)
        self._app_dir = app_dir or os.path.dirname(os.path.dirname(__file__))
        self._selected_path = ""
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI"""
        self.setWindowTitle("欢迎使用 PanzerNote")
        self.setFixedSize(500, 280)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # 标题
        title_label = QLabel("欢迎使用 PanzerNote！")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 说明文字
        desc_label = QLabel(
            "请选择程序数据保存位置：\n\n"
            "• 程序配置和笔记将保存在此位置\n"
            "• 建议选择非系统盘（如D盘）\n"
            "• 后续可将整个文件夹移动到其他位置"
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # 路径选择
        path_layout = QHBoxLayout()
        
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("选择保存位置...")
        # 默认路径使用程序所在目录
        default_path = self._app_dir
        self.path_edit.setText(default_path)
        self._selected_path = default_path
        path_layout.addWidget(self.path_edit)
        
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_folder)
        browse_btn.setFixedWidth(80)
        path_layout.addWidget(browse_btn)
        
        layout.addLayout(path_layout)
        
        # 添加弹簧
        layout.addStretch()
        
        # 确定按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        confirm_btn = QPushButton("确定并开始")
        confirm_btn.setFixedSize(120, 35)
        confirm_btn.clicked.connect(self._confirm)
        btn_layout.addWidget(confirm_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
    
    def _browse_folder(self):
        """浏览文件夹"""
        folder = QFileDialog.getExistingDirectory(
            self, 
            "选择保存位置",
            self.path_edit.text() or "C:/"
        )
        if folder:
            # 在选择的文件夹下创建PanzerNote子目录
            if not folder.endswith("PanzerNote"):
                folder = os.path.join(folder, "PanzerNote")
            self.path_edit.setText(folder)
            self._selected_path = folder
    
    def _confirm(self):
        """确认选择"""
        path = self.path_edit.text().strip()
        
        if not path:
            QMessageBox.warning(self, "提示", "请选择保存位置")
            return
        
        # 检查路径是否有效
        try:
            # 尝试创建目录
            os.makedirs(path, exist_ok=True)
            
            # 创建子目录结构
            subdirs = [
                "data/config",
                "data/gamedata",
                "data/assets/portraits",
                "data/assets/voices",
                "data/assets/icons",
                "notebooks/日记",
                "notebooks/工作",
                "notebooks/回忆",
                "temp/autosave"
            ]
            for subdir in subdirs:
                os.makedirs(os.path.join(path, subdir), exist_ok=True)
            
            # 如果选择的路径不是程序目录，复制必要的资源文件
            if path != self._app_dir:
                self._copy_assets(path)
            
            self._selected_path = path
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(
                self, 
                "错误", 
                f"无法创建目录：\n{str(e)}\n\n请选择其他位置或检查权限。"
            )
    
    def _copy_assets(self, dest_path: str):
        """复制资源文件到目标路径"""
        src_assets = os.path.join(self._app_dir, "data", "assets")
        dest_assets = os.path.join(dest_path, "data", "assets")
        
        # 复制图标等资源
        if os.path.exists(src_assets):
            for item in os.listdir(src_assets):
                src_item = os.path.join(src_assets, item)
                dest_item = os.path.join(dest_assets, item)
                if os.path.isdir(src_item):
                    if not os.path.exists(dest_item):
                        shutil.copytree(src_item, dest_item)
                else:
                    if not os.path.exists(dest_item):
                        shutil.copy2(src_item, dest_item)
        
        # 复制游戏数据
        src_gamedata = os.path.join(self._app_dir, "data", "gamedata")
        dest_gamedata = os.path.join(dest_path, "data", "gamedata")
        
        if os.path.exists(src_gamedata):
            for item in os.listdir(src_gamedata):
                src_item = os.path.join(src_gamedata, item)
                dest_item = os.path.join(dest_gamedata, item)
                if os.path.isfile(src_item) and not os.path.exists(dest_item):
                    shutil.copy2(src_item, dest_item)
    
    def get_selected_path(self) -> str:
        """获取选择的路径"""
        return self._selected_path
