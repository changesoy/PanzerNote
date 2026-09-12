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
from typing import Optional

from PyQt6 import sip
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame
)
from PyQt6.QtCore import Qt, QTimer, QEvent, QPoint, pyqtSignal
from PyQt6.QtGui import QPixmap, QFont, QPainter, QColor

from ..core.config import Config
from ..utils.logger import get_logger
from ..themes.theme_aware_mixin import ThemeAwareMixin
from ..themes.theme_v2.consumer import v2_token


_POSITION_DEBOUNCE_MS = 16
_DEFAULT_SIZE_PERCENT = 7
_MIN_SIZE_PERCENT = 3
_MAX_SIZE_PERCENT = 20
_BASE_ASPECT_RATIO = 210 / 380
_MARGIN_RIGHT = 10
_MARGIN_BOTTOM = 5

# 气泡内边距（SpeechBubble 布局的 contentsMargins）与 QSS 边框宽度
# （见 apply_theme_colors 的 `border: 2px solid`）—— 两者共同决定文字的可用宽度
_PAD_H = 14
_PAD_V = 12
_PAD_X = 2 * _PAD_H  # 左右内边距之和
_PAD_Y = 2 * _PAD_V  # 上下内边距之和
_BORDER_W = 2
_MIN_BUBBLE_HEIGHT = 40
_DEFAULT_BUBBLE_MIN_W = 60
_DEFAULT_BUBBLE_MAX_W = 200


class SpeechBubble(QFrame):
    """台词气泡

    高度由**文本换行后的行数**决定（见 _fit_to_text），不设上限：气泡挤不下时
    由 SecretaryWidget 把窗口向上撑高，而不是把文字裁掉。
    """

    # 自身被隐藏时发出（定时到期或显式 hide），供小秘书收回窗口高度
    hidden = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_PAD_H, _PAD_V, _PAD_H, _PAD_V)

        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        self._min_w = _DEFAULT_BUBBLE_MIN_W
        self._max_w = _DEFAULT_BUBBLE_MAX_W

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

        self.hide()

    def apply_theme_colors(self, bubble_bg: str, bubble_border: str, text_primary: str):
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bubble_bg};
                border: {_BORDER_W}px solid {bubble_border};
                border-radius: 12px;
            }}
        """)
        self.label.setStyleSheet(f"""
            QLabel {{
                font-size: 12px;
                color: {text_primary};
                background: transparent;
                border: none;
                line-height: 1.4;
            }}
        """)

    def update_size_constraints(self, widget_width: int):
        """根据小秘书宽度更新气泡可用的宽度区间。

        只约束宽度：高度必须由文本行数决定，否则多行台词会被压扁裁切。
        """
        self._max_w = max(80, int(widget_width * 0.9))
        self._min_w = max(60, int(widget_width * 0.55))
        # 宽度区间变了 → 同一段文本的换行行数也变，可见时立即重算
        if not self.isHidden():
            self._fit_to_text()

    def _fit_to_text(self) -> None:
        """按「可用宽度 → 换行行数」显式算出气泡的宽与高。

        QLabel 开 wordWrap 后高度依赖宽度（heightForWidth），而 adjustSize()
        走的是 sizeHint —— 换行文本下两者并不一致：父布局空间不足时气泡会被
        压到最小高度，表现就是第三行起被裁掉。故这里显式定宽 + 按该宽度求高。
        宽度取文本单行宽度并夹在 [_min_w, _max_w]：短语保持紧凑，长句用足宽度。
        """
        chrome_x = _PAD_X + 2 * _BORDER_W
        natural = self.label.fontMetrics().horizontalAdvance(self.label.text())
        label_w = max(1, max(self._min_w, min(self._max_w, natural + chrome_x)) - chrome_x)
        # 显式固定标签宽度：保证实际换行宽度与下面求高所用宽度一致
        self.label.setFixedWidth(label_w)
        self.setFixedWidth(label_w + chrome_x)
        text_h = self.label.heightForWidth(label_w)
        self.setFixedHeight(max(_MIN_BUBBLE_HEIGHT, text_h + _PAD_Y + 2 * _BORDER_W))

    def show_message(self, text: str, duration: int = 3000):
        """显示消息"""
        self.label.setText(text)
        self._fit_to_text()
        self.show()

        if duration > 0:
            self.hide_timer.start(duration)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.hidden.emit()


class SecretaryWidget(ThemeAwareMixin, QWidget):
    """小秘书部件 - 固定在父容器右下角

    位置跟随逻辑：
      1. 监听父容器的 Resize 和 Move 事件
      2. 使用防抖定时器（16ms ≈ 1帧@60fps）避免高频更新
      3. 动态计算右下角位置，确保不超出父容器边界
      4. 支持窗口最大化/最小化/多显示器拖动

    为什么是**独立顶层窗**而不是父容器的子控件：
      Markdown 预览的 WebView2 后端是原生子窗口（HWND），而 Windows 下
      原生子窗口永远绘制在非原生 Qt 控件之上 —— 作为子控件的小秘书会被
      预览整片盖住（QWebEngineView 不是原生窗口，所以此前未暴露）。
      因此本控件以 Qt.Tool 顶层窗形式存在，父窗口作为其 owner：
      悬浮在主窗口之上、不进任务栏、随主窗口最小化。
      代价是它不再随父控件自动显隐/移动，需自行对齐（见 sync_visibility）。
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

    def __init__(self, config: Config, theme_engine, parent=None):
        super().__init__(parent)

        # 独立置顶工具窗（原因见类文档）：父窗口为 owner，不进任务栏。
        # WindowDoesNotAcceptFocus + WA_ShowWithoutActivating：
        # 点击小秘书不应把焦点从编辑器抢走（子控件时代不会发生）。
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.config = config
        self._theme_engine = theme_engine
        self._lines = self.DEFAULT_LINES.copy()
        self._parent_widget = parent
        # owner 窗口在构造时固定（事件过滤器需在父控件之外单独监听它）
        self._owner_window: Optional[QWidget] = parent.window() if parent else None
        self._position_dirty = False
        self._last_position = QPoint()
        # size_percent 算出的基准高度；多行台词期间窗口会临时高于它
        self._base_height = 0
        self._size_percent: int = self.config.get_secretary_setting(
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
        # 气泡隐藏后收回窗口高度（多行台词期间被 _ensure_bubble_room 撑高）
        self.bubble.hidden.connect(self._on_bubble_hidden)

        if theme_engine is None:
            raise RuntimeError("SecretaryWidget 必须传入 theme_engine，不允许为 None")
        self._init_theme(theme_engine)

        if parent:
            parent.installEventFilter(self)
            # 顶层窗移动时父容器自身不移动 → 必须同时监听主窗口
            if self._owner_window is not None and self._owner_window is not parent:
                self._owner_window.installEventFilter(self)

        QTimer.singleShot(500, self._initial_setup)

    def _apply_theme_colors(self):
        # B3：小秘书归记事本侧 UI，主题感知（无 v1 回退，B8：字面量 = v1 light 值）
        self.bubble.apply_theme_colors(
            v2_token(self._theme_engine, "surface_raised", "#FFFFFF"),
            v2_token(self._theme_engine, "border_muted", "#E0E0E0"),
            v2_token(self._theme_engine, "text_primary", "#212121"),
        )

    def _initial_setup(self):
        """初始设置"""
        self.sync_visibility()
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
        layout.addWidget(self.bubble, 0, Qt.AlignmentFlag.AlignHCenter)

        self.portrait_label = QLabel()
        self.portrait_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.portrait_label.setCursor(Qt.CursorShape.PointingHandCursor)

        self._load_portrait()

        layout.addWidget(self.portrait_label, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        if not self.config.get_secretary_setting("show_secretary", True):
            self.hide()

        self._apply_size()

    def _apply_size(self):
        """根据 size_percent 和父容器尺寸计算并应用小秘书尺寸"""
        if not self._parent_alive():
            self.setFixedSize(210, 380)
            self._base_height = 380
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
        self._base_height = height
        self.bubble.update_size_constraints(width)

        portrait_h = int(height * 0.75)
        self.portrait_label.setFixedHeight(portrait_h)

        self._load_portrait()
        # 台词可能正在显示：窗口尺寸变了要按新的可用宽度重新留位
        self._ensure_bubble_room()
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
            pixmap = pixmap.scaledToHeight(max_h, Qt.TransformationMode.SmoothTransformation)
        if pixmap.width() > max_w:
            pixmap = pixmap.scaledToWidth(max_w, Qt.TransformationMode.SmoothTransformation)
        self.portrait_label.setPixmap(pixmap)

    def _create_placeholder(self):
        """创建占位图"""
        w = max(80, self.width() - 20)
        h = max(100, self.portrait_label.height() - 20)
        placeholder = QPixmap(w, h)
        placeholder.fill(Qt.GlobalColor.transparent)

        painter = QPainter(placeholder)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_color = v2_token(self._theme_engine, "border_muted", "#E0E0E0")
        text_color = v2_token(self._theme_engine, "text_secondary", "#757575")
        painter.setBrush(QColor(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(10, 10, w - 20, h - 20, 10, 10)

        painter.setPen(QColor(text_color))
        font_size = max(8, min(12, w // 10))
        painter.setFont(QFont("Microsoft YaHei", font_size))
        painter.drawText(placeholder.rect(), Qt.AlignmentFlag.AlignCenter, "小秘书\n(待添加立绘)")

        painter.end()

        self.portrait_label.setPixmap(placeholder)

    def _format_line(self, line: str) -> str:
        """格式化台词"""
        nickname = self.config.get_secretary_setting("user_nickname", "指挥官")
        self_name = self.config.get_secretary_setting("secretary_self", "我")

        return line.format(nickname=nickname, self=self_name)

    def _calculate_target_position(self) -> QPoint:
        """动态计算目标位置（**全局坐标**，本控件是独立顶层窗）

        基于父容器尺寸和自身尺寸，计算右下角位置。
        确保不超出父容器边界，处理极端尺寸情况。

        Returns:
            目标位置 QPoint。顶层窗的 move() 收全局坐标，
            故此处先把父容器内的相对坐标映射到全局。
        """
        if not self._parent_alive():
            return QPoint(0, 0)

        parent_rect = self._parent_widget.rect()

        x = parent_rect.width() - self.width() - _MARGIN_RIGHT
        y = parent_rect.height() - self.height() - _MARGIN_BOTTOM

        x = max(0, min(x, parent_rect.width() - self.width()))
        y = max(0, min(y, parent_rect.height() - self.height()))

        global_pos: QPoint = self._parent_widget.mapToGlobal(QPoint(x, y))
        return global_pos

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

    def _parent_alive(self) -> bool:
        """父容器是否仍可用。

        控件销毁后其 Python 包装对象会变成悬空引用，
        事件过滤器在窗口销毁期仍可能被调用，需先探活再访问。
        """
        return self._parent_widget is not None and not sip.isdeleted(self._parent_widget)

    def sync_visibility(self) -> None:
        """对齐可见性 —— 独立顶层窗不会随父控件自动显示/隐藏。

        隐藏条件：用户关闭显示（show_secretary=false）、
        父容器已销毁，或父容器当前不可见（切到游戏视图、主窗口尚未显示等）。
        """
        wants = bool(self.config.get_secretary_setting("show_secretary", True))
        if self._parent_widget is None:
            parent_visible = True
        else:
            parent_visible = self._parent_alive() and self._parent_widget.isVisible()
        if wants and parent_visible:
            self._update_position()
            if not self.isVisible():
                self.show()
                self.raise_()
        elif self.isVisible():
            self.hide()

    def eventFilter(self, obj, event):
        """事件过滤器 - 监听父容器与主窗口的 resize / move / 显隐"""
        if obj is self._parent_widget or (
            self._owner_window is not None and obj is self._owner_window
        ):
            et = event.type()
            if et == QEvent.Type.Resize:
                if obj is self._parent_widget:
                    self._apply_size()
                self._request_position_update()
                self.sync_visibility()
            elif et == QEvent.Type.Move:
                self._request_position_update()
            elif et in (QEvent.Type.Show, QEvent.Type.Hide):
                self.sync_visibility()
        return super().eventFilter(obj, event)

    def _ensure_bubble_room(self) -> None:
        """台词撑不下时把窗口向上长高，避免气泡被挤压裁切。

        立绘固定占窗口高度的 75%，窗口尺寸又由 size_percent 定死，留给气泡的
        只有约 25% —— 台词超过两行时气泡只剩几十像素，第三行起会被裁掉。
        这里按布局自身的最小需求补足高度（而不是手算边距与间距：间距是否计入
        由 Qt 对空项的处理决定，手算容易差几像素）。窗口底边不动、高度只增不减，
        气泡隐藏后由 _on_bubble_hidden 收回。
        """
        layout = self.layout()
        if layout is None or self.bubble.isHidden() or not self._parent_alive():
            return
        needed = layout.minimumSize().height()
        if needed <= self.height():
            return
        self.setFixedSize(self.width(), needed)
        self._update_position()

    def _on_bubble_hidden(self) -> None:
        """气泡消失后收回为基准高度（立绘尺寸不变，仍是底边对齐）"""
        # 控件解体时子控件仍会发 hideEvent，此时不能再碰自己的 C++ 对象
        if sip.isdeleted(self):
            return
        if self._base_height <= 0 or self.height() == self._base_height:
            return
        self.setFixedSize(self.width(), self._base_height)
        if self._parent_alive():
            self._update_position()

    def show_message(self, text: str, duration: int = 3000):
        """显示消息"""
        self.bubble.show_message(text, duration)
        self._ensure_bubble_room()

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
                      skin_name: Optional[str] = None, state: str = "正常"):
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
        if event.button() == Qt.MouseButton.LeftButton:
            self.show_random_message()
            self._idle_timer.start()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """双击切换小秘书状态（正常/大破）"""
        if event.button() == Qt.MouseButton.LeftButton:
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
