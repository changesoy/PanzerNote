# -*- coding: utf-8 -*-
"""标签页相关对话框（从 editor_tabs.py 拆出，纯结构重构不改行为）。

SaveAsDialog：另存为对话框，支持选择文件名与编码，
由 EditorTabWidget.save_current_as 等保存流入口使用。
"""

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class SaveAsDialog(QDialog):
    """另存为对话框 - 支持选择编码"""

    def __init__(self, suggested_path: str, current_encoding: str = "UTF-8", parent=None):
        super().__init__(parent)
        self.setWindowTitle("另存为")
        self.setMinimumWidth(500)

        self._filepath = ""
        self._encoding = current_encoding

        layout = QVBoxLayout(self)

        # 文件路径
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("文件名:"))
        self.path_edit = QLineEdit(suggested_path)
        path_layout.addWidget(self.path_edit, 1)
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        # 编码选择
        encoding_layout = QHBoxLayout()
        encoding_layout.addWidget(QLabel("编码:"))
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(["UTF-8", "GBK", "UTF-16"])
        index = self.encoding_combo.findText(current_encoding.upper())
        if index >= 0:
            self.encoding_combo.setCurrentIndex(index)
        encoding_layout.addWidget(self.encoding_combo)
        encoding_layout.addStretch()
        layout.addLayout(encoding_layout)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _browse(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "另存为", self.path_edit.text(),
            "文本文件 (*.txt);;Markdown (*.md);;Python (*.py);;网页文件 (*.html);;PDF 文档 (*.pdf);;所有文件 (*.*)"
        )
        if filepath:
            self.path_edit.setText(filepath)

    def _save(self):
        path = self.path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "提示", "请输入文件名")
            return
        self._filepath = path
        self._encoding = self.encoding_combo.currentText()
        self.accept()

    def get_filepath(self) -> str:
        return self._filepath

    def get_encoding(self) -> str:
        return self._encoding
