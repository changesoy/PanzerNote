# -*- coding: utf-8 -*-
"""游戏侧固定配色（D28：独立视觉域，值不随主题明暗变化）。

颜色集中放在 ``themes/game_palette.json``，不写死在 Python 代码里；
消费方（资源栏/游戏侧栏）经本加载器读取，主题切换不影响游戏侧观感。
"""
import json
from functools import lru_cache
from pathlib import Path

_GAME_PALETTE_FILE = Path(__file__).resolve().parents[2] / "themes" / "game_palette.json"


@lru_cache(maxsize=1)
def game_palette() -> dict[str, str]:
    """读取游戏侧固定配色（{key: "#RRGGBB"}）。"""
    with open(_GAME_PALETTE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("game_palette.json 顶层必须是 JSON 对象")
    return {str(k): str(v) for k, v in data.items()}
