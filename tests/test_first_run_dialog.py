# -*- coding: utf-8 -*-
import os
import pytest
from PyQt6.QtWidgets import QApplication

from src.ui.first_run_dialog import FirstRunDialog


class TestFirstRunDialog:
    def test_init(self, qtbot, tmp_path):
        dlg = FirstRunDialog(app_dir=str(tmp_path))
        qtbot.addWidget(dlg)
        assert dlg is not None
        assert dlg.windowTitle() == "欢迎使用 PanzerNote"

    def test_default_path(self, qtbot, tmp_path):
        dlg = FirstRunDialog(app_dir=str(tmp_path))
        qtbot.addWidget(dlg)
        assert dlg.path_edit.text() == str(tmp_path)

    def test_get_selected_path(self, qtbot, tmp_path):
        dlg = FirstRunDialog(app_dir=str(tmp_path))
        qtbot.addWidget(dlg)
        assert dlg.get_selected_path() == str(tmp_path)

    def test_confirm_creates_dirs(self, qtbot, tmp_path):
        target = os.path.join(str(tmp_path), "PanzerNote")
        dlg = FirstRunDialog(app_dir=str(tmp_path))
        qtbot.addWidget(dlg)
        dlg.path_edit.setText(target)
        dlg._confirm()
        assert os.path.isdir(os.path.join(target, "data", "config"))
        assert os.path.isdir(os.path.join(target, "notebooks", "日记"))
