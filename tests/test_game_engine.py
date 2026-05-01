# -*- coding: utf-8 -*-
import math
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from src.game.game_engine import GameEngine


def _make_config(**overrides) -> MagicMock:
    defaults = {
        "idle_reward_rate": 1.0,
        "bauxite_counter": 0,
    }
    defaults.update(overrides)

    config = MagicMock()

    def get_side_effect(key, default=None):
        return defaults.get(key, default)

    config.get_game_setting = MagicMock(side_effect=get_side_effect)
    config.add_resource = MagicMock()
    config.set_game_setting = MagicMock()
    config.get_last_login = MagicMock(return_value=None)

    return config


class TestGameEngine:
    def test_calculate_idle_reward_basic(self):
        config = _make_config(bauxite_counter=2)
        engine = GameEngine(config)
        reward = engine.calculate_idle_reward()

        assert reward["fuel"] == 5
        assert reward["ammo"] == 5
        assert reward["steel"] == 5
        assert reward["bauxite"] == 5

    def test_calculate_idle_reward_no_bauxite(self):
        config = _make_config(bauxite_counter=0)
        engine = GameEngine(config)

        reward = engine.calculate_idle_reward()
        assert reward["bauxite"] == 0

    def test_calculate_idle_reward_rate_multiplier(self):
        config = _make_config(idle_reward_rate=2.0, bauxite_counter=2)
        engine = GameEngine(config)
        reward = engine.calculate_idle_reward()

        assert reward["fuel"] == 10
        assert reward["ammo"] == 10
        assert reward["steel"] == 10
        assert reward["bauxite"] == 10

    def test_apply_idle_reward(self):
        config = _make_config(bauxite_counter=2)
        engine = GameEngine(config)
        reward = engine.apply_idle_reward()

        assert reward["fuel"] == 5
        assert config.add_resource.call_count == 4

    def test_apply_idle_reward_no_bauxite(self):
        config = _make_config(bauxite_counter=0)
        engine = GameEngine(config)

        reward = engine.apply_idle_reward()
        assert reward["bauxite"] == 0
        assert config.add_resource.call_count == 3

    def test_calculate_offline_reward_no_last_login(self):
        config = _make_config()
        engine = GameEngine(config)

        assert engine.calculate_offline_reward() is None

    def test_calculate_offline_reward_too_short(self):
        config = _make_config()
        recent = (datetime.now() - timedelta(minutes=3)).isoformat()
        config.get_last_login = MagicMock(return_value=recent)
        engine = GameEngine(config)

        assert engine.calculate_offline_reward() is None

    def test_calculate_offline_reward_valid(self):
        config = _make_config()
        past = (datetime.now() - timedelta(minutes=60)).isoformat()
        config.get_last_login = MagicMock(return_value=past)
        engine = GameEngine(config)

        reward = engine.calculate_offline_reward()
        assert reward is not None
        assert reward["fuel"] > 0
        assert reward["offline_minutes"] >= 60

    def test_calculate_offline_reward_capped(self):
        config = _make_config()
        past = (datetime.now() - timedelta(days=2)).isoformat()
        config.get_last_login = MagicMock(return_value=past)
        engine = GameEngine(config)

        reward = engine.calculate_offline_reward()
        assert reward is not None
        assert reward["offline_minutes"] <= 1440

    def test_format_offline_time_minutes(self):
        assert GameEngine.format_offline_time(45) == "45分钟"

    def test_format_offline_time_hours_and_minutes(self):
        assert GameEngine.format_offline_time(125) == "2小时5分钟"

    def test_bauxite_counter_cycles(self):
        config = _make_config(bauxite_counter=0)
        engine = GameEngine(config)

        engine.calculate_idle_reward()
        assert engine._bauxite_counter == 1

        engine.calculate_idle_reward()
        assert engine._bauxite_counter == 2

        engine.calculate_idle_reward()
        assert engine._bauxite_counter == 0
