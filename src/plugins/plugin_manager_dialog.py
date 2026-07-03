# -*- coding: utf-8 -*-
"""
插件管理对话框
提供插件列表查看、加载/激活/停用/卸载/热加载操作
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QPushButton, QLabel,
)

from ..themes.theme_aware_mixin import ThemeAwareMixin
from ..utils.error_handler import ErrorHandler, ErrorCategory
from ..themes.theme_aware_mixin import ThemeAwareMixin


class PluginManagerDialog(ThemeAwareMixin, QDialog):
    def __init__(self, plugin_manager, secretary, parent=None, theme_engine=None):
        super().__init__(parent)
        self._plugin_manager = plugin_manager
        self._secretary = secretary
        resolved_theme_engine = theme_engine or getattr(parent, "theme_engine", None)
        self.setObjectName("PluginManagerDialog")
        self.setWindowTitle("插件管理")
        self.setMinimumSize(500, 400)
        self._init_ui()
        if theme_engine:
            self._init_theme(theme_engine)

        if resolved_theme_engine:
            self._init_theme(resolved_theme_engine)

    def _init_ui(self):
        layout = QVBoxLayout(self)

        self._list_widget = QListWidget()
        self._list_widget.setObjectName("PluginList")
        self._list_widget.setAlternatingRowColors(True)
        self._count_label = QLabel()
        self._count_label.setObjectName("PluginCountLabel")

        self._refresh_list()
        layout.addWidget(self._count_label)
        layout.addWidget(self._list_widget)

        btn_layout = QHBoxLayout()

        load_btn = QPushButton("加载")
        activate_btn = QPushButton("激活")
        deactivate_btn = QPushButton("停用")
        unload_btn = QPushButton("卸载")
        reload_btn = QPushButton("热加载")

        load_btn.clicked.connect(self._on_load)
        activate_btn.clicked.connect(self._on_activate)
        deactivate_btn.clicked.connect(self._on_deactivate)
        unload_btn.clicked.connect(self._on_unload)
        reload_btn.clicked.connect(self._on_reload)

        btn_layout.addWidget(load_btn)
        btn_layout.addWidget(activate_btn)
        btn_layout.addWidget(deactivate_btn)
        btn_layout.addWidget(unload_btn)
        btn_layout.addWidget(reload_btn)
        layout.addLayout(btn_layout)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _apply_theme_colors(self, colors):
        self.setStyleSheet(f"""
        QDialog#PluginManagerDialog {{
            background-color: {colors.dialog_bg};
            color: {colors.text_primary};
        }}

        QLabel#PluginCountLabel {{
            color: {colors.text_primary};
            font-size: 14px;
            padding: 4px 0;
        }}

        QListWidget#PluginList {{
            background-color: {colors.card};
            color: {colors.text_primary};
            border: 1px solid {colors.border};
            border-radius: 4px;
            padding: 6px;
            outline: none;
            alternate-background-color: {colors.surface};
        }}

        QListWidget#PluginList::item {{
            color: {colors.text_primary};
            background: transparent;
            padding: 6px 8px;
            border-radius: 4px;
        }}

        QListWidget#PluginList::item:hover {{
            background-color: {colors.surface};
        }}

        QListWidget#PluginList::item:selected {{
            background-color: {colors.primary_light};
            color: {colors.text_primary};
        }}

        QPushButton {{
            background-color: {colors.primary};
            color: white;
            border: 1px solid {colors.primary_dark};
            border-radius: 4px;
            padding: 6px 14px;
            min-height: 24px;
        }}

        QPushButton:hover {{
            background-color: {colors.primary_dark};
        }}

        QPushButton:pressed {{
            background-color: {colors.primary_dark};
        }}

        QPushButton:disabled {{
            background-color: {colors.border};
            color: {colors.text_disabled};
            border-color: {colors.border};
        }}

        QScrollBar:vertical {{
            background-color: {colors.surface};
            width: 12px;
            margin: 0;
        }}

        QScrollBar::handle:vertical {{
            background-color: {colors.border};
            border-radius: 6px;
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
            height: 12px;
            margin: 0;
        }}

        QScrollBar::handle:horizontal {{
            background-color: {colors.border};
            border-radius: 6px;
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

        self._list_widget.viewport().setStyleSheet(
            f"background-color: {colors.card}; color: {colors.text_primary};"
        )

    def _get_selected_plugin_id(self):
        item = self._list_widget.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _refresh_list(self):
        self._list_widget.clear()
        plugins = self._plugin_manager.get_discovered_plugins()
        for info in plugins:
            name = info.get("name", "未知")
            version = info.get("version", "?")
            state = info.get("state", "UNLOADED")
            desc = info.get("description", "")
            item_text = f"{name} v{version} [{state}]"
            if desc:
                item_text += f" - {desc}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self._list_widget.addItem(item)
        if not plugins:
            self._list_widget.addItem(QListWidgetItem("未发现插件"))
        self._count_label.setText(f"已发现 {len(plugins)} 个插件")

    def _on_load(self):
        pid = self._get_selected_plugin_id()
        if pid:
            try:
                self._plugin_manager.load_plugin(pid)
                self._secretary.show_message(f"插件 {pid} 已加载")
                self._refresh_list()
            except Exception as e:
                ErrorHandler.show_from_exception(e, ErrorCategory.GENERAL, "加载失败")

    def _on_activate(self):
        pid = self._get_selected_plugin_id()
        if pid:
            try:
                self._plugin_manager.activate_plugin(pid)
                self._secretary.show_message(f"插件 {pid} 已激活")
                self._refresh_list()
            except Exception as e:
                ErrorHandler.show_from_exception(e, ErrorCategory.GENERAL, "激活失败")

    def _on_deactivate(self):
        pid = self._get_selected_plugin_id()
        if pid:
            try:
                self._plugin_manager.deactivate_plugin(pid)
                self._secretary.show_message(f"插件 {pid} 已停用")
                self._refresh_list()
            except Exception as e:
                ErrorHandler.show_from_exception(e, ErrorCategory.GENERAL, "停用失败")

    def _on_unload(self):
        pid = self._get_selected_plugin_id()
        if pid:
            try:
                self._plugin_manager.unload_plugin(pid)
                self._secretary.show_message(f"插件 {pid} 已卸载")
                self._refresh_list()
            except Exception as e:
                ErrorHandler.show_from_exception(e, ErrorCategory.GENERAL, "卸载失败")

    def _on_reload(self):
        pid = self._get_selected_plugin_id()
        if pid:
            try:
                self._plugin_manager.reload_plugin(pid)
                self._secretary.show_message(f"插件 {pid} 已热加载")
                self._refresh_list()
            except Exception as e:
                ErrorHandler.show_from_exception(e, ErrorCategory.GENERAL, "热加载失败")

    def _apply_theme_colors(self, colors):
        pass
