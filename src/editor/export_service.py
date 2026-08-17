# -*- coding: utf-8 -*-
"""
导出服务
集中管理 HTML 和 PDF 导出逻辑，统一使用 secure_markdown_renderer 安全渲染。

创建者：MainWindow._export_html / _export_pdf
持有者：MainWindow（短期持有，导出完成后释放）
完成通知：
  HTML：同步完成
  PDF：QWebEngineView.loadFinished → printToPdf 回调
失败通知：异常抛出 / 回调参数为空
关闭时行为：QWebEngineView 通过 printToPdf 回调完成后 deleteLater 自动清理
"""

import os

from ..security.file_access_context import FileAccessContext
from ..utils.logger import get_logger
from .secure_markdown_renderer import (
    render_markdown_to_safe_html,
    render_plain_text_to_safe_html,
    build_export_html_document,
)

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False


class ExportService:
    """集中导出服务

    职责：
    1. 判断内容是否为 Markdown
    2. 统一调用 secure_markdown_renderer 渲染
    3. HTML 导出：渲染 + 写文件
    4. PDF 导出：渲染 + QWebEngineView + printToPdf

    不在后台线程创建或操作 Qt UI 对象。
    QWebEngineView 在主线程创建和使用。
    """

    @staticmethod
    def is_markdown_content(content: str, widget_type_name: str = "") -> bool:
        """判断内容是否应按 Markdown 渲染

        参数：
          content：编辑器文本内容
          widget_type_name：当前 widget 的类名字符串
        """
        if widget_type_name == "MarkdownPreviewWidget":
            return True
        if content and content.strip().startswith('#'):
            return True
        return False

    @staticmethod
    def render_content(content: str, is_markdown: bool) -> str:
        """渲染内容为安全的 HTML 片段

        参数：
          content：原始文本
          is_markdown：是否按 Markdown 渲染

        返回：安全的 HTML 片段
        """
        if is_markdown:
            return render_markdown_to_safe_html(content)
        return render_plain_text_to_safe_html(content)

    @staticmethod
    def export_html(content: str, is_markdown: bool, filepath: str, colors,
                    title: str = "", file_guard=None) -> None:
        """导出为 HTML 文件

        参数：
          content：原始文本
          is_markdown：是否按 Markdown 渲染
          filepath：导出文件路径
          colors：v2_export_colors 产物（dict），提供主题色值
          title：文档标题
          file_guard：FileGuard 实例（必填），写入经 safe_write_bytes 安全执行

        异常：文件写入失败时抛出 IOError
        """
        body_html = ExportService.render_content(content, is_markdown)
        full_html = build_export_html_document(body_html, colors, title)

        file_guard.safe_write_bytes(
            filepath,
            full_html.encode("utf-8"),
            context=FileAccessContext.USER_DOCUMENT_SAVE,
        )

    @staticmethod
    def export_pdf(content: str, is_markdown: bool, parent_widget,
                   on_pdf_generated, colors, title: str = "") -> object:
        """导出为 PDF 文件

        参数：
          content：原始文本
          is_markdown：是否按 Markdown 渲染
          parent_widget：父 widget（用于 QWebEngineView 的 parent）
          on_pdf_generated：回调函数 (pdf_data: bytes, filepath: str) -> None
          colors：v2_export_colors 产物（dict），提供主题色值
          title：文档标题

        返回：QWebEngineView 实例（调用方不应持有，由内部自动清理）

        异常：WebEngine 不可用时抛出 RuntimeError
        """
        if not HAS_WEBENGINE:
            raise RuntimeError("导出PDF需要QtWebEngine组件")

        body_html = ExportService.render_content(content, is_markdown)
        full_html = build_export_html_document(body_html, colors, title)

        web_view = QWebEngineView(parent_widget)

        def _on_load_finished(ok):
            if not ok:
                on_pdf_generated(b"")
                web_view.deleteLater()
                return
            page = web_view.page()
            if page is None:
                on_pdf_generated(b"")
                web_view.deleteLater()
                return
            page.printToPdf(
                lambda pdf_data: _on_pdf_ready(pdf_data)
            )

        def _on_pdf_ready(pdf_data):
            on_pdf_generated(pdf_data)
            web_view.deleteLater()

        web_view.loadFinished.connect(_on_load_finished)
        web_view.setHtml(full_html)
        return web_view
