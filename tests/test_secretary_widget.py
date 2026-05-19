# -*- coding: utf-8 -*-
import os
import json
import pytest
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QResizeEvent

from src.core.config import Config
from src.game.secretary_widget import SpeechBubble, SecretaryWidget


def _make_config(tmp_path):
    config_dir = os.path.join(str(tmp_path), "data", "config")
    gamedata_dir = os.path.join(str(tmp_path), "data", "gamedata")
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs(gamedata_dir, exist_ok=True)
    path_file = os.path.join(str(tmp_path), "user_data_path.txt")
    with open(path_file, "w", encoding="utf-8") as f:
        f.write(str(tmp_path))
    return Config(app_dir=str(tmp_path))


class TestSpeechBubble:
    def test_init(self, qtbot):
        bubble = SpeechBubble()
        qtbot.addWidget(bubble)
        assert bubble is not None
        assert bubble.isHidden()

    def test_show_message(self, qtbot):
        bubble = SpeechBubble()
        qtbot.addWidget(bubble)
        bubble.show_message("Hello", duration=0)
        assert bubble.isVisible()
        assert bubble.label.text() == "Hello"

    def test_show_message_with_timer(self, qtbot):
        bubble = SpeechBubble()
        qtbot.addWidget(bubble)
        bubble.show_message("Test", duration=100)
        assert bubble.isVisible()


class TestSecretaryWidget:
    def test_init(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(800, 600)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        assert widget is not None

    def test_show_message(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(800, 600)
        parent.show()
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        widget.show()
        widget.show_message("Test message", duration=0)
        assert widget.bubble.label.text() == "Test message"

    def test_show_event_message(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(800, 600)
        parent.show()
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        widget.show()
        widget.show_event_message("保存文件")
        assert widget.bubble.label.text() != ""

    def test_format_line(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(800, 600)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        result = widget._format_line("{nickname}，你好！")
        assert "指挥官" in result

    def test_set_secretary(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(800, 600)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        widget.set_secretary("059", "虎王", state="正常")
        assert config.get_secretary_setting("character_id") == "059"
        assert config.get_secretary_setting("character_name") == "虎王"

    def test_clear_secretary(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(800, 600)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        widget.set_secretary("059", "虎王")
        widget.clear_secretary()
        assert config.get_secretary_setting("character_id") is None

    def test_set_state(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(800, 600)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        widget.set_state("大破")
        assert config.get_secretary_setting("state") == "大破"

    def test_get_portrait_path_default(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(800, 600)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        path = widget._get_portrait_path()
        assert "secretary.png" in path

    def test_get_portrait_path_with_character(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(800, 600)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        widget.set_secretary("059", "虎王", state="正常")
        path = widget._get_portrait_path()
        assert "059" in path
        assert "虎王" in path

    def test_get_portrait_path_with_skin(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(800, 600)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        widget.set_secretary("059", "虎王", skin_name="冲浪行动", state="正常")
        path = widget._get_portrait_path()
        assert "皮肤" in path
        assert "冲浪行动" in path

    def test_load_lines_config(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        gamedata_dir = os.path.join(str(tmp_path), "data", "gamedata")
        lines_data = {
            "lines": {"自定义事件": ["自定义台词1", "自定义台词2"]},
            "user_nickname": "提督",
            "secretary_self": "小秘书"
        }
        lines_path = os.path.join(gamedata_dir, "secretary_lines.json")
        with open(lines_path, "w", encoding="utf-8") as f:
            json.dump(lines_data, f, ensure_ascii=False)

        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(800, 600)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        assert "自定义事件" in widget._lines

    def test_hide_when_setting_off(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        config.set_secretary_setting("show_secretary", False)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(800, 600)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        assert widget.isHidden()

    def test_size_percent_default(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(1200, 900)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        assert widget.get_size_percent() == 7

    def test_set_size_percent(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(1200, 900)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)

        old_w, old_h = widget.width(), widget.height()
        widget.set_size_percent(10)
        assert widget.get_size_percent() == 10
        assert widget.width() > old_w
        assert widget.height() > old_h

    def test_set_size_percent_clamped(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(1200, 900)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)

        widget.set_size_percent(1)
        assert widget.get_size_percent() == 3

        widget.set_size_percent(50)
        assert widget.get_size_percent() == 20

    def test_set_size_percent_persisted(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(1200, 900)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)

        widget.set_size_percent(12)
        assert config.get_secretary_setting("size_percent") == 12


class TestSecretaryPositionTracking:
    def test_calculate_target_position(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(1200, 900)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        target = widget._calculate_target_position()
        assert target.x() >= 0
        assert target.y() >= 0

    def test_calculate_target_position_no_parent(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        widget = SecretaryWidget(config, parent=None)
        qtbot.addWidget(widget)
        target = widget._calculate_target_position()
        assert target.x() == 0
        assert target.y() == 0

    def test_position_right_aligned(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(1200, 900)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        target = widget._calculate_target_position()
        expected_x = max(0, 1200 - widget.width() - 10)
        assert target.x() == expected_x

    def test_position_bottom_aligned(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(1200, 900)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        target = widget._calculate_target_position()
        expected_y = max(0, 900 - widget.height() - 5)
        assert target.y() == expected_y

    def test_position_clamped_to_zero(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(10, 10)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        target = widget._calculate_target_position()
        assert target.x() >= 0
        assert target.y() >= 0

    def test_request_position_update(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(1200, 900)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        widget._request_position_update()
        assert widget._position_dirty is True
        assert widget._position_timer.isActive()

    def test_commit_position_update(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(1200, 900)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        widget._position_dirty = True
        widget._commit_position_update()
        assert widget._position_dirty is False

    def test_commit_position_skips_when_clean(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(1200, 900)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        widget._update_position()
        widget._position_dirty = False
        old_pos = widget._last_position
        widget._commit_position_update()
        assert widget._last_position == old_pos

    def test_update_position_immediate(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(1200, 900)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        widget._update_position()
        assert widget._position_dirty is False
        assert widget._last_position.x() >= 0

    def test_event_filter_resize(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(1200, 900)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        widget._position_dirty = False
        from PyQt6.QtCore import QSize
        resize_event = QResizeEvent(QSize(800, 400), QSize(1200, 900))
        widget.eventFilter(parent, resize_event)
        assert widget._position_dirty is True

    def test_debounce_timer_interval(self, qtbot, tmp_path):
        config = _make_config(tmp_path)
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.resize(1200, 900)
        widget = SecretaryWidget(config, parent=parent)
        qtbot.addWidget(widget)
        assert widget._position_timer.interval() <= 50
