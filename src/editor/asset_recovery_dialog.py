# -*- coding: utf-8 -*-
"""图片断链恢复对话框（Markdown 图片工作流 E6c2）。

把 `AssetRecoveryService.plan` 的结果摊平成一份确认清单：可恢复项显示「来源 + 动作」，
证据不足的项显示原因。用户点「开始恢复」才真正动文件；没有任何可恢复项时按钮禁用。

不设自定义配色：整体跟随应用级 QSS（主题切换时随全局样式重绘）。
"""

from __future__ import annotations

import os

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .asset_recovery_service import (
    RECOVER_COPY,
    RECOVER_MOVE,
    AssetRecoveryItem,
    AssetRecoveryPlan,
)

_ACTION_LABELS = {
    RECOVER_MOVE: "恢复（移动）",
    RECOVER_COPY: "恢复（复制）",
}
_NEEDS_USER_LABEL = "需人工处理"

_HEADERS = ("缺失文件", "恢复来源", "动作 / 说明")


class AssetRecoveryDialog(QDialog):
    """列出缺失图片与恢复方案；确认后由调用方执行恢复。"""

    def __init__(self, plan: AssetRecoveryPlan, parent=None):
        super().__init__(parent)
        self._plan = plan
        self.setWindowTitle("恢复缺失的图片")
        self.setMinimumSize(720, 420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self._summary_text(), self))

        self._table = QTableWidget(len(plan.items), len(_HEADERS), self)
        self._table.setHorizontalHeaderLabels(list(_HEADERS))
        vertical = self._table.verticalHeader()
        if vertical is not None:
            vertical.setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for row, item in enumerate(plan.items):
            self._fill_row(row, item)
        header = self._table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table)

        buttons = QDialogButtonBox(self)
        self._accept_button = buttons.addButton(
            "开始恢复", QDialogButtonBox.ButtonRole.AcceptRole
        )
        buttons.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if self._accept_button is not None:
            self._accept_button.setEnabled(bool(plan.recoverable))

    # ---------- 内容 ----------

    def _summary_text(self) -> str:
        recoverable = len(self._plan.recoverable)
        needs_user = len(self._plan.needs_user)
        parts = [f"共 {len(self._plan.items)} 个图片资源缺失"]
        if recoverable:
            parts.append(f"可恢复 {recoverable} 个")
        if needs_user:
            parts.append(f"需人工处理 {needs_user} 个")
        return (
            "，".join(parts)
            + "。恢复不改动 Markdown，只把图片放回文档期望的位置。"
        )

    def _fill_row(self, row: int, item: AssetRecoveryItem) -> None:
        name_item = QTableWidgetItem(os.path.basename(item.missing_abs))
        name_item.setToolTip(item.missing_abs)
        self._table.setItem(row, 0, name_item)

        source = item.source_abs or "—"
        source_item = QTableWidgetItem(source)
        source_item.setToolTip(source)
        self._table.setItem(row, 1, source_item)

        label = _ACTION_LABELS.get(item.outcome, _NEEDS_USER_LABEL)
        if item.reason:
            label = f"{label}｜{item.reason}"
        self._table.setItem(row, 2, QTableWidgetItem(label))
