# -*- coding: utf-8 -*-
"""命令面板 — Ctrl+Shift+P / F1 唤起，搜索并执行快捷键命令"""

from __future__ import annotations

from typing import List, Tuple, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QLabel, QFrame, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QEvent
from PyQt6.QtGui import QFont, QKeyEvent, QColor, QMouseEvent, QKeySequence

from ..utils.dpi_helper import scale
from ..themes.theme_aware_mixin import ThemeAwareMixin
from ..themes.theme_v2.consumer import v2_color, v2_token

# (display_name, shortcut_display, action_id)
CommandEntry = Tuple[str, str, str]


class CommandPalette(ThemeAwareMixin, QDialog):
    """命令面板弹出窗口。

    类似 VS Code Ctrl+Shift+P：输入关键字过滤命令列表，
    回车执行选中命令，Esc / F1 / 快捷键 关闭，可拖动。
    """

    command_triggered = pyqtSignal(str)

    # 上次关闭时的位置（类级记忆）
    _last_known_pos: Optional[QPoint] = None

    def __init__(self, commands: List[CommandEntry], theme_engine, shortcut: str = "",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("CommandPalette 必须传入 theme_engine，不允许为 None")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
        )
        self.setWindowTitle("命令面板")
        self.setMinimumWidth(scale(420))
        self.setMaximumWidth(scale(600))
        self.setMaximumHeight(scale(360))

        self._all_commands = commands
        self._drag_start: Optional[QPoint] = None
        self._close_key = self._parse_close_key(shortcut)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 搜索框 — 兼作拖动手柄
        self._search = QLineEdit()
        self._search.setPlaceholderText("输入命令名称搜索...")
        self._search.setFont(QFont("Microsoft YaHei", 10))
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_filter)
        self._search.installEventFilter(self)
        layout.addWidget(self._search)

        # 命令列表
        self._list = QListWidget()
        self._list.setFont(QFont("Microsoft YaHei", 9))
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.itemActivated.connect(self._on_activated)
        self._list.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self._list)

        # 底部提示
        close_keys = "Esc/F1"
        if self._close_key is not None:
            ks = self._close_key.toString()
            if ks:
                close_keys += f"/{ks}"
        self._hint_label = QLabel(f"↑↓ 导航  Enter 执行  {close_keys} 关闭  拖拽搜索栏移动")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setFont(QFont("Microsoft YaHei", 8))
        layout.addWidget(self._hint_label)

        self._populate()
        self._search.setFocus()

        self._init_theme(theme_engine)

    def _apply_theme_colors(self, colors):
        # B4：命令面板消费 v2 recipe/token（dialog/input recipe），回退 v1。
        # QListWidget 由全局 tree_item recipe 驱动，不在页面内打补丁（B3 契约 8.1）。
        dialog_bg = v2_color(self._theme_engine, "dialog", "background", colors.surface)
        input_bg = v2_color(self._theme_engine, "input", "background", colors.card)
        input_fg = v2_color(self._theme_engine, "input", "text", colors.text_primary)
        border = v2_token(self._theme_engine, "border_muted", colors.border)
        text_secondary = v2_token(self._theme_engine, "text_secondary", colors.text_secondary)

        self.setStyleSheet(f"""
            CommandPalette {{
                background-color: {dialog_bg};
            }}
            QLineEdit {{
                border: none;
                border-bottom: 1px solid {border};
                padding: 8px 12px;
                background: {input_bg};
                color: {input_fg};
                font-size: 13px;
            }}
        """)
        self._hint_label.setStyleSheet(f"color: {text_secondary}; padding: 4px;")
        self._border_color = border

    # --- 快捷键关闭键 ---

    @staticmethod
    def _parse_close_key(shortcut: str) -> Optional[QKeySequence]:
        """将快捷键字符串解析为 QKeySequence。"""
        if not shortcut:
            return None
        return QKeySequence(shortcut)

    # --- 位置记忆 ---

    def hideEvent(self, event):
        """关闭时记录位置。"""
        CommandPalette._last_known_pos = self.pos()
        super().hideEvent(event)

    # --- 拖动 ---

    def _handle_drag_start(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()

    def _handle_drag_move(self, event: QMouseEvent):
        if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_start
            if delta.manhattanLength() > 3:
                self.move(self.pos() + delta)
                self._drag_start = event.globalPosition().toPoint()

    # --- 列表 ---

    def _populate(self, filter_text: str = "") -> None:
        """根据过滤文本重建列表。"""
        self._list.clear()
        low = filter_text.lower().strip()
        for name, shortcut, action_id in self._all_commands:
            if low and low not in name.lower() and low not in shortcut.lower():
                continue
            display = f"{name}"
            if shortcut:
                display = f"{name}  —  {shortcut}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, action_id)
            item.setToolTip(f"快捷键: {shortcut}" if shortcut else "无快捷键")
            self._list.addItem(item)

        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _on_filter(self, text: str) -> None:
        self._populate(text)

    def _on_activated(self, item: QListWidgetItem) -> None:
        action_id = item.data(Qt.ItemDataRole.UserRole)
        if action_id:
            self.command_triggered.emit(action_id)
            self.accept()

    def _should_close(self, event) -> bool:
        """判断键盘事件是否应关闭面板。"""
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_F1):
            return True
        if self._close_key is not None and not self._close_key.isEmpty():
            pressed = QKeySequence(event.keyCombination())
            if pressed == self._close_key:
                return True
        return False

    # --- 键盘 ---

    def eventFilter(self, obj, event):
        """拦截搜索框的键盘/鼠标事件。"""
        if obj is self._search:
            if event.type() == QEvent.Type.MouseButtonPress:
                self._handle_drag_start(event)
                return False
            if event.type() == QEvent.Type.MouseMove:
                self._handle_drag_move(event)
                return False
            if event.type() == QEvent.Type.KeyPress:
                if self._should_close(event):
                    self.reject()
                    return True
                if event.key() == Qt.Key.Key_Down:
                    if self._list.count() > 0:
                        self._list.setFocus()
                        self._list.setCurrentRow(0)
                    return True
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    item = self._list.currentItem()
                    if item:
                        self._on_activated(item)
                    return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: Optional[QKeyEvent]):
        """列表获得焦点时的按键处理。"""
        if event is None:
            return
        if self._should_close(event):
            self.reject()
        elif event.key() == Qt.Key.Key_Up and self._list.currentRow() == 0:
            self._search.setFocus()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        """绘制外边框。"""
        super().paintEvent(event)
        from PyQt6.QtGui import QPainter, QPen
        painter = QPainter(self)
        border_color = self._border_color
        painter.setPen(QPen(QColor(border_color), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()
