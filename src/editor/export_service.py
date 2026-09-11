# -*- coding: utf-8 -*-
"""
导出服务
集中管理 HTML 和 PDF 导出逻辑，统一使用 secure_markdown_renderer 安全渲染。

创建者：MainWindow._export_html / _export_pdf
持有者：MainWindow（短期持有，导出完成后释放）
完成通知：
  HTML：同步完成
  PDF：Web Preview Adapter.loadFinished → printToPdf 回调
失败通知：异常抛出 / 回调参数为空
关闭时行为：离屏适配器在 printToPdf 回调完成后自动释放（deleteLater）
"""

from ..security.file_access_context import FileAccessContext
from ..themes.theme_engine import ThemeEngine
from ..themes.theme_v2.consumer import v2_export_variant_id
from .highlight_themes import highlight_code_html
from .secure_markdown_renderer import (
    DEFAULT_CODE_FONT_FAMILY,
    CodeHighlighter,
    render_markdown_to_safe_html,
    render_plain_text_to_safe_html,
    build_export_html_document,
)
from .web_preview import create_preview_adapter


class ExportService:
    """集中导出服务

    职责：
    1. 判断内容是否为 Markdown
    2. 统一调用 secure_markdown_renderer 渲染
    3. HTML 导出：渲染 + 写文件
    4. PDF 导出：渲染 + Web Preview Adapter（离屏）+ printToPdf

    不在后台线程创建或操作 Qt UI 对象。
    离屏适配器在主线程创建和使用。
    """

    @staticmethod
    def _code_highlighter(theme_engine: ThemeEngine) -> CodeHighlighter:
        """导出用代码高亮器：固定亮色变体的 syntax 配色。

        导出文档打印在白底上，深色主题的语法配色会糊在白底里，故与导出配色
        一致地取 light 变体。
        """
        variant_id = v2_export_variant_id(theme_engine)

        def _highlight(code: str, language: str) -> str:
            return highlight_code_html(code, language, theme_engine, variant_id)

        return _highlight

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
    def render_content(content: str, is_markdown: bool,
                       theme_engine: ThemeEngine) -> str:
        """渲染内容为安全的 HTML 片段

        参数：
          content：原始文本
          is_markdown：是否按 Markdown 渲染
          theme_engine：主题引擎，对 fenced code 做语法高亮（与预览同源、
            固定亮色变体配色）。必填——不提供「无主题引擎则退化为纯文本
            代码块」的降级路径。

        返回：安全的 HTML 片段
        """
        if is_markdown:
            return render_markdown_to_safe_html(
                content, ExportService._code_highlighter(theme_engine)
            )
        return render_plain_text_to_safe_html(content)

    @staticmethod
    def export_html(content: str, is_markdown: bool, filepath: str, colors,
                    theme_engine: ThemeEngine, title: str = "",
                    file_guard=None,
                    code_font: str = DEFAULT_CODE_FONT_FAMILY) -> None:
        """导出为 HTML 文件

        参数：
          content：原始文本
          is_markdown：是否按 Markdown 渲染
          filepath：导出文件路径
          colors：v2_export_colors 产物（dict），提供主题色值
          theme_engine：主题引擎，用于代码块语法高亮（必填）
          title：文档标题
          file_guard：FileGuard 实例（必填），写入经 safe_write_bytes 安全执行
          code_font：代码块字体族名（设置项「代码字体」）

        异常：文件写入失败时抛出 IOError
        """
        body_html = ExportService.render_content(content, is_markdown, theme_engine)
        full_html = build_export_html_document(body_html, colors, title, code_font)

        file_guard.safe_write_bytes(
            filepath,
            full_html.encode("utf-8"),
            context=FileAccessContext.EXPORT_TARGET,
        )

    @staticmethod
    def export_pdf(content: str, is_markdown: bool, parent_widget,
                   on_pdf_generated, colors, theme_engine: ThemeEngine,
                   title: str = "",
                   code_font: str = DEFAULT_CODE_FONT_FAMILY) -> object:
        """导出为 PDF 文件

        参数：
          content：原始文本
          is_markdown：是否按 Markdown 渲染
          parent_widget：父 widget（用于离屏预览控件的 parent）
          on_pdf_generated：回调函数 (pdf_data: bytes, filepath: str) -> None
          colors：v2_export_colors 产物（dict），提供主题色值
          theme_engine：主题引擎，用于代码块语法高亮（必填）
          title：文档标题
          code_font：代码块字体族名（设置项「代码字体」）

        返回：离屏预览控件（调用方不应持有，由内部自动清理）
        """
        body_html = ExportService.render_content(content, is_markdown, theme_engine)
        full_html = build_export_html_document(body_html, colors, title, code_font)

        # PDF 导出经 Web 预览适配器（离屏实例），后端由 create_preview_adapter 选择
        adapter = create_preview_adapter(parent_widget)
        adapter.export_pdf(full_html, on_pdf_generated)
        return adapter.widget()
