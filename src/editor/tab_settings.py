# -*- coding: utf-8 -*-
"""EditorTabWidget 批量设置 mixin（从 editor_tabs.py 拆出，纯结构重构不改行为）。

职责：把设置项广播到本面板全部编辑器 / 预览（行宽 / 预览行宽 / 缩略图 /
行号 / 当前行高亮 / 补全 / 字体 / 代码字体 / 行距 / 预览排版 / 缩进宽度），
以及遍历辅助 _iter_editors。

组合契约：本 mixin 由 EditorTabWidget 组合。方法体访问的跨职责方法在
``_EditorTabWidgetContract`` 中以**裸 Callable 类型注解**声明——运行时由
EditorTabWidget 实际实现；本模块不初始化任何状态。裸注解不产生类属性，
任意 MRO 顺序下都不会遮蔽真实现（见 E3 踩坑记录）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from PyQt6.QtWidgets import QTabWidget

from .markdown_preview import MarkdownPreviewWidget

if TYPE_CHECKING:
    from .editor import Editor


class _EditorTabWidgetContract(QTabWidget):
    """EditorTabWidget 组合 TabSettingsMixin 时必须提供的状态与方法。

    继承 QTabWidget 仅为补齐 Qt 基类能力；运行时不实例化、不初始化任何状态。
    方法一律裸 Callable 注解（见模块 docstring）。
    """

    _get_editor_from_widget: Callable[..., Optional[Editor]]


class TabSettingsMixin(_EditorTabWidgetContract):
    """批量设置职责：设置项广播 + 编辑器遍历。"""

    def _iter_editors(self):
        for i in range(self.count()):
            widget = self.widget(i)
            editor = self._get_editor_from_widget(widget)
            if editor:
                yield editor


    def set_wrap_mode_all(self, mode: str):
        for editor in self._iter_editors():
            editor.set_wrap_mode(mode)

    def set_preview_wrap_mode_all(self, mode: str):
        """把「预览行宽」设置广播到所有 Markdown 预览（与编辑区行宽互不影响）。"""
        for i in range(self.count()):
            widget = self.widget(i)
            if isinstance(widget, MarkdownPreviewWidget):
                widget.set_preview_wrap_mode(mode)


    def set_minimap_all(self, visible: bool):
        for editor in self._iter_editors():
            editor.set_minimap_visible(visible)

    def minimap_visible(self) -> Optional[bool]:
        """本面板第一个编辑器的缩略图可见性；无编辑器返回 None。

        作为全局切换（ViewCoordinator.toggle_minimap）的基准状态读取。
        """
        for editor in self._iter_editors():
            return bool(editor.is_minimap_visible())
        return None

    def md_preview_visible(self) -> Optional[bool]:
        """本面板第一个 Markdown 预览标签的预览可见性；无预览标签返回 None。

        作为全局切换（ViewCoordinator.toggle_md_preview）的基准状态读取。
        """
        for i in range(self.count()):
            widget = self.widget(i)
            if isinstance(widget, MarkdownPreviewWidget):
                return widget.is_preview_visible()
        return None

    def set_md_preview_visible_all(self, visible: bool):
        """把预览显隐广播到本面板全部 Markdown 预览标签（全局切换语义）。"""
        for i in range(self.count()):
            widget = self.widget(i)
            if isinstance(widget, MarkdownPreviewWidget):
                widget.set_preview_visible(visible)

    def apply_auto_minimap_all(self):
        for editor in self._iter_editors():
            editor.apply_auto_minimap()

    def set_line_numbers_all(self, show: bool):
        for editor in self._iter_editors():
            editor.set_show_line_numbers(show)

    def set_highlight_current_line_all(self, enabled: bool):
        for editor in self._iter_editors():
            editor.set_highlight_current_line(enabled)

    def set_completion_enabled_all(self, enabled: bool) -> None:
        """对所有已打开编辑器应用补全开关。"""
        for editor in self._iter_editors():
            editor.set_completion_enabled(enabled)

    def set_font_all(self, family: str, size: int):
        for editor in self._iter_editors():
            editor.set_editor_font(family, size)

    def set_code_font_all(self, family: str):
        """对所有已打开编辑器应用「代码字体」（编辑器侧改 Markdown 高亮器的
        代码 format；预览侧见 refresh_preview_typography_all）。
        """
        for editor in self._iter_editors():
            editor.set_code_font(family)

    def set_line_spacing_all(self, spacing: float):
        """对所有已打开编辑器应用「正文行距」。

        编辑器内正文与代码块不区分（同一文本流按块设行距，切分代码块代价高），
        代码块行距只作用于预览与导出，见 refresh_preview_typography_all。
        """
        for editor in self._iter_editors():
            editor.set_line_spacing(spacing)

    def refresh_preview_typography_all(self):
        """刷新所有 Markdown 预览的排版 CSS（代码字体 / 正文行距 / 代码块行距）。

        这三项只存在于 CSS：已加载的预览就地更新变量，未加载的由首屏整页灌入。
        三者共用一次刷新，避免设置应用时重复整页重建。
        """
        for i in range(self.count()):
            widget = self.widget(i)
            if isinstance(widget, MarkdownPreviewWidget):
                widget.refresh_typography_settings()

    def update_indent_settings_all(self):
        """缩进配置变更后，更新所有已打开编辑器的 Tab 显示宽度"""
        from .indentation import get_indent_width
        for editor in self._iter_editors():
            font_metrics = editor.fontMetrics()
            tab_width = font_metrics.horizontalAdvance(' ') * get_indent_width(editor.config)
            editor.setTabStopDistance(tab_width)
