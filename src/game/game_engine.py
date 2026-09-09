# -*- coding: utf-8 -*-
"""
挂机引擎模块
封装在线挂机奖励和离线收益计算逻辑
"""

import math
from datetime import datetime
from typing import Optional

from ..core.config import Config
from ..utils.logger import get_logger


class GameEngine:
    """挂机收益引擎

    资源平衡规则：
    - 在线：燃料/弹药/钢材 +5/分钟，铝材 +5/3分钟
    - 离线：在线的 1/3，向大取整
    """

    BASE_RATE = 5
    BAUXITE_INTERVAL = 3
    OFFLINE_MIN_MINUTES = 5
    OFFLINE_MAX_MINUTES = 1440

    def __init__(self, config: Config) -> None:
        self._config = config
        self._bauxite_counter: int = config.get_savegame_field("bauxite_counter", 0)

    def calculate_idle_reward(self) -> dict:
        """计算单次在线挂机奖励（每分钟调用）

        Returns:
            {"fuel": int, "ammo": int, "steel": int, "bauxite": int}
        """
        rate = self._config.get_game_setting("idle_reward_rate", 1.0)

        fuel = int(self.BASE_RATE * rate)
        ammo = int(self.BASE_RATE * rate)
        steel = int(self.BASE_RATE * rate)

        self._bauxite_counter += 1
        if self._bauxite_counter >= self.BAUXITE_INTERVAL:
            bauxite = int(self.BASE_RATE * rate)
            self._bauxite_counter = 0
        else:
            bauxite = 0

        self._config.set_savegame_field("bauxite_counter", self._bauxite_counter)

        return {"fuel": fuel, "ammo": ammo, "steel": steel, "bauxite": bauxite}

    def apply_idle_reward(self) -> dict:
        """计算并应用在线挂机奖励

        Returns:
            本次获得的资源字典
        """
        reward = self.calculate_idle_reward()

        self._config.add_resource("fuel", reward["fuel"])
        self._config.add_resource("ammo", reward["ammo"])
        self._config.add_resource("steel", reward["steel"])
        if reward["bauxite"] > 0:
            self._config.add_resource("bauxite", reward["bauxite"])

        return reward

    def add_typing_reward(self, reward: int) -> None:
        """将打字奖励转化为资源

        打字奖励按 1:1:1:0.2 比例分配到燃料/弹药/钢材/铝材
        """
        fuel = reward
        ammo = reward
        steel = reward
        bauxite = max(1, int(reward * 0.2))
        self._config.add_resource("fuel", fuel)
        self._config.add_resource("ammo", ammo)
        self._config.add_resource("steel", steel)
        self._config.add_resource("bauxite", bauxite)

    def calculate_offline_reward(self) -> Optional[dict]:
        """计算离线挂机收益

        Returns:
            离线收益字典，若不满足条件返回 None
        """
        last_login = self._config.get_last_login()
        if not last_login:
            return None

        try:
            last_time = datetime.fromisoformat(last_login)
            now = datetime.now()

            offline_seconds = (now - last_time).total_seconds()
            offline_minutes = offline_seconds / 60

            if offline_minutes < self.OFFLINE_MIN_MINUTES:
                return None

            offline_minutes = min(offline_minutes, self.OFFLINE_MAX_MINUTES)

            rate = self._config.get_game_setting("idle_reward_rate", 1.0)

            fuel = math.ceil(offline_minutes * self.BASE_RATE / 3 * rate)
            ammo = math.ceil(offline_minutes * self.BASE_RATE / 3 * rate)
            steel = math.ceil(offline_minutes * self.BASE_RATE / 3 * rate)
            bauxite = math.ceil(offline_minutes * self.BASE_RATE / (3 * self.BAUXITE_INTERVAL) * rate)

            return {
                "fuel": fuel,
                "ammo": ammo,
                "steel": steel,
                "bauxite": bauxite,
                "offline_minutes": offline_minutes,
            }
        except Exception as e:
            get_logger(__name__).error("计算离线收益失败: %s", e)
            return None

    def apply_offline_reward(self) -> Optional[dict]:
        """计算并应用离线挂机收益

        Returns:
            离线收益字典（含 offline_minutes），若不满足条件返回 None
        """
        reward = self.calculate_offline_reward()
        if reward is None:
            return None

        self._config.add_resource("fuel", reward["fuel"])
        self._config.add_resource("ammo", reward["ammo"])
        self._config.add_resource("steel", reward["steel"])
        self._config.add_resource("bauxite", reward["bauxite"])

        return reward

    @staticmethod
    def format_offline_time(offline_minutes: float) -> str:
        """格式化离线时间显示"""
        hours = int(offline_minutes // 60)
        mins = int(offline_minutes % 60)
        if hours > 0:
            return f"{hours}小时{mins}分钟"
        return f"{mins}分钟"
