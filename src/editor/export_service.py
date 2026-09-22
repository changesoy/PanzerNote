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

import base64
import os
import re
from typing import Callable, Optional

from ..core.settings_store import (
    DEFAULT_CODE_FONT_FAMILY,
    DEFAULT_CODE_LINE_SPACING,
    DEFAULT_LINE_SPACING,
)
from ..security.file_access_context import FileAccessContext
from ..security.file_guard import FileGuard
from ..themes.theme_engine import ThemeEngine
from ..themes.theme_v2.consumer import v2_export_variant_id
from ..utils.logger import get_logger
from .highlight_themes import highlight_code_html
from .image_reference_scanner import resolve_local_ref
from .secure_markdown_renderer import (
    CodeHighlighter,
    render_markdown_to_safe_html,
    render_plain_text_to_safe_html,
    build_export_html_document,
    build_export_shell,
    build_export_content_script,
)
from .web_preview import create_preview_adapter

logger = get_logger(__name__)

# <img ... src="..."> 的 src 取值（双/单引号）；用于把本地图片内嵌为 data URI
_IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=)(["\'])([^"\']*)\2', re.IGNORECASE)

_IMAGE_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
}


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
                    code_font: str = DEFAULT_CODE_FONT_FAMILY,
                    line_spacing: float = DEFAULT_LINE_SPACING,
                    code_line_spacing: float = DEFAULT_CODE_LINE_SPACING,
                    resource_root: str = "",
                    on_notice: Callable[[str], None] | None = None) -> None:
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
          line_spacing：正文行距倍数（设置项「正文行距」）
          code_line_spacing：代码块行距倍数（设置项「代码块行距」）
          resource_root：相对资源的解析根目录（通常为当前文档所在目录）。提供时
            把本地相对图片内嵌为 data URI —— HTML 导出按设计是单文件自包含，
            相对路径在导出位置之外必然断链，故不能只留相对 src。
          on_notice：非致命降级提示回调 (message: str) -> None（本地图片缺失 /
            格式不支持 / 读取失败时，导出仍成功但会缺图，须让用户可见）

        异常：文件写入失败时抛出 IOError
        """
        body_html = ExportService.render_content(content, is_markdown, theme_engine)
        body_html = _embed_local_images(
            body_html, resource_root, file_guard, on_notice=on_notice
        )
        full_html = build_export_html_document(
            body_html, colors, title, code_font, line_spacing, code_line_spacing
        )

        file_guard.safe_write_bytes(
            filepath,
            full_html.encode("utf-8"),
            context=FileAccessContext.EXPORT_TARGET,
        )

    @staticmethod
    def export_pdf(content: str, is_markdown: bool, parent_widget,
                   on_pdf_generated, colors, theme_engine: ThemeEngine,
                   title: str = "",
                   code_font: str = DEFAULT_CODE_FONT_FAMILY,
                   line_spacing: float = DEFAULT_LINE_SPACING,
                   code_line_spacing: float = DEFAULT_CODE_LINE_SPACING,
                   on_notice: Callable[[str], None] | None = None,
                   resource_root: str = "") -> object:
        """导出为 PDF 文件

        参数：
          content：原始文本
          is_markdown：是否按 Markdown 渲染
          parent_widget：父 widget（用于离屏预览控件的 parent）
          on_pdf_generated：回调函数 (pdf_data: bytes) -> None
          colors：v2_export_colors 产物（dict），提供主题色值
          theme_engine：主题引擎，用于代码块语法高亮（必填）
          title：文档标题
          code_font：代码块字体族名（设置项「代码字体」）
          line_spacing：正文行距倍数（设置项「正文行距」）
          code_line_spacing：代码块行距倍数（设置项「代码块行距」）
          on_notice：非致命降级提示回调 (message: str) -> None（M4：如
            图表未在就绪门超时前渲染完成，导出仍成功但可能少图，须让用户可见）
          resource_root：相对资源的解析根目录（通常为当前文档所在目录）。
            渲染产物里的本地图片是相对路径（如 `PanzerNote_assets/x.png`），
            不声明资源根时离屏文档没有 base href，导出结果必然缺图。

        返回：离屏预览控件（调用方不应持有，由内部自动清理）
        """
        body_html = ExportService.render_content(content, is_markdown, theme_engine)
        # PDF 走 WebView2 导航（B 阶段 1′ 方案 A）：NavigateToString 对文档有
        # 2 MB 上限（内联 Mermaid 约 5.6 MB 会直接失败），故一律只导航空壳，
        # 正文与图表库经文档级脚本通道注入（该通道实测可承载 5.6 MB）。
        shell_html = build_export_shell(
            body_html, colors, title, code_font, line_spacing, code_line_spacing
        )
        content_js = build_export_content_script(body_html)

        # PDF 导出经 Web 预览适配器（离屏实例），后端由 create_preview_adapter 选择
        adapter = create_preview_adapter(parent_widget)
        # 与预览同源：资源根交给后端映射，适配器据此注入 base href 解析相对图片
        adapter.set_resource_root(resource_root or None)
        if on_notice is not None:
            adapter.export_notice.connect(on_notice)
        adapter.export_pdf(shell_html, content_js, on_pdf_generated)
        return adapter.widget()


def _embed_local_images(
    body_html: str,
    resource_root: str,
    file_guard: Optional[FileGuard],
    on_notice: Optional[Callable[[str], None]] = None,
) -> str:
    """把 body 里的本地相对图片内嵌为 data URI（外链 / 读取失败保持原样）。

    HTML 导出按设计是单文件自包含，而渲染产物里的图片是相对路径 —— 导出到文档
    目录之外时相对路径必然断链，故在此读回原始字节内嵌；后端无资源根能力、
    只能靠 base href 的场景（PDF）不走这里。

    本该内嵌却失败的本地图（缺失 / 格式不支持 / 读取失败）经 on_notice 汇总告知：
    导出仍算成功，但用户必须知道成品里会缺图，不能静默降级。外链图片不算失败。
    """
    if not resource_root or file_guard is None or "<img" not in body_html.lower():
        return body_html

    failed: list[str] = []

    def _replace(match: "re.Match[str]") -> str:
        prefix, quote, src = match.group(1), match.group(2), match.group(3)
        data_uri = _to_data_uri(src, resource_root, file_guard)
        if data_uri is None:
            if resolve_local_ref(resource_root, src) is not None:
                failed.append(src)
            return match.group(0)
        return f"{prefix}{quote}{data_uri}{quote}"

    embedded = _IMG_SRC_RE.sub(_replace, body_html)
    if failed and on_notice is not None:
        on_notice(_embed_failure_message(failed))
    return embedded


def _embed_failure_message(failed: list[str]) -> str:
    """内嵌失败提示文案（最多列出前 3 个，其余按数量概括）。"""
    shown = "、".join(failed[:3])
    more = f" 等 {len(failed)} 张" if len(failed) > 3 else ""
    return f"导出为HTML：本地图片 {shown}{more} 未能内嵌，导出文件里会缺图"


def _to_data_uri(
    src: str, resource_root: str, file_guard: FileGuard
) -> Optional[str]:
    """本地相对图片 → data URI；非本地 / 不支持的格式 / 读取失败返回 None。

    路径解析与引用扫描共用 `resolve_local_ref`（同一口径：去 fragment/query →
    percent-decode → 排除 scheme / 根路径），避免两处实现漂移。
    """
    target = resolve_local_ref(resource_root, src)
    if target is None:
        return None
    mime = _IMAGE_MIME_BY_EXT.get(os.path.splitext(target)[1].lower())
    if mime is None or not os.path.isfile(target):
        return None
    try:
        data = file_guard.safe_read_bytes(
            target, context=FileAccessContext.DOCUMENT_ASSET
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("导出内嵌图片失败，保留原路径 %s: %s", target, exc)
        return None
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
