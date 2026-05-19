# -*- coding: utf-8 -*-
"""
状态栏组件
显示光标位置、字符数、编码、文件类型
"""

from PyQt6.QtWidgets import QStatusBar, QLabel, QFrame, QHBoxLayout, QWidget
from PyQt6.QtCore import Qt

from ..themes.theme_aware_mixin import ThemeAwareMixin


class StatusBarWidget(ThemeAwareMixin, QStatusBar):

    def __init__(self, theme_engine, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._init_theme(theme_engine)

    def _init_ui(self):
        self._separator_style = ""

        left_widget = QWidget()
        left_layout = QHBoxLayout(left_widget)
        left_layout.setContentsMargins(5, 0, 5, 0)
        left_layout.setSpacing(0)

        self.position_label = QLabel("行 1, 列 1")
        self.position_label.setMinimumWidth(100)
        left_layout.addWidget(self.position_label)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        left_layout.addWidget(sep1)
        self._sep1 = sep1

        self.char_count_label = QLabel("0 个字符")
        self.char_count_label.setMinimumWidth(80)
        left_layout.addWidget(self.char_count_label)

        sep1b = QFrame()
        sep1b.setFrameShape(QFrame.Shape.VLine)
        left_layout.addWidget(sep1b)
        self._sep1b = sep1b

        self.word_count_label = QLabel("0 个词")
        self.word_count_label.setMinimumWidth(70)
        left_layout.addWidget(self.word_count_label)

        self.addWidget(left_widget)

        self.addWidget(QLabel(""), 1)

        self.encoding_label = QLabel("UTF-8")
        self.encoding_label.setMinimumWidth(60)
        self.encoding_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.addPermanentWidget(self.encoding_label)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        self.addPermanentWidget(sep2)
        self._sep2 = sep2

        self.file_type_label = QLabel("纯文本")
        self.file_type_label.setMinimumWidth(70)
        self.file_type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.addPermanentWidget(self.file_type_label)

    def _apply_theme_colors(self, colors):
        self.setStyleSheet(f"""
            QStatusBar {{
                background-color: {colors.statusbar_bg};
                border-top: 1px solid {colors.border};
            }}
            QStatusBar::item {{
                border: none;
            }}
            QLabel {{
                padding: 2px 8px;
                color: {colors.text_primary};
            }}
        """)
        sep_style = f"""
            QFrame {{
                background-color: {colors.divider};
                max-width: 1px;
                margin: 3px 0px;
            }}
        """
        self._separator_style = sep_style
        for sep in (self._sep1, self._sep1b, self._sep2):
            sep.setStyleSheet(sep_style)

    def update_stats(self, char_count: int, line: int, column: int,
                     encoding: str = "UTF-8", file_type: str = "纯文本",
                     word_count: int = 0):
        self.position_label.setText(f"行 {line}, 列 {column}")
        self.char_count_label.setText(f"{char_count} 个字符")
        self.word_count_label.setText(f"{word_count} 个词")
        self.encoding_label.setText(encoding.upper())
        self.file_type_label.setText(file_type)

    def set_encoding(self, encoding: str):
        self.encoding_label.setText(encoding.upper())

    def set_file_type(self, file_type: str):
        self.file_type_label.setText(file_type)
