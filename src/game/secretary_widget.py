# -*- coding: utf-8 -*-
"""
小秘书组件
显示战车娘立绘和台词气泡

v1.6.2 改动：
  - 位置跟随逻辑重构：监听父容器 resize 和 move 信号
  - 动态位置计算算法，支持窗口最大化/最小化/多显示器拖动
  - 防抖机制：位置更新响应时间不超过 50ms
  - DPI 缩放适配：所有尺寸使用相对单位

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
"""

import os
import json
import random
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, QEvent, QPoint
from PyQt5.QtGui import QPixmap, QFont, QPainter, QColor

from ..core.config import Config
from ..utils.logger import get_logger
from ..themes.theme_aware_mixin import ThemeAwareMixin


_POSITION_DEBOUNCE_MS = 16
_DEFAULT_SIZE_PERCENT = 7
_MIN_SIZE_PERCENT = 3
_MAX_SIZE_PERCENT = 20
_BASE_ASPECT_RATIO = 210 / 380
_MARGIN_RIGHT = 10
_MARGIN_BOTTOM = 5


class SpeechBubble(QFrame):
    """台词气泡"""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)

        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

        self.hide()

    def apply_theme_colors(self, colors):
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {colors.secretary_bubble_bg};
                border: 2px solid {colors.success};
                border-radius: 12px;
            }}
        """)
        self.label.setStyleSheet(f"""
            QLabel {{
                font-size: 12px;
                color: {colors.text_primary};
                background: transparent;
                border: none;
                line-height: 1.4;
            }}
        """)

    def update_size_constraints(self, widget_width: int):
        """根据小秘书宽度更新气泡尺寸约束"""
        bubble_max_w = max(80, int(widget_width * 0.9))
        bubble_min_w = max(60, int(widget_width * 0.55))
        self.setMaximumWidth(bubble_max_w)
        self.setMinimumWidth(bubble_min_w)
        self.setMinimumHeight(40)

    def show_message(self, text: str, duration: int = 3000):
        """显示消息"""
        self.label.setText(text)
        self.adjustSize()
        self.show()

        if duration > 0:
            self.hide_timer.start(duration)


class SecretaryWidget(ThemeAwareMixin, QWidget):
    """小秘书部件 - 固定在父容器右下角

    位置跟随逻辑：
      1. 监听父容器的 Resize 和 Move 事件
      2. 使用防抖定时器（16ms ≈ 1帧@60fps）避免高频更新
      3. 动态计算右下角位置，确保不超出父容器边界
      4. 支持窗口最大化/最小化/多显示器拖动
    """

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

    def __init__(self, config: Config, theme_engine=None, parent=None):
        super().__init__(parent)
        self.config = config
        self._lines = self.DEFAULT_LINES.copy()
        self._parent_widget = parent
        self._position_dirty = False
        self._last_position = QPoint()
        self._size_percent = self.config.get_secretary_setting(
            "size_percent", _DEFAULT_SIZE_PERCENT
        )

        self._load_lines_config()

        self._position_timer = QTimer(self)
        self._position_timer.setSingleShot(True)
        self._position_timer.setInterval(_POSITION_DEBOUNCE_MS)
        self._position_timer.timeout.connect(self._commit_position_update)

        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(120000)
        self._idle_timer.timeout.connect(self._on_idle)

        self._init_ui()

        if theme_engine:
            self._init_theme(theme_engine)

        if parent:
            parent.installEventFilter(self)

        QTimer.singleShot(500, self._initial_setup)

    def _apply_theme_colors(self, colors):
        self.bubble.apply_theme_colors(colors)

    def _initial_setup(self):
        """初始设置"""
        self._update_position()
        self.show_event_message("启动")
        self._idle_timer.start()

    def _load_lines_config(self):
        """加载台词配置"""
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 10)
        layout.setSpacing(8)

        layout.addStretch(1)

        self.bubble = SpeechBubble()
        layout.addWidget(self.bubble, 0, Qt.AlignHCenter)

        self.portrait_label = QLabel()
        self.portrait_label.setAlignment(Qt.AlignCenter)
        self.portrait_label.setCursor(Qt.PointingHandCursor)

        self._load_portrait()

        layout.addWidget(self.portrait_label, 0, Qt.AlignBottom | Qt.AlignHCenter)

        self.setAttribute(Qt.WA_TranslucentBackground)

        if not self.config.get_secretary_setting("show_secretary", True):
            self.hide()

        self._apply_size()

    def _apply_size(self):
        """根据 size_percent 和父容器尺寸计算并应用小秘书尺寸"""
        if not self._parent_widget:
            self.setFixedSize(210, 380)
            self.bubble.update_size_constraints(210)
            self.portrait_label.setFixedHeight(300)
            return

        parent_area = self._parent_widget.width() * self._parent_widget.height()
        widget_area = parent_area * (self._size_percent / 100.0)

        height = int((widget_area / _BASE_ASPECT_RATIO) ** 0.5)
        width = int(height * _BASE_ASPECT_RATIO)

        width = max(80, width)
        height = max(120, height)

        self.setFixedSize(width, height)
        self.bubble.update_size_constraints(width)

        portrait_h = int(height * 0.75)
        self.portrait_label.setFixedHeight(portrait_h)

        self._load_portrait()
        self._request_position_update()

    def set_size_percent(self, percent: int):
        """设置小秘书尺寸百分比

        Args:
            percent: 占父容器面积的百分比，范围 3~20
        """
        percent = max(_MIN_SIZE_PERCENT, min(_MAX_SIZE_PERCENT, percent))
        if percent == self._size_percent:
            return
        self._size_percent = percent
        self.config.set_secretary_setting("size_percent", percent)
        self._apply_size()

    def get_size_percent(self) -> int:
        """获取当前尺寸百分比"""
        return self._size_percent

    def _get_portrait_path(self) -> str:
        """获取立绘路径"""
        char_id = self.config.get_secretary_setting("character_id")

        if char_id is None:
            return os.path.join(self.config.get_portraits_path(), "secretary.png")

        char_name = self.config.get_secretary_setting("character_name", "")
        skin_name = self.config.get_secretary_setting("skin_name")
        state = self.config.get_secretary_setting("state", "正常")

        portraits_path = self.config.get_portraits_path()

        if skin_name:
            folder = os.path.join(portraits_path, "皮肤", state)
            filename = f"{char_id} {char_name} {skin_name}-{state}.png"
        else:
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
            default_path = self._get_default_portrait_path()
            if os.path.exists(default_path):
                self._set_portrait_pixmap(default_path)
            else:
                self._create_placeholder()

    def _set_portrait_pixmap(self, path: str):
        """设置立绘图片"""
        pixmap = QPixmap(path)
        max_h = self.portrait_label.height() - 10
        max_w = self.width() - 10
        if max_h < 10:
            max_h = 200
        if max_w < 10:
            max_w = 150
        if pixmap.height() > max_h:
            pixmap = pixmap.scaledToHeight(max_h, Qt.SmoothTransformation)
        if pixmap.width() > max_w:
            pixmap = pixmap.scaledToWidth(max_w, Qt.SmoothTransformation)
        self.portrait_label.setPixmap(pixmap)

    def _create_placeholder(self):
        """创建占位图"""
        w = max(80, self.width() - 20)
        h = max(100, self.portrait_label.height() - 20)
        placeholder = QPixmap(w, h)
        placeholder.fill(Qt.transparent)

        painter = QPainter(placeholder)
        painter.setRenderHint(QPainter.Antialiasing)

        bg_color = self._theme_engine.get_active_theme().colors.border if hasattr(self, '_theme_engine') and self._theme_engine else "#E0E0E0"
        text_color = self._theme_engine.get_active_theme().colors.text_secondary if hasattr(self, '_theme_engine') and self._theme_engine else "#757575"
        painter.setBrush(QColor(bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(10, 10, w - 20, h - 20, 10, 10)

        painter.setPen(QColor(text_color))
        font_size = max(8, min(12, w // 10))
        painter.setFont(QFont("Microsoft YaHei", font_size))
        painter.drawText(placeholder.rect(), Qt.AlignCenter, "小秘书\n(待添加立绘)")

        painter.end()

        self.portrait_label.setPixmap(placeholder)

    def _format_line(self, line: str) -> str:
        """格式化台词"""
        nickname = self.config.get_secretary_setting("user_nickname", "指挥官")
        self_name = self.config.get_secretary_setting("secretary_self", "我")

        return line.format(nickname=nickname, self=self_name)

    def _calculate_target_position(self) -> QPoint:
        """动态计算目标位置

        基于父容器尺寸和自身尺寸，计算右下角位置。
        确保不超出父容器边界，处理极端尺寸情况。

        Returns:
            目标位置 QPoint
        """
        if not self._parent_widget:
            return QPoint(0, 0)

        parent_rect = self._parent_widget.rect()
        margin_right = _MARGIN_RIGHT
        margin_bottom = _MARGIN_BOTTOM

        x = parent_rect.width() - self.width() - margin_right
        y = parent_rect.height() - self.height() - margin_bottom

        x = max(0, min(x, parent_rect.width() - self.width()))
        y = max(0, min(y, parent_rect.height() - self.height()))

        return QPoint(x, y)

    def _request_position_update(self):
        """请求位置更新（防抖）

        标记位置为脏，启动防抖定时器。
        多次快速请求只会触发一次实际位置更新。
        """
        self._position_dirty = True
        if not self._position_timer.isActive():
            self._position_timer.start()

    def _commit_position_update(self):
        """提交位置更新

        仅在位置确实需要变化时才调用 move()，
        避免不必要的重绘。
        """
        if not self._position_dirty:
            return

        target = self._calculate_target_position()
        if target != self._last_position:
            self.move(target)
            self._last_position = target

        self._position_dirty = False

    def _update_position(self):
        """立即更新位置（无防抖，用于初始化等场景）"""
        target = self._calculate_target_position()
        self.move(target)
        self._last_position = target
        self._position_dirty = False

    def eventFilter(self, obj, event):
        """事件过滤器 - 监听父容器 resize 和 move 事件"""
        if obj == self._parent_widget:
            if event.type() == QEvent.Resize:
                self._apply_size()
                self._request_position_update()
            elif event.type() == QEvent.Move:
                self._request_position_update()
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

        self._load_portrait()

    def clear_secretary(self):
        """清除小秘书设置，使用默认立绘"""
        self.config.set_secretary_setting("character_id", None)
        self.config.set_secretary_setting("character_name", None)
        self.config.set_secretary_setting("skin_name", None)
        self.config.set_secretary_setting("state", "正常")
        self.config.set_secretary_setting("secretary_self", "我")

        self._load_portrait()

    def set_state(self, state: str):
        """设置状态（正常/大破）"""
        self.config.set_secretary_setting("state", state)
        self._load_portrait()

    def mousePressEvent(self, event):
        """鼠标点击事件"""
        if event.button() == Qt.LeftButton:
            self.show_random_message()
            self._idle_timer.start()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """双击切换小秘书状态（正常/大破）"""
        if event.button() == Qt.LeftButton:
            current_state = self.config.get_secretary_setting("state", "正常")
            new_state = "大破" if current_state == "正常" else "正常"
            self.set_state(new_state)
            state_text = "大破" if new_state == "大破" else "正常"
            self.show_message(f"状态切换为：{state_text}", 2000)
            self._idle_timer.start()
        super().mouseDoubleClickEvent(event)

    def _on_idle(self):
        """闲置时随机显示台词"""
        if self.isVisible():
            self.show_event_message("闲置")
