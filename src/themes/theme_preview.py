# -*- coding: utf-8 -*-
"""
主题预览对话框

提供实时预览、主题切换和自定义调整功能。
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QSplitter, QWidget, QScrollArea,
    QGroupBox, QFormLayout, QCheckBox, QDialogButtonBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette

from .theme_engine import ThemeEngine, ThemeDefinition, ThemeColorScheme
from .theme_aware_mixin import ThemeAwareMixin


class ThemePreviewWidget(QWidget):
    theme_applied = pyqtSignal(str)

    def __init__(self, theme_engine: ThemeEngine, parent=None):
        super().__init__(parent)
        self._engine = theme_engine
        self._current_theme_id = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("可用主题"))

        self._theme_list = QListWidget()
        self._theme_list.currentItemChanged.connect(self._on_theme_selected)
        left_layout.addWidget(self._theme_list)

        self._apply_btn = QPushButton("应用主题")
        self._apply_btn.clicked.connect(self._on_apply)
        left_layout.addWidget(self._apply_btn)

        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._preview_area = QScrollArea()
        self._preview_area.setWidgetResizable(True)
        self._preview_content = QWidget()
        self._preview_layout = QVBoxLayout(self._preview_content)
        self._preview_area.setWidget(self._preview_content)
        right_layout.addWidget(self._preview_area)

        self._info_label = QLabel("选择一个主题进行预览")
        right_layout.addWidget(self._info_label)

        splitter.addWidget(right_panel)
        splitter.setSizes([200, 500])

        self._refresh_theme_list()

    def _refresh_theme_list(self):
        self._theme_list.clear()
        themes = self._engine.get_all_themes()
        for theme_id, theme in themes.items():
            item = QListWidgetItem(theme.name)
            item.setData(Qt.ItemDataRole.UserRole, theme_id)
            if theme.is_dark:
                item.setText(f"{theme.name} (深色)")
            self._theme_list.addItem(item)

        active = self._engine.get_active_theme()
        for i in range(self._theme_list.count()):
            theme_item = self._theme_list.item(i)
            if theme_item is not None and theme_item.data(Qt.ItemDataRole.UserRole) == active.id:
                self._theme_list.setCurrentItem(theme_item)
                break

    def _on_theme_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        if current is None:
            return
        theme_id = current.data(Qt.ItemDataRole.UserRole)
        theme = self._engine.get_theme(theme_id)
        if theme:
            self._current_theme_id = theme_id
            self._update_preview(theme)

    def _update_preview(self, theme: ThemeDefinition):
        while self._preview_layout.count():
            child = self._preview_layout.takeAt(0)
            if child is not None:
                w = child.widget()
                if w is not None:
                    w.deleteLater()

        info_group = QGroupBox("主题信息")
        info_layout = QFormLayout()
        info_layout.addRow("名称:", QLabel(theme.name))
        info_layout.addRow("版本:", QLabel(theme.version))
        info_layout.addRow("作者:", QLabel(theme.author or "未知"))
        info_layout.addRow("描述:", QLabel(theme.description or "无"))
        is_dark_label = QLabel("是" if theme.is_dark else "否")
        info_layout.addRow("深色模式:", is_dark_label)
        info_group.setLayout(info_layout)
        self._preview_layout.addWidget(info_group)

        colors_group = QGroupBox("颜色方案预览")
        colors_layout = QVBoxLayout()

        c = theme.colors

        # ── 通用颜色 ──
        general_group = QGroupBox("通用颜色")
        general_layout = QVBoxLayout()
        general_items = [
            ("主色 (Primary)", c.primary),
            ("主色深色 (Primary Dark)", c.primary_dark),
            ("主色浅色 (Primary Light)", c.primary_light),
            ("强调色 (Accent)", c.accent),
            ("背景色 (Background)", c.background),
            ("表面色 (Surface)", c.surface),
            ("卡片色 (Card)", c.card),
            ("主文本 (Text)", c.text_primary),
            ("次文本 (Text Secondary)", c.text_secondary),
            ("禁用文本 (Text Disabled)", c.text_disabled),
            ("边框色 (Border)", c.border),
            ("分割线 (Divider)", c.divider),
            ("错误色 (Error)", c.error),
            ("警告色 (Warning)", c.warning),
            ("成功色 (Success)", c.success),
            ("信息色 (Info)", c.info),
        ]

        for label_text, color_hex in general_items:
            row = QHBoxLayout()
            label = QLabel(label_text)
            swatch = QLabel()
            swatch.setFixedSize(40, 20)
            swatch.setStyleSheet(
                f"background-color: {color_hex}; "
                f"border: 1px solid #999; border-radius: 2px;"
            )
            hex_label = QLabel(color_hex)
            hex_label.setFont(QFont("Consolas", 9))
            row.addWidget(swatch)
            row.addWidget(label)
            row.addStretch()
            row.addWidget(hex_label)
            general_layout.addLayout(row)
        general_group.setLayout(general_layout)
        colors_layout.addWidget(general_group)

        # ── 编辑器颜色 ──
        editor_group = QGroupBox("编辑器颜色")
        editor_layout = QVBoxLayout()
        editor_items = [
            ("编辑器背景", c.editor_bg),
            ("行号颜色", c.editor_line_number),
            ("当前行高亮", c.editor_current_line),
            ("文本选中", c.editor_selection),
            ("括号匹配背景", c.editor_bracket_match_bg),
            ("括号匹配前景", c.editor_bracket_match_fg),
            ("未匹配括号", c.editor_bracket_unmatched),
        ]

        for label_text, color_hex in editor_items:
            row = QHBoxLayout()
            label = QLabel(label_text)
            swatch = QLabel()
            swatch.setFixedSize(40, 20)
            swatch.setStyleSheet(
                f"background-color: {color_hex}; "
                f"border: 1px solid #999; border-radius: 2px;"
            )
            hex_label = QLabel(color_hex)
            hex_label.setFont(QFont("Consolas", 9))
            row.addWidget(swatch)
            row.addWidget(label)
            row.addStretch()
            row.addWidget(hex_label)
            editor_layout.addLayout(row)
        editor_group.setLayout(editor_layout)
        colors_layout.addWidget(editor_group)

        # ── UI 区域颜色 ──
        ui_group = QGroupBox("UI 区域颜色")
        ui_layout = QVBoxLayout()
        ui_items = [
            ("侧边栏背景", c.sidebar_bg),
            ("状态栏背景", c.statusbar_bg),
            ("菜单栏背景", c.menubar_bg),
            ("对话框背景", c.dialog_bg),
            ("缩略图背景", c.minimap_bg),
            ("缩略图视口", c.minimap_viewport),
            ("小秘书气泡背景", c.secretary_bubble_bg),
            ("小秘书气泡边框", c.secretary_bubble_border),
        ]

        for label_text, color_hex in ui_items:
            row = QHBoxLayout()
            label = QLabel(label_text)
            swatch = QLabel()
            swatch.setFixedSize(40, 20)
            swatch.setStyleSheet(
                f"background-color: {color_hex}; "
                f"border: 1px solid #999; border-radius: 2px;"
            )
            hex_label = QLabel(color_hex)
            hex_label.setFont(QFont("Consolas", 9))
            row.addWidget(swatch)
            row.addWidget(label)
            row.addStretch()
            row.addWidget(hex_label)
            ui_layout.addLayout(row)
        ui_group.setLayout(ui_layout)
        colors_layout.addWidget(ui_group)

        colors_group.setLayout(colors_layout)
        self._preview_layout.addWidget(colors_group)

        resources_group = QGroupBox("资源颜色")
        res_layout = QVBoxLayout()
        resource_items = [
            ("燃料", c.resource_fuel),
            ("弹药", c.resource_ammo),
            ("钢材", c.resource_steel),
            ("铝材", c.resource_bauxite),
        ]
        for label_text, color_hex in resource_items:
            row = QHBoxLayout()
            swatch = QLabel()
            swatch.setFixedSize(40, 20)
            swatch.setStyleSheet(
                f"background-color: {color_hex}; "
                f"border: 1px solid #999; border-radius: 2px;"
            )
            label = QLabel(label_text)
            hex_label = QLabel(color_hex)
            hex_label.setFont(QFont("Consolas", 9))
            row.addWidget(swatch)
            row.addWidget(label)
            row.addStretch()
            row.addWidget(hex_label)
            res_layout.addLayout(row)

        resources_group.setLayout(res_layout)
        self._preview_layout.addWidget(resources_group)

        self._preview_layout.addStretch()

        self._info_label.setText(
            f"预览主题: {theme.name} | "
            f"颜色数: {len(c.to_dict())} | "
            f"{'深色' if theme.is_dark else '浅色'}模式"
        )

    def _on_apply(self):
        if self._current_theme_id:
            self._engine.set_active_theme(self._current_theme_id)
            self.theme_applied.emit(self._current_theme_id)


class ThemePreviewDialog(ThemeAwareMixin, QDialog):
    theme_applied = pyqtSignal(str)

    def __init__(self, theme_engine: ThemeEngine, parent=None):
        super().__init__(parent)
        self._engine = theme_engine
        self._setup_ui()
        self._init_theme(theme_engine)

    def _setup_ui(self):
        self.setWindowTitle("主题管理")
        self.setMinimumSize(700, 500)

        layout = QVBoxLayout(self)

        self._preview_widget = ThemePreviewWidget(self._engine, self)
        self._preview_widget.theme_applied.connect(self._on_theme_applied)
        layout.addWidget(self._preview_widget)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_theme_applied(self, theme_id: str):
        self.theme_applied.emit(theme_id)

    def _apply_theme_colors(self, colors):
        pass
