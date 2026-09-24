# -*- coding: utf-8 -*-
"""
状态栏组件
显示光标位置、字符数、编码、文件类型
"""

from PyQt6.QtWidgets import QStatusBar, QLabel, QFrame, QHBoxLayout, QWidget, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QUrl
from PyQt6.QtGui import QDesktopServices

from ..themes.theme_aware_mixin import ThemeAwareMixin
from ..themes.theme_v2.consumer import v2_token


class StatusBarWidget(ThemeAwareMixin, QStatusBar):

    eol_toggled = pyqtSignal(str)

    def __init__(self, theme_engine, parent=None):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("StatusBar 必须传入 theme_engine，不允许为 None")
        self._init_ui()
        self._init_theme(theme_engine)

    def _init_ui(self):
        self._separator_style = ""

        left_widget = QWidget()
        left_layout = QHBoxLayout(left_widget)
        left_layout.setContentsMargins(5, 0, 5, 0)
        left_layout.setSpacing(0)

        self.position_label = QLabel("行 1, 列 1")
        self.position_label.setMinimumWidth(100)
        left_layout.addWidget(self.position_label)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        left_layout.addWidget(sep1)
        self._sep1 = sep1

        self.char_count_label = QLabel("0 个字符")
        self.char_count_label.setMinimumWidth(80)
        left_layout.addWidget(self.char_count_label)

        sep1b = QFrame()
        sep1b.setFrameShape(QFrame.Shape.VLine)
        left_layout.addWidget(sep1b)
        self._sep1b = sep1b

        self.word_count_label = QLabel("0 个词")
        self.word_count_label.setMinimumWidth(70)
        left_layout.addWidget(self.word_count_label)

        self.addWidget(left_widget)

        self.addWidget(QLabel(""), 1)

        self.encoding_label = QLabel("UTF-8")
        self.encoding_label.setMinimumWidth(60)
        self.encoding_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.addPermanentWidget(self.encoding_label)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        self.addPermanentWidget(sep2)
        self._sep2 = sep2

        self.eol_label = QLabel("LF")
        self.eol_label.setMinimumWidth(40)
        self.eol_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.eol_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.eol_label.setToolTip("点击切换行尾类型（LF ↔ CRLF）")
        self.eol_label.installEventFilter(self)
        self.addPermanentWidget(self.eol_label)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.VLine)
        self.addPermanentWidget(sep3)
        self._sep3 = sep3

        self.file_type_label = QLabel("纯文本")
        self.file_type_label.setMinimumWidth(70)
        self.file_type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.addPermanentWidget(self.file_type_label)

        # 大文件模式指示（1.3 D6）：仅当前编辑器处于大文件模式时显示
        sep4 = QFrame()
        sep4.setFrameShape(QFrame.Shape.VLine)
        self.addPermanentWidget(sep4)
        self._sep4 = sep4

        self.large_file_label = QLabel("大文件")
        self.large_file_label.setToolTip(
            "当前文档处于大文件模式（达 1 万行自动降级高成本功能）：\n"
            "关闭自动补全、跳过折叠计算、隐藏缩略图、暂停预览自动刷新、"
            "禁用切换动画\n"
            "（可在设置 → 编辑器 → 大文件中关闭该模式）"
        )
        sep4.hide()
        self.large_file_label.hide()
        self.addPermanentWidget(self.large_file_label)

        # 预览健康诊断（1.4）：WebView2 缺失 / 初始化失败时显示，
        # 点击弹出原因与修复指引（D7 已决：状态栏 + 点击弹对话框）
        sep5 = QFrame()
        sep5.setFrameShape(QFrame.Shape.VLine)
        self.addPermanentWidget(sep5)
        self._sep5 = sep5

        self.preview_health_label = QLabel("预览不可用")
        self.preview_health_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview_health_label.setToolTip("预览后端不可用，点击查看原因与修复指引")
        self.preview_health_label.installEventFilter(self)
        sep5.hide()
        self.preview_health_label.hide()
        self.addPermanentWidget(self.preview_health_label)
        self._preview_failure_reason: str | None = None

    def _apply_theme_colors(self):
        # B3：状态栏消费 statusbar recipe（补漏 C：收敛自建 v2_token QSS → recipe 单一来源）
        # 兜底字面量 = v1 light 值（recipe 缺失时保持旧观感，理论不触发）。
        style = None
        components = getattr(self._theme_engine, "components", None)
        if components is not None:
            style = components.resolve("statusbar")
        if style is None:
            statusbar_bg = v2_token(self._theme_engine, "surface_secondary", "#F5F5F5")
            border = v2_token(self._theme_engine, "border_muted", "#E0E0E0")
            text_primary = v2_token(self._theme_engine, "text_primary", "#212121")
            divider = v2_token(self._theme_engine, "border_muted", "#EEEEEE")
        else:
            statusbar_bg = style["background"]
            border = style["border"]
            text_primary = style["text"]
            divider = style["divider"]
        self.setStyleSheet(f"""
            QStatusBar {{
                background-color: {statusbar_bg};
                border-top: 1px solid {border};
            }}
            QStatusBar::item {{
                border: none;
            }}
            QLabel {{
                padding: 2px 8px;
                color: {text_primary};
            }}
        """)
        sep_style = f"""
            QFrame {{
                background-color: {divider};
                max-width: 1px;
                margin: 3px 0px;
            }}
        """
        self._separator_style = sep_style
        for sep in (self._sep1, self._sep1b, self._sep2, self._sep3, self._sep4, self._sep5):
            sep.setStyleSheet(sep_style)

    def eventFilter(self, obj, event):
        """拦截 EOL 标签的鼠标释放事件进行切换"""
        if obj is self.eol_label and event.type() == QEvent.Type.MouseButtonRelease:
            current = self.eol_label.text()
            new_eol = "CRLF" if current in ("LF", "Mixed") else "LF"
            self.eol_label.setText(new_eol)
            self.eol_toggled.emit(new_eol)
            return True
        # 1.4：点击「预览不可用」标签弹出诊断对话框
        #（getattr 防护：构造期 _init_ui 未完成时该属性尚不存在）
        label = getattr(self, "preview_health_label", None)
        if (
            label is not None
            and obj is label
            and event.type() == QEvent.Type.MouseButtonRelease
        ):
            self._show_preview_diagnosis()
            return True
        return super().eventFilter(obj, event)

    def update_stats(self, char_count: int, line: int, column: int,
                     encoding: str = "UTF-8", file_type: str = "纯文本",
                     word_count: int = 0, eol: str = "LF"):
        self.position_label.setText(f"行 {line}, 列 {column}")
        self.char_count_label.setText(f"{char_count} 个字符")
        self.word_count_label.setText(f"{word_count} 个词")
        self.encoding_label.setText(encoding.upper())
        self.eol_label.setText(eol)
        self.file_type_label.setText(file_type)

    def set_encoding(self, encoding: str):
        self.encoding_label.setText(encoding.upper())

    def set_file_type(self, file_type: str):
        self.file_type_label.setText(file_type)

    def set_large_file_mode(self, active: bool) -> None:
        """切换「大文件」指示标签可见性（随当前编辑器状态更新）。"""
        self._sep4.setVisible(active)
        self.large_file_label.setVisible(active)

    def set_preview_unavailable(self, reason: str | None) -> None:
        """预览后端不可用时显示常驻指示（1.4，D7 已决）。

        reason 为用户可读的失败原因；传 None 隐藏指示并清除原因
        （当前故障均需重启应用才能恢复，正常会话不会走到隐藏路径）。
        """
        self._preview_failure_reason = reason
        visible = reason is not None
        self._sep5.setVisible(visible)
        self.preview_health_label.setVisible(visible)

    def _show_preview_diagnosis(self) -> None:
        """弹出预览故障诊断对话框：具体原因 + 通用修复指引 + 下载入口。"""
        reason = self._preview_failure_reason
        if not reason:
            return
        # 惰性导入：仅点击时需要，避免状态栏构造期耦合运行时检测模块
        from .webview2_runtime import DOWNLOAD_URL, INSTALL_HINT

        text = reason if INSTALL_HINT in reason else f"{reason}\n\n{INSTALL_HINT}"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("预览不可用")
        box.setText(text)
        open_button = box.addButton("打开下载页", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("关闭", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl(DOWNLOAD_URL))
