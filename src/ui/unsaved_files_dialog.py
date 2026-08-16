# -*- coding: utf-8 -*-
"""未保存文件确认对话框（3.5.7）

单文件与多文件共用同一对话框类，样式一致（差异仅为列表行数与是否显示「取消」按钮）。
对齐 VS Code Save All / Don't Save：
- 「保存并关闭」：保存所有未保存文件后关闭
- 「不保存并关闭」：丢弃修改后关闭
- 「取消」（可选按钮）/ 叉号 / ESC：取消
"""

from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QVBoxLayout,
)

from ..themes.theme_engine import ThemeEngine
from ..utils.dpi_helper import scale


class UnsavedChoice:
    """对话框选择结果。"""

    SAVE = "save"
    DISCARD = "discard"
    CANCEL = "cancel"


class UnsavedFilesDialog(QDialog):
    """统一「未保存文件确认」对话框（3.5.7）。

    用法：`UnsavedFilesDialog.ask(parent, theme_engine, titles, ...)` 返回
    UnsavedChoice.SAVE / DISCARD / CANCEL。
    """

    def __init__(
        self,
        parent,
        theme_engine: ThemeEngine,
        titles: List[str],
        *,
        show_cancel: bool = False,
        window_title: str = "有未保存的文件",
    ) -> None:
        super().__init__(parent)
        self._theme_engine = theme_engine
        self._titles = list(titles)
        self._choice = UnsavedChoice.CANCEL
        self._cancel_handled = False
        self._init_ui(show_cancel, window_title)

    def _init_ui(self, show_cancel: bool, window_title: str) -> None:
        self.setWindowTitle(window_title)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setMinimumWidth(scale(420))

        layout = QVBoxLayout(self)
        layout.setSpacing(scale(8))
        layout.setContentsMargins(scale(16), scale(16), scale(16), scale(16))

        header = QLabel(f"有 {len(self._titles)} 个文件未保存，是否保存并关闭？")
        layout.addWidget(header)

        self._list = QListWidget()
        for title in self._titles:
            self._list.addItem(title)
        layout.addWidget(self._list, 1)

        buttons = QDialogButtonBox(self)
        save_btn = buttons.addButton("保存并关闭", QDialogButtonBox.ButtonRole.AcceptRole)
        discard_btn = buttons.addButton("不保存并关闭", QDialogButtonBox.ButtonRole.DestructiveRole)
        cancel_btn = None
        if show_cancel:
            cancel_btn = buttons.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(buttons)

        # 显式接线：QDialogButtonBox 的 AcceptRole/DestructiveRole/RejectRole 按钮
        # 不会自动映射到 QDialog 的 accepted/rejected，逐按钮连接 clicked 保证语义确定。
        assert save_btn is not None and discard_btn is not None  # addButton 返回值类型收窄
        save_btn.clicked.connect(self._on_save)
        discard_btn.clicked.connect(self._on_discard)
        if cancel_btn is not None:
            cancel_btn.clicked.connect(self._on_cancel)
        # 叉号 / ESC 触发 QDialog.rejected → 统一走 _on_cancel（内部防重入）
        self.rejected.connect(self._on_cancel)

        # B5：QDialog 背景由全局 dialog recipe 驱动，QListWidget 由全局
        # tree_item recipe 驱动，页面不再打局部样式补丁。

    def choice(self) -> str:
        """返回 UnsavedChoice.SAVE / DISCARD / CANCEL。"""
        return self._choice

    def _on_save(self) -> None:
        self._choice = UnsavedChoice.SAVE
        self.accept()

    def _on_discard(self) -> None:
        self._choice = UnsavedChoice.DISCARD
        self.accept()

    def _on_cancel(self) -> None:
        """取消：叉号 / ESC（QDialog.rejected）或「取消」按钮（clicked）。

        防重入：reject() 会再次发出 rejected 信号，需用标志位拦截。
        """
        if self._cancel_handled:
            return
        self._cancel_handled = True
        self._choice = UnsavedChoice.CANCEL
        self.reject()

    @staticmethod
    def ask(
        parent,
        theme_engine: ThemeEngine,
        titles: List[str],
        *,
        show_cancel: bool = False,
        window_title: str = "有未保存的文件",
    ) -> str:
        """模态询问，返回 UnsavedChoice.SAVE / DISCARD / CANCEL。"""
        dlg = UnsavedFilesDialog(
            parent,
            theme_engine,
            titles,
            show_cancel=show_cancel,
            window_title=window_title,
        )
        dlg.exec()
        return dlg.choice()
