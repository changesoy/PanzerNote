# -*- coding: utf-8 -*-
"""Markdown 标题解析器 — 纯函数，从文本中提取标题层级与行号"""

from __future__ import annotations

import re
from typing import List, Tuple

# (level, line_number, title)
Heading = Tuple[int, int, str]

# 匹配 Markdown ATX 标题：行首 1-6 个 # + 空格 + 标题文本
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")

# 匹配围栏代码块起止：``` 或 ~~~
_FENCE_RE = re.compile(r"^(```|~~~)")


def parse_headings(text: str) -> List[Heading]:
    """从 Markdown 文本中提取标题列表。

    返回按行号升序排列的 (层级, 行号(1-based), 标题文本) 列表。
    仅识别 ATX 风格标题（`# Title`），忽略 Setext 风格（下划线）。
    跳过围栏代码块内的 `#` 注释行。
    """
    headings: List[Heading] = []
    in_code_block = False
    for line_num, line in enumerate(text.split("\n"), start=1):
        if _FENCE_RE.match(line):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            headings.append((level, line_num, title))
    return headings
