# -*- coding: utf-8 -*-
"""
导出控制器
集中管理 PDF / HTML 导出流程编排（原 MainWindow._export_pdf / _export_html / _on_pdf_generated）。

创建者：MainWindow（_init_ui 之后构造注入）
持有者：MainWindow
完成通知：见 ExportService（HTML 同步完成；PDF 经 WebView2 print_to_pdf_async 回调）
"""

import os

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

from ..game.secretary_widget import SecretaryWidget
from ..security.file_access_context import FileAccessContext
from ..themes.theme_engine import ThemeEngine
from ..themes.theme_v2.consumer import v2_export_colors
from ..utils.error_handler import ErrorHandler, ErrorCategory

from .editor_tabs import EditorTabWidget


class ExportActionController:
    """导出控制器：承载 PDF / HTML 导出流程的编排逻辑。

    依赖全部构造注入，不持有 MainWindow 引用；弹窗父窗口由 parent_widget 提供。
    """

    def __init__(
        self,
        editor_tabs: EditorTabWidget,
        theme_engine: ThemeEngine,
        secretary: SecretaryWidget,
        parent_widget: QWidget,
    ) -> None:
        self._editor_tabs = editor_tabs
        self._theme_engine = theme_engine
        self._secretary = secretary
        self._parent_widget = parent_widget

    def _typography(self) -> dict:
        """导出所需的排版设置（设置项「代码字体 / 正文行距 / 代码块行距」）。

        三者必须整体取自设置——曾漏传两个行距，导出只能吃到 `build_export_html_document`
        的默认倍数，表现为「预览改了行距、导出纹丝不动」。
        """
        config = self._editor_tabs.config
        return {
            "code_font": config.get_code_font_family(),
            "line_spacing": config.get_line_spacing(),
            "code_line_spacing": config.get_code_line_spacing(),
        }

    def export_pdf(self) -> None:
        """导出当前文档为 PDF（经 WebView2 print_to_pdf_async 异步生成）。"""
        from .export_service import ExportService
        try:
            editor = self._editor_tabs.current_editor()
            if not editor:
                return
            filepath, _ = QFileDialog.getSaveFileName(
                self._parent_widget, "导出PDF", "", "PDF文件 (*.pdf)"
            )
            if not filepath:
                return

            content = editor.toPlainText()
            widget = self._editor_tabs.currentWidget()
            widget_type = type(widget).__name__ if widget else ""
            is_md = ExportService.is_markdown_content(content, widget_type)

            def on_pdf_ready(pdf_data):
                self._on_pdf_generated(pdf_data, filepath)

            ExportService.export_pdf(
                content,
                is_md,
                self._parent_widget,
                on_pdf_ready,
                v2_export_colors(self._theme_engine),
                theme_engine=self._theme_engine,
                **self._typography(),
            )
        except RuntimeError as e:
            QMessageBox.warning(self._parent_widget, "导出失败", str(e))

    def _on_pdf_generated(self, pdf_data, filepath) -> None:
        """PDF 生成完成的回调：写文件 / 提示 / 失败弹窗。"""
        if pdf_data:
            try:
                # 目标路径由用户在导出“另存为”对话框中显式授权（EXPORT_TARGET），
                # 无需再走 PathValidator 白名单；仍受文件大小限制与原子写入保护。
                file_guard = self._editor_tabs.config.get_file_guard()
                file_guard.safe_write_bytes(
                    filepath, pdf_data, context=FileAccessContext.EXPORT_TARGET
                )
                self._secretary.show_message(
                    f"已导出PDF: {os.path.basename(filepath)}"
                )
            except Exception as e:
                ErrorHandler.show_from_exception(
                    e,
                    ErrorCategory.FILE,
                    f"写入PDF文件失败：{os.path.basename(filepath)}",
                )
        else:
            QMessageBox.warning(self._parent_widget, "导出失败", "PDF生成失败")

    def export_html(self) -> None:
        """导出当前文档为 HTML（同步完成）。"""
        from .export_service import ExportService
        editor = self._editor_tabs.current_editor()
        if not editor:
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self._parent_widget, "导出HTML", "", "HTML文件 (*.html)"
        )
        if not filepath:
            return

        content = editor.toPlainText()
        widget = self._editor_tabs.currentWidget()
        widget_type = type(widget).__name__ if widget else ""
        is_md = ExportService.is_markdown_content(content, widget_type)

        try:
            ExportService.export_html(
                content,
                is_md,
                filepath,
                v2_export_colors(self._theme_engine),
                file_guard=self._editor_tabs.config.get_file_guard(),
                theme_engine=self._theme_engine,
                **self._typography(),
            )
            self._secretary.show_message(
                f"已导出HTML: {os.path.basename(filepath)}"
            )
        except Exception as e:
            QMessageBox.warning(self._parent_widget, "导出失败", str(e))
