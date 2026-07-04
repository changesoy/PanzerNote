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

    def apply_theme_colors(self, colors) -> None:
        """应用自动补全弹窗主题颜色。

        由 Editor._apply_theme_colors() 调用。
        CompletionPopup 是无父顶层浮窗，不依赖主窗口 QSS 级联。
        """
        self.setStyleSheet(f"""
    QListWidget#CompletionPopup {{
        background-color: {colors.card};
        color: {colors.text_primary};
        border: 1px solid {colors.border};
        border-radius: 4px;
        padding: 2px;
        outline: none;
        selection-background-color: {colors.primary_light};
        selection-color: {colors.text_primary};
    }}

    QListWidget#CompletionPopup::item {{
        color: {colors.text_primary};
        background: transparent;
        padding: 4px 8px;
        min-height: 22px;
        border-radius: 3px;
    }}

    QListWidget#CompletionPopup::item:hover {{
        background-color: {colors.surface};
        color: {colors.text_primary};
    }}

    QListWidget#CompletionPopup::item:selected {{
        background-color: {colors.primary_light};
        color: {colors.text_primary};
    }}

    QListWidget#CompletionPopup::item:selected:active {{
        background-color: {colors.primary_light};
        color: {colors.text_primary};
    }}

    QListWidget#CompletionPopup::item:selected:!active {{
        background-color: {colors.primary_light};
        color: {colors.text_primary};
    }}

    QScrollBar:vertical {{
        background-color: {colors.surface};
        width: 10px;
        margin: 0;
    }}

    QScrollBar::handle:vertical {{
        background-color: {colors.border};
        border-radius: 5px;
        min-height: 20px;
        margin: 2px;
    }}

    QScrollBar::handle:vertical:hover {{
        background-color: {colors.text_disabled};
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QScrollBar:horizontal {{
        background-color: {colors.surface};
        height: 10px;
        margin: 0;
    }}

    QScrollBar::handle:horizontal {{
        background-color: {colors.border};
        border-radius: 5px;
        min-width: 20px;
        margin: 2px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background-color: {colors.text_disabled};
    }}

    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {{
        width: 0;
    }}
    """)

        # QListWidget 的 viewport 在部分平台/样式下可能保持系统默认背景，显式补一次。
        self.viewport().setStyleSheet(  # type: ignore[union-attr]
            f"background-color: {colors.card};"
        )

    def apply_font(self, font_family: str, font_size: int) -> None:
        """同步编辑器的字体和行高到补全弹窗。

        由 Editor._apply_theme_colors() 调用。
        补全弹窗字号为编辑器的 0.8 倍，行间距按 1.1 倍字号计算。
        """
        popup_font_size = max(2, int(font_size * 0.8))
        font = QFont(font_family, popup_font_size)
        self.setFont(font)
        # QSS 的 ::item 不支持 margin，用 setSpacing() 控制选项间隙
        self.setSpacing(1)
        item_height = int(popup_font_size * 1.1)
        self.setStyleSheet(self.styleSheet() + f"""
    QListWidget#CompletionPopup::item {{
        min-height: {item_height}px;
        padding: 0px 8px;
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
