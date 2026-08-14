# -*- coding: utf-8 -*-
"""
Document 级 Markdown 渲染缓存（跨 Preview 共享，Wave 4 C 批）

同一 SharedDocument 的多 View 预览共用一份渲染结果：以 QTextDocument 弱引用 +
doc.revision() 为键缓存最终 HTML（含代码块高亮 / 本地图片 / 折叠包裹 / source map）。

- revision 单调递增且内容不变则不变 → 内容未变即命中，跳过渲染
- 弱引用键：文档关闭/释放自动回收，无泄漏、无需手动清理
- 每 document 仅保留最新一条，不保留历史 revision
- 仅主线程访问（渲染由防抖定时器驱动），无需加锁
"""

import weakref
from typing import Callable, Tuple

from PyQt6.QtGui import QTextDocument

# 每 document 一条：content_version -> 最终 HTML
_CacheEntry = Tuple[int, str]


class DocumentRenderCache:
    def __init__(self) -> None:
        self._cache: weakref.WeakKeyDictionary[
            QTextDocument, _CacheEntry
        ] = weakref.WeakKeyDictionary()

    def get_or_render(
        self,
        doc: QTextDocument,
        revision: int,
        render_func: Callable[[], str],
    ) -> str:
        """同 document 且 revision 相同 → 返回缓存；否则渲染并写入缓存。"""
        cached = self._cache.get(doc)
        if cached is not None and cached[0] == revision:
            return cached[1]
        html = render_func()
        self._cache[doc] = (revision, html)
        return html

    def clear(self) -> None:
        """清空全部缓存（主题切换等影响渲染产物的场景调用）。"""
        self._cache.clear()


# 全局共享实例：多 Preview widget 跨实例共用
_DOC_RENDER_CACHE = DocumentRenderCache()


def clear_document_render_cache() -> None:
    """供主题切换等场景显式失效缓存。"""
    _DOC_RENDER_CACHE.clear()
