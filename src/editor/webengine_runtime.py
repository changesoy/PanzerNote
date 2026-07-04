# -*- coding: utf-8 -*-
"""
管理应用启动阶段的首个 WebEngine 控件挂载。
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, QTimer, Qt
from PyQt6.QtWidgets import QWidget

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    WEBENGINE_AVAILABLE = True
except ImportError:
    QWebEngineView = None  # type: ignore[assignment,misc]
    WEBENGINE_AVAILABLE = False


class WebEngineRuntime(QObject):
    """管理应用启动阶段的首个 WebEngine 控件挂载。"""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._anchor_host: Optional[QWidget] = None
        self._anchor_view: Optional[QWebEngineView] = None
        self._real_view_attached = False

    @property
    def available(self) -> bool:
        return WEBENGINE_AVAILABLE

    def prepare_startup_anchor(self, parent: QWidget) -> None:
        """在主窗口显示前挂载一个最小 WebEngine 控件。"""
        if not self.available:
            return

        if self._anchor_view is not None:
            return

        host = QWidget(parent)
        host.setObjectName("webEngineStartupAnchor")
        host.setGeometry(0, 0, 1, 1)
        host.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        host.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )

        view = QWebEngineView(host)
        view.setGeometry(0, 0, 1, 1)
        view.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        view.setHtml(
            "<!doctype html><html><body></body></html>"
        )

        host.show()
        view.show()

        host.lower()

        self._anchor_host = host
        self._anchor_view = view

    def notify_real_view_attached(self) -> None:
        """首个真实预览视图进入控件树后释放启动锚点。"""
        if self._real_view_attached:
            return

        self._real_view_attached = True

        QTimer.singleShot(0, self._release_startup_anchor)

    def _release_startup_anchor(self) -> None:
        host = self._anchor_host

        self._anchor_host = None
        self._anchor_view = None

        if host is not None:
            host.deleteLater()