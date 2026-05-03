# -*- coding: utf-8 -*-
"""
快捷键提示面板

可通过 Ctrl+/ 调出，清晰展示所有可用快捷键及其对应功能。
支持按功能模块分类展示，支持搜索过滤。
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QTreeWidget, QTreeWidgetItem,
    QPushButton, QFrame, QSizePolicy, QHeaderView,
    QDialog, QKeySequenceEdit
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QKeySequence

from ..utils.dpi_helper import scale, scale_stylesheet


class ShortcutEditDialog(QDialog):
    """快捷键编辑对话框"""

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
        current_label.setStyleSheet("color: #666;")
        layout.addWidget(current_label)

        self._key_edit = QKeySequenceEdit()
        if current_shortcut:
            self._key_edit.setKeySequence(QKeySequence(current_shortcut))
        layout.addWidget(self._key_edit)

        hint = QLabel("按下新的快捷键组合，然后点击确认")
        hint.setStyleSheet("color: #999; font-size: 11px;")
        layout.addWidget(hint)

        self._conflict_label = QLabel("")
        self._conflict_label.setStyleSheet("color: #e53935; font-size: 11px;")
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


class ShortcutPanel(QWidget):
    """快捷键提示面板

    可通过 Ctrl+/ 调出，展示所有可用快捷键。
    支持按功能模块分类展示和搜索过滤。
    """

    def __init__(self, shortcut_manager, parent=None):
        super().__init__(parent)
        self._manager = shortcut_manager
        self._edit_callback = None
        self._init_ui()

    def set_edit_callback(self, callback):
        """设置快捷键编辑回调

        Args:
            callback: 回调函数 (action_id: str, new_shortcut: str) -> None
        """
        self._edit_callback = callback

    def _init_ui(self):
        self.setWindowTitle("快捷键提示")
        self.setMinimumSize(scale(500), scale(400))
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            scale(12), scale(12), scale(12), scale(12)
        )
        layout.setSpacing(scale(8))

        header_layout = QHBoxLayout()

        title = QLabel("快捷键列表")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        header_layout.addWidget(title)

        header_layout.addStretch()

        hint = QLabel("Ctrl+/ 打开/关闭此面板")
        hint.setStyleSheet("color: #999; font-size: 11px;")
        header_layout.addWidget(hint)

        layout.addLayout(header_layout)

        search_layout = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索快捷键或功能名称...")
        self._search_input.textChanged.connect(self._on_search)
        self._search_input.setMinimumHeight(scale(32))
        search_layout.addWidget(self._search_input)
        layout.addLayout(search_layout)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["功能", "快捷键"])
        self._tree.setAlternatingRowColors(True)
        self._tree.setIndentation(scale(20))
        self._tree.setAnimated(True)

        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)

        self._tree.setStyleSheet(scale_stylesheet("""
            QTreeWidget {
                font-family: "Microsoft YaHei";
                font-size: 13px;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QTreeWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #f0f0f0;
            }
            QTreeWidget::item:hover {
                background-color: #e3f2fd;
            }
            QTreeWidget::item:selected {
                background-color: #bbdefb;
            }
        """))

        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._tree)

        footer = QLabel("双击快捷键项可自定义 | 灰色项为系统级快捷键")
        footer.setStyleSheet("color: #999; font-size: 11px;")
        layout.addWidget(footer)

        self._populate_tree()

    def _populate_tree(self, filter_text: str = ""):
        """填充快捷键树

        Args:
            filter_text: 搜索过滤文本
        """
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
            category_item.setData(0, Qt.UserRole, "__category__")

            for action_id, info in items.items():
                if filter_lower:
                    if (filter_lower not in info["name"].lower() and
                            filter_lower not in info["shortcut"].lower()):
                        continue

                item = QTreeWidgetItem(category_item, [
                    info["name"],
                    info["shortcut"] or "无"
                ])
                item.setData(0, Qt.UserRole, action_id)

                shortcut_text = info["shortcut"]
                if shortcut_text:
                    from ..core.shortcut_manager import _SYSTEM_SHORTCUTS
                    normalized = self._manager._normalize_key(shortcut_text)
                    if normalized in _SYSTEM_SHORTCUTS:
                        item.setForeground(1, Qt.gray)

    def _on_search(self, text: str):
        """搜索过滤"""
        self._populate_tree(text)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """双击编辑快捷键"""
        action_id = item.data(0, Qt.UserRole)
        if not action_id or action_id == "__category__":
            return

        name = item.text(0)
        current_shortcut = self._manager.get_shortcut(action_id) or ""

        dialog = ShortcutEditDialog(action_id, name, current_shortcut, self)
        if dialog.exec_() == QDialog.Accepted:
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
        """刷新面板内容"""
        self._populate_tree(self._search_input.text())
