# -*- coding: utf-8 -*-
"""
设置动作控制器（Wave 3 分支 D）

承载 MainWindow 的设置动作编排逻辑（Wave 3 设置区块迁移）：
- show_editor_settings / apply_editor_settings / export_settings /
  import_settings / save_settings / reset_settings

设计约束（沿用 hotfix.txt / Wave 3 方案）：
- 控制器持编排逻辑，MainWindow 保留一行委托。
- wrap 菜单（QAction）是 MainWindow 的 UI 财产，控制器不持有：
  应用设置后由 MainWindow 委托方法自行 _sync_wrap_menu()。
- show 与 apply 共享同一应用路径 _apply_editor_dict，消除原两处重复。
- 导入设置沿用 FileOpenService 校验 + FileGuard.safe_read；
  导出设置经 FileGuard.safe_write（与 HTML 导出安全写入一致）。
- _show_game_settings（游戏侧占位）保留在 MainWindow，不在本控制器。
"""

import os

from PyQt6.QtWidgets import QDialog, QFileDialog, QMessageBox, QWidget

from .. import __version__
from ..core.config import Config
from ..core.config_import_service import ConfigImportError, ConfigImportService
from ..core.timer_manager import TimerManager
from ..game.secretary_widget import SecretaryWidget
from ..utils.feature_flags import set_enabled as _feature_set_enabled
from .editor_settings_dialog import EditorSettingsDialog
from .editor_tabs import EditorTabWidget
from .file_open_service import (
    FileOpenSecurityError,
    FileOpenService,
    FileOpenSource,
)


class SettingsActionController:
    """设置动作编排控制器（不持有任何 UI action）。"""

    def __init__(
        self,
        config: Config,
        editor_tabs: EditorTabWidget,
        secretary: SecretaryWidget,
        timer_manager: TimerManager,
        file_open_service: FileOpenService,
        parent_widget: QWidget,  # MainWindow，弹窗宿主
    ) -> None:
        self._config = config
        self._editor_tabs = editor_tabs
        self._secretary = secretary
        self._timer_manager = timer_manager
        self._file_open_service = file_open_service
        self._parent_widget = parent_widget

    # === 显示/应用 ===

    def show_editor_settings(self) -> None:
        """显示记事本设置对话框，确认后保存并应用。"""
        dialog = EditorSettingsDialog(self._config, self._parent_widget)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            settings = dialog.get_settings()
            editor = settings["editor"]
            secretary = settings["secretary"]

            # 保存编辑器设置
            for key, value in editor.items():
                self._config.set_editor_setting(key, value)

            # 保存小秘书设置
            for key, value in secretary.items():
                self._config.set_secretary_setting(key, value)

            self._config.save_settings()

            # E3：大文件模式开关写 feature flag（持久化 feature_flags.json，
            # 不混入 config.json 的 editor 设置）。
            _feature_set_enabled("large_file_mode", dialog.large_file_mode_cb.isChecked())

            # 应用设置（与 apply_editor_settings 共享路径）
            self._apply_editor_dict(editor, secretary)
            self._secretary.show_message("设置已保存并应用")

    def apply_editor_settings(self) -> None:
        """从 config 读取当前设置并应用到 UI。"""
        editor = {
            "show_line_numbers": self._config.get_editor_setting("show_line_numbers", True),
            "highlight_current_line": self._config.get_editor_setting("highlight_current_line", True),
            "font_family": self._config.get_editor_setting("font_family", "Microsoft YaHei"),
            "font_size": self._config.get_editor_setting("font_size", 12),
            "wrap_mode": self._config.get_editor_setting("wrap_mode", "no_wrap"),
            "auto_save_interval": self._config.get_editor_setting("auto_save_interval", 30),
            "enable_completion": self._config.get_editor_setting("enable_completion", False),
        }
        secretary = {
            "show_secretary": self._config.get_secretary_setting("show_secretary", True),
            "size_percent": self._config.get_secretary_setting("size_percent", 7),
        }
        self._apply_editor_dict(editor, secretary)

    def _apply_editor_dict(self, editor: dict, secretary: dict) -> None:
        """把编辑器/秘书设置应用到 UI（show 与 apply 共享的实现路径）。"""
        self._editor_tabs.set_line_numbers_all(editor["show_line_numbers"])
        self._editor_tabs.set_highlight_current_line_all(editor["highlight_current_line"])
        self._editor_tabs.set_font_all(editor["font_family"], editor["font_size"])
        self._editor_tabs.set_wrap_mode_all(editor["wrap_mode"])
        self._editor_tabs.apply_auto_minimap_all()
        self._editor_tabs.update_indent_settings_all()
        self._editor_tabs.set_completion_enabled_all(editor.get("enable_completion", False))
        self._timer_manager.update_auto_save_interval(editor["auto_save_interval"])

        # 小秘书设置
        if secretary["show_secretary"]:
            self._secretary.show()
            self._secretary.set_size_percent(secretary["size_percent"])
        else:
            self._secretary.hide()

    # === 导出/导入 ===

    def export_settings(self) -> None:
        """导出设置到 JSON 文件（经 FileGuard 安全写入）。"""
        filepath, _ = QFileDialog.getSaveFileName(
            self._parent_widget,
            "导出设置",
            "panzernote_settings.json",
            "JSON文件 (*.json)",
        )
        if not filepath:
            return
        import json as json_module
        try:
            export_data = {
                "version": __version__,
                "settings": self._config.get_settings(),
                "workspace": self._config.get_workspace(),
            }
            content = json_module.dumps(export_data, ensure_ascii=False, indent=2)
            self._config.get_file_guard().safe_write(
                filepath,
                content,
                encoding='utf-8',
                context=self._config.INTERNAL_CONFIG_CTX,
            )
            self._secretary.show_message(
                f"设置已导出到 {os.path.basename(filepath)}"
            )
        except Exception as e:
            QMessageBox.warning(self._parent_widget, "导出失败", str(e))

    def import_settings(self) -> None:
        """导入设置 JSON 文件（路径校验 + 安全读取 + 覆盖确认）。"""
        filepath, _ = QFileDialog.getOpenFileName(
            self._parent_widget, "导入设置", "", "JSON文件 (*.json)"
        )
        if not filepath:
            return
        import json as json_module
        try:
            validated = self._file_open_service.validate_open_request(
                filepath, FileOpenSource.SETTINGS_IMPORT
            )
        except FileOpenSecurityError as e:
            QMessageBox.warning(self._parent_widget, "导入失败", str(e))
            return

        try:
            content = self._config.get_file_guard().safe_read(
                validated,
                encoding='utf-8',
                context=self._config.INTERNAL_CONFIG_CTX,
            )
            data = json_module.loads(content)
            if not isinstance(data, dict) or "settings" not in data:
                QMessageBox.warning(self._parent_widget, "导入失败", "无效的设置文件格式")
                return
            reply = QMessageBox.question(
                self._parent_widget,
                "确认导入",
                "导入设置将覆盖当前所有设置，是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return
            service = ConfigImportService(self._config)
            skipped = service.import_from_json(content)
            if skipped:
                QMessageBox.warning(
                    self._parent_widget,
                    "导入完成（部分跳过）",
                    "以下字段因格式不正确已跳过：\n" + "\n".join(skipped[:10]),
                )
            self.apply_editor_settings()
            self._secretary.show_message("设置已导入，部分设置将在重启后生效")
        except ConfigImportError as e:
            QMessageBox.warning(self._parent_widget, "导入失败", str(e))
        except Exception as e:
            QMessageBox.warning(self._parent_widget, "导入失败", str(e))

    # === 保存/重置 ===

    def save_settings(self) -> None:
        """保存设置。"""
        self._config.save_settings()
        self._secretary.show_message("设置已保存")

    def reset_settings(self) -> None:
        """恢复默认设置（确认后重置并应用）。"""
        msg_box = QMessageBox(self._parent_widget)
        msg_box.setWindowTitle("确认")
        msg_box.setText("确定要恢复所有设置为默认值吗？")
        msg_box.setIcon(QMessageBox.Icon.Question)

        yes_btn = msg_box.addButton("确定", QMessageBox.ButtonRole.AcceptRole)
        no_btn = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)

        msg_box.exec()

        if msg_box.clickedButton() == yes_btn:
            self._config.reset_to_defaults()
            self.apply_editor_settings()
            self._secretary.show_message("设置已恢复为默认值")
