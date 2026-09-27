# -*- coding: utf-8 -*-
"""EditorTabWidget 编辑命令 mixin（从 editor_tabs.py 拆出，纯结构重构不改行为）。

职责：编辑命令代理（撤销/重做/剪贴板/缩放/行操作/大小写/Markdown 表格与
任务列表/格式化/转到行）、插入图片入口、缺失图片恢复（预检 → 对话框 →
执行 → asset_recovery_finished 信号）、书签与折叠状态持久化。

组合契约：本 mixin 由 EditorTabWidget 组合。方法体访问的跨职责状态与
方法在 ``_EditorTabWidgetContract`` 中以**裸 Callable 类型注解**声明——
运行时由 EditorTabWidget（含 TabFileOpsMixin / TabSaveFlowMixin 提供的
文件与保存方法）实际实现；本模块不初始化任何状态。裸注解不产生类属性，
因此无论 MRO 顺序如何都不会遮蔽真实现（对比 def 空体声明，见 E3 踩坑记录）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional, Tuple

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QDialog, QInputDialog, QMessageBox, QTabWidget

from ..utils.logger import get_logger
from .asset_recovery_dialog import AssetRecoveryDialog
from .asset_recovery_service import AssetRecoveryService

if TYPE_CHECKING:
    from ..core.config import Config
    from .editor import Editor


class _EditorTabWidgetContract(QTabWidget):
    """EditorTabWidget 组合 TabEditCommandsMixin 时必须提供的状态与方法。

    继承 QTabWidget 仅为补齐 Qt 基类能力与 pyqtSignal descriptor 的类型约束；
    运行时不实例化、不初始化任何状态。方法一律裸 Callable 注解（见模块 docstring）。
    """

    config: Config

    asset_recovery_finished: pyqtSignal

    current_editor: Callable[..., Optional[Editor]]
    _get_editor_from_widget: Callable[..., Optional[Editor]]
    _is_markdown_file: Callable[..., bool]
    _save_file: Callable[..., Tuple[bool, int]]
    _await_save_settled: Callable[..., bool]
    set_font_all: Callable[..., None]


class TabEditCommandsMixin(_EditorTabWidgetContract):
    """编辑命令职责：命令代理 + 插入图片 + 图片恢复 + 书签/折叠持久化。"""

    def undo(self) -> bool:
        """撤销。行尾切换属文档级元数据（不在 Qt 撤销栈内），可撤销判定须一并看它。"""
        editor = self.current_editor()
        if editor is None:
            return False
        shared_doc = editor.shared_doc
        eol_pending = shared_doc is not None and shared_doc.has_pending_eol_undo()
        doc = editor.document()
        if eol_pending or (doc is not None and doc.isUndoAvailable()):
            editor.undo()
            return True
        return False

    def redo(self):
        editor = self.current_editor()
        if editor:
            editor.redo()

    def cut(self):
        editor = self.current_editor()
        if editor:
            editor.cut()

    def copy(self):
        editor = self.current_editor()
        if editor:
            editor.copy()

    def paste(self):
        editor = self.current_editor()
        if editor:
            editor.paste()

    def select_all(self):
        editor = self.current_editor()
        if editor:
            editor.selectAll()

    def zoom_in(self):
        """放大：字号+1，同步到配置并应用到所有编辑器"""
        current_size = self.config.get_editor_setting("font_size", 12)
        new_size = min(current_size + 1, 48)
        if new_size != current_size:
            self.config.set_editor_setting("font_size", new_size)
            font_family = self.config.get_editor_setting("font_family", "Microsoft YaHei")
            self.set_font_all(font_family, new_size)

    def zoom_out(self):
        """缩小：字号-1，同步到配置并应用到所有编辑器"""
        current_size = self.config.get_editor_setting("font_size", 12)
        new_size = max(current_size - 1, 8)
        if new_size != current_size:
            self.config.set_editor_setting("font_size", new_size)
            font_family = self.config.get_editor_setting("font_family", "Microsoft YaHei")
            self.set_font_all(font_family, new_size)

    def zoom_reset(self):
        """重置缩放：恢复默认字号12"""
        self.config.set_editor_setting("font_size", 12)
        font_family = self.config.get_editor_setting("font_family", "Microsoft YaHei")
        self.set_font_all(font_family, 12)

    # === 行操作代理 ===

    def delete_current_line(self):
        """删除当前行"""
        editor = self.current_editor()
        if editor:
            editor.delete_current_line()

    def copy_line(self):
        """复制当前行到剪贴板"""
        editor = self.current_editor()
        if editor:
            editor.copy_line()

    def paste_line(self):
        """粘贴为新的行"""
        editor = self.current_editor()
        if editor:
            editor.paste_line()

    def move_line_up(self):
        """上移当前行"""
        editor = self.current_editor()
        if editor:
            editor.move_line_up()

    def move_line_down(self):
        """下移当前行"""
        editor = self.current_editor()
        if editor:
            editor.move_line_down()

    # === 插入图片代理 ===

    def insert_image_from_file(self):
        """插入图片：委托当前编辑器写入 PanzerNote_assets/ 并插入相对路径。"""
        editor = self.current_editor()
        if editor:
            editor.insert_image_from_file()

    # === 图片恢复代理（E6c2） ===

    def recover_missing_images(self) -> bool:
        """恢复当前文档断链的图片。

        流程：预检（ledger 线索 + 可证明范围独占判定）→ 对话框确认 → 执行。
        执行沿用迁移服务的 `copy → verify → delete` 保底，失败不丢源文件。
        """
        widget = self.currentWidget()
        if widget is None:
            return False
        shared_doc = getattr(widget, "shared_doc", None)
        filepath = shared_doc.filepath if shared_doc is not None else None
        editor = self._get_editor_from_widget(widget)
        if editor is None or not filepath or not self._is_markdown_file(filepath):
            QMessageBox.information(
                self, "恢复缺失的图片", "仅已保存的 Markdown 文档支持图片恢复。"
            )
            return False

        # 预检读编辑器当前内容：保存是异步的，刚插入的引用此刻可能还没落盘
        if shared_doc is not None and shared_doc.dirty:
            self._save_file(widget, filepath, shared_doc.encoding)
            if not self._await_save_settled(shared_doc):
                QMessageBox.warning(self, "无法恢复", "文档正在保存，请稍后再试。")
                return False

        service = AssetRecoveryService(self.config)
        try:
            plan = service.plan(filepath, editor.toPlainText())
        except Exception as exc:  # noqa: BLE001
            get_logger(__name__).warning("图片恢复预检失败: %s", exc)
            return False
        if not plan.items:
            QMessageBox.information(
                self, "恢复缺失的图片", "当前文档没有缺失的图片资源。"
            )
            return False

        dialog = AssetRecoveryDialog(plan, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        try:
            result = service.apply(plan)
        except Exception as exc:  # noqa: BLE001
            get_logger(__name__).error("图片恢复执行失败: %s", exc)
            return False

        # 汇总仍缺失的项：本就判为需人工 + 执行时失败 / 目标被占用的
        remaining = len(plan.needs_user) + result.failed + result.skipped
        self.asset_recovery_finished.emit(
            filepath, result.moved, result.copied, remaining
        )
        return True

    # === 大小写转换代理 ===

    def toggle_case(self):
        editor = self.current_editor()
        if editor:
            editor.toggle_case()

    def to_uppercase(self):
        editor = self.current_editor()
        if editor:
            editor.to_uppercase()

    def to_lowercase(self):
        editor = self.current_editor()
        if editor:
            editor.to_lowercase()

    def to_titlecase(self):
        editor = self.current_editor()
        if editor:
            editor.to_titlecase()

    # === Markdown 编辑代理（阶段 2：任务列表 / 表格） ===

    def toggle_task_checkbox(self):
        editor = self.current_editor()
        if editor:
            editor.toggle_task_checkbox()

    def table_insert_row_above(self):
        editor = self.current_editor()
        if editor:
            editor.table_insert_row_above()

    def table_insert_row_below(self):
        editor = self.current_editor()
        if editor:
            editor.table_insert_row_below()

    def table_delete_row(self):
        editor = self.current_editor()
        if editor:
            editor.table_delete_row()

    def table_insert_column_left(self):
        editor = self.current_editor()
        if editor:
            editor.table_insert_column_left()

    def table_insert_column_right(self):
        editor = self.current_editor()
        if editor:
            editor.table_insert_column_right()

    def table_delete_column(self):
        editor = self.current_editor()
        if editor:
            editor.table_delete_column()

    def table_format_align(self):
        editor = self.current_editor()
        if editor:
            editor.table_format_align()

    def table_align_left(self):
        editor = self.current_editor()
        if editor:
            editor.table_align_left()

    def table_align_center(self):
        editor = self.current_editor()
        if editor:
            editor.table_align_center()

    def table_align_right(self):
        editor = self.current_editor()
        if editor:
            editor.table_align_right()

    # === 行内格式 / 标题代理（阶段 2 G2/G5） ===

    def format_bold(self):
        editor = self.current_editor()
        if editor:
            editor.format_bold()

    def format_italic(self):
        editor = self.current_editor()
        if editor:
            editor.format_italic()

    def format_inline_code(self):
        editor = self.current_editor()
        if editor:
            editor.format_inline_code()

    def format_link(self):
        editor = self.current_editor()
        if editor:
            editor.format_link()

    def set_heading_level(self, level: int):
        editor = self.current_editor()
        if editor:
            editor.set_heading_level(level)

    # === 转到行 ===

    def goto_line(self, line_number: int):
        editor = self.current_editor()
        if editor:
            editor.goto_line(line_number)

    def show_goto_line_dialog(self):
        """显示转到行对话框"""
        editor = self.current_editor()
        if not editor:
            return

        doc = editor.document()
        if doc is None:
            return
        max_line = doc.blockCount()
        current_line = editor.textCursor().blockNumber() + 1

        line, ok = QInputDialog.getInt(
            self, "转到行",
            f"输入行号 (1 - {max_line}):",
            current_line, 1, max_line
        )
        if ok:
            editor.goto_line(line)

    # === 文档格式化 ===

    def format_document(self):
        """格式化当前文档"""
        editor = self.current_editor()
        if editor:
            editor.format_document()

    # === 书签持久化 ===

    def _restore_bookmarks(self, widget, filepath: str, lines: list) -> None:
        """恢复已保存的书签到编辑器。"""
        editor = self._get_editor_from_widget(widget)
        if editor is not None:
            editor.set_bookmarks(set(lines))

    def save_all_bookmarks(self) -> None:
        """保存所有已打开标签页的书签到 config。"""
        for i in range(self.count()):
            widget = self.widget(i)
            if widget is None:
                continue
            # D3b：路径读 Document
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is None or not shared_doc.filepath:
                continue
            editor = self._get_editor_from_widget(widget)
            if editor is not None:
                bookmarks = editor.get_bookmarks()
                self.config.set_bookmarks(shared_doc.filepath, list(bookmarks) if bookmarks else [])

    def _restore_folds(self, widget, filepath: str, lines: list) -> None:
        """恢复已保存的折叠状态。"""
        editor = self._get_editor_from_widget(widget)
        if editor is not None and hasattr(editor, '_folding'):
            # 确保折叠区间已计算（load_content 时 _file_type 可能还不是 Markdown）
            editor._refresh_folding()
            editor._folding.set_collapsed_lines(lines)

    def save_all_folds(self) -> None:
        """保存所有已打开标签页的折叠状态到 config。"""
        for i in range(self.count()):
            widget = self.widget(i)
            if widget is None:
                continue
            # D3b：路径读 Document
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is None or not shared_doc.filepath:
                continue
            editor = self._get_editor_from_widget(widget)
            if editor is not None and hasattr(editor, '_folding'):
                collapsed = editor._folding.get_collapsed_lines()
                self.config.set_folds(shared_doc.filepath, collapsed if collapsed else [])
