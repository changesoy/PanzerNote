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
    """
    html_text = _DANGEROUS_TAG_RE.sub('&lt;\\1', html_text)
    html_text = _DANGEROUS_ATTR_RE.sub('', html_text)
    html_text = _DANGEROUS_ATTR_UNQUOTED_RE.sub('', html_text)
    html_text = _JAVASCRIPT_URL_RE.sub('\\1="about:blank"', html_text)
    html_text = _JAVASCRIPT_URL_UNQUOTED_RE.sub('\\1="about:blank"', html_text)
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


def build_export_html_document(body_html: str, title: str = "") -> str:
    """构建完整的导出 HTML 文档

    参数：
      body_html：已渲染的安全 HTML 片段
      title：文档标题（可选）

    返回：完整的 HTML 文档字符串
    """
    title_tag = f"<title>{html_module.escape(title)}</title>" if title else ""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
{title_tag}
<style>
body {{
    font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
    padding: 20px;
    max-width: 800px;
    margin: 0 auto;
    line-height: 1.7;
    color: #2b2b2b;
}}
pre {{
    white-space: pre-wrap;
    background: #f5f5f5;
    padding: 10px;
    border-radius: 4px;
    overflow-x: auto;
}}
code {{
    background: #f5f5f5;
    padding: 2px 4px;
    border-radius: 3px;
}}
pre code {{
    display: block;
    padding: 10px;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
}}
th, td {{
    border: 1px solid #ddd;
    padding: 8px 12px;
    text-align: left;
}}
th {{
    background: #f5f5f5;
    font-weight: bold;
}}
img {{
    max-width: 100%;
}}
h1, h2, h3, h4, h5, h6 {{
    color: #2b2b2b;
    margin-top: 24px;
    margin-bottom: 12px;
}}
h1 {{
    border-bottom: 1px solid #d0d0d0;
    padding-bottom: 6px;
}}
h2 {{
    border-bottom: 1px solid #d9d9d9;
    padding-bottom: 5px;
}}
</style>
</head>
<body>
{body_html}
</body>
</html>"""
