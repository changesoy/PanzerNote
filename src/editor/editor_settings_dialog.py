# -*- coding: utf-8 -*-
"""
记事本设置对话框

v1.5.4 新增
v1.5.5 改动：
  - 「自动缩略图（仅代码文件）」→「自动开关缩略图」
  - 增加字体选择功能（使用本地字体库）
  - 字体大小现在可以正确应用到编辑器
  - 显示行号 / 高亮当前行开关现在可以正确应用
"""

from PyQt6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QPushButton, QSpinBox, QComboBox, QGroupBox, QFormLayout,
    QFontComboBox, QSlider
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ..core.config import Config


class EditorSettingsDialog(QDialog):
    """记事本设置对话框"""

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("记事本设置")
        self.setMinimumWidth(450)

        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # ── 显示选项 ──
        display_group = QGroupBox("显示")
        display_layout = QFormLayout(display_group)

        self.show_line_numbers_cb = QCheckBox()
        display_layout.addRow("显示行号:", self.show_line_numbers_cb)

        self.highlight_current_line_cb = QCheckBox()
        display_layout.addRow("高亮当前行:", self.highlight_current_line_cb)

        layout.addWidget(display_group)

        # ── 缩略图选项 ──
        minimap_group = QGroupBox("代码缩略图")
        minimap_layout = QFormLayout(minimap_group)

        self.show_minimap_cb = QCheckBox()
        minimap_layout.addRow("显示缩略图:", self.show_minimap_cb)

        self.auto_minimap_cb = QCheckBox()
        self.auto_minimap_cb.setToolTip(
            "勾选后，仅对代码文件显示缩略图（.txt 和 .md 不显示）"
        )
        minimap_layout.addRow("自动开关缩略图:", self.auto_minimap_cb)

        layout.addWidget(minimap_group)

        # ── 编辑器选项 ──
        editor_group = QGroupBox("编辑器")
        editor_layout = QFormLayout(editor_group)
        self.auto_pair_brackets_cb = QCheckBox()
        self.auto_pair_brackets_cb.setToolTip("输入 (、[、{、\"、' 时自动补全对应的右括号/引号")
        editor_layout.addRow("括号/引号自动配对:", self.auto_pair_brackets_cb)

        # 字体选择（使用本地字体库）
        self.font_family_combo = QFontComboBox()
        self.font_family_combo.setMinimumWidth(200)
        editor_layout.addRow("字体:", self.font_family_combo)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 48)
        self.font_size_spin.setSuffix(" pt")
        editor_layout.addRow("字体大小:", self.font_size_spin)

        self.wrap_mode_combo = QComboBox()
        self.wrap_mode_combo.addItem("不换行", "no_wrap")
        self.wrap_mode_combo.addItem("限制行宽", "limit_width")
        editor_layout.addRow("行宽模式:", self.wrap_mode_combo)

        self.autosave_spin = QSpinBox()
        self.autosave_spin.setRange(10, 300)
        self.autosave_spin.setSuffix(" 秒")
        editor_layout.addRow("自动保存间隔:", self.autosave_spin)

        layout.addWidget(editor_group)

        # ── 小秘书选项 ──
        secretary_group = QGroupBox("小秘书")
        secretary_layout = QFormLayout(secretary_group)

        self.show_secretary_cb = QCheckBox()
        secretary_layout.addRow("显示小秘书:", self.show_secretary_cb)

        size_widget = QWidget()
        size_layout = QHBoxLayout(size_widget)
        size_layout.setContentsMargins(0, 0, 0, 0)

        self.secretary_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.secretary_size_slider.setRange(3, 20)
        self.secretary_size_slider.setTickPosition(QSlider.TicksBelow)
        self.secretary_size_slider.setTickInterval(1)
        size_layout.addWidget(self.secretary_size_slider)

        self.secretary_size_label = QLabel("7%")
        self.secretary_size_label.setMinimumWidth(40)
        size_layout.addWidget(self.secretary_size_label)

        self.secretary_size_slider.valueChanged.connect(
            lambda v: self.secretary_size_label.setText(f"{v}%")
        )

        secretary_layout.addRow("尺寸占比:", size_widget)

        layout.addWidget(secretary_group)

        # ── 按钮 ──
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def _load_settings(self):
        """从配置加载当前设置"""
        self.show_line_numbers_cb.setChecked(
            self.config.get_editor_setting("show_line_numbers", True)
        )
        self.highlight_current_line_cb.setChecked(
            self.config.get_editor_setting("highlight_current_line", True)
        )
        self.show_minimap_cb.setChecked(
            self.config.get_editor_setting("show_minimap", True)
        )
        self.auto_minimap_cb.setChecked(
            self.config.get_editor_setting("auto_minimap", False)
        )
        self.auto_pair_brackets_cb.setChecked(
            self.config.get_editor_setting("auto_pair_brackets", True)
        )

        # 字体
        font_family = self.config.get_editor_setting("font_family", "Microsoft YaHei")
        target_font = QFont(font_family)
        self.font_family_combo.setCurrentFont(target_font)

        self.font_size_spin.setValue(
            self.config.get_editor_setting("font_size", 12)
        )

        wrap_mode = self.config.get_editor_setting("wrap_mode", "no_wrap")
        index = self.wrap_mode_combo.findData(wrap_mode)
        if index >= 0:
            self.wrap_mode_combo.setCurrentIndex(index)

        self.autosave_spin.setValue(
            self.config.get_editor_setting("auto_save_interval", 30)
        )

        self.show_secretary_cb.setChecked(
            self.config.get_secretary_setting("show_secretary", True)
        )

        size_percent = self.config.get_secretary_setting("size_percent", 7)
        self.secretary_size_slider.setValue(size_percent)
        self.secretary_size_label.setText(f"{size_percent}%")

    def get_settings(self) -> dict:
        """获取用户修改后的设置

        返回嵌套字典，按命名空间分组：
        - "editor": 编辑器相关设置
        - "secretary": 小秘书相关设置
        """
        return {
            "editor": {
                "show_line_numbers": self.show_line_numbers_cb.isChecked(),
                "highlight_current_line": self.highlight_current_line_cb.isChecked(),
                "show_minimap": self.show_minimap_cb.isChecked(),
                "auto_minimap": self.auto_minimap_cb.isChecked(),
                "font_family": self.font_family_combo.currentFont().family(),
                "font_size": self.font_size_spin.value(),
                "wrap_mode": self.wrap_mode_combo.currentData(),
                "auto_save_interval": self.autosave_spin.value(),
                "auto_pair_brackets": self.auto_pair_brackets_cb.isChecked(),
            },
            "secretary": {
                "show_secretary": self.show_secretary_cb.isChecked(),
                "size_percent": self.secretary_size_slider.value(),
            },
        }
