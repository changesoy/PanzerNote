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
from typing import Callable, List

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

# fenced code 输出（与预览同构：<pre><code class="language-x">…</code></pre>）
# 公开名：预览（markdown_preview）与导出共用同一份识别逻辑，避免两处各自维护
CODEBLOCK_RE = re.compile(
    r'<pre(?P<pre_attrs>[^>]*)>\s*'
    r'<code(?P<code_attrs>[^>]*)>'
    r'(?P<body>.*?)'
    r'</code>\s*</pre>',
    re.DOTALL | re.IGNORECASE,
)


def extract_language_from_code_attrs(attrs: str) -> str:
    """从 code 标签的属性串中提取语言名称（预览/导出共用）。

    同时识别 class="language-x" 与 class="lang-x" 两种前缀。
    """
    m = re.search(r'class="([^"]*)"', attrs or "")
    if not m:
        return ""
    classes = m.group(1).split()
    for cls in classes:
        if cls.startswith("language-"):
            return cls.removeprefix("language-")
        if cls.startswith("lang-"):
            return cls.removeprefix("lang-")
    return ""


# 代码高亮回调：(源码, 语言名) → 含内联样式的 HTML 片段
CodeHighlighter = Callable[[str, str], str]


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


def _apply_code_highlight(html_text: str, highlight: CodeHighlighter) -> str:
    """把 fenced code 块替换为高亮后的 <pre><code> 块。

    导出侧传入 highlight 回调（复用预览的 highlight_code_html），
    使导出的代码块与预览保持同一套语法高亮；无回调时保持纯文本代码块。
    """
    def _replace(match: re.Match[str]) -> str:
        language = extract_language_from_code_attrs(match.group("code_attrs") or "")
        raw = html_module.unescape(match.group("body"))
        if raw.endswith("\n"):
            raw = raw[:-1]
        return f"<pre><code>{highlight(raw, language)}</code></pre>"

    return CODEBLOCK_RE.sub(_replace, html_text)


def render_markdown_to_safe_html(
    markdown_text: str, highlight: CodeHighlighter | None = None
) -> str:
    """将 Markdown 文本渲染为安全的 HTML

    渲染优先级：
      1. markdown-it-py（html=False，启用 GFM 表格/删除线扩展）
      2. python-markdown（渲染后走 strip_dangerous_html 清洗）
      3. 纯文本 fallback（html.escape）

    参数：
      markdown_text：Markdown 源文本
      highlight：可选的代码高亮回调 (源码, 语言名) → HTML；提供时 fenced code
        块会被替换为高亮 HTML（导出与预览保持一致的语法高亮）

    返回：安全的 HTML 片段（不含 <html>/<body> 等外层标签）
    """
    def _finish(rendered: str) -> str:
        safe = strip_dangerous_html(rendered)
        return _apply_code_highlight(safe, highlight) if highlight else safe

    if HAS_MARKDOWN_IT:
        try:
            md = _MarkdownIt("commonmark", {"html": False})
            # commonmark preset 不含表格/删除线（GFM 扩展），与预览渲染保持一致
            md.enable(["table", "strikethrough"])
            try:
                from mdit_py_plugins.tasklists import tasklists_plugin
                tasklists_plugin(md)
            except ImportError:
                get_logger(__name__).debug("mdit_py_plugins 未安装，任务列表语法不可用")
            return _finish(md.render(markdown_text))
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
        return _finish(result)

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


# ════════════════════════════════════════════════════════
#  QTextDocument CSS 子集转换（方案 A：去 WebEngine）
# ════════════════════════════════════════════════════════

def convert_layout_css_for_qtext(theme_colors: dict[str, str]) -> str:
    """把 MARKDOWN_LAYOUT_CSS 转换为 QTextDocument 支持的 CSS 子集。

    QTextDocument 富文本 CSS 子集不支持：
      - :root 变量与 var() 引用（此处以具体色值注入）
      - 伪类（:hover）、nth-child、属性选择器、::-webkit-scrollbar
      - border-radius / max-width（QTextDocument 忽略，直接剔除）

    theme_colors 键（不带 -- 前缀，与 MARKDOWN_LAYOUT_CSS 变量名一致）：
      text-primary / text-secondary / text-muted / border / border-soft /
      divider / surface / surface-soft / surface-hover / primary /
      primary-hover / bg-codeblock / scrollbar-thumb-hover
    缺失键会抛 ValueError（显式失败，避免静默渲染错误色）。

    返回值是纯字符串 CSS，供 QTextDocument 的 <style> 块使用；
    代码块容器等 class 级样式由调用方（markdown_preview）单独注入。
    """
    result = MARKDOWN_LAYOUT_CSS
    # 1. 剔除 :root 变量定义块（QTextDocument 不支持 CSS 变量）
    result = re.sub(r':root\s*\{[^{}]*\}', '', result)

    # 2. var(--xxx) → 具体色值
    def _replace_var(match: re.Match[str]) -> str:
        name = match.group(1)
        try:
            return theme_colors[name]
        except KeyError:
            raise ValueError(
                f"QTextDocument CSS 转换缺少变量色值: {name}"
            ) from None

    result = re.sub(r'var\(--([\w-]+)\)', _replace_var, result)

    # 3. 剔除不支持的规则（伪类 / nth-child / 属性选择器 / 滚动条）
    result = re.sub(r'::-webkit-scrollbar[^{}]*\{[^{}]*\}', '', result)
    result = re.sub(r'tr:nth-child\([^)]*\)\s*\{[^{}]*\}', '', result)
    result = re.sub(r'[^{}\n]*:hover[^{}]*\{[^{}]*\}', '', result)
    result = re.sub(r'section\[[^\]]*\]\s*\{[^{}]*\}', '', result)
    result = re.sub(r'li\s+input\[[^\]]*\]\s*\{[^{}]*\}', '', result)
    result = result.replace(':not(pre) > code', 'code')

    # 4. 剔除 QTextDocument 不支持的观感属性（忽略无害，去掉避免误读）
    result = re.sub(r'\s*border-radius\s*:\s*[^;]+;', '', result)
    result = re.sub(r'\s*max-width\s*:\s*[^;]+;', '', result)

    # 5. 复位代码块内的行内代码样式
    #    QTextDocument 不支持 :not()，第 3 步把 `:not(pre) > code` 降级成了
    #    `code`，行内代码的底色/内边距/边框因此一并落到代码块里的 <code> 上，
    #    与容器 <pre> 的代码块底色叠成「文字处一色、行内空白另一色」的双色块。
    #    这里用 Qt 支持的后代选择器复位（行内代码规则只应作用于代码块之外）。
    result += (
        "\npre code { background-color: transparent;"
        " padding: 0; border: none; }\n"
    )
    return result


_QTABLE_OPEN_RE = re.compile(r'<table(?P<attrs>[^>]*)>', re.IGNORECASE)


def _apply_qtext_table_attributes(body_html: str) -> str:
    """把表格样式转成 QTextDocument 认得的 HTML 属性。

    QTextDocument 的富文本引擎只读表格的 HTML 属性（border / cellspacing /
    cellpadding / width），完全忽略 th、td 上的 CSS border 与 padding；
    只靠 CSS 会导出成无边框、无内边距、单元格文字互相挤压的裸表格。

    这里**不给表头加底色**：单元格背景会被 Qt 的导入器“粘”到表格之后的块上
    （实测表格后的列表项整行被染成表头底色），而表头本身已由 Qt 默认渲染为
    加粗居中，观感损失有限。
    """
    def _table(match: re.Match[str]) -> str:
        attrs = match.group("attrs")
        if "border" in attrs.lower():
            return match.group(0)
        return f'<table border="1" cellspacing="0" cellpadding="6" width="100%"{attrs}>'

    return _QTABLE_OPEN_RE.sub(_table, body_html)


def build_export_qtext_html_document(
    body_html: str, theme_colors: dict[str, str], title: str = ""
) -> str:
    """构建 QTextDocument（PDF 导出）渲染的完整 HTML。

    与 build_export_html_document 的区别：QTextDocument 不支持 CSS 变量、
    :root 与部分属性，故经 convert_layout_css_for_qtext 把 var(--x) 换成具体
    色值，表格改用 HTML 属性表达，并用同样不含变量的外壳样式（导出文档是
    静态白纸，不需要变量）。

    参数：
      body_html：已渲染的安全 HTML 片段
      theme_colors：v2_export_colors 产物（下划线键名）
      title：文档标题（可选）

    返回：完整的 HTML 文档字符串
    """
    # MARKDOWN_LAYOUT_CSS 的变量名是连字符形式，此处做键名映射
    qtext_colors = {
        "text-primary": theme_colors["text_primary"],
        "text-secondary": theme_colors["text_secondary"],
        "text-muted": theme_colors["text_disabled"],
        "border": theme_colors["border"],
        "border-soft": theme_colors["divider"],
        "divider": theme_colors["divider"],
        "surface": theme_colors["surface"],
        "surface-soft": theme_colors["surface"],
        "surface-hover": theme_colors["sidebar_bg"],
        "primary": theme_colors["primary"],
        "primary-hover": theme_colors["primary_dark"],
        "bg-codeblock": theme_colors["bg_codeblock"],
        "scrollbar-thumb-hover": theme_colors["text_disabled"],
    }
    layout_css = convert_layout_css_for_qtext(qtext_colors)
    body_html = _apply_qtext_table_attributes(body_html)

    # 外壳样式：body/pre 为导出特有；白纸文档固定用亮色变体色值
    # （code 的等宽字体与 pre 的 pre-wrap 不可省——缺 pre-wrap 时长代码行
    #   会超出页面可绘宽度而被裁切；pre 需显式复位行高——QTextDocument 会把
    #   <pre> 的每一行当作独立块，正文的 line-height 会在行间留出白缝，
    #   表现为代码块被切成一条条背景）
    shell_css = (
        "body { font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
        f" font-size: 11pt; line-height: 1.7;"
        f" color: {theme_colors['text_primary']}; }}\n"
        "pre { white-space: pre-wrap; line-height: normal;"
        f" background-color: {theme_colors['bg_codeblock']}; padding: 10px; }}\n"
        "code { font-family: 'Consolas', 'Courier New', monospace; }\n"
    )

    title_tag = f"<title>{html_module.escape(title)}</title>" if title else ""
    return (
        "<html><head>"
        f"{title_tag}"
        f"<style>\n{shell_css}{layout_css}\n</style>"
        f"</head><body>{body_html}</body></html>"
    )

