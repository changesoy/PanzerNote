"""基于文档缓冲区的自动补全。

从当前打开的文档中提取已出现的词语，根据光标前缀提供补全候选。
通过轻量级弹框展示，支持 Tab/Enter 接受、Esc 关闭，IME 输入法期间不弹出。
"""

from __future__ import annotations

import re
from typing import Dict, List

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QKeyEvent
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QWidget

from ..themes.theme_engine import ThemeEngine
from ..themes.theme_v2.consumer import v2_color, v2_token

# 词语提取正则：字母/数字/下划线 + 中日韩统一表意文字
_WORD_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]|[a-zA-Z0-9_]{2,}")


class CompletionPopup(QListWidget):
    """自动补全弹框。

    以 ToolTip 形式浮于编辑器上方，不抢夺焦点。
    """

    item_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("CompletionPopup")
        self.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        )
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMaximumHeight(180)
        self.setMinimumWidth(200)
        self._is_visible = False
        self.itemDoubleClicked.connect(self._on_accept)
        # _rebuild_qss() 的两路输入：主题色（apply_theme_colors）与条目
        # 行高（apply_font）。任一更新都整体重建样式表，不做增量拼接。
        self._theme_engine: ThemeEngine | None = None
        self._item_min_height = 22

    def apply_theme_colors(self, theme_engine: ThemeEngine) -> None:
        """应用自动补全弹窗主题颜色。

        由 Editor._apply_theme_colors() 调用。
        CompletionPopup 是无父顶层浮窗，不依赖主窗口 QSS 级联，
        样式优先消费 v2 recipe（tooltip / scrollbar / tree_item）。
        """
        self._theme_engine = theme_engine
        self._rebuild_qss()

    def apply_font(self, font_family: str, font_size: int) -> None:
        """同步编辑器的字体和行高到补全弹窗。

        由 Editor._apply_theme_colors() 调用。
        补全弹窗字号为编辑器的 0.8 倍，行间距按 1.1 倍字号计算。
        """
        popup_font_size = max(2, int(font_size * 0.8))
        self.setFont(QFont(font_family, popup_font_size))
        # QSS 的 ::item 不支持 margin，用 setSpacing() 控制选项间隙
        self.setSpacing(1)
        self._item_min_height = int(popup_font_size * 1.1)
        self._rebuild_qss()

    def _rebuild_qss(self) -> None:
        """从当前主题色与条目行高整体重建样式表。"""
        if self._theme_engine is None:
            return
        engine = self._theme_engine
        # 弹层容器吃 tooltip recipe；滚动条吃 scrollbar recipe；条目 hover
        # 用 surface_secondary（弹窗背景是 surface_raised，同色 hover 不可见）。
        # 选中色走 accent_soft token（B8：= v1 primary_light）。
        bg = v2_color(engine, "tooltip", "background", "#FFFFFF")
        fg = v2_color(engine, "tooltip", "text", "#212121")
        border = v2_color(engine, "tooltip", "border", "#E0E0E0")
        hover_bg = v2_token(engine, "surface_secondary", "#F5F5F5")
        sel_bg = v2_token(engine, "accent_soft", "#BBDEFB")
        sb_track = v2_color(engine, "scrollbar", "track", "#F5F5F5")
        sb_handle = v2_color(engine, "scrollbar", "handle", "#E0E0E0")
        sb_handle_hover = v2_color(engine, "scrollbar", "handle_hover",
                                   "#BDBDBD")
        self.setStyleSheet(f"""
    QListWidget#CompletionPopup {{
        background-color: {bg};
        color: {fg};
        border: 1px solid {border};
        border-radius: 4px;
        padding: 2px;
        outline: none;
        selection-background-color: {sel_bg};
        selection-color: {fg};
    }}

    QListWidget#CompletionPopup::item {{
        color: {fg};
        background: transparent;
        padding: 4px 8px;
        min-height: {self._item_min_height}px;
        border-radius: 3px;
    }}

    QListWidget#CompletionPopup::item:hover {{
        background-color: {hover_bg};
        color: {fg};
    }}

    QListWidget#CompletionPopup::item:selected {{
        background-color: {sel_bg};
        color: {fg};
    }}

    QListWidget#CompletionPopup::item:selected:active {{
        background-color: {sel_bg};
        color: {fg};
    }}

    QListWidget#CompletionPopup::item:selected:!active {{
        background-color: {sel_bg};
        color: {fg};
    }}

    QScrollBar:vertical {{
        background-color: {sb_track};
        width: 10px;
        margin: 0;
    }}

    QScrollBar::handle:vertical {{
        background-color: {sb_handle};
        border-radius: 5px;
        min-height: 20px;
        margin: 2px;
    }}

    QScrollBar::handle:vertical:hover {{
        background-color: {sb_handle_hover};
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QScrollBar:horizontal {{
        background-color: {sb_track};
        height: 10px;
        margin: 0;
    }}

    QScrollBar::handle:horizontal {{
        background-color: {sb_handle};
        border-radius: 5px;
        min-width: 20px;
        margin: 2px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background-color: {sb_handle_hover};
    }}

    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {{
        width: 0;
    }}
    """)

    # ---- 显示控制 ----

    def show_at(self, pos: QPoint) -> None:
        if self.count() == 0:
            self.hide()
            return
        self.setCurrentRow(0)
        self.move(pos)
        self.show()
        self._is_visible = True

    def hide(self) -> None:
        super().hide()
        self._is_visible = False

    @property
    def visible(self) -> bool:
        return self._is_visible

    # ---- 候选刷新 ----

    def set_candidates(self, candidates: List[str]) -> None:
        self.clear()
        for text in candidates:
            QListWidgetItem(text, self)
        if self._is_visible:
            if self.count() > 0:
                self.setCurrentRow(0)
            else:
                self.hide()

    # ---- 接受 ----

    def accept_current(self) -> str:
        item = self.currentItem()
        if item is not None:
            text: str = item.text()
            self.hide()
            return text
        return ""

    def _on_accept(self, _item: QListWidgetItem | None = None) -> None:
        it = self.currentItem()
        if it is not None:
            self.hide()
            self.item_selected.emit(it.text())

    # ---- 键盘导航 ----

    def key_press_event(self, event: QKeyEvent) -> bool:
        """处理弹框内键盘导航，返回 True 表示已消费按键。

        Enter/Return: 接受当前候选后关闭弹框，不触发换行。
                     再次按 Enter（弹框已关闭）才触发换行/dedent。
        Tab: 接受当前候选（不触发换行）。
        """
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.hide()
            return True
        if key == Qt.Key.Key_Up:
            self._navigate(-1)
            return True
        if key == Qt.Key.Key_Down:
            self._navigate(1)
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_accept()  # 接受补全
            return True  # 消费事件，不触发换行
        if key == Qt.Key.Key_Tab:
            self._on_accept()
            return True
        return False

    def _navigate(self, delta: int) -> None:
        count = self.count()
        if count == 0:
            return
        row = (self.currentRow() + delta) % count
        self.setCurrentRow(row)


class CompletionProvider:
    """从文档文本中提取补全候选词，按大小写匹配 + 频率排序。"""

    def __init__(self):
        self._word_freq: Dict[str, int] = {}

    def rebuild_from_text(self, text: str) -> None:
        """从全文重建词频表。"""
        freq: Dict[str, int] = {}
        for m in _WORD_RE.finditer(text):
            w = m.group()
            freq[w] = freq.get(w, 0) + 1
        self._word_freq = freq

    def candidates_for_prefix(self, prefix: str, max_items: int = 8) -> List[str]:
        """返回以 prefix 开头的前 max_items 个候选词。

        排序规则：
        1. 大小写精确匹配优先（prefix 原样匹配 > 忽略大小写匹配）
        2. 频率降序（出现次数多的排前面）
        3. 长度升序（短词优先）
        """
        if not prefix:
            return []
        lower = prefix.lower()
        matched: List[str] = []
        for w in self._word_freq:
            if w.lower().startswith(lower) and w != prefix:
                matched.append(w)
        matched.sort(key=lambda w: (
            0 if w.startswith(prefix) else 1,
            -self._word_freq[w],
            len(w),
            w.lower(),
        ))
        return matched[:max_items]

    def clear(self) -> None:
        self._word_freq.clear()
