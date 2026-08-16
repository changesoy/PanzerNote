# -*- coding: utf-8 -*-
"""
代码高亮主题管理模块
统一管理编辑器（左侧）和 Markdown 预览（右侧）的代码配色方案

使用方式：
    编辑器：  get_editor_formats(theme_engine) → {Token: QTextCharFormat}
    预览CSS： get_preview_css(theme_engine)     → str (注入到 HTML <style>)

颜色值统一由 ThemeEngine 的 ThemeColorScheme 管理。
Token → syntax_* 映射、bold/italic 装饰在此定义。
"""

from typing import Optional, cast

from PyQt6.QtGui import QTextCharFormat, QColor, QFont

from ..utils.logger import get_logger
from ..themes.theme_v2.consumer import v2_syntax_colors

try:
    from pygments.token import Token
    from pygments.style import Style as PygmentsStyle
    from pygments.formatters import HtmlFormatter
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False


# ════════════════════════════════════════════════════════
#  Token → syntax_* 映射表
#  所有 Pygments Token 到 ThemeColorScheme 语义 token 属性的映射
# ════════════════════════════════════════════════════════

if HAS_PYGMENTS:
    TOKEN_MAP = {
        # ── 关键字 ──
        Token.Keyword:                     "syntax_keyword",
        Token.Keyword.Constant:            "syntax_keyword",
        Token.Keyword.Declaration:         "syntax_keyword",
        Token.Keyword.Namespace:           "syntax_keyword",
        Token.Keyword.Pseudo:              "syntax_keyword",
        Token.Keyword.Reserved:            "syntax_keyword",
        Token.Keyword.Type:                "syntax_keyword_type",
        Token.Operator.Word:               "syntax_keyword",

        # ── 名称 ──
        Token.Name.Builtin:                "syntax_builtin",
        Token.Name.Builtin.Pseudo:         "syntax_builtin",
        Token.Name.Class:                  "syntax_class",
        Token.Name.Exception:              "syntax_class",
        Token.Name.Function:               "syntax_function",
        Token.Name.Function.Magic:         "syntax_function",
        Token.Name.Decorator:              "syntax_function",
        Token.Name.Tag:                    "syntax_tag",
        Token.Name.Attribute:              "syntax_variable",
        Token.Name.Namespace:              "syntax_namespace",
        Token.Name.Variable:               "syntax_variable",
        Token.Name.Variable.Class:         "syntax_variable",
        Token.Name.Variable.Global:        "syntax_variable",
        Token.Name.Variable.Instance:      "syntax_variable",
        Token.Name.Constant:               "syntax_variable",
        Token.Name.Label:                  "syntax_namespace",
        Token.Name.Entity:                 "syntax_variable",

        # ── 字面量：字符串 ──
        Token.Literal.String:              "syntax_string",
        Token.Literal.String.Backtick:     "syntax_string",
        Token.Literal.String.Char:         "syntax_string",
        Token.Literal.String.Delimiter:    "syntax_string",
        Token.Literal.String.Double:       "syntax_string",
        Token.Literal.String.Heredoc:      "syntax_string",
        Token.Literal.String.Other:        "syntax_string",
        Token.Literal.String.Regex:        "syntax_string",
        Token.Literal.String.Single:       "syntax_string",
        Token.Literal.String.Symbol:       "syntax_string",
        Token.Literal.String.Affix:        "syntax_string_affix",
        Token.Literal.String.Interpol:     "syntax_string_affix",
        Token.Literal.String.Doc:          "syntax_string_doc",
        Token.Literal.String.Escape:       "syntax_string_escape",

        # ── 字面量：数字 ──
        Token.Literal.Number:              "syntax_number",
        Token.Literal.Number.Bin:          "syntax_number",
        Token.Literal.Number.Float:        "syntax_number",
        Token.Literal.Number.Hex:          "syntax_number",
        Token.Literal.Number.Integer:      "syntax_number",
        Token.Literal.Number.Integer.Long: "syntax_number",
        Token.Literal.Number.Oct:          "syntax_number",

        # ── 注释 ──
        Token.Comment:                     "syntax_comment",
        Token.Comment.Hashbang:            "syntax_comment",
        Token.Comment.Multiline:           "syntax_comment",
        Token.Comment.Preproc:             "syntax_comment",
        Token.Comment.PreprocFile:         "syntax_comment",
        Token.Comment.Single:              "syntax_comment",
        Token.Comment.Special:             "syntax_comment",

        # ── 运算符 / 标点 ──
        Token.Operator:                    "syntax_operator",
        Token.Punctuation:                 "syntax_punctuation",

        # ── 泛型 ──
        Token.Generic.Heading:             "syntax_heading",
        Token.Generic.Subheading:          "syntax_heading",
        Token.Generic.Deleted:             "syntax_deleted",
        Token.Generic.Inserted:            "syntax_inserted",
        Token.Generic.Error:               "syntax_error",
        Token.Generic.Traceback:           "syntax_error",
        Token.Generic.Output:              "syntax_output",
        Token.Generic.Prompt:              "syntax_output",

        # ── 文本 / 错误 ──
        Token.Text:                        "syntax_text",
        Token.Error:                       "syntax_error",
    }

    # ── bold / italic 装饰（跨主题统一）──
    _TOKEN_BOLD = frozenset({
        Token.Keyword,
        Token.Keyword.Constant,
        Token.Keyword.Declaration,
        Token.Keyword.Namespace,
        Token.Keyword.Pseudo,
        Token.Keyword.Reserved,
        Token.Name.Class,
        Token.Name.Exception,
        Token.Name.Decorator,
        Token.Operator.Word,
        Token.Literal.String.Affix,
        Token.Literal.String.Interpol,
        Token.Literal.String.Escape,
        Token.Comment.Special,
        Token.Generic.Heading,
        Token.Generic.Subheading,
        Token.Generic.Emph,
        Token.Generic.Strong,
        Token.Generic.Prompt,
    })

    _TOKEN_ITALIC = frozenset({
        Token.Name.Constant,
        Token.Literal.String.Doc,
        Token.Comment,
        Token.Comment.Hashbang,
        Token.Comment.Multiline,
        Token.Comment.Preproc,
        Token.Comment.PreprocFile,
        Token.Comment.Single,
        Token.Comment.Special,
        Token.Generic.Emph,
    })
else:
    TOKEN_MAP = {}
    _TOKEN_BOLD = frozenset()
    _TOKEN_ITALIC = frozenset()


# ════════════════════════════════════════════════════════
#  公开接口
# ════════════════════════════════════════════════════════

def _color_map(theme_engine) -> dict:
    """构建 {Token: color} 映射。

    B2：优先消费 Theme v2 syntax palette（含 override）；v2 不可用时回退 v1
    ThemeColorScheme 的 syntax_* 属性。
    """
    v2_colors = v2_syntax_colors(theme_engine)
    if v2_colors:
        return {token: v2_colors.get(name) for token, name in TOKEN_MAP.items() if name in v2_colors}
    colors = theme_engine.get_active_theme().colors
    return {token: getattr(colors, name) for token, name in TOKEN_MAP.items() if hasattr(colors, name)}


def build_format(style: dict) -> QTextCharFormat:
    """从样式字典构建 QTextCharFormat"""
    fmt = QTextCharFormat()
    if "color" in style:
        fmt.setForeground(QColor(style["color"]))
    if style.get("bold"):
        fmt.setFontWeight(QFont.Weight.Bold)
    if style.get("italic"):
        fmt.setFontItalic(True)
    if style.get("underline"):
        fmt.setFontUnderline(True)
    return fmt


def _build_format_from_token(token, color_map) -> QTextCharFormat:
    """从 color_map 构建单个 Token 的 QTextCharFormat"""
    color = color_map.get(token)
    if color is None:
        return QTextCharFormat()
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if token in _TOKEN_BOLD:
        fmt.setFontWeight(QFont.Weight.Bold)
    if token in _TOKEN_ITALIC:
        fmt.setFontItalic(True)
    return fmt


# ════════════════════════════════════════════════════════
#  编辑器用：QTextCharFormat
# ════════════════════════════════════════════════════════

def get_editor_formats(theme_engine):
    """获取编辑器用的 {Token: QTextCharFormat} 字典

    Args:
        theme_engine: ThemeEngine 实例
    Returns:
        dict: {Token: QTextCharFormat}
    """
    if not HAS_PYGMENTS:
        return {}
    color_map = _color_map(theme_engine)
    return {token: _build_format_from_token(token, color_map) for token in TOKEN_MAP}


# ════════════════════════════════════════════════════════
#  预览用：CSS
# ════════════════════════════════════════════════════════

def _style_to_pygments_str(token, color_map) -> str:
    """从 color_map 构建单个 Token 的 Pygments style 字符串"""
    color = color_map.get(token)
    if color is None:
        return ""
    parts = []
    if token in _TOKEN_BOLD:
        parts.append("bold")
    if token in _TOKEN_ITALIC:
        parts.append("italic")
    parts.append(color)
    return " ".join(parts)


def get_preview_css(theme_engine, css_class="codehilite"):
    """生成 Markdown 预览用的代码高亮 CSS

    Args:
        theme_engine: ThemeEngine 实例
        css_class: codehilite 外层 CSS class 名
    Returns:
        str: CSS 文本；Pygments 不可用时返回空字符串
    """
    if not HAS_PYGMENTS:
        return ""
    color_map = _color_map(theme_engine)
    pygments_styles = {}
    for token in TOKEN_MAP:
        s = _style_to_pygments_str(token, color_map)
        if s:
            pygments_styles[token] = s
    if not pygments_styles:
        return ""
    CustomStyle = type("CustomStyle", (PygmentsStyle,), {
        "default_style": "",
        "styles": pygments_styles,
    })
    formatter = HtmlFormatter(style=CustomStyle)
    return formatter.get_style_defs(f".{css_class}")


# ════════════════════════════════════════════════════════
#  预览用：内联样式高亮（适用于 QTextBrowser）
# ════════════════════════════════════════════════════════

def _get_pygments_style_class(theme_engine):
    """从主题定义动态创建 Pygments Style 子类

    Returns:
        type | None: 继承 PygmentsStyle 的类；Pygments 不可用时返回 None
    """
    if not HAS_PYGMENTS:
        return None
    color_map = _color_map(theme_engine)
    pygments_styles = {}
    for token in TOKEN_MAP:
        s = _style_to_pygments_str(token, color_map)
        if s:
            pygments_styles[token] = s
    if not pygments_styles:
        return None
    return type("PanzerNoteStyle", (PygmentsStyle,), {
        "default_style": "",
        "styles": pygments_styles,
    })


def highlight_code_html(code: str, language: str, theme_engine) -> str:
    """将源代码高亮并返回包含内联样式的 HTML 片段

    Args:
        code:       原始源代码文本
        language:   编程语言名称（如 "python"、"javascript"），为空则不高亮
        theme_engine: ThemeEngine 实例
    Returns:
        str: 含内联样式的 HTML 文本；高亮失败时回退为 HTML 转义纯文本
    """
    import html as _html

    if not language or not language.strip():
        return _html.escape(code)

    if not HAS_PYGMENTS:
        return _html.escape(code)

    StyleClass = _get_pygments_style_class(theme_engine)
    if StyleClass is None:
        return _html.escape(code)

    try:
        from pygments.lexers import get_lexer_by_name
        from pygments import highlight as _pygments_highlight

        lexer = get_lexer_by_name(language.strip(), stripnl=False, stripall=False)
        formatter = HtmlFormatter(
            style=StyleClass,
            noclasses=True,
            nowrap=True,
        )
        result = cast(str, _pygments_highlight(code, lexer, formatter))
        if result.endswith('\n'):
            result = result[:-1]
        return result
    except Exception:
        get_logger(__name__).debug("代码高亮失败，回退到纯文本")
        return _html.escape(code)
