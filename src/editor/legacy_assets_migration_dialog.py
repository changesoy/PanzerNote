# -*- coding: utf-8 -*-
"""旧 `assets/` 目录迁移预演确认对话框（分支① 1.5，D8 已决）。

展示完整变更清单（移动 / 改名 / 重写文档 / 跳过），**只读**——用户确认后由
调用方执行迁移。不做撤销（D8 已决）：保底机制 + 预演清单已覆盖安全需求。
"""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .legacy_assets_migration_service import LegacyAssetsPlan

_HEADERS = ("图片文件", "所在目录", "目标", "状态")


class LegacyAssetsMigrationDialog(QDialog):
    """预演清单确认。`exec()` 返回 Accepted 即用户确认执行。"""

    def __init__(self, plan: LegacyAssetsPlan, parent=None):
        super().__init__(parent)
        self._plan = plan
        self.setWindowTitle("迁移旧图片目录")
        self.setMinimumSize(820, 520)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self._summary_text(), self))

        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack, 1)

        self._stack.addWidget(self._build_table_page())
        blocked_page = self._build_blocked_page()
        if blocked_page is not None:
            self._stack.addWidget(blocked_page)

        switch_row = QHBoxLayout()
        self._switch_btn = QPushButton("被跳过的图片", self)
        self._switch_btn.setVisible(self._stack.count() > 1)
        self._switch_btn.clicked.connect(self._toggle_page)
        switch_row.addStretch(1)
        switch_row.addWidget(self._switch_btn)
        layout.addLayout(switch_row)

        buttons = QDialogButtonBox(self)
        run_btn = buttons.addButton("执行迁移", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        if run_btn is not None:
            run_btn.setEnabled(bool(plan.items))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ---------- 页面 ----------

    def _build_table_page(self) -> QWidget:
        page = QWidget(self)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        table = QTableWidget(len(self._plan.items), len(_HEADERS), page)
        table.setHorizontalHeaderLabels(list(_HEADERS))
        vertical = table.verticalHeader()
        if vertical is not None:
            vertical.setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

        header = table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        for row, item in enumerate(self._plan.items):
            renamed = "，改名避开同名" if item.renamed_from else ""
            status = (
                f"被 {len(item.referencing_docs)} 篇文档引用{renamed}"
                if item.referenced
                else "未被引用，一并迁入" + renamed
            )
            table.setItem(row, 0, QTableWidgetItem(os.path.basename(item.source_abs)))
            table.setItem(
                row, 1, QTableWidgetItem(os.path.basename(os.path.dirname(item.source_abs)))
            )
            table.setItem(
                row, 2, QTableWidgetItem(os.path.basename(item.dest_abs))
            )
            table.setItem(row, 3, QTableWidgetItem(status))
        page_layout.addWidget(table)
        return page

    def _build_blocked_page(self) -> Optional[QWidget]:
        blocked = self._plan.blocked_images
        if not blocked:
            return None
        page = QWidget(self)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(
            QLabel("以下图片仅被「打开且未保存」的文档引用，本次跳过（防断链）：", page)
        )
        view = QTextBrowser(page)
        view.setPlainText("\n".join(blocked))
        page_layout.addWidget(view)
        return page

    def _toggle_page(self) -> None:
        next_index = (self._stack.currentIndex() + 1) % self._stack.count()
        self._stack.setCurrentIndex(next_index)

    # ---------- 文案 ----------

    def _summary_text(self) -> str:
        plan = self._plan
        referenced = sum(1 for i in plan.items if i.referenced)
        lines = [
            f"找到 {len(plan.legacy_dirs)} 个旧 assets 目录、{len(plan.items)} 张图片"
            f"（其中 {referenced} 张被引用）。",
            f"将重写 {len(plan.rewrite_docs)} 篇文档中的引用；未保存的打开文档不会被改动。",
            "迁移采用「复制 → 校验 → 删除源」保底，任一步失败源文件保持原样。",
        ]
        if plan.renamed_count:
            lines.append(f"有 {plan.renamed_count} 张图片因目标同名不同内容而改名。")
        return "\n".join(lines)
