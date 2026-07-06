# -*- coding: utf-8 -*-
"""
跨文件搜索结果面板
提供搜索输入栏、选项切换、按文件分组的结果列表。
双击结果项跳转到对应文件的对应行。
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QApplication,
)

from .find_in_files_service import FindInFilesWorker
from ..themes.theme_aware_mixin import ThemeAwareMixin


class FindInFilesPanel(ThemeAwareMixin, QWidget):
    """跨文件搜索面板。

    result_clicked(filepath, line_number) — 用户双击结果时发出。
    """

    result_clicked = pyqtSignal(str, int)

    SCOPE_WORKSPACE = 0
    SCOPE_OPEN = 1
    SCOPE_RECENT = 2

    def __init__(
        self,
        get_workspace_root: Callable[[], str],
        theme_engine,
        get_open_files: Callable[[], list[str]] | None = None,
        get_recent_files: Callable[[], list[str]] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("FindInFilesPanel 必须传入 theme_engine，不允许为 None")
        self._get_workspace_root = get_workspace_root
        self._get_open_files = get_open_files or (lambda: [])
        self._get_recent_files = get_recent_files or (lambda: [])
        self._worker: Optional[FindInFilesWorker] = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._do_search)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # --- 搜索输入栏 ---
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索项目中的文件…")
        self._search_input.textChanged.connect(self._on_query_changed)
        self._search_input.returnPressed.connect(self._do_search_now)
        layout.addWidget(self._search_input)

        # --- 范围选择 ---
        scope_layout = QHBoxLayout()
        self._scope_label = QLabel("范围:")
        self._scope_label.setStyleSheet("font-size: 11px;")
        scope_layout.addWidget(self._scope_label)

        self._scope_combo = QComboBox()
        self._scope_combo.addItem("工作区文件")
        self._scope_combo.addItem("当前打开的文件")
        self._scope_combo.addItem("最近打开的文件")
        self._scope_combo.setCurrentIndex(0)
        self._scope_combo.currentIndexChanged.connect(self._on_scope_changed)
        scope_layout.addWidget(self._scope_combo, 1)
        layout.addLayout(scope_layout)

        # --- 选项行 ---
        opts_layout = QHBoxLayout()

        self._case_cb = QCheckBox("Aa")
        self._case_cb.setToolTip("大小写敏感")
        self._case_cb.stateChanged.connect(self._on_option_changed)
        opts_layout.addWidget(self._case_cb)

        self._word_cb = QCheckBox("W")
        self._word_cb.setToolTip("全词匹配")
        self._word_cb.stateChanged.connect(self._on_option_changed)
        opts_layout.addWidget(self._word_cb)

        self._regex_cb = QCheckBox(".*")
        self._regex_cb.setToolTip("正则表达式")
        self._regex_cb.stateChanged.connect(self._on_option_changed)
        opts_layout.addWidget(self._regex_cb)

        opts_layout.addStretch()

        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setVisible(False)
        self._cancel_btn.clicked.connect(self._cancel_search)
        opts_layout.addWidget(self._cancel_btn)

        layout.addLayout(opts_layout)

        # --- 结果树 ---
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(12)
        self._tree.setRootIsDecorated(True)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.setAnimated(False)
        layout.addWidget(self._tree)

        # --- 状态栏 ---
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._status_label)

        self.setMinimumWidth(180)

        self._init_theme(theme_engine)

    def _apply_theme_colors(self, colors):
        self._scope_label.setStyleSheet(f"font-size: 11px; color: {colors.text_secondary};")
        self._status_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 11px;")

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------

    def _on_query_changed(self) -> None:
        if self._search_input.text():
            self._debounce.start()
        else:
            self._cancel_search()
            self._tree.clear()
            self._status_label.setText("")

    def _on_option_changed(self) -> None:
        if self._search_input.text():
            self._debounce.start()

    def _do_search_now(self) -> None:
        self._debounce.stop()
        self._do_search()

    def _on_scope_changed(self) -> None:
        if self._search_input.text():
            self._debounce.start()

    def _do_search(self) -> None:
        query = self._search_input.text()
        if not query:
            return

        self._cancel_search()
        self._tree.clear()

        scope = self._scope_combo.currentIndex()

        if scope == self.SCOPE_OPEN:
            file_list = self._get_open_files()
            if not file_list:
                self._status_label.setText("没有打开的文件")
                return
            root_dir = self._get_workspace_root()
            self._worker = FindInFilesWorker(
                root_dir, query,
                case_sensitive=self._case_cb.isChecked(),
                whole_word=self._word_cb.isChecked(),
                use_regex=self._regex_cb.isChecked(),
                file_list=file_list,
            )
        elif scope == self.SCOPE_RECENT:
            file_list = self._get_recent_files()
            if not file_list:
                self._status_label.setText("没有最近打开的文件")
                return
            root_dir = self._get_workspace_root()
            self._worker = FindInFilesWorker(
                root_dir, query,
                case_sensitive=self._case_cb.isChecked(),
                whole_word=self._word_cb.isChecked(),
                use_regex=self._regex_cb.isChecked(),
                file_list=file_list,
            )
        else:
            root_dir = self._get_workspace_root()
            if not root_dir or not os.path.exists(root_dir):
                self._status_label.setText("工作区目录不存在")
                return
            self._worker = FindInFilesWorker(
                root_dir, query,
                case_sensitive=self._case_cb.isChecked(),
                whole_word=self._word_cb.isChecked(),
                use_regex=self._regex_cb.isChecked(),
            )

        self._worker.result_found.connect(self._add_result)
        self._worker.search_finished.connect(self._on_search_done)
        self._worker.start()

        self._cancel_btn.setVisible(True)
        self._status_label.setText("搜索中…")

    def _cancel_search(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        self._worker = None
        self._cancel_btn.setVisible(False)

    def _on_search_done(self, total: int) -> None:
        self._cancel_btn.setVisible(False)
        self._worker = None
        if total == 0:
            self._status_label.setText("未找到匹配项")
        else:
            self._status_label.setText(f"找到 {total} 项匹配")

        # 自动展开所有文件节点
        self._tree.expandAll()

    # ------------------------------------------------------------------
    # 结果展示
    # ------------------------------------------------------------------

    def _add_result(self, filepath: str, line_num: int, col: int, line_text: str) -> None:
        # 找到或创建文件分组节点
        file_node = self._find_file_node(filepath)
        if file_node is None:
            file_node = QTreeWidgetItem()
            try:
                display_name = filepath
                root_dir = self._get_workspace_root()
                if root_dir and os.path.commonpath([filepath, root_dir]) == root_dir:
                    display_name = os.path.relpath(filepath, root_dir)
            except (ValueError, TypeError):
                display_name = filepath
            file_node.setText(0, display_name)
            file_node.setData(0, Qt.ItemDataRole.UserRole, filepath)
            file_node.setToolTip(0, filepath)

            font = QFont()
            font.setBold(True)
            file_node.setFont(0, font)

            self._tree.addTopLevelItem(file_node)

        # 添加匹配行
        match_node = QTreeWidgetItem()
        preview = line_text.strip()
        if len(preview) > 120:
            preview = preview[:117] + "..."
        match_node.setText(0, f"L{line_num}:{col}  {preview}")
        match_node.setData(0, Qt.ItemDataRole.UserRole, (filepath, line_num))

        font = QFont("Consolas, Courier New, monospace")
        font.setPointSize(QApplication.font().pointSize() - 1)
        match_node.setFont(0, font)

        file_node.addChild(match_node)

    def _find_file_node(self, filepath: str) -> Optional[QTreeWidgetItem]:
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item is not None and item.data(0, Qt.ItemDataRole.UserRole) == filepath:
                return item
        return None

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, tuple) and len(data) == 2:
            filepath, line_num = data
            self.result_clicked.emit(filepath, line_num)
        elif isinstance(data, str):
            # 点文件节点：折叠/展开即可，不跳转
            pass

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    def focus_search(self) -> None:
        """聚焦搜索输入框。"""
        self._search_input.setFocus()
        self._search_input.selectAll()

    def closeEvent(self, event) -> None:
        self._cancel_search()
        super().closeEvent(event)
