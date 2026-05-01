# -*- coding: utf-8 -*-
"""
资源栏组件
显示四项资源和打字统计
"""

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QFrame
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap

from ..core.config import Config


class ResourceItem(QWidget):
    """单个资源显示项"""
    
    def __init__(self, icon_path: str, name: str, parent=None):
        super().__init__(parent)
        self.name = name
        self._value = 0
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 10, 2)
        layout.setSpacing(5)
        
        # 图标（占位）
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(24, 24)
        self.icon_label.setStyleSheet(f"""
            background-color: {self._get_placeholder_color()};
            border-radius: 4px;
        """)
        # TODO: 加载实际图标
        # if icon_path and os.path.exists(icon_path):
        #     pixmap = QPixmap(icon_path).scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        #     self.icon_label.setPixmap(pixmap)
        layout.addWidget(self.icon_label)
        
        # 数值
        self.value_label = QLabel("0")
        self.value_label.setFont(QFont("Consolas", 11))
        self.value_label.setMinimumWidth(60)
        layout.addWidget(self.value_label)
    
    def _get_placeholder_color(self) -> str:
        """获取占位颜色"""
        colors = {
            "fuel": "#4CAF50",      # 绿色 - 燃料
            "ammo": "#FFC107",      # 金黄色 - 弹药
            "steel": "#9E9E9E",     # 灰色 - 钢材
            "bauxite": "#FF9800"    # 橙色 - 铝材
        }
        return colors.get(self.name, "#666666")
    
    def set_value(self, value: int):
        """设置数值"""
        self._value = value
        # 格式化为千分位
        self.value_label.setText(f"{value:,}")
    
    def get_value(self) -> int:
        """获取数值"""
        return self._value


class ResourceBar(QWidget):
    """资源栏"""
    
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        
        self.setFixedHeight(36)
        self.setStyleSheet("""
            ResourceBar {
                background-color: #f5f5f5;
                border-bottom: 1px solid #ddd;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(5)
        
        # 资源图标路径
        assets_path = config.get_assets_path()
        
        # 四项资源
        self.fuel = ResourceItem(f"{assets_path}/icons/fuel.png", "fuel")
        layout.addWidget(self.fuel)
        
        self.ammo = ResourceItem(f"{assets_path}/icons/ammo.png", "ammo")
        layout.addWidget(self.ammo)
        
        self.steel = ResourceItem(f"{assets_path}/icons/steel.png", "steel")
        layout.addWidget(self.steel)
        
        self.bauxite = ResourceItem(f"{assets_path}/icons/bauxite.png", "bauxite")
        layout.addWidget(self.bauxite)
        
        # 弹簧
        layout.addStretch()
        
        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)
        
        # 文档数和今日打字
        self.docs_label = QLabel("文档:0")
        self.docs_label.setFont(QFont("Microsoft YaHei", 10))
        layout.addWidget(self.docs_label)
        
        layout.addSpacing(15)
        
        self.typing_label = QLabel("今日:0字")
        self.typing_label.setFont(QFont("Microsoft YaHei", 10))
        layout.addWidget(self.typing_label)
        
        # 初始加载数据
        self.refresh()
    
    def refresh(self):
        """刷新资源显示"""
        resources = self.config.get_resources()
        self.fuel.set_value(resources.get("fuel", 0))
        self.ammo.set_value(resources.get("ammo", 0))
        self.steel.set_value(resources.get("steel", 0))
        self.bauxite.set_value(resources.get("bauxite", 0))
    
    def update_typing_stats(self, today_chars: int, total_docs: int):
        """更新打字统计"""
        self.docs_label.setText(f"文档:{total_docs}")
        self.typing_label.setText(f"今日:{today_chars}字")
    
    def add_resources(self, fuel: int = 0, ammo: int = 0, steel: int = 0, bauxite: int = 0):
        """增加资源（带动画效果预留）"""
        if fuel:
            self.config.add_resource("fuel", fuel)
        if ammo:
            self.config.add_resource("ammo", ammo)
        if steel:
            self.config.add_resource("steel", steel)
        if bauxite:
            self.config.add_resource("bauxite", bauxite)
        
        self.refresh()
