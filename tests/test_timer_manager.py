# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import QTimer

from src.core.timer_manager import TimerManager


def _make_config() -> MagicMock:
    config = MagicMock()
    config.get_editor_setting = MagicMock(return_value=30)
    return config


class TestTimerManager:
    def test_setup_creates_timers(self):
        config = _make_config()
        tm = TimerManager(config)
        tm.setup(
            on_auto_save=MagicMock(),
            on_update_stats=MagicMock(),
            on_idle_reward=MagicMock(),
        )

        assert tm.auto_save_timer is not None
        assert tm.stats_timer is not None
        assert tm.idle_reward_timer is not None

    def test_update_auto_save_interval(self):
        config = _make_config()
        tm = TimerManager(config)
        tm.setup(
            on_auto_save=MagicMock(),
            on_update_stats=MagicMock(),
            on_idle_reward=MagicMock(),
        )

        tm.update_auto_save_interval(60)
        assert tm.auto_save_timer.interval() == 60000

    def test_stop_all(self):
        config = _make_config()
        tm = TimerManager(config)
        tm.setup(
            on_auto_save=MagicMock(),
            on_update_stats=MagicMock(),
            on_idle_reward=MagicMock(),
        )

        tm.stop_all()
        assert not tm.auto_save_timer.isActive()
        assert not tm.stats_timer.isActive()
        assert not tm.idle_reward_timer.isActive()

    def test_auto_save_callback(self):
        config = _make_config()
        callback = MagicMock()
        tm = TimerManager(config)
        tm.setup(
            on_auto_save=callback,
            on_update_stats=MagicMock(),
            on_idle_reward=MagicMock(),
        )

        tm._handle_auto_save()
        callback.assert_called_once()

    def test_auto_save_callback_exception(self):
        config = _make_config()
        callback = MagicMock(side_effect=RuntimeError("fail"))
        tm = TimerManager(config)
        tm.setup(
            on_auto_save=callback,
            on_update_stats=MagicMock(),
            on_idle_reward=MagicMock(),
        )

        tm._handle_auto_save()
        callback.assert_called_once()
