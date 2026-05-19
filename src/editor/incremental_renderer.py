# -*- coding: utf-8 -*-
"""
Markdown 渲染缓存
基于文本 MD5 哈希的全文级缓存系统，避免重复渲染相同内容

核心设计：
1. 全文级缓存：基于文本 MD5 哈希缓存渲染结果
2. LRU淘汰：缓存满时淘汰最久未使用的条目
"""

import hashlib
from collections import OrderedDict
from typing import Callable, Optional

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


class RenderCache:
    """渲染缓存

    基于文本 MD5 哈希缓存渲染结果，相同文本直接返回缓存。
    当 feature flag "markdown_incremental" 关闭时，所有方法为空操作。
    """

    def __init__(self, render_func: Callable[[str], str], cache_size: int = 100):
        self._render_func = render_func
        self._cache = LRUCache(cache_size)
        self._last_text: str = ""
        self._last_html: str = ""

    def render(self, text: str) -> str:
        if not is_enabled("markdown_incremental"):
            self._last_text = text
            self._last_html = str(self._render_func(text))
            return self._last_html

        if not text:
            self._last_text = ""
            self._last_html = ""
            return ""

        if text == self._last_text:
            return self._last_html

        text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        cached = self._cache.get(text_hash)
        if cached is not None:
            self._last_text = text
            self._last_html = cached
            return cached

        result = str(self._render_func(text))

        self._cache.put(text_hash, result)
        self._last_text = text
        self._last_html = result

        return result

    def invalidate(self):
        self._last_text = ""
        self._last_html = ""
        self._cache.clear()
