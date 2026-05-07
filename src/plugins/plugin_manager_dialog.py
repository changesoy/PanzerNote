# -*- coding: utf-8 -*-
"""
插件管理对话框
提供插件列表查看、加载/激活/停用/卸载/热加载操作
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QPushButton, QLabel,
)

from ..utils.error_handler import ErrorHandler, ErrorCategory


class PluginManagerDialog(QDialog):
    def __init__(self, plugin_manager, secretary, parent=None):
        super().__init__(parent)
        self._plugin_manager = plugin_manager
        self._secretary = secretary
        self.setWindowTitle("插件管理")
        self.setMinimumSize(500, 400)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        self._list_widget = QListWidget()
        self._count_label = QLabel()

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

    def _get_selected_plugin_id(self):
        item = self._list_widget.currentItem()
        if item:
            return item.data(Qt.UserRole)
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
            item.setData(Qt.UserRole, name)
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
