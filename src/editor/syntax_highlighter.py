# -*- coding: utf-8 -*-
"""
语法高亮模块
基于Pygments实现多语言语法高亮
配色方案由 highlight_themes.py 统一管理
"""

import re
from typing import Optional
from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QTextDocument

from ..utils.logger import get_logger

try:
    from pygments.lexers import get_lexer_for_filename, get_lexer_by_name
    from pygments.token import Token
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False

from .highlight_themes import get_editor_formats, get_theme, build_format


# ════════════════════════════════════════════════════════
#  Pygments 语法高亮器
# ════════════════════════════════════════════════════════

class PygmentsHighlighter(QSyntaxHighlighter):
    """基于Pygments的语法高亮器

    支持Python、C/C++、Java、JavaScript、JSON、HTML、CSS、XML等
    """

    def __init__(self, document: QTextDocument, lexer, theme_name=None):
        super().__init__(document)
        self._lexer = lexer
        self._formats = get_editor_formats(theme_name)

    def _get_format(self, token_type):
        """获取token类型对应的格式，沿继承链向上查找"""
        tt = token_type
        while tt:
            if tt in self._formats:
                return self._formats[tt]
            tt = tt.parent if hasattr(tt, 'parent') else None
        return None

    def highlightBlock(self, text: Optional[str]):
        """高亮单行文本"""
        if not text:
            return
        try:
            tokens = self._lexer.get_tokens(text)
            offset = 0
            for token_type, value in tokens:
                length = len(value)
                fmt = self._get_format(token_type)
                if fmt:
                    self.setFormat(offset, length, fmt)
                offset += length
        except Exception:
            get_logger(__name__).debug("Pygments 词法分析失败")


# ════════════════════════════════════════════════════════
#  Markdown 语法高亮器（内置，仿 PyCharm 编辑器风格）
# ════════════════════════════════════════════════════════

class MarkdownHighlighter(QSyntaxHighlighter):
    """Markdown语法高亮器 —— 仿 JetBrains / PyCharm 编辑器风格

    支持跨行代码块（通过 QSyntaxHighlighter 的 block state 机制）
    支持明/暗两套配色方案
    """

    STATE_NORMAL = -1
    STATE_CODE_BLOCK = 1

    _FALLBACK_LIGHT_COLORS = {
        "h1_fg": "#000000",
        "h2_fg": "#000000",
        "h3_fg": "#000000",
        "h456_fg": "#2b2b2b",
        "bold_fg": "#2b2b2b",
        "italic_fg": "#2b2b2b",
        "code_fg": "#008000",
        "code_bg": "#f2f2f2",
        "link_fg": "#2470B3",
        "image_fg": "#6A1B9A",
        "list_fg": "#2b2b2b",
        "quote_fg": "#808080",
        "hr_fg": "#AAAAAA",
        "fence_fg": "#808080",
        "code_block_fg": "#2b2b2b",
        "code_block_bg": "#f5f5f5",
    }

    _FALLBACK_DARK_COLORS = {
        "h1_fg": "#E0E0E0",
        "h2_fg": "#E0E0E0",
        "h3_fg": "#E0E0E0",
        "h456_fg": "#D4D4D4",
        "bold_fg": "#D4D4D4",
        "italic_fg": "#D4D4D4",
        "code_fg": "#CE9178",
        "code_bg": "#2D2D2D",
        "link_fg": "#569CD6",
        "image_fg": "#C586C0",
        "list_fg": "#D4D4D4",
        "quote_fg": "#6A9955",
        "hr_fg": "#555555",
        "fence_fg": "#A0A0A0",
        "code_block_fg": "#D4D4D4",
        "code_block_bg": "#2D2D30",
    }

    def __init__(self, document: QTextDocument, is_dark: bool = False, theme_engine=None):
        super().__init__(document)
        self._is_dark = is_dark
        self._theme_engine = theme_engine
        self._init_formats(is_dark)
        self._fence_re = re.compile(r'^```')

    def _init_formats(self, is_dark: bool):
        """初始化所有格式"""
        fallback_colors = self._FALLBACK_DARK_COLORS if is_dark else self._FALLBACK_LIGHT_COLORS
        theme_colors = None
        if self._theme_engine:
            theme_colors = self._theme_engine.get_active_theme().colors

        def get_color(key: str) -> str:
            if theme_colors is not None:
                token_key = f"md_{key}"
                if hasattr(theme_colors, token_key):
                    return str(getattr(theme_colors, token_key))
            return fallback_colors.get(key, "#000000")

        self.inline_rules = []

        h1_fmt = QTextCharFormat()
        h1_fmt.setForeground(QColor(get_color("h1_fg")))
        h1_fmt.setFontWeight(QFont.Weight.Bold)
        h1_fmt.setFontPointSize(20)
        self.h1_format = h1_fmt

        h2_fmt = QTextCharFormat()
        h2_fmt.setForeground(QColor(get_color("h2_fg")))
        h2_fmt.setFontWeight(QFont.Weight.Bold)
        h2_fmt.setFontPointSize(17)
        self.h2_format = h2_fmt

        h3_fmt = QTextCharFormat()
        h3_fmt.setForeground(QColor(get_color("h3_fg")))
        h3_fmt.setFontWeight(QFont.Weight.Bold)
        h3_fmt.setFontPointSize(14)
        self.h3_format = h3_fmt

        h456_fmt = QTextCharFormat()
        h456_fmt.setForeground(QColor(get_color("h456_fg")))
        h456_fmt.setFontWeight(QFont.Weight.Bold)
        h456_fmt.setFontPointSize(12)
        self.h456_format = h456_fmt

        bold_fmt = QTextCharFormat()
        bold_fmt.setFontWeight(QFont.Weight.Bold)
        bold_fmt.setForeground(QColor(get_color("bold_fg")))
        self.inline_rules.append((re.compile(r'\*\*[^*]+\*\*'), bold_fmt))
        self.inline_rules.append((re.compile(r'__[^_]+__'), bold_fmt))

        italic_fmt = QTextCharFormat()
        italic_fmt.setFontItalic(True)
        italic_fmt.setForeground(QColor(get_color("italic_fg")))
        self.inline_rules.append((re.compile(r'(?<!\*)\*[^*]+\*(?!\*)'), italic_fmt))
        self.inline_rules.append((re.compile(r'(?<!_)_[^_]+_(?!_)'), italic_fmt))

        code_fmt = QTextCharFormat()
        code_fmt.setForeground(QColor(get_color("code_fg")))
        code_fmt.setFontFamily("Consolas")
        code_fmt.setBackground(QColor(get_color("code_bg")))
        self.inline_rules.append((re.compile(r'`[^`\n]+`'), code_fmt))

        link_fmt = QTextCharFormat()
        link_fmt.setForeground(QColor(get_color("link_fg")))
        link_fmt.setFontUnderline(True)
        self.inline_rules.append((re.compile(r'\[([^\]]+)\]\([^\)]+\)'), link_fmt))

        img_fmt = QTextCharFormat()
        img_fmt.setForeground(QColor(get_color("image_fg")))
        self.inline_rules.append((re.compile(r'!\[([^\]]*)\]\([^\)]+\)'), img_fmt))

        list_fmt = QTextCharFormat()
        list_fmt.setForeground(QColor(get_color("list_fg")))
        list_fmt.setFontWeight(QFont.Weight.Bold)
        self.inline_rules.append((re.compile(r'^\s*[-*+]\s'), list_fmt))
        self.inline_rules.append((re.compile(r'^\s*\d+\.\s'), list_fmt))

        quote_fmt = QTextCharFormat()
        quote_fmt.setForeground(QColor(get_color("quote_fg")))
        quote_fmt.setFontItalic(True)
        self.inline_rules.append((re.compile(r'^>\s.*$'), quote_fmt))

        hr_fmt = QTextCharFormat()
        hr_fmt.setForeground(QColor(get_color("hr_fg")))
        self.inline_rules.append((re.compile(r'^[-*_]{3,}\s*$'), hr_fmt))

        self.fence_format = QTextCharFormat()
        self.fence_format.setForeground(QColor(get_color("fence_fg")))
        self.fence_format.setFontFamily("Consolas")

        self.code_block_format = QTextCharFormat()
        self.code_block_format.setForeground(QColor(get_color("code_block_fg")))
        self.code_block_format.setFontFamily("Consolas")
        self.code_block_format.setBackground(QColor(get_color("code_block_bg")))

    def set_dark_mode(self, is_dark: bool):
        """切换明/暗主题，重新高亮文档"""
        if is_dark == self._is_dark:
            return
        self._is_dark = is_dark
        self._init_formats(is_dark)
        # 触发重新高亮
        doc = self.document()
        if doc:
            self.rehighlight()

    def highlightBlock(self, text: Optional[str]):
        if text is None:
            return
        prev_state = self.previousBlockState()

        if prev_state == self.STATE_CODE_BLOCK:
            if self._fence_re.match(text):
                self.setFormat(0, len(text), self.fence_format)
                self.setCurrentBlockState(self.STATE_NORMAL)
            else:
                self.setFormat(0, len(text), self.code_block_format)
                self.setCurrentBlockState(self.STATE_CODE_BLOCK)
            return

        if self._fence_re.match(text):
            self.setFormat(0, len(text), self.fence_format)
            self.setCurrentBlockState(self.STATE_CODE_BLOCK)
            return

        self.setCurrentBlockState(self.STATE_NORMAL)

        stripped = text.lstrip()
        if stripped.startswith('#'):
            if stripped.startswith('# ') or stripped == '#':
                self.setFormat(0, len(text), self.h1_format)
                return
            elif stripped.startswith('## ') or stripped == '##':
                self.setFormat(0, len(text), self.h2_format)
                return
            elif stripped.startswith('### ') or stripped == '###':
                self.setFormat(0, len(text), self.h3_format)
                return
            elif re.match(r'^#{4,6}\s', stripped) or re.match(r'^#{4,6}$', stripped):
                self.setFormat(0, len(text), self.h456_format)
                return

        for pattern, fmt in self.inline_rules:
            for match in pattern.finditer(text):
                start = match.start()
                length = match.end() - start
                self.setFormat(start, length, fmt)


# ════════════════════════════════════════════════════════
#  工厂函数
# ════════════════════════════════════════════════════════

def get_highlighter_for_file(document: QTextDocument, filepath_or_ext: str,
                             theme_name=None, is_dark: bool = False, theme_engine=None):
    """根据文件类型获取合适的高亮器

    Args:
        document: QTextDocument
        filepath_or_ext: 文件路径或扩展名
        theme_name: 主题名称（None 使用默认）
        is_dark: 是否为暗色主题
        theme_engine: ThemeEngine 实例，用于 Markdown 高亮主题 token 取值
    Returns:
        (highlighter | None, file_type_str)
    """
    import os

    if filepath_or_ext.startswith('.'):
        ext = filepath_or_ext.lower()
        filename = "file" + ext
    else:
        ext = os.path.splitext(filepath_or_ext)[1].lower()
        filename = os.path.basename(filepath_or_ext)

    EXT_TO_TYPE = {
        '.md': 'Markdown', '.markdown': 'Markdown',
        '.py': 'Python', '.pyw': 'Python',
        '.c': 'C', '.h': 'C',
        '.cpp': 'C++', '.hpp': 'C++', '.cc': 'C++', '.cxx': 'C++',
        '.java': 'Java',
        '.js': 'JavaScript', '.jsx': 'JavaScript',
        '.ts': 'TypeScript', '.tsx': 'TypeScript',
        '.json': 'JSON',
        '.html': 'HTML', '.htm': 'HTML',
        '.css': 'CSS',
        '.xml': 'XML',
        '.sql': 'SQL',
        '.sh': 'Shell', '.bash': 'Shell',
        '.bat': 'Batch', '.cmd': 'Batch',
        '.yaml': 'YAML', '.yml': 'YAML',
        '.toml': 'TOML',
        '.ini': 'INI', '.cfg': 'INI',
        '.lua': 'Lua',
        '.rb': 'Ruby',
        '.go': 'Go',
        '.rs': 'Rust',
        '.swift': 'Swift',
        '.kt': 'Kotlin',
        '.r': 'R',
        '.txt': '纯文本',
        '': '纯文本',
    }

    file_type = EXT_TO_TYPE.get(ext, '纯文本')

    if file_type == 'Markdown':
        return MarkdownHighlighter(document, is_dark=is_dark, theme_engine=theme_engine), file_type

    if file_type == '纯文本':
        return None, file_type

    if HAS_PYGMENTS:
        try:
            lexer = get_lexer_for_filename(filename, stripnl=False, stripall=False)
            return PygmentsHighlighter(document, lexer, theme_name), file_type
        except Exception:
            get_logger(__name__).debug("无法为文件 %s 创建 Pygments 高亮器", filename)

    return None, file_type
