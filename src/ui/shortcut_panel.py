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


class ShortcutEditDialog(ThemeAwareMixin, QDialog):

    shortcut_changed = pyqtSignal(str, str)

    def __init__(self, action_id: str, action_name: str,
                 current_shortcut: str, parent=None):
        super().__init__(parent)
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

        theme_engine = getattr(parent, "_theme_engine", None)
        if theme_engine:
            self._init_theme(theme_engine)

    def _apply_theme_colors(self, colors):
        self.setStyleSheet(scale_stylesheet(f"""
        QDialog {{
            background-color: {colors.dialog_bg};
            color: {colors.text_primary};
        }}

        QLabel {{
            color: {colors.text_primary};
        }}

        QKeySequenceEdit {{
            background-color: {colors.card};
            color: {colors.text_primary};
            border: 1px solid {colors.border};
            border-radius: 4px;
            padding: 6px 8px;
            selection-background-color: {colors.primary_light};
        }}

        QKeySequenceEdit:focus {{
            border-color: {colors.primary};
        }}

        QPushButton {{
            background-color: {colors.primary};
            color: white;
            border: 1px solid {colors.primary_dark};
            border-radius: 4px;
            padding: 6px 14px;
            min-height: 24px;
        }}

        QPushButton:hover {{
            background-color: {colors.primary_dark};
        }}

        QPushButton:pressed {{
            background-color: {colors.primary_dark};
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

    def __init__(self, shortcut_manager, theme_engine=None, parent=None):
        super().__init__(parent)
        self._manager = shortcut_manager
        self._edit_callback = None
        self._init_ui()
        if theme_engine:
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
        self.setStyleSheet(scale_stylesheet(f"""
        QWidget#ShortcutPanel {{
            background-color: {colors.dialog_bg};
            color: {colors.text_primary};
        }}

        QLabel#ShortcutTitleLabel {{
            color: {colors.text_primary};
            background: transparent;
        }}

        QLabel#ShortcutHintLabel,
        QLabel#ShortcutFooterLabel {{
            color: {colors.text_secondary};
            background: transparent;
        }}

        QLineEdit#ShortcutSearchInput {{
            background-color: {colors.card};
            color: {colors.text_primary};
            border: 1px solid {colors.border};
            border-radius: 4px;
            padding: 6px 8px;
            selection-background-color: {colors.primary_light};
        }}

        QLineEdit#ShortcutSearchInput:focus {{
            border-color: {colors.primary};
        }}

        QTreeWidget#ShortcutTree {{
            font-family: "Microsoft YaHei";
            font-size: 13px;
            background-color: {colors.card};
            color: {colors.text_primary};
            border: 1px solid {colors.border};
            border-radius: 4px;
            outline: none;
            alternate-background-color: {colors.surface};
        }}

        QTreeWidget#ShortcutTree::item {{
            color: {colors.text_primary};
            padding: 4px 8px;
            border-bottom: 1px solid {colors.divider};
        }}

        QTreeWidget#ShortcutTree::item:hover {{
            background-color: {colors.surface};
        }}

        QTreeWidget#ShortcutTree::item:selected {{
            background-color: {colors.editor_selection};
            color: {colors.text_primary};
        }}

        QTreeWidget#ShortcutTree::branch {{
            background-color: {colors.card};
        }}

        QHeaderView::section {{
            background-color: {colors.surface};
            color: {colors.text_primary};
            border: none;
            border-right: 1px solid {colors.border};
            border-bottom: 1px solid {colors.border};
            padding: 6px 8px;
            font-weight: bold;
        }}

        QScrollBar:vertical {{
            background-color: {colors.surface};
            width: 12px;
            margin: 0;
        }}

        QScrollBar::handle:vertical {{
            background-color: {colors.border};
            border-radius: 6px;
            min-height: 20px;
            margin: 2px;
        }}

        QScrollBar::handle:vertical:hover {{
            background-color: {colors.text_disabled};
        }}

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        """))

        self._tree.viewport().setStyleSheet(  # type: ignore[union-attr]
            f"background-color: {colors.card}; color: {colors.text_primary};"
        )

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

        dialog = ShortcutEditDialog(action_id, name, current_shortcut, self)
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
