# -*- coding: utf-8 -*-
"""
定时器管理模块
集中管理主窗口的所有 QTimer
"""

from PyQt5.QtCore import QTimer, QObject
from typing import Callable, Optional

from ..core.config import Config
from ..utils.logger import get_logger


class TimerManager(QObject):
    """定时器管理器

    管理三类定时器：
    - auto_save_timer: 自动保存
    - stats_timer: 统计信息刷新
    - idle_reward_timer: 在线挂机奖励
    """

    def __init__(self, config: Config, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._logger = get_logger(__name__)

        self.auto_save_timer: Optional[QTimer] = None
        self.stats_timer: Optional[QTimer] = None
        self.idle_reward_timer: Optional[QTimer] = None

        self._on_auto_save: Optional[Callable] = None
        self._on_update_stats: Optional[Callable] = None
        self._on_idle_reward: Optional[Callable] = None

    def setup(
        self,
        on_auto_save: Callable,
        on_update_stats: Callable,
        on_idle_reward: Callable,
    ) -> None:
        """初始化所有定时器并绑定回调

        Args:
            on_auto_save: 自动保存回调
            on_update_stats: 统计更新回调
            on_idle_reward: 挂机奖励回调
        """
        self._on_auto_save = on_auto_save
        self._on_update_stats = on_update_stats
        self._on_idle_reward = on_idle_reward

        self.auto_save_timer = QTimer(self)
        interval = self._config.get_editor_setting("auto_save_interval", 30) * 1000
        self.auto_save_timer.setInterval(interval)
        self.auto_save_timer.timeout.connect(self._handle_auto_save)
        self.auto_save_timer.start()

        self.stats_timer = QTimer(self)
        self.stats_timer.setInterval(500)
        self.stats_timer.timeout.connect(self._handle_update_stats)
        self.stats_timer.start()

        self.idle_reward_timer = QTimer(self)
        self.idle_reward_timer.setInterval(60000)
        self.idle_reward_timer.timeout.connect(self._handle_idle_reward)
        self.idle_reward_timer.start()

    def update_auto_save_interval(self, seconds: int) -> None:
        """更新自动保存间隔"""
        if self.auto_save_timer:
            self.auto_save_timer.setInterval(seconds * 1000)

    def stop_all(self) -> None:
        """停止所有定时器"""
        for timer in (self.auto_save_timer, self.stats_timer, self.idle_reward_timer):
            if timer:
                timer.stop()

    def _handle_auto_save(self) -> None:
        if self._on_auto_save:
            try:
                self._on_auto_save()
            except Exception as e:
                self._logger.error("自动保存回调异常: %s", e)

    def _handle_update_stats(self) -> None:
        if self._on_update_stats:
            try:
                self._on_update_stats()
            except Exception as e:
                self._logger.error("统计更新回调异常: %s", e)

    def _handle_idle_reward(self) -> None:
        if self._on_idle_reward:
            try:
                self._on_idle_reward()
            except Exception as e:
                self._logger.error("挂机奖励回调异常: %s", e)
