# -*- coding: utf-8 -*-
"""PanzerNote 帮助中心：使用说明与新手攻略。

文案存放于 data/help/*.md（数据文件，不硬编码在代码里），
经 secure_markdown_renderer 安全渲染后展示；
配色消费 Theme v2 token，随主题深浅色自动更新。
"""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
)

from ..editor.secure_markdown_renderer import render_markdown_to_safe_html
from ..themes.theme_aware_mixin import ThemeAwareMixin
from ..themes.theme_v2.consumer import v2_token
from ..utils.logger import get_logger

_PAGES = (
    ("manual", "使用说明"),
    ("guide", "新手攻略"),
)

# 文档缺失时的占位片段（token 无关，纯结构）
_MISSING_FRAGMENT = "<p>帮助文档缺失。请检查程序目录下 data/help/ 是否完整。</p>"


def _load_help_fragment(app_dir: str, page_id: str) -> str:
    """读取 data/help/{page_id}.md 并渲染为安全 HTML 片段（不含外层标签）。"""
    path = os.path.join(app_dir, "data", "help", f"{page_id}.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            markdown_text = f.read()
    except OSError as e:
        get_logger(__name__).warning("帮助文档加载失败: %s, 错误: %s", path, e)
        return _MISSING_FRAGMENT
    return render_markdown_to_safe_html(markdown_text)


class HelpDialog(ThemeAwareMixin, QDialog):
    """显示使用说明和新手攻略两个职责独立的帮助页面。"""

    def __init__(self, app_dir: str, theme_engine, initial_page: str = "manual", parent=None):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("HelpDialog 必须传入 theme_engine，不允许为 None")
        self.setWindowTitle("PanzerNote 帮助中心")
        self.setMinimumSize(720, 560)
        self.resize(820, 640)

        # page_id -> (browser, 安全 HTML 片段)；片段保存供主题刷新时重建完整 HTML
        self._pages: dict[str, tuple[QTextBrowser, str]] = {}
        self._tabs = QTabWidget(self)
        for page_id, title in _PAGES:
            fragment = _load_help_fragment(app_dir, page_id)
            browser = QTextBrowser()
            browser.setOpenExternalLinks(False)
            browser.setReadOnly(True)
            browser.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self._pages[page_id] = (browser, fragment)
            self._tabs.addTab(browser, title)
        self._tabs.setCurrentIndex(1 if initial_page == "guide" else 0)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(self._tabs)
        layout.addWidget(buttons)

        self._init_theme(theme_engine)

    def _apply_theme_colors(self):
        """页面配色消费 v2 token，主题切换时重建 HTML 与控件样式。"""
        bg = v2_token(self._theme_engine, "surface_primary", "#FFFFFF")
        fg = v2_token(self._theme_engine, "text_primary", "#212121")
        fg_secondary = v2_token(self._theme_engine, "text_secondary", "#757575")
        border = v2_token(self._theme_engine, "border_muted", "#E0E0E0")
        accent = v2_token(self._theme_engine, "accent", "#2196F3")
        code_bg = v2_token(self._theme_engine, "md_code_bg", "#F5F5F5")
        code_fg = v2_token(self._theme_engine, "md_code_fg", "#C7254E")

        css = f"""
body {{
    background-color: {bg};
    color: {fg};
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 14px;
    line-height: 1.6;
}}
h1, h2, h3 {{ color: {fg}; }}
h2 {{
    border-bottom: 1px solid {border};
    padding-bottom: 4px;
}}
a {{ color: {accent}; }}
code {{
    background-color: {code_bg};
    color: {code_fg};
    border-radius: 3px;
    padding: 1px 4px;
}}
pre code {{
    display: block;
    padding: 8px;
}}
hr {{ border: none; border-top: 1px solid {border}; }}
li {{ color: {fg}; }}
p {{ color: {fg}; }}
span.secondary {{ color: {fg_secondary}; }}
"""

        for tab_browser, fragment in self._pages.values():
            tab_browser.setStyleSheet(
                f"QTextBrowser {{ background-color: {bg}; color: {fg};"
                f" border: 1px solid {border}; }}"
            )
            tab_browser.setHtml(
                f"<html><head><style>{css}</style></head><body>{fragment}</body></html>"
            )
