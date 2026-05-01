# -*- coding: utf-8 -*-
"""
Feature Flag 系统
控制性能优化特性的开关，默认使用旧有实现路径
"""

import json
import os
from typing import Dict

_FLAGS: Dict[str, bool] = {
    "virtual_scroll": False,
    "minimap_block_cache": False,
    "async_highlight": False,
    "markdown_incremental": False,
    "lazy_loading": False,
}

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
            pass


def is_enabled(flag_name: str) -> bool:
    return _FLAGS.get(flag_name, False)


def set_enabled(flag_name: str, enabled: bool):
    if flag_name in _FLAGS:
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
            pass
