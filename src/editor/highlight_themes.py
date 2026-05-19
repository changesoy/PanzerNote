# -*- coding: utf-8 -*-
"""
代码高亮主题管理模块
统一管理编辑器（左侧）和 Markdown 预览（右侧）的代码配色方案

使用方式：
    编辑器：  get_editor_formats(theme_name) → {Token: QTextCharFormat}
    预览CSS： get_preview_css(theme_name)     → str (注入到 HTML <style>)

在 settings.json → editor.code_highlight_theme 中切换主题。
新增主题只需在 THEMES 字典中增加一个条目即可。
"""

from PyQt6.QtGui import QTextCharFormat, QColor, QFont

from ..utils.logger import get_logger

try:
    from pygments.token import Token
    from pygments.style import Style as PygmentsStyle
    from pygments.formatters import HtmlFormatter
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False


# ════════════════════════════════════════════════════════
#  主题定义
#  每个主题包含 name / description / styles 三个字段
#  styles 为 {Token: {"color","bold","italic","underline","background"}} 字典
# ════════════════════════════════════════════════════════

if HAS_PYGMENTS:
    THEMES = {
        # ────── PyCharm / IntelliJ Light ──────
        "pycharm_light": {
            "name": "PyCharm Light",
            "description": "仿 JetBrains IntelliJ / PyCharm Light 主题",
            "styles": {
                # ── 关键字 ── 深蓝加粗
                Token.Keyword:                  {"color": "#0033B3", "bold": True},
                Token.Keyword.Constant:         {"color": "#0033B3", "bold": True},
                Token.Keyword.Declaration:      {"color": "#0033B3", "bold": True},
                Token.Keyword.Namespace:        {"color": "#0033B3", "bold": True},
                Token.Keyword.Pseudo:           {"color": "#0033B3", "bold": True},
                Token.Keyword.Reserved:         {"color": "#0033B3", "bold": True},
                Token.Keyword.Type:             {"color": "#0033B3"},

                # ── 名称 ──
                Token.Name.Builtin:             {"color": "#8000FF"},
                Token.Name.Builtin.Pseudo:      {"color": "#94558D"},
                Token.Name.Class:               {"color": "#000000", "bold": True},
                Token.Name.Function:            {"color": "#00627A"},
                Token.Name.Function.Magic:      {"color": "#00627A"},
                Token.Name.Decorator:           {"color": "#BBB529"},
                Token.Name.Exception:           {"color": "#000000", "bold": True},
                Token.Name.Tag:                 {"color": "#000080"},
                Token.Name.Attribute:           {"color": "#660E7A"},
                Token.Name.Namespace:           {"color": "#000000"},
                Token.Name.Variable:            {"color": "#660E7A"},
                Token.Name.Variable.Class:      {"color": "#660E7A"},
                Token.Name.Variable.Global:     {"color": "#660E7A"},
                Token.Name.Variable.Instance:   {"color": "#660E7A"},
                Token.Name.Constant:            {"color": "#660E7A", "italic": True},
                Token.Name.Label:               {"color": "#000000"},
                Token.Name.Entity:              {"color": "#660E7A"},

                # ── 字面量：字符串 ── 绿色
                Token.Literal.String:           {"color": "#067D17"},
                Token.Literal.String.Affix:     {"color": "#0033B3", "bold": True},
                Token.Literal.String.Backtick:  {"color": "#067D17"},
                Token.Literal.String.Char:      {"color": "#067D17"},
                Token.Literal.String.Delimiter: {"color": "#067D17"},
                Token.Literal.String.Doc:       {"color": "#067D17", "italic": True},
                Token.Literal.String.Double:    {"color": "#067D17"},
                Token.Literal.String.Escape:    {"color": "#0037A6", "bold": True},
                Token.Literal.String.Heredoc:   {"color": "#067D17"},
                Token.Literal.String.Interpol:  {"color": "#0033B3", "bold": True},
                Token.Literal.String.Other:     {"color": "#067D17"},
                Token.Literal.String.Regex:     {"color": "#067D17"},
                Token.Literal.String.Single:    {"color": "#067D17"},
                Token.Literal.String.Symbol:    {"color": "#067D17"},

                # ── 字面量：数字 ── 蓝色
                Token.Literal.Number:           {"color": "#1750EB"},
                Token.Literal.Number.Bin:       {"color": "#1750EB"},
                Token.Literal.Number.Float:     {"color": "#1750EB"},
                Token.Literal.Number.Hex:       {"color": "#1750EB"},
                Token.Literal.Number.Integer:   {"color": "#1750EB"},
                Token.Literal.Number.Integer.Long: {"color": "#1750EB"},
                Token.Literal.Number.Oct:       {"color": "#1750EB"},

                # ── 注释 ── 灰色斜体
                Token.Comment:                  {"color": "#8C8C8C", "italic": True},
                Token.Comment.Hashbang:         {"color": "#8C8C8C", "italic": True},
                Token.Comment.Multiline:        {"color": "#8C8C8C", "italic": True},
                Token.Comment.Preproc:          {"color": "#8C8C8C", "italic": True},
                Token.Comment.PreprocFile:      {"color": "#8C8C8C", "italic": True},
                Token.Comment.Single:           {"color": "#8C8C8C", "italic": True},
                Token.Comment.Special:          {"color": "#8C8C8C", "italic": True, "bold": True},

                # ── 运算符 / 标点 ──
                Token.Operator:                 {"color": "#000000"},
                Token.Operator.Word:            {"color": "#0033B3", "bold": True},
                Token.Punctuation:              {"color": "#000000"},

                # ── 泛型 ──
                Token.Generic.Heading:          {"color": "#000000", "bold": True},
                Token.Generic.Subheading:       {"color": "#000000", "bold": True},
                Token.Generic.Emph:             {"italic": True},
                Token.Generic.Strong:           {"bold": True},
                Token.Generic.Deleted:          {"color": "#A31515"},
                Token.Generic.Inserted:         {"color": "#067D17"},
                Token.Generic.Error:            {"color": "#FF0000"},
                Token.Generic.Traceback:        {"color": "#FF0000"},
                Token.Generic.Output:           {"color": "#2b2b2b"},
                Token.Generic.Prompt:           {"color": "#000000", "bold": True},

                # ── 其他 ──
                Token.Text:                     {"color": "#2b2b2b"},
                Token.Error:                    {"color": "#FF0000"},
            }
        },
    }
else:
    THEMES = {}

DEFAULT_THEME = "pycharm_light"


# ════════════════════════════════════════════════════════
#  公开接口
# ════════════════════════════════════════════════════════

def get_available_themes():
    """返回可用主题名称列表

    Returns:
        list[str]: 如 ["pycharm_light"]
    """
    return list(THEMES.keys())


def get_theme(name=None):
    """获取主题样式字典 {Token: style_dict}

    Args:
        name: 主题名称，None 则使用默认
    Returns:
        dict: {Token: {"color": ..., "bold": ..., ...}}
    """
    if not HAS_PYGMENTS:
        return {}
    name = name or DEFAULT_THEME
    theme = THEMES.get(name, THEMES.get(DEFAULT_THEME, {}))
    return theme.get("styles", {})


def get_theme_info(name=None):
    """获取主题元信息

    Returns:
        dict: {"name": "...", "description": "..."}
    """
    name = name or DEFAULT_THEME
    theme = THEMES.get(name, {})
    return {
        "name": theme.get("name", name),
        "description": theme.get("description", ""),
    }


# ════════════════════════════════════════════════════════
#  编辑器用：QTextCharFormat
# ════════════════════════════════════════════════════════

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


def get_editor_formats(theme_name=None):
    """获取编辑器用的 {Token: QTextCharFormat} 字典

    Args:
        theme_name: 主题名称，None 使用默认
    Returns:
        dict: {Token: QTextCharFormat}
    """
    styles = get_theme(theme_name)
    return {token: build_format(style) for token, style in styles.items()}


# ════════════════════════════════════════════════════════
#  预览用：CSS
# ════════════════════════════════════════════════════════

def _style_dict_to_pygments_str(style_dict):
    """将 style_dict 转换为 Pygments Style 字符串格式

    示例: {"color": "#0033B3", "bold": True} → "bold #0033B3"
    """
    parts = []
    if style_dict.get("bold"):
        parts.append("bold")
    if style_dict.get("italic"):
        parts.append("italic")
    if style_dict.get("underline"):
        parts.append("underline")
    if "color" in style_dict:
        parts.append(style_dict["color"])
    if "background" in style_dict:
        parts.append(f"bg:{style_dict['background']}")
    return " ".join(parts)


def get_preview_css(theme_name=None, css_class="codehilite"):
    """生成 Markdown 预览用的代码高亮 CSS

    通过 Pygments HtmlFormatter 自动将主题映射为
    ``.codehilite .xx`` 选择器的 CSS 规则。

    Args:
        theme_name: 主题名称
        css_class: codehilite 外层 CSS class 名
    Returns:
        str: CSS 文本；Pygments 不可用时返回空字符串
    """
    if not HAS_PYGMENTS:
        return ""

    styles = get_theme(theme_name)
    if not styles:
        return ""

    # 动态创建 Pygments Style 子类
    pygments_styles = {}
    for token, style_dict in styles.items():
        pygments_styles[token] = _style_dict_to_pygments_str(style_dict)

    CustomStyle = type("CustomStyle", (PygmentsStyle,), {
        "default_style": "",
        "styles": pygments_styles,
    })

    formatter = HtmlFormatter(style=CustomStyle)
    return formatter.get_style_defs(f".{css_class}")


# ════════════════════════════════════════════════════════
#  预览用：内联样式高亮（适用于 QTextBrowser）
# ════════════════════════════════════════════════════════

def _get_pygments_style_class(theme_name=None):
    """从主题定义动态创建 Pygments Style 子类

    Returns:
        type | None: 继承 PygmentsStyle 的类；Pygments 不可用时返回 None
    """
    if not HAS_PYGMENTS:
        return None

    styles = get_theme(theme_name)
    if not styles:
        return None

    pygments_styles = {}
    for token, style_dict in styles.items():
        pygments_styles[token] = _style_dict_to_pygments_str(style_dict)

    return type("PanzerNoteStyle", (PygmentsStyle,), {
        "default_style": "",
        "styles": pygments_styles,
    })


def highlight_code_html(code: str, language: str, theme_name=None) -> str:
    """将源代码高亮并返回包含内联样式的 HTML 片段

    生成 ``<span style="...">`` 标签，无需外部 CSS，
    可在 QTextBrowser 和 QWebEngineView 中直接渲染。

    Args:
        code:       原始源代码文本
        language:   编程语言名称（如 "python"、"javascript"），为空则不高亮
        theme_name: 主题名称，None 使用默认
    Returns:
        str: 含内联样式的 HTML 文本；高亮失败时回退为 HTML 转义纯文本
    """
    import html as _html

    if not language or not language.strip():
        return _html.escape(code)

    if not HAS_PYGMENTS:
        return _html.escape(code)

    StyleClass = _get_pygments_style_class(theme_name)
    if StyleClass is None:
        return _html.escape(code)

    try:
        from pygments.lexers import get_lexer_by_name
        from pygments import highlight as _pygments_highlight

        lexer = get_lexer_by_name(language.strip(), stripnl=False, stripall=False)
        formatter = HtmlFormatter(
            style=StyleClass,
            noclasses=True,   # 生成内联 style 而非 CSS class
            nowrap=True,      # 不包裹 <pre>/<div>，我们自己控制容器
        )
        result = _pygments_highlight(code, lexer, formatter)
        # 移除 Pygments 附加的尾部换行
        if result.endswith('\n'):
            result = result[:-1]
        return result
    except Exception:
        get_logger(__name__).debug("代码高亮失败，回退到纯文本")
        return _html.escape(code)
