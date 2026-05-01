# -*- coding: utf-8 -*-
"""
小秘书组件
显示战车娘立绘和台词气泡

立绘文件夹架构：
portraits/
├── secretary.png              ← 默认立绘
├── 原始/
│   ├── 正常/
│   │   └── {id} {名字}-正常.png
│   └── 大破/
│       └── {id} {名字}-大破.png
└── 皮肤/
    ├── 正常/
    │   └── {id} {名字} {皮肤名}-正常.png
    └── 大破/
        └── {id} {名字} {皮肤名}-大破.png

文件命名规则：
- 原始正常：{id} {名字}-正常.png        例：059 虎王-正常.png
- 原始大破：{id} {名字}-大破.png        例：059 虎王-大破.png
- 皮肤正常：{id} {名字} {皮肤名}-正常.png  例：059 虎王 冲浪行动-正常.png
- 皮肤大破：{id} {名字} {皮肤名}-大破.png  例：059 虎王 冲浪行动-大破.png
"""

import os
import json
import random
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, QEvent
from PyQt5.QtGui import QPixmap, QFont, QPainter, QColor

from ..core.config import Config
from ..utils.logger import get_logger


class SpeechBubble(QFrame):
    """台词气泡"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 2px solid #4CAF50;
                border-radius: 12px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #333;
                background: transparent;
                border: none;
                line-height: 1.4;
            }
        """)
        layout.addWidget(self.label)
        
        self.setMaximumWidth(200)
        self.setMinimumWidth(120)
        self.setMinimumHeight(60)
        
        # 隐藏定时器
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)
        
        self.hide()
    
    def show_message(self, text: str, duration: int = 3000):
        """显示消息"""
        self.label.setText(text)
        self.adjustSize()
        self.show()
        
        if duration > 0:
            self.hide_timer.start(duration)


class SecretaryWidget(QWidget):
    """小秘书部件 - 固定在父容器右下角"""
    
    # 默认台词
    DEFAULT_LINES = {
        "启动": [
            "{nickname}，早上好！",
            "新的一天开始了，{nickname}~",
            "{self}会一直陪着你的！",
            "欢迎回来，{nickname}！"
        ],
        "保存文件": [
            "文件已保存！",
            "辛苦了，{nickname}~",
            "{self}帮你记录好了！",
            "保存成功！"
        ],
        "建造开始": [
            "建造开始了，请稍等~",
            "{nickname}，{self}期待新伙伴！",
            "开始建造！"
        ],
        "建造完成": [
            "建造完成了！",
            "恭喜{nickname}！",
            "新伙伴来报到啦~"
        ],
        "获得新角色": [
            "恭喜{nickname}解锁新角色！",
            "图鉴又点亮一位呢！"
        ],
        "获得资源": [
            "{nickname}真努力~",
            "资源到账了！",
            "继续加油！"
        ],
        "闲置": [
            "要休息一下吗？",
            "{self}会一直在这里等你的~",
            "记得多喝水哦~",
            "在想什么呢？"
        ],
        "点击": [
            "怎么了？",
            "有什么事吗，{nickname}？",
            "嗯？",
            "需要帮忙吗？",
            "要{self}做什么吗？"
        ],
        "无法撤销": [
            "当前没有可撤销的操作",
            "已经是最初状态了哦~"
        ],
        "欢迎": [
            "还没有打开文件呢",
            "新建一个文件开始写作吧~",
            "{nickname}今天想写些什么？"
        ]
    }
    
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self._lines = self.DEFAULT_LINES.copy()
        self._parent_widget = parent
        
        self._load_lines_config()
        self._init_ui()
        
        # 安装事件过滤器以跟踪父容器大小变化
        if parent:
            parent.installEventFilter(self)
        
        # 延迟显示启动台词和定位
        QTimer.singleShot(500, self._initial_setup)
    
    def _initial_setup(self):
        """初始设置"""
        self._update_position()
        self.show_event_message("启动")
    
    def _load_lines_config(self):
        """加载台词配置"""
        # 从程序目录加载台词配置
        lines_path = os.path.join(
            self.config.get_app_dir(),
            "data", "gamedata", "secretary_lines.json"
        )
        
        if os.path.exists(lines_path):
            try:
                with open(lines_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if "lines" in data:
                        self._lines = data["lines"]
                    if "user_nickname" in data:
                        self.config.set_secretary_setting("user_nickname", data["user_nickname"])
                    if "secretary_self" in data:
                        self.config.set_secretary_setting("secretary_self", data["secretary_self"])
            except Exception:
                get_logger(__name__).warning("加载台词配置失败: %s", lines_path)
    
    def _init_ui(self):
        """初始化UI"""
        self.setFixedSize(210, 380)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 10)
        layout.setSpacing(8)
        
        # 添加弹簧把内容推到底部
        layout.addStretch(1)
        
        # 台词气泡
        self.bubble = SpeechBubble()
        layout.addWidget(self.bubble, 0, Qt.AlignHCenter)
        
        # 立绘显示
        self.portrait_label = QLabel()
        self.portrait_label.setAlignment(Qt.AlignCenter)
        self.portrait_label.setCursor(Qt.PointingHandCursor)
        self.portrait_label.setFixedHeight(300)
        
        # 加载立绘
        self._load_portrait()
        
        layout.addWidget(self.portrait_label, 0, Qt.AlignBottom | Qt.AlignHCenter)
        
        # 设置透明背景
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 根据设置决定是否显示
        if not self.config.get_secretary_setting("show_secretary", True):
            self.hide()
    
    def _get_portrait_path(self) -> str:
        """获取立绘路径
        
        根据配置中的角色ID、名字、皮肤、状态构建路径
        
        Returns:
            立绘文件的完整路径，如果character_id为None则返回默认立绘路径
        """
        char_id = self.config.get_secretary_setting("character_id")
        
        # 如果没有设置角色，返回默认立绘路径
        if char_id is None:
            return os.path.join(self.config.get_portraits_path(), "secretary.png")
        
        char_name = self.config.get_secretary_setting("character_name", "")
        skin_name = self.config.get_secretary_setting("skin_name")
        state = self.config.get_secretary_setting("state", "正常")
        
        portraits_path = self.config.get_portraits_path()
        
        if skin_name:
            # 皮肤立绘：{id} {名字} {皮肤名}-{状态}.png
            folder = os.path.join(portraits_path, "皮肤", state)
            filename = f"{char_id} {char_name} {skin_name}-{state}.png"
        else:
            # 原始立绘：{id} {名字}-{状态}.png
            folder = os.path.join(portraits_path, "原始", state)
            filename = f"{char_id} {char_name}-{state}.png"
        
        return os.path.join(folder, filename)
    
    def _get_default_portrait_path(self) -> str:
        """获取默认立绘路径"""
        return os.path.join(self.config.get_portraits_path(), "secretary.png")
    
    def _load_portrait(self):
        """加载立绘"""
        portrait_path = self._get_portrait_path()
        
        if os.path.exists(portrait_path):
            self._set_portrait_pixmap(portrait_path)
        else:
            # Fallback 到默认立绘
            default_path = self._get_default_portrait_path()
            if os.path.exists(default_path):
                self._set_portrait_pixmap(default_path)
            else:
                # 创建占位图
                self._create_placeholder()
    
    def _set_portrait_pixmap(self, path: str):
        """设置立绘图片"""
        pixmap = QPixmap(path)
        # 自适应缩放，最大高度290px
        if pixmap.height() > 290:
            pixmap = pixmap.scaledToHeight(290, Qt.SmoothTransformation)
        if pixmap.width() > 200:
            pixmap = pixmap.scaledToWidth(200, Qt.SmoothTransformation)
        self.portrait_label.setPixmap(pixmap)
    
    def _create_placeholder(self):
        """创建占位图"""
        placeholder = QPixmap(150, 250)
        placeholder.fill(Qt.transparent)
        
        painter = QPainter(placeholder)
        painter.setRenderHint(QPainter.Antialiasing)
        
        painter.setBrush(QColor("#E0E0E0"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(10, 10, 130, 230, 10, 10)
        
        painter.setPen(QColor("#757575"))
        painter.setFont(QFont("Microsoft YaHei", 10))
        painter.drawText(placeholder.rect(), Qt.AlignCenter, "小秘书\n(待添加立绘)")
        
        painter.end()
        
        self.portrait_label.setPixmap(placeholder)
    
    def _format_line(self, line: str) -> str:
        """格式化台词"""
        nickname = self.config.get_secretary_setting("user_nickname", "指挥官")
        self_name = self.config.get_secretary_setting("secretary_self", "我")
        
        return line.format(nickname=nickname, self=self_name)
    
    def _update_position(self):
        """更新位置到父容器右下角"""
        if self._parent_widget:
            parent_rect = self._parent_widget.rect()
            x = parent_rect.width() - self.width() - 10
            y = parent_rect.height() - self.height() - 5
            self.move(max(0, x), max(0, y))
    
    def eventFilter(self, obj, event):
        """事件过滤器 - 监听父容器大小变化"""
        if obj == self._parent_widget and event.type() == QEvent.Resize:
            self._update_position()
        return super().eventFilter(obj, event)
    
    def show_message(self, text: str, duration: int = 3000):
        """显示消息"""
        self.bubble.show_message(text, duration)
    
    def show_event_message(self, event: str):
        """显示事件相关的台词"""
        lines = self._lines.get(event, self._lines.get("点击", ["..."]))
        line = random.choice(lines)
        formatted = self._format_line(line)
        self.show_message(formatted)
    
    def show_random_message(self):
        """显示随机闲聊台词"""
        self.show_event_message("点击")
    
    def set_secretary(self, char_id: str, char_name: str, 
                      skin_name: str = None, state: str = "正常"):
        """设置小秘书
        
        Args:
            char_id: 角色ID，如 "059"（3位数字）
            char_name: 角色名，如 "虎王"
            skin_name: 皮肤名，如 "冲浪行动"，None表示原始
            state: 状态，"正常" 或 "大破"
        """
        self.config.set_secretary_setting("character_id", char_id)
        self.config.set_secretary_setting("character_name", char_name)
        self.config.set_secretary_setting("skin_name", skin_name)
        self.config.set_secretary_setting("state", state)
        self.config.set_secretary_setting("secretary_self", char_name)
        
        # 重新加载立绘
        self._load_portrait()
    
    def clear_secretary(self):
        """清除小秘书设置，使用默认立绘"""
        self.config.set_secretary_setting("character_id", None)
        self.config.set_secretary_setting("character_name", None)
        self.config.set_secretary_setting("skin_name", None)
        self.config.set_secretary_setting("state", "正常")
        self.config.set_secretary_setting("secretary_self", "我")
        
        # 重新加载立绘
        self._load_portrait()
    
    def set_state(self, state: str):
        """设置状态（正常/大破）"""
        self.config.set_secretary_setting("state", state)
        self._load_portrait()
    
    def mousePressEvent(self, event):
        """鼠标点击事件"""
        if event.button() == Qt.LeftButton:
            self.show_random_message()
        super().mousePressEvent(event)
