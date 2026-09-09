# -*- coding: utf-8 -*-
"""
安全 Markdown 渲染器
提供统一的安全 Markdown → HTML 渲染入口，供预览、HTML 导出、PDF 导出共用。

安全策略：
  markdown-it-py：html=False（不渲染原始 HTML）
  python-markdown fallback：渲染后统一走 strip_dangerous_html 清洗
  纯文本 fallback：html.escape()

统一禁止：
  script / iframe / object / embed / form / input / textarea / button / link / meta / base
  on* 事件属性（onerror / onclick / onload 等）
  javascript: URL
"""

import re
import html as html_module
from typing import List

from ..utils.logger import get_logger

try:
    from markdown_it import MarkdownIt as _MarkdownIt
    HAS_MARKDOWN_IT = True
except ImportError:
    HAS_MARKDOWN_IT = False

try:
    import markdown as _md_lib
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

_DANGEROUS_TAG_RE = re.compile(
    r'<(script|iframe|object|embed|form|input|textarea|button|link|meta|base)'
    r'[\s>]',
    re.IGNORECASE,
)
# 任务列表 checkbox 白名单：仅放行带 type="checkbox" 且 disabled 的 <input>（GFM 任务列表渲染产物），
# 其余 input 仍由 _DANGEROUS_TAG_RE 转义
_CHECKBOX_INPUT_RE = re.compile(
    r'<input\b(?=[^>]*\btype\s*=\s*["\']checkbox["\'])'
    r'(?=[^>]*\bdisabled\b)[^>]*>',
    re.IGNORECASE,
)
_DANGEROUS_ATTR_RE = re.compile(
    r'\s(on\w+|formaction|action|data\s*[:=])\s*=\s*["\'][^"\']*["\']',
    re.IGNORECASE,
)
_DANGEROUS_ATTR_UNQUOTED_RE = re.compile(
    r'\s(on\w+|formaction|action|data)\s*=\s*[^\s>\"\'/]+',
    re.IGNORECASE,
)
_JAVASCRIPT_URL_RE = re.compile(
    r'(href|src|action)\s*=\s*["\']\s*javascript\s*:',
    re.IGNORECASE,
)
_JAVASCRIPT_URL_UNQUOTED_RE = re.compile(
    r'(href|src|action)\s*=\s*javascript\s*:',
    re.IGNORECASE,
)


def strip_dangerous_html(html_text: str) -> str:
    """清洗 HTML 中的危险标签和属性

    统一禁止：
      - script, iframe, object, embed, form, input, textarea, button, link, meta, base
      - on* 事件属性（带引号和不带引号）
      - javascript: URL（带引号和不带引号）

    例外：任务列表 checkbox（<input type="checkbox" disabled>，GFM 任务列表渲染产物）
    经白名单保护，其余 input 仍按危险标签转义。
    """
    placeholders: List[str] = []

    def _protect_checkbox(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f"__pn_checkbox_{len(placeholders) - 1}__"

    html_text = _CHECKBOX_INPUT_RE.sub(_protect_checkbox, html_text)
    html_text = _DANGEROUS_TAG_RE.sub('&lt;\\1', html_text)
    html_text = _DANGEROUS_ATTR_RE.sub('', html_text)
    html_text = _DANGEROUS_ATTR_UNQUOTED_RE.sub('', html_text)
    html_text = _JAVASCRIPT_URL_RE.sub('\\1="about:blank"', html_text)
    html_text = _JAVASCRIPT_URL_UNQUOTED_RE.sub('\\1="about:blank"', html_text)
    for idx, original in enumerate(placeholders):
        html_text = html_text.replace(f"__pn_checkbox_{idx}__", original)
    # 恢复的 checkbox 在保护期间未经过属性清洗，补一轮（幂等）
    html_text = _DANGEROUS_ATTR_RE.sub('', html_text)
    html_text = _DANGEROUS_ATTR_UNQUOTED_RE.sub('', html_text)
    return html_text


def render_markdown_to_safe_html(markdown_text: str) -> str:
    """将 Markdown 文本渲染为安全的 HTML

    渲染优先级：
      1. markdown-it-py（html=False）
      2. python-markdown（渲染后走 strip_dangerous_html 清洗）
      3. 纯文本 fallback（html.escape）

    返回：安全的 HTML 片段（不含 <html>/<body> 等外层标签）
    """
    if HAS_MARKDOWN_IT:
        try:
            md = _MarkdownIt("commonmark", {"html": False})
            try:
                from mdit_py_plugins.tasklists import tasklists_plugin
                tasklists_plugin(md)
            except ImportError:
                get_logger(__name__).debug("mdit_py_plugins 未安装，任务列表语法不可用")
            return strip_dangerous_html(md.render(markdown_text))
        except Exception:
            get_logger(__name__).debug("markdown-it 渲染失败，回退到 python-markdown")

    if HAS_MARKDOWN:
        extensions = [
            'tables', 'fenced_code', 'toc',
            'attr_list', 'def_list', 'sane_lists',
        ]
        try:
            result = _md_lib.markdown(markdown_text, extensions=extensions)
        except Exception:
            try:
                result = _md_lib.markdown(markdown_text)
            except Exception:
                get_logger(__name__).warning("python-markdown 渲染失败")
                return html_module.escape(markdown_text)
        return strip_dangerous_html(result)

    return html_module.escape(markdown_text)


def render_plain_text_to_safe_html(text: str) -> str:
    """将纯文本渲染为安全的 HTML（<pre> 包裹 + html.escape）

    用于非 Markdown 文件的导出。
    """
    return f"<pre>{html_module.escape(text)}</pre>"


# ════════════════════════════════════════════════════════
#  Markdown 内容排版 CSS（单一来源，Wave 1.5）
# ════════════════════════════════════════════════════════
#  预览（markdown_preview.PREVIEW_HTML_TEMPLATE）与导出文档
#  （build_export_html_document）共用这份内容排版样式，颜色一律经
#  CSS 变量引用，避免两处各自维护一套排版规则导致主题逐渐分裂。
#  本常量是普通字符串（非 format 模板），花括号为字面量。

MARKDOWN_LAYOUT_CSS = """/* ========== 标题 ========== */
h1, h2, h3, h4, h5, h6 {
    color: var(--text-primary);
    font-weight: bold;
    margin-top: 24px;
    margin-bottom: 12px;
    line-height: 1.3;
}
h1 {
    font-size: 1.85em;
    border-bottom: 1px solid var(--border);
    padding-bottom: 6px;
}
h2 {
    font-size: 1.5em;
    border-bottom: 1px solid var(--border-soft);
    padding-bottom: 5px;
}
h3 { font-size: 1.3em; }
h4 { font-size: 1.15em; }
h5 { font-size: 1.05em; }
h6 { font-size: 1em; color: var(--text-muted); }

/* ========== 段落 / 文本 ========== */
p { margin: 8px 0; }
strong { font-weight: 700; }
em { font-style: italic; }

/* ========== 行内代码 ========== */
:not(pre) > code {
    font-family: "JetBrains Mono", Consolas, "Courier New", "Microsoft YaHei", monospace;
    background: var(--surface);
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 0.92em;
    color: var(--text-primary);
    border: 1px solid var(--divider);
}

/* ========== 引用 ========== */
blockquote {
    border-left: 3px solid var(--scrollbar-thumb-hover);
    padding: 4px 16px;
    margin: 10px 0;
    background: var(--surface-soft);
    color: var(--text-secondary);
}
blockquote p { margin: 4px 0; }

/* ========== 表格 ========== */
table {
    border-collapse: collapse;
    width: 100%;
    margin: 12px 0;
}
th, td {
    border: 1px solid var(--border);
    padding: 6px 12px;
    text-align: left;
}
th {
    background: var(--surface);
    font-weight: 600;
}
tr:nth-child(even) { background: var(--surface-hover); }

/* ========== 链接 ========== */
a { color: var(--primary); text-decoration: none; }
a:hover { text-decoration: underline; color: var(--primary-hover); }

/* ========== 图片 ========== */
img { max-width: 100%; border-radius: 3px; }

/* ========== 分割线 ========== */
hr { border: none; border-top: 1px solid var(--border); margin: 20px 0; }

/* ========== 列表 ========== */
ul, ol { padding-left: 26px; margin: 6px 0; }
li { margin: 3px 0; }

/* ========== 任务列表 ========== */
li input[type="checkbox"] {
    margin-right: 6px;
    vertical-align: middle;
}
"""


def build_export_html_document(body_html: str, theme_colors: dict[str, str], title: str = "") -> str:
    """构建完整的导出 HTML 文档

    参数：
      body_html：已渲染的安全 HTML 片段
      theme_colors：v2 色值集合（v2_export_colors 产物），提供主题色值
      title：文档标题（可选）

    返回：完整的 HTML 文档字符串

    样式来源（Wave 1.5）：
      - :root 内联主题色值定义 CSS 变量（变量名与预览模板一致）
      - 内容排版复用 MARKDOWN_LAYOUT_CSS（与预览单一来源）
      - body / pre 为导出特有（静态文档外壳，居中限定宽度）
    """
    title_tag = f"<title>{html_module.escape(title)}</title>" if title else ""
    root_vars = f""":root {{
    --text-primary: {theme_colors["text_primary"]};
    --text-secondary: {theme_colors["text_secondary"]};
    --text-muted: {theme_colors["text_disabled"]};
    --border: {theme_colors["border"]};
    --border-soft: {theme_colors["divider"]};
    --divider: {theme_colors["divider"]};
    --surface: {theme_colors["surface"]};
    --surface-soft: {theme_colors["surface"]};
    --surface-hover: {theme_colors["sidebar_bg"]};
    --primary: {theme_colors["primary"]};
    --primary-hover: {theme_colors["primary_dark"]};
    --bg-codeblock: {theme_colors["bg_codeblock"]};
    --scrollbar-thumb-hover: {theme_colors["text_disabled"]};
}}"""
    export_shell_css = """/* ========== 导出文档外壳 ========== */
body {
    font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
    padding: 20px;
    max-width: 800px;
    margin: 0 auto;
    line-height: 1.7;
    color: var(--text-primary);
}
pre {
    white-space: pre-wrap;
    background: var(--bg-codeblock);
    padding: 10px;
    border-radius: 4px;
    overflow-x: auto;
}
pre code {
    display: block;
    padding: 10px;
}
"""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
{title_tag}
<style>
{root_vars}
{MARKDOWN_LAYOUT_CSS}
{export_shell_css}
</style>
</head>
<body>
{body_html}
</body>
</html>"""
