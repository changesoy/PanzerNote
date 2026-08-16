# -*- coding: utf-8 -*-
"""
快捷键提示面板

可通过 Ctrl+/ 调出，清晰展示所有可用快捷键及其对应功能。
支持按功能模块分类展示，支持搜索过滤。

v1.6.4 改动：
  - 主题感知：订阅 theme_changed 信号
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QTreeWidget, QTreeWidgetItem,
    QPushButton, QFrame, QSizePolicy, QHeaderView,
    QDialog, QKeySequenceEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence

from ..utils.dpi_helper import scale, scale_stylesheet
from ..themes.theme_aware_mixin import ThemeAwareMixin
from ..themes.theme_v2.consumer import v2_color, v2_style_value, v2_token


class ShortcutEditDialog(ThemeAwareMixin, QDialog):

    shortcut_changed = pyqtSignal(str, str)

    def __init__(self, action_id: str, action_name: str,
                 current_shortcut: str, theme_engine, parent=None):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("ShortcutEditDialog 必须传入 theme_engine，不允许为 None")
        self._action_id = action_id
        self._action_name = action_name

        self.setWindowTitle(f"修改快捷键 - {action_name}")
        self.setMinimumWidth(scale(350))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            scale(16), scale(16), scale(16), scale(16)
        )
        layout.setSpacing(scale(12))

        info_label = QLabel(f"操作：{action_name}")
        info_label.setFont(QFont("Microsoft YaHei", 11))
        layout.addWidget(info_label)

        current_label = QLabel(f"当前快捷键：{current_shortcut or '无'}")
        layout.addWidget(current_label)

        self._key_edit = QKeySequenceEdit()
        if current_shortcut:
            self._key_edit.setKeySequence(QKeySequence(current_shortcut))
        layout.addWidget(self._key_edit)

        hint = QLabel("按下新的快捷键组合，然后点击确认")
        layout.addWidget(hint)

        self._conflict_label = QLabel("")
        self._conflict_label.setWordWrap(True)
        layout.addWidget(self._conflict_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        reset_btn = QPushButton("重置默认")
        reset_btn.clicked.connect(self._on_reset)
        btn_layout.addWidget(reset_btn)

        clear_btn = QPushButton("清除快捷键")
        clear_btn.clicked.connect(self._on_clear)
        btn_layout.addWidget(clear_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("确认")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_confirm)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

        self._new_shortcut = current_shortcut

        self._init_theme(theme_engine)

    def _apply_theme_colors(self, colors):
        # B5：QDialog/QLabel/QPushButton 由全局 QSS（dialog/button recipe）驱动；
        # QKeySequenceEdit 不在全局覆盖清单，消费 input recipe 色值，回退 v1。
        bg = v2_color(self._theme_engine, "input", "background", colors.card)
        text = v2_color(self._theme_engine, "input", "text", colors.text_primary)
        border = v2_color(self._theme_engine, "input", "border", colors.border)
        focus_border = v2_color(self._theme_engine, "input", "focus_border", colors.primary)
        selection = v2_color(self._theme_engine, "input", "selection_bg", colors.primary_light)
        radius = v2_style_value(self._theme_engine, "input", "radius", 4)
        pad = v2_style_value(self._theme_engine, "input", "padding", 6)
        self.setStyleSheet(scale_stylesheet(f"""
        QKeySequenceEdit {{
            background-color: {bg};
            color: {text};
            border: 1px solid {border};
            border-radius: {radius}px;
            padding: {pad}px 8px;
            selection-background-color: {selection};
        }}

        QKeySequenceEdit:focus {{
            border-color: {focus_border};
        }}
        """))

    def _on_reset(self):
        self._key_edit.clear()
        self._new_shortcut = "__reset__"
        self.accept()

    def _on_clear(self):
        self._key_edit.clear()
        self._new_shortcut = ""
        self.accept()

    def _on_confirm(self):
        seq = self._key_edit.keySequence()
        if seq.isEmpty():
            self._new_shortcut = ""
        else:
            self._new_shortcut = seq.toString()
        self.accept()

    def get_new_shortcut(self) -> str:
        return self._new_shortcut

    def get_action_id(self) -> str:
        return self._action_id

    def set_conflict_message(self, message: str):
        self._conflict_label.setText(message)


class ShortcutPanel(ThemeAwareMixin, QWidget):

    def __init__(self, shortcut_manager, theme_engine, parent=None):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("ShortcutPanel 必须传入 theme_engine，不允许为 None")
        self._manager = shortcut_manager
        self._edit_callback = None
        self._init_ui()
        self._init_theme(theme_engine)

    def set_edit_callback(self, callback):
        self._edit_callback = callback

    def _init_ui(self):
        self.setObjectName("ShortcutPanel")
        self.setWindowTitle("快捷键提示")
        self.setMinimumSize(scale(500), scale(400))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            scale(12), scale(12), scale(12), scale(12)
        )
        layout.setSpacing(scale(8))

        header_layout = QHBoxLayout()

        self._title_label = QLabel("快捷键列表")
        self._title_label.setObjectName("ShortcutTitleLabel")
        self._title_label.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        header_layout.addWidget(self._title_label)

        header_layout.addStretch()

        self._hint_label = QLabel("Ctrl+/ 打开/关闭此面板")
        self._hint_label.setObjectName("ShortcutHintLabel")
        header_layout.addWidget(self._hint_label)

        layout.addLayout(header_layout)

        search_layout = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索快捷键或功能名称...")
        self._search_input.textChanged.connect(self._on_search)
        self._search_input.setMinimumHeight(scale(32))
        search_layout.addWidget(self._search_input)
        layout.addLayout(search_layout)

        self._tree = QTreeWidget()
        self._tree.setObjectName("ShortcutTree")
        self._tree.setHeaderLabels(["功能", "快捷键"])
        self._tree.setAlternatingRowColors(True)
        self._tree.setIndentation(scale(20))
        self._tree.setAnimated(True)

        header = self._tree.header()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._tree)

        self._footer_label = QLabel("双击快捷键项可自定义 | 灰色项为系统级快捷键")
        self._footer_label.setObjectName("ShortcutFooterLabel")
        layout.addWidget(self._footer_label)

        self._populate_tree()

    def _apply_theme_colors(self, colors):
        # B5：QWidget 面板背景与 QLabel 消费 v2 token；QLineEdit/QTreeWidget/
        # QScrollBar 由全局 recipe（input/tree_item/scrollbar）驱动。
        # QHeaderView 不在全局覆盖清单，token 化保留。
        panel_bg = v2_token(self._theme_engine, "surface_secondary", colors.dialog_bg)
        surface = v2_token(self._theme_engine, "surface_primary", colors.surface)
        text_primary = v2_token(self._theme_engine, "text_primary", colors.text_primary)
        text_secondary = v2_token(self._theme_engine, "text_secondary", colors.text_secondary)
        border = v2_token(self._theme_engine, "border_muted", colors.border)
        self.setStyleSheet(scale_stylesheet(f"""
        QWidget#ShortcutPanel {{
            background-color: {panel_bg};
            color: {text_primary};
        }}

        QLabel#ShortcutTitleLabel {{
            color: {text_primary};
            background: transparent;
        }}

        QLabel#ShortcutHintLabel,
        QLabel#ShortcutFooterLabel {{
            color: {text_secondary};
            background: transparent;
        }}

        QHeaderView::section {{
            background-color: {surface};
            color: {text_primary};
            border: none;
            border-right: 1px solid {border};
            border-bottom: 1px solid {border};
            padding: 6px 8px;
            font-weight: bold;
        }}
        """))

    def _populate_tree(self, filter_text: str = ""):
        self._tree.clear()
        all_shortcuts = self._manager.get_all_shortcuts()
        filter_lower = filter_text.lower()

        for category in self._manager.get_categories():
            items = all_shortcuts.get(category, {})
            if not items:
                continue

            if filter_lower:
                has_match = False
                for action_id, info in items.items():
                    if (filter_lower in info["name"].lower() or
                            filter_lower in info["shortcut"].lower()):
                        has_match = True
                        break
                if not has_match:
                    continue

            category_item = QTreeWidgetItem(self._tree, [category, ""])
            category_item.setExpanded(True)
            font = category_item.font(0)
            font.setBold(True)
            font.setPointSize(12)
            category_item.setFont(0, font)
            category_item.setData(0, Qt.ItemDataRole.UserRole, "__category__")

            for action_id, info in items.items():
                if filter_lower:
                    if (filter_lower not in info["name"].lower() and
                            filter_lower not in info["shortcut"].lower()):
                        continue

                item = QTreeWidgetItem(category_item, [
                    info["name"],
                    info["shortcut"] or "无"
                ])
                item.setData(0, Qt.ItemDataRole.UserRole, action_id)

                shortcut_text = info["shortcut"]
                if shortcut_text:
                    from ..core.shortcut_manager import _SYSTEM_SHORTCUTS
                    normalized = self._manager._normalize_key(shortcut_text)
                    if normalized in _SYSTEM_SHORTCUTS:
                        item.setForeground(1, Qt.GlobalColor.gray)

    def _on_search(self, text: str):
        self._populate_tree(text)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        action_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not action_id or action_id == "__category__":
            return

        name = item.text(0)
        current_shortcut = self._manager.get_shortcut(action_id) or ""

        dialog = ShortcutEditDialog(action_id, name, current_shortcut, self._theme_engine, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_shortcut = dialog.get_new_shortcut()
            if new_shortcut == "__reset__":
                self._manager.reset_shortcut(action_id)
            else:
                success, conflicts = self._manager.set_shortcut(action_id, new_shortcut)
                if not success and conflicts:
                    conflict_names = ", ".join(c["name"] for c in conflicts)
                    dialog.set_conflict_message(f"快捷键冲突：{conflict_names}")
                    return

            if self._edit_callback:
                self._edit_callback(action_id, new_shortcut)

            self._populate_tree(self._search_input.text())

    def refresh(self):
        self._populate_tree(self._search_input.text())
