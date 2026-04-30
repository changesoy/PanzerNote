# -*- coding: utf-8 -*-
"""
状态栏组件
显示光标位置、字符数、编码、文件类型
"""

from PyQt5.QtWidgets import QStatusBar, QLabel, QFrame, QHBoxLayout, QWidget
from PyQt5.QtCore import Qt


class StatusBarWidget(QStatusBar):
    """状态栏"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI"""
        # 设置样式
        self.setStyleSheet("""
            QStatusBar {
                background-color: #f0f0f0;
                border-top: 1px solid #ddd;
            }
            QStatusBar::item {
                border: none;
            }
            QLabel {
                padding: 2px 8px;
                color: #333;
            }
        """)
        
        # 创建分隔符样式
        separator_style = """
            QFrame {
                background-color: #ccc;
                max-width: 1px;
                margin: 3px 0px;
            }
        """
        
        # 左侧容器
        left_widget = QWidget()
        left_layout = QHBoxLayout(left_widget)
        left_layout.setContentsMargins(5, 0, 5, 0)
        left_layout.setSpacing(0)
        
        # 行列位置
        self.position_label = QLabel("行 1, 列 1")
        self.position_label.setMinimumWidth(100)
        left_layout.addWidget(self.position_label)
        
        # 分隔符
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet(separator_style)
        left_layout.addWidget(sep1)
        
        # 字符数
        self.char_count_label = QLabel("0 个字符")
        self.char_count_label.setMinimumWidth(80)
        left_layout.addWidget(self.char_count_label)
        
        self.addWidget(left_widget)
        
        # 添加弹簧占位
        self.addWidget(QLabel(""), 1)
        
        # 右侧：编码
        self.encoding_label = QLabel("UTF-8")
        self.encoding_label.setMinimumWidth(60)
        self.encoding_label.setAlignment(Qt.AlignCenter)
        self.addPermanentWidget(self.encoding_label)
        
        # 分隔符
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet(separator_style)
        self.addPermanentWidget(sep2)
        
        # 右侧：文件类型
        self.file_type_label = QLabel("纯文本")
        self.file_type_label.setMinimumWidth(70)
        self.file_type_label.setAlignment(Qt.AlignCenter)
        self.addPermanentWidget(self.file_type_label)
    
    def update_stats(self, char_count: int, line: int, column: int, 
                     encoding: str = "UTF-8", file_type: str = "纯文本"):
        """更新统计信息
        
        Args:
            char_count: 字符数
            line: 当前行号
            column: 当前列号
            encoding: 编码方式
            file_type: 文件类型
        """
        self.position_label.setText(f"行 {line}, 列 {column}")
        self.char_count_label.setText(f"{char_count} 个字符")
        self.encoding_label.setText(encoding.upper())
        self.file_type_label.setText(file_type)
    
    def set_encoding(self, encoding: str):
        """设置编码显示"""
        self.encoding_label.setText(encoding.upper())
    
    def set_file_type(self, file_type: str):
        """设置文件类型显示"""
        self.file_type_label.setText(file_type)
