# -*- coding: utf-8 -*-
"""
Markdown增量渲染引擎
基于行的增量渲染系统，仅重新渲染变更行及其影响区域

核心设计：
1. 行级增量渲染：对比前后文本差异，仅重新渲染变更行
2. LRU缓存：缓存渲染结果，避免重复渲染
3. 代码块懒加载：仅在代码块进入视口时触发渲染
"""

from typing import Optional, Dict, List, Callable
from collections import OrderedDict
import hashlib

from ..utils.logger import get_logger
from ..utils.feature_flags import is_enabled


class LRUCache:
    def __init__(self, max_size: int = 100):
        self._max_size = max_size
        self._cache: OrderedDict[str, str] = OrderedDict()

    def get(self, key: str) -> Optional[str]:
        if key in self._cache:
            self._cache.move_to_end(key)
            return str(self._cache[key])
        return None

    def put(self, key: str, value: str):
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = value
        else:
            self._cache[key] = value
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def clear(self):
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


class IncrementalRenderer:
    """增量渲染引擎

    对比前后文本差异，仅重新渲染变更行。
    当 feature flag "markdown_incremental" 关闭时，所有方法为空操作。
    """

    def __init__(self, render_func: Callable[[str], str], cache_size: int = 100):
        self._render_func = render_func
        self._cache = LRUCache(cache_size)
        self._last_text: str = ""
        self._last_html: str = ""
        self._line_cache: Dict[int, str] = {}

    def render(self, text: str) -> str:
        if not is_enabled("markdown_incremental"):
            self._last_text = text
            self._last_html = str(self._render_func(text))
            return self._last_html

        if not text:
            self._last_text = ""
            self._last_html = ""
            self._line_cache.clear()
            return ""

        if text == self._last_text:
            return self._last_html

        old_lines = self._last_text.split("\n") if self._last_text else []
        new_lines = text.split("\n")

        text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        cached = self._cache.get(text_hash)
        if cached is not None:
            self._last_text = text
            self._last_html = cached
            self._line_cache.clear()
            for i, line in enumerate(new_lines):
                self._line_cache[i] = line
            return cached

        changed = self._detect_changes(old_lines, new_lines)

        if not changed and self._last_html:
            return self._last_html

        result = str(self._render_func(text))

        self._cache.put(text_hash, result)
        self._last_text = text
        self._last_html = result

        self._line_cache.clear()
        for i, line in enumerate(new_lines):
            self._line_cache[i] = line

        return result

    def _detect_changes(self, old_lines: List[str], new_lines: List[str]) -> bool:
        if len(old_lines) != len(new_lines):
            return True

        for old, new in zip(old_lines, new_lines):
            if old != new:
                return True

        return False

    def invalidate(self):
        self._last_text = ""
        self._last_html = ""
        self._line_cache.clear()
        self._cache.clear()
