# -*- coding: utf-8 -*-
"""
游戏侧边栏组件
包含返回、建造、车库、图鉴按钮
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QToolButton, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont


class GameIconButton(QToolButton):
    """游戏图标按钮"""
    
    def __init__(self, icon_name: str, tooltip: str, color: str = "#666666", parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.tooltip_text = tooltip
        self.color = color
        self._is_current = False
        
        self.setFixedSize(50, 50)
        self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        
        # 创建占位图标
        self._create_placeholder_icon()
        
        self._update_style()
    
    def _create_placeholder_icon(self):
        """创建占位图标"""
        # 创建一个简单的彩色方块作为占位图标
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制圆角矩形
        painter.setBrush(QColor(self.color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(2, 2, 28, 28, 6, 6)
        
        # 绘制文字
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Arial", 12, QFont.Bold))
        
        # 根据图标名称显示不同的字符
        char_map = {
            "back": "←",
            "construction": "建",
            "garage": "库",
            "collection": "鉴"
        }
        char = char_map.get(self.icon_name, "?")
        painter.drawText(pixmap.rect(), Qt.AlignCenter, char)
        
        painter.end()
        
        self.setIcon(QIcon(pixmap))
        self.setIconSize(QSize(32, 32))
    
    def _update_style(self):
        """更新样式"""
        if self._is_current:
            self.setStyleSheet("""
                QToolButton {
                    background-color: #e3f2fd;
                    border: 2px solid #2196F3;
                    border-radius: 8px;
                }
                QToolButton:hover {
                    background-color: #bbdefb;
                }
            """)
        else:
            self.setStyleSheet("""
                QToolButton {
                    background-color: transparent;
                    border: 2px solid transparent;
                    border-radius: 8px;
                }
                QToolButton:hover {
                    background-color: #f0f0f0;
                    border: 2px solid #ddd;
                }
            """)
    
    def set_current(self, is_current: bool):
        """设置是否为当前选中"""
        self._is_current = is_current
        self._update_style()


class GameSidebar(QWidget):
    """游戏侧边栏"""
    
    # 视图切换信号
    view_changed = pyqtSignal(str)  # back / construction / garage / collection
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setStyleSheet("""
            GameSidebar {
                background-color: #fafafa;
                border-right: 1px solid #e0e0e0;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignTop)
        
        # 返回按钮
        self.back_btn = GameIconButton("back", "返回 (Ctrl+Z / Esc)", "#78909C")
        self.back_btn.clicked.connect(lambda: self.view_changed.emit("back"))
        layout.addWidget(self.back_btn, 0, Qt.AlignHCenter)
        
        # 分隔线
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setFrameShadow(QFrame.Sunken)
        line1.setFixedWidth(40)
        layout.addWidget(line1, 0, Qt.AlignHCenter)
        
        # 建造按钮
        self.construction_btn = GameIconButton("construction", "建造 (Ctrl+2)", "#4CAF50")
        self.construction_btn.clicked.connect(lambda: self._on_btn_clicked("construction"))
        layout.addWidget(self.construction_btn, 0, Qt.AlignHCenter)
        
        # 分隔线
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setFrameShadow(QFrame.Sunken)
        line2.setFixedWidth(40)
        layout.addWidget(line2, 0, Qt.AlignHCenter)
        
        # 车库按钮
        self.garage_btn = GameIconButton("garage", "车库 (Ctrl+3)", "#FF9800")
        self.garage_btn.clicked.connect(lambda: self._on_btn_clicked("garage"))
        layout.addWidget(self.garage_btn, 0, Qt.AlignHCenter)
        
        # 分隔线
        line3 = QFrame()
        line3.setFrameShape(QFrame.HLine)
        line3.setFrameShadow(QFrame.Sunken)
        line3.setFixedWidth(40)
        layout.addWidget(line3, 0, Qt.AlignHCenter)
        
        # 图鉴按钮
        self.collection_btn = GameIconButton("collection", "图鉴 (Ctrl+4)", "#9C27B0")
        self.collection_btn.clicked.connect(lambda: self._on_btn_clicked("collection"))
        layout.addWidget(self.collection_btn, 0, Qt.AlignHCenter)
        
        # 弹簧
        layout.addStretch()
        
        # 按钮映射
        self._buttons = {
            "construction": self.construction_btn,
            "garage": self.garage_btn,
            "collection": self.collection_btn
        }
    
    def _on_btn_clicked(self, view: str):
        """按钮点击处理"""
        self.view_changed.emit(view)
    
    def set_current_view(self, view: str):
        """设置当前视图"""
        for name, btn in self._buttons.items():
            btn.set_current(name == view)
