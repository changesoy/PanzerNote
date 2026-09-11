# -*- coding: utf-8 -*-
"""WebEngine 后端：WebPreviewAdapter 的 Qt WebEngine 实现

把既有 QWebEngineView 用法原样搬运到接口实现中，行为逐条对齐，
不改变任何可观察行为：

  widget()            -> QWebEngineView 本体
  set_html()          -> QWebEngineView.setHtml（base_url 取自 set_resource_root）
  run_javascript()    -> page().runJavaScript（page 为 None 时静默跳过）
  set_visible()       -> QWebEngineView.setVisible
  set_resource_root() -> 记住根目录，供下次 set_html 作为 base_url
  export_pdf()        -> loadFinished -> page().printToPdf(cb)
  load_finished       -> 转发 QWebEngineView.loadFinished
  message_received    -> 转发 page().titleChanged（保持既有 title 前缀协议）
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QByteArray, QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QWidget

from .web_preview import WebPreviewAdapter


class WebEnginePreviewAdapter(WebPreviewAdapter):
    """基于 QWebEngineView 的预览适配器。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._view = QWebEngineView(parent)
        self._resource_root: str | None = None

        self._view.loadFinished.connect(self.load_finished)

        page = self._view.page()
        if page is not None:
            # 预览 -> 编辑器：JS 经 document.title 回传消息
            page.titleChanged.connect(self.message_received)

    def widget(self) -> QWidget:
        return self._view

    def set_html(self, html: str) -> None:
        if self._resource_root:
            base_url = QUrl.fromLocalFile(self._resource_root + '/')
            self._view.setHtml(html, base_url)
        else:
            self._view.setHtml(html)

    def run_javascript(self, script: str) -> None:
        page = self._view.page()
        if page is not None:
            page.runJavaScript(script)

    def set_visible(self, visible: bool) -> None:
        self._view.setVisible(visible)

    def set_resource_root(self, root: str | None) -> None:
        self._resource_root = root

    def export_pdf(self, html: str, on_done: Callable[[bytes], None]) -> None:
        view = self._view

        def _release() -> None:
            # 与既有实现一致：释放离屏控件；同时释放适配器自身（一次性使用）
            view.deleteLater()
            self.deleteLater()

        def _on_load_finished(ok: bool) -> None:
            if not ok:
                on_done(b"")
                _release()
                return
            page = view.page()
            if page is None:
                on_done(b"")
                _release()
                return
            page.printToPdf(lambda pdf_data: _on_pdf_ready(pdf_data))

        def _on_pdf_ready(pdf_data: QByteArray | bytes | bytearray | memoryview) -> None:
            # 统一收敛为 bytes，兑现接口契约（内容与原实现逐字节一致）
            payload: bytes
            if isinstance(pdf_data, QByteArray):
                payload = pdf_data.data()
            elif isinstance(pdf_data, (bytes, bytearray)):
                payload = bytes(pdf_data)
            else:
                payload = pdf_data.tobytes()
            on_done(payload)
            _release()

        view.loadFinished.connect(_on_load_finished)
        self.set_html(html)
