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


class PluginManagerDialog(ThemeAwareMixin, QDialog):
    def __init__(self, plugin_manager, secretary, theme_engine, parent=None):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("PluginManagerDialog 必须传入 theme_engine，不允许为 None")
        self._plugin_manager = plugin_manager
        self._secretary = secretary
        self.setObjectName("PluginManagerDialog")
        self.setWindowTitle("插件管理")
        self.setMinimumSize(500, 400)
        self._init_ui()

        self._init_theme(theme_engine)

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
        # B5：QDialog 背景由全局 dialog recipe 驱动，QListWidget/QPushButton/
        # QScrollBar 由全局 tree_item/button/scrollbar recipe 驱动，
        # 页面不再打局部样式补丁（B3 消费契约 8.1）。
        pass

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
            # Batch 5（D14）：安全模式状态（上次启动启动阶段异常退出，需手动处理）
            if state == "SAFE_MODE":
                state = "安全模式"
            desc = info.get("description", "")
            caps = info.get("capabilities", [])
            item_text = f"{name} v{version} [{state}]"
            if caps:
                item_text += f" 能力: {', '.join(caps)}"
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
