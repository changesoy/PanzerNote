# -*- coding: utf-8 -*-
"""
括号匹配器

提供纯函数，在文本中扫描与光标处括号配对的括号位置。
支持嵌套匹配、扫描上限、中英文括号。
"""

from typing import Dict, Optional, Tuple

# 需匹配的括号对（不含引号，引号语义匹配过于复杂）
BRACKET_PAIRS: Dict[str, str] = {
    # 英文括号
    '(': ')',
    '[': ']',
    '{': '}',
    # 中文括号
    '\uff08': '\uff09',  # （）
    '\u3010': '\u3011',  # 【】
    '\u300c': '\u300d',  # 「」
    '\u300e': '\u300f',  # 『』
    '\u300a': '\u300b',  # 《》
    '\u3008': '\u3009',  # 〈〉
}

# 反向映射：闭合 → 开始
_CLOSE_TO_OPEN: Dict[str, str] = {v: k for k, v in BRACKET_PAIRS.items()}

# 扫描上限（字符数），防止超大文件卡顿
SCAN_LIMIT = 20000


def find_matching_bracket(
    text: str,
    cursor_pos: int,
) -> Tuple[Optional[int], Optional[int]]:
    """查找与光标位置最近括号匹配的配对括号

    检测光标前一字符和后一字符是否为括号，若是则扫描配对位置。

    参数：
      text：文档完整文本
      cursor_pos：光标位置（整数值，0 ≤ cursor_pos ≤ len(text)）
    返回：
      (bracket_pos, match_pos)，均未匹配时返回 (None, None)
      - bracket_pos：光标处括号的位置
      - match_pos：配对括号的位置

    示例：
      text="(hello)"，cursor_pos=1（光标在 ( 后）→ (0, 6)
      text="(hello)"，cursor_pos=6（光标在 ) 前）→ (6, 0)
      text="hello"，cursor_pos=0 → (None, None)
    """
    if not text or cursor_pos < 0 or cursor_pos > len(text):
        return (None, None)

    # 优先检查光标前一字符
    if cursor_pos > 0:
        char_before = text[cursor_pos - 1]
        if char_before in BRACKET_PAIRS or char_before in _CLOSE_TO_OPEN:
            match = _try_match(text, cursor_pos - 1, char_before)
            return (cursor_pos - 1, match)

    # 再检查光标后一字符
    if cursor_pos < len(text):
        char_after = text[cursor_pos]
        if char_after in BRACKET_PAIRS or char_after in _CLOSE_TO_OPEN:
            match = _try_match(text, cursor_pos, char_after)
            return (cursor_pos, match)

    return (None, None)


def _try_match(text: str, bracket_pos: int, char: str) -> Optional[int]:
    """尝试为 bracket_pos 处的括号查找配对位置

    返回配对位置，若 char 非括号或超限未找到则返回 None。
    """
    if char in BRACKET_PAIRS:
        # 开始括号 → 向前扫描
        return _scan_forward(text, bracket_pos, char, BRACKET_PAIRS[char])

    if char in _CLOSE_TO_OPEN:
        # 闭合括号 → 向后扫描
        open_char = _CLOSE_TO_OPEN[char]
        return _scan_backward(text, bracket_pos, open_char, char)

    return None


def _scan_forward(text: str, start: int, open_char: str, close_char: str) -> Optional[int]:
    """从 start 位置向前扫描配对的闭合括号

    使用计数器处理嵌套：
      - 遇到同类型开始括号，计数器 +1
      - 遇到同类型闭合括号，计数器 -1
      - 计数器归零时找到配对
    """
    depth = 1
    limit = min(len(text), start + SCAN_LIMIT + 1)
    for i in range(start + 1, limit):
        ch = text[i]
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return i
    return None


def _scan_backward(text: str, start: int, open_char: str, close_char: str) -> Optional[int]:
    """从 start 位置向后扫描配对的开始括号

    计数器逻辑同 _scan_forward，方向相反。
    """
    depth = 1
    limit = max(0, start - SCAN_LIMIT)
    for i in range(start - 1, limit - 1, -1):
        ch = text[i]
        if ch == close_char:
            depth += 1
        elif ch == open_char:
            depth -= 1
            if depth == 0:
                return i
    return None
