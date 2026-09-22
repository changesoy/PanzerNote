# -*- coding: utf-8 -*-
"""清理未使用图片确认对话框（Markdown 图片工作流收尾）。

列表展示孤儿图片（目录分组、显示大小），**默认全部不勾选**——用户显式勾选后点
「移入回收站」才删除（send2trash，可反悔）。删除由调用方执行，本对话框只做选择。
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .orphan_image_service import OrphanImage

_HEADERS = ("", "图片文件", "所在目录", "大小")


class OrphanImageDialog(QDialog):
    """列出未使用的图片；返回勾选的绝对路径列表。"""

    def __init__(self, orphans: list[OrphanImage], parent=None):
        super().__init__(parent)
        self._orphans = orphans
        self.setWindowTitle("清理未使用的图片")
        self.setMinimumSize(760, 460)

        total = sum(o.size for o in orphans)
        total_text = (
            f"{total / (1024 * 1024):.1f} MB" if total >= 1024 * 1024
            else f"{max(1, total // 1024)} KB"
        )
        layout = QVBoxLayout(self)
        summary = (
            f"找到 {len(orphans)} 张未被任何 Markdown 引用的图片（合计 {total_text}）。\n"
            "删除后不可恢复（会先移入回收站）。默认不勾选，请确认后再删除。"
        )
        layout.addWidget(QLabel(summary, self))

        self._table = QTableWidget(len(orphans), len(_HEADERS), self)
        self._table.setHorizontalHeaderLabels(list(_HEADERS))
        vertical = self._table.verticalHeader()
        if vertical is not None:
            vertical.setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

        header = self._table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        for row, orphan in enumerate(orphans):
            self._table.setCellWidget(
                row, 0, self._make_check(row, orphan)
            )
            self._table.setItem(row, 1, QTableWidgetItem(orphan.name))
            self._table.setItem(
                row, 2, QTableWidgetItem(self._relative_dir(orphan.dirname))
            )
            self._table.setItem(row, 3, QTableWidgetItem(orphan.human_size))
        layout.addWidget(self._table)

        buttons = QDialogButtonBox(self)
        delete_btn = buttons.addButton(
            "移入回收站", QDialogButtonBox.ButtonRole.AcceptRole
        )
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        if delete_btn is not None:
            delete_btn.setEnabled(bool(orphans))
        buttons.accepted.connect(self._on_delete)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _make_check(self, row: int, orphan: OrphanImage) -> QCheckBox:
        check = QCheckBox(self)
        check.setChecked(False)
        check.stateChanged.connect(lambda _state, r=row: self._update_count())
        check.setProperty("row", row)
        return check

    def _relative_dir(self, dirname: str) -> str:
        # 目录列只显示「…/PanzerNote_assets」层级：取父级目录名 + assets 名
        parent = os.path.basename(os.path.dirname(dirname))
        return f"{parent or '…'}/{os.path.basename(dirname)}"

    def _update_count(self) -> None:
        pass  # 按钮启用在 _on_delete 计算；无需实时刷新

    def _selected(self) -> list[str]:
        selected: list[str] = []
        for row in range(self._table.rowCount()):
            widget = self._table.cellWidget(row, 0)
            if isinstance(widget, QCheckBox) and widget.isChecked():
                selected.append(self._orphans[row].abs_path)
        return selected

    def _on_delete(self) -> None:
        self._selected_paths = self._selected()
        self.accept()

    def selected_paths(self) -> list[str]:
        return getattr(self, "_selected_paths", [])
