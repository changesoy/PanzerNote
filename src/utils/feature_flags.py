# -*- coding: utf-8 -*-
"""
Feature Flag 系统
控制性能优化特性的开关，默认使用旧有实现路径

行为说明：
- is_enabled(flag_name): 查询 flag 状态。若 flag_name 不在已注册列表中，
  记录警告日志并返回 False，避免拼写错误被静默忽略。
- set_enabled(flag_name, enabled): 设置 flag 状态。若 flag_name 不在已注册
  列表中，记录警告日志且不执行修改。
"""

import json
import os
from typing import Dict

from .logger import get_logger

_FLAGS: Dict[str, bool] = {
    "virtual_scroll": False,
    "lazy_highlight": False,
    "minimap_block_cache": False,
    "async_highlight": False,
    "markdown_incremental": False,
    "lazy_loading": False,
    "signal_driven_stats": True,
}

_FLAG_ALIASES: Dict[str, str] = {}

_config_path: str = ""


def init_flags(config_dir: str):
    global _config_path
    _config_path = os.path.join(config_dir, "feature_flags.json")
    if os.path.exists(_config_path):
        try:
            with open(_config_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                _FLAGS.update(saved)
        except Exception:
            get_logger(__name__).warning("加载 feature flags 失败", exc_info=True)


def is_enabled(flag_name: str) -> bool:
    """查询指定 feature flag 是否启用

    Args:
        flag_name: flag 名称，必须是 _FLAGS 中已注册的名称

    Returns:
        flag 的布尔值；若 flag_name 不存在则返回 False

    Note:
        当 flag_name 不在已注册列表中时，会记录警告日志，
        以便开发者在日志中发现拼写错误等问题。
    """
    resolved = _FLAG_ALIASES.get(flag_name, flag_name)
    if resolved not in _FLAGS:
        get_logger(__name__).warning(
            "查询了未注册的 feature flag: '%s'，已注册: %s",
            flag_name,
            list(_FLAGS.keys()),
        )
        return False
    return _FLAGS[resolved]


def set_enabled(flag_name: str, enabled: bool):
    """设置指定 feature flag 的状态

    Args:
        flag_name: flag 名称，必须是 _FLAGS 中已注册的名称
        enabled: 是否启用

    Note:
        当 flag_name 不在已注册列表中时，会记录警告日志且不执行修改。
    """
    resolved = _FLAG_ALIASES.get(flag_name, flag_name)
    if resolved not in _FLAGS:
        get_logger(__name__).warning(
            "尝试设置未注册的 feature flag: '%s'，已注册: %s",
            flag_name,
            list(_FLAGS.keys()),
        )
        return
    _FLAGS[resolved] = enabled
    if flag_name in _FLAGS and flag_name != resolved:
        _FLAGS[flag_name] = enabled
    _save()


def get_all_flags() -> Dict[str, bool]:
    return dict(_FLAGS)


def _save():
    if _config_path:
        try:
            with open(_config_path, "w", encoding="utf-8") as f:
                json.dump(_FLAGS, f, indent=2)
        except Exception:
            get_logger(__name__).warning("保存 feature flags 失败", exc_info=True)
