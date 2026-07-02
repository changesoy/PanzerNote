# -*- coding: utf-8 -*-
"""Markdown 大纲导航面板 — QTreeWidget 展示标题树，点击跳转"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPalette
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QLabel

from src.editor.outline_parser import parse_headings, Heading


class OutlinePanel(QWidget):
    """Markdown 大纲导航面板。

    显示当前文档的标题树，点击标题跳转到对应行。
    仅在 .md /.markdown 文件下显示内容。
    """

    heading_clicked = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._editor = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._rebuild)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel("大纲")
        header_font = QFont()
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(16)
        self._tree.setRootIsDecorated(False)
        self._tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._tree)

        self.setMinimumWidth(140)
        self.setMaximumWidth(300)

    def set_editor(self, editor) -> None:
        """绑定编辑器，开始监听其内容变化。传 None 则清空。"""
        if self._editor is not None:
            try:
                self._editor.textChanged.disconnect(self._on_text_changed)
            except (TypeError, RuntimeError):
                pass

        self._editor = editor
        if editor is not None:
            editor.textChanged.connect(self._on_text_changed)
            self._rebuild()
        else:
            self._tree.clear()

    def _on_text_changed(self) -> None:
        """文本变化时延迟重建（300ms 防抖）。"""
        self._debounce.start()

    def _rebuild(self) -> None:
        """解析当前编辑器文本并重建标题树。"""
        self._tree.clear()
        if self._editor is None:
            return

        try:
            text = self._editor.toPlainText()
        except (RuntimeError, AttributeError):
            return

        headings = parse_headings(text)
        if not headings:
            return

        # 将标题树化为嵌套结构：每个标题挂在最近的上级标题下
        self._build_tree(headings)

    def _build_tree(self, headings: list[Heading]) -> None:
        self._tree.clear()

        font_base = QFont()
        font_base.setPointSize(font_base.pointSize() + 1)

        for level, line_num, title in headings:
            item = QTreeWidgetItem()
            # 纯装饰缩进：缩进量只取决于 heading 层级，不依赖父子关系
            indent = "  " * (level - 1)
            item.setText(0, f"{indent}{title}")
            item.setData(0, Qt.ItemDataRole.UserRole, line_num)
            item.setToolTip(0, f"第 {line_num} 行")

            font = QFont(font_base)
            if level == 1:
                font.setBold(True)
            elif level >= 5:
                font.setPointSize(font.pointSize() - 1)
            item.setFont(0, font)

            self._tree.addTopLevelItem(item)

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        line_num = item.data(0, Qt.ItemDataRole.UserRole)
        if line_num is not None:
            self.heading_clicked.emit(line_num)
