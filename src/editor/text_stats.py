# -*- coding: utf-8 -*-
"""
文本统计纯函数

提供中英文混合词数统计，将 CJK 表意文字按“字”计数，
拉丁/数字/下划线等按“词”计数，两者相加。
"""

import re
from typing import List, Tuple


# CJK 主要区间：CJK Unified Ideographs + CJK Extension A
_CJK_RANGES: List[Tuple[int, int]] = [
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0x3400, 0x4DBF),   # CJK Extension A
]

_CJK_PATTERN = re.compile(
    "|".join(
        f"[{chr(lo)}-{chr(hi)}]"
        for lo, hi in _CJK_RANGES
    )
)

# 拉丁/数字/下划线等词组分隔
_WORD_PATTERN = re.compile(r"[A-Za-z0-9_\u00C0-\u024F]+")


def count_mixed_words(text: str) -> int:
    """统计中英文混合文本的词数

    - CJK 表意文字按单字计数
    - 拉丁字母/数字/下划线等按词计数
    - 二者相加

    参数：
      text：待统计的文本
    返回：
      词数（整数）
    """
    if not text:
        return 0

    cjk_count = len(_CJK_PATTERN.findall(text))
    word_count = len(_WORD_PATTERN.findall(text))
    return cjk_count + word_count
