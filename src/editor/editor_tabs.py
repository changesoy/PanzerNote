# -*- coding: utf-8 -*-
"""
编辑器标签页组件
管理多个编辑器标签，支持Markdown分屏预览

v1.5.4 改动：
  - 集成 FindReplaceBar 查找替换功能
  - DraggableTabBar：支持将标签拖拽到文件树移动文件
  - auto_minimap 支持
"""

import os
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Set, cast

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QTabBar, QMessageBox,
    QFileDialog, QPlainTextEdit, QTextEdit, QMenu,
    QInputDialog, QLabel, QDialog, QHBoxLayout, QComboBox,
    QPushButton, QLineEdit, QFormLayout, QApplication, QToolButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QPoint, QByteArray
from PyQt6.QtGui import QFont, QTextCursor, QColor, QTextCharFormat, QDrag, QAction

from ..core.config import Config
from ..core.document_model import TabState, TabStateRegistry
from ..utils.logger import get_logger
from ..utils.error_handler import ErrorHandler, ErrorCategory
from ..utils.feature_flags import is_enabled
from ..security.file_guard import FileSizeExceededError, FileOperationTimeoutError
from ..security.file_access_context import FileAccessContext
from ..security.input_validator import InputValidator
from ..themes.theme_aware_mixin import ThemeAwareMixin
from .editor import Editor
from .markdown_preview import MarkdownPreviewWidget
from .find_replace import FindReplaceBar
from .save_task_manager import SaveTaskManager, SaveState
from .temp_session_manager import TempSessionManager
from .eol_utils import detect_eol_from_bytes
from .webengine_runtime import WebEngineRuntime


# ════════════════════════════════════════════════════════
#  另存为对话框
# ════════════════════════════════════════════════════════

class SaveAsDialog(QDialog):
    """另存为对话框 - 支持选择编码"""

    def __init__(self, suggested_path: str, current_encoding: str = "UTF-8", parent=None):
        super().__init__(parent)
        self.setWindowTitle("另存为")
        self.setMinimumWidth(500)

        self._filepath = ""
        self._encoding = current_encoding

        layout = QVBoxLayout(self)

        # 文件路径
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("文件名:"))
        self.path_edit = QLineEdit(suggested_path)
        path_layout.addWidget(self.path_edit, 1)
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        # 编码选择
        encoding_layout = QHBoxLayout()
        encoding_layout.addWidget(QLabel("编码:"))
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(["UTF-8", "GBK", "UTF-16"])
        index = self.encoding_combo.findText(current_encoding.upper())
        if index >= 0:
            self.encoding_combo.setCurrentIndex(index)
        encoding_layout.addWidget(self.encoding_combo)
        encoding_layout.addStretch()
        layout.addLayout(encoding_layout)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _browse(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "另存为", self.path_edit.text(),
            "文本文件 (*.txt);;Markdown (*.md);;Python (*.py);;网页文件 (*.html);;PDF 文档 (*.pdf);;所有文件 (*.*)"
        )
        if filepath:
            self.path_edit.setText(filepath)

    def _save(self):
        path = self.path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "提示", "请输入文件名")
            return
        self._filepath = path
        self._encoding = self.encoding_combo.currentText()
        self.accept()

    def get_filepath(self) -> str:
        return self._filepath

    def get_encoding(self) -> str:
        return self._encoding


# ════════════════════════════════════════════════════════
#  DraggableTabBar —— 支持拖拽标签到文件树
# ════════════════════════════════════════════════════════

# 自定义 MIME 类型
MIME_TAB_FILEPATH = "application/x-panzernote-tab-filepath"
# 3.5.11：未命名标签（无 filepath）拖拽时携带 tab_id，供迁移/落盘定位源标签
MIME_TAB_ID = "application/x-panzernote-tab-id"


class DraggableTabBar(QTabBar):
    """可拖拽标签栏

    在 QTabBar 内部拖拽 → 正常的标签重新排序
    向外拖拽（如文件树） → 发起 QDrag，携带文件路径信息，可移动文件
    """

    file_drop_requested = pyqtSignal(str, str)  # (src_filepath, dest_folder)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_start_pos = QPoint()
        self._drag_tab_index = -1

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self._drag_tab_index = self.tabAt(event.pos())
        elif event.button() == Qt.MouseButton.MiddleButton:
            tab_index = self.tabAt(event.pos())
            if tab_index >= 0:
                self.tabCloseRequested.emit(tab_index)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return

        if self._drag_tab_index < 0:
            super().mouseMoveEvent(event)
            return

        # 只有鼠标离开标签栏区域才发起外部拖拽
        if self.rect().contains(event.pos()):
            super().mouseMoveEvent(event)
            return

        # 距离阈值
        distance = (event.pos() - self._drag_start_pos).manhattanLength()
        if distance < QApplication.startDragDistance():
            super().mouseMoveEvent(event)
            return

        # 获取该标签对应的 tab_id 与文件路径（3.5.11：未命名标签无路径也可拖拽）
        tab_widget = cast(QTabWidget, self.parent())
        if not tab_widget or not hasattr(tab_widget, '_get_filepath_for_index'):
            super().mouseMoveEvent(event)
            return

        widget = tab_widget.widget(self._drag_tab_index)
        tab_id = getattr(widget, 'tab_id', None) if widget else None
        if tab_id is None:
            super().mouseMoveEvent(event)
            return

        filepath = tab_widget._get_filepath_for_index(self._drag_tab_index) or ""

        # 发起 QDrag
        # 注意：MIME_TAB_FILEPATH 仅对已保存文件设置——空数据格式在平台拖拽协议中
        # 可能被丢弃，导致目标 hasFormat 判断失败；未命名标签靠 MIME_TAB_ID 识别。
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_TAB_ID, str(tab_id).encode('utf-8'))
        if filepath:
            mime.setData(MIME_TAB_FILEPATH, filepath.encode('utf-8'))
            mime.setText(os.path.basename(filepath))
        drag.setMimeData(mime)

        result = drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction)
        self._drag_tab_index = -1


# ════════════════════════════════════════════════════════
#  _TabCloseButton —— 自定义关闭按钮容器
# ════════════════════════════════════════════════════════

class _TabCloseButton(QWidget):
    """标签关闭按钮容器。

    原生 QTabBar 关闭按钮是固定贴右边缘的 QToolButton widget，
    QSS 的 subcontrol-position / right / margin 对它无效，
    tab 的 padding-right 也不影响其位置。
    本容器用固定宽度 + QHBoxLayout 的 contentsMargins 右侧留白，
    让内部小按钮左移，使 × 图标落在文字与 tab 右边界之间。
    """

    def __init__(self, theme_engine, parent=None):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("_TabCloseButton 必须传入 theme_engine，不允许为 None")
        self._theme_engine = theme_engine
        self.setFixedSize(28, 22)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 10, 1)
        layout.setSpacing(0)

        self._btn = QToolButton()
        self._btn.setObjectName("tabCloseInnerBtn")
        self._btn.setFixedSize(15, 16)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setText("×")
        colors = theme_engine.get_active_theme().colors
        self._apply_btn_style(colors)
        layout.addWidget(self._btn)
        layout.addStretch()

        self._btn.clicked.connect(self._on_clicked)

    def _apply_btn_style(self, colors) -> None:
        self._btn.setStyleSheet(
            f"#tabCloseInnerBtn {{ border: none; background: transparent; border-radius: 2px; padding: 0; }}"
            f"#tabCloseInnerBtn:hover {{ background: {colors.hover_bg}; }}"
        )

    def _on_clicked(self):
        tab_bar = self.parent()
        while tab_bar is not None and not isinstance(tab_bar, QTabBar):
            tab_bar = tab_bar.parent()
        if tab_bar is None:
            return
        for i in range(tab_bar.count()):
            if tab_bar.tabButton(i, QTabBar.ButtonPosition.RightSide) is self:
                tab_widget = tab_bar.parent()
                while tab_widget is not None and not isinstance(tab_widget, QTabWidget):
                    tab_widget = tab_widget.parent()
                if tab_widget is not None and hasattr(tab_widget, '_on_tab_close_requested'):
                    tab_widget._on_tab_close_requested(i)
                return


# ════════════════════════════════════════════════════════
#  EditorTabWidget
# ════════════════════════════════════════════════════════

class EditorTabWidget(ThemeAwareMixin, QTabWidget):
    """编辑器标签页管理"""

    current_changed = pyqtSignal(int)
    content_modified = pyqtSignal()
    tab_count_changed = pyqtSignal(int)
    chars_typed = pyqtSignal(int)
    cursor_position_changed = pyqtSignal()
    word_count_updated = pyqtSignal()
    file_saved = pyqtSignal()

    def __init__(
        self,
        config: Config,
        theme_engine,
        webengine_runtime: WebEngineRuntime | None = None,
        parent=None,
    ):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("EditorTabs 必须传入 theme_engine，不允许为 None")
        self.config = config
        self._theme_engine = theme_engine
        self._webengine_runtime = webengine_runtime

        self._registry = TabStateRegistry()
        self._next_tab_id = 0
        self._used_untitled_numbers: Set[int] = set()
        self._closed_tabs_stack: List[Dict] = []

        self._save_manager = SaveTaskManager(self)
        self._save_manager.save_state_changed.connect(self._on_save_state_changed)
        self._save_manager.save_failed.connect(self._on_save_failed)

        self._pending_close_tab_ids: Set[int] = set()
        self._pending_save_info: Dict[int, Dict] = {}
        self._pending_save_as_info: Dict[int, Dict] = {}

        self._session_manager = TempSessionManager(config.get_temp_path(), config.get_file_guard())

        self._tab_bar = DraggableTabBar(self)
        self.setTabBar(self._tab_bar)

        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        # 3.5.4：接受跨分屏标签迁移拖拽（MIME_TAB_FILEPATH）
        self.setAcceptDrops(True)

        self.tabCloseRequested.connect(self._on_tab_close_requested)
        self.currentChanged.connect(self._on_current_changed)

        tb = self.tabBar()
        if tb is not None:
            tb.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            tb.customContextMenuRequested.connect(self._show_tab_context_menu)

        self._init_theme(theme_engine)

        # ── 查找替换栏（嵌入在标签内容上方） ──
        # 不在这里创建，而是由 main_window 在 editor_container 中创建
        self._find_bar: Optional[FindReplaceBar] = None

    def tabInserted(self, index):
        super().tabInserted(index)
        btn = _TabCloseButton(self._theme_engine, self)
        self.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, btn)  # type: ignore[union-attr]
        # 3.5.12：迁移过来的标签 tab_id 已存在，先刷新 tooltip（未注册时显示「未保存」）
        self._update_tab_tooltip(index)

    def _update_tab_tooltip(self, index: int) -> None:
        """3.5.12：标签 tooltip 区分已保存（完整路径）与未保存（「未保存」）。"""
        widget = self.widget(index)
        tab_id = getattr(widget, 'tab_id', None)
        if tab_id is None:
            return
        state = self._registry.get(tab_id)
        if state is not None and state.filepath and not state.is_new:
            self.setTabToolTip(index, state.filepath)
        else:
            self.setTabToolTip(index, "未保存")

    def set_find_bar(self, find_bar: FindReplaceBar):
        """设置外部传入的查找替换栏"""
        self._find_bar = find_bar

    @property
    def save_manager(self) -> SaveTaskManager:
        return self._save_manager

    @property
    def session_manager(self) -> TempSessionManager:
        return self._session_manager

    @property
    def registry(self) -> TabStateRegistry:
        """类型化的文档状态注册表（替代 _tab_info dict）"""
        return self._registry

    def _get_filepath_for_index(self, index: int) -> Optional[str]:
        """获取指定标签页的文件路径（供 DraggableTabBar 使用）"""
        widget = self.widget(index)
        if widget and hasattr(widget, 'tab_id'):
            state = self._registry.get(widget.tab_id)
            if state and state.filepath and not state.is_new:
                return state.filepath
        return None

    def _get_editor_from_widget(self, widget) -> Optional[Editor]:
        if isinstance(widget, Editor):
            return widget
        elif isinstance(widget, MarkdownPreviewWidget):
            return widget.editor
        return None

    @staticmethod
    def _strip_tab_suffix(title: str) -> str:
        for suffix in (" !", " ⏳", " *"):
            if title.endswith(suffix):
                return title[:-len(suffix)]
        return title

    def _iter_editors(self):
        for i in range(self.count()):
            widget = self.widget(i)
            editor = self._get_editor_from_widget(widget)
            if editor:
                yield editor

    def _get_next_untitled_number(self) -> int:
        num = 1
        while num in self._used_untitled_numbers:
            num += 1
        return num

    def _release_untitled_number(self, title: str):
        if title.startswith("未命名") and title.endswith(".txt"):
            try:
                num = int(title[3:-4])
                self._used_untitled_numbers.discard(num)
            except ValueError:
                get_logger(__name__).debug("未命名标签页编号解析失败: %s", title)

    def _generate_tab_id(self) -> int:
        tab_id = self._next_tab_id
        self._next_tab_id += 1
        return tab_id

    # === 3.5.4 跨分屏标签迁移（拖拽） ===

    def dragEnterEvent(self, event):
        """接受标签迁移拖拽（MIME_TAB_FILEPATH / MIME_TAB_ID）；其余放行给窗口级拖放。"""
        if (event.mimeData().hasFormat(MIME_TAB_FILEPATH)
                or event.mimeData().hasFormat(MIME_TAB_ID)):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """跨分屏标签迁移：源标签栏位于另一个 EditorTabWidget 时执行迁移。"""
        source = event.source()
        if not (event.mimeData().hasFormat(MIME_TAB_FILEPATH)
                or event.mimeData().hasFormat(MIME_TAB_ID)):
            event.ignore()
            return
        if not isinstance(source, DraggableTabBar):
            event.ignore()
            return
        source_tabs = source.parent()
        if not isinstance(source_tabs, EditorTabWidget) or source_tabs is self:
            event.ignore()
            return
        index = source._drag_tab_index
        if index < 0 or index >= source_tabs.count():
            event.ignore()
            return
        if self._migrate_tab_from(source_tabs, index):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _migrate_tab_from(self, source_tabs: "EditorTabWidget", index: int) -> bool:
        """把源面板 index 位置的标签迁移到本面板（脏标记不丢）。

        顺序关键：取信息 → 源移除/注销 → 目标添加/注册 → 提升 _next_tab_id。
        源移除后 emit tab_count_changed（空分屏自动关闭 / 主面板空会话兜底联动）。
        """
        if source_tabs is self:
            return False
        widget = source_tabs.widget(index)
        if widget is None:
            return False
        tab_id = getattr(widget, 'tab_id', None)
        if tab_id is None:
            return False
        state = source_tabs._registry.get(tab_id)
        if state is None:
            return False
        if source_tabs._save_manager.is_saving(tab_id):
            return False  # 保存中拒绝迁移，避免跨面板保存状态机竞态
        title = source_tabs.tabText(index)

        # 源：移除标签 + 注销状态（removeTab 为原生方法，不触发关闭确认）
        source_tabs.removeTab(index)
        source_tabs._registry.unregister(tab_id)
        source_tabs._save_manager.unregister_tab(tab_id)
        source_tabs.tab_count_changed.emit(source_tabs.count())

        # 目标：添加标签 + 注册状态（tabInserted 自动重建关闭按钮）
        self.addTab(widget, title)
        self._registry.register(tab_id, state)
        self._save_manager.register_tab(tab_id)
        # 3.5.11：未命名标签迁移，编号随标签转移（源释放、目标占用）
        if state.is_new and state.untitled_number is not None:
            source_tabs._used_untitled_numbers.discard(state.untitled_number)
            self._used_untitled_numbers.add(state.untitled_number)
        # 关键：每个面板 _next_tab_id 独立计数，提升避免未来生成重复 tab_id
        self._next_tab_id = max(self._next_tab_id, tab_id + 1)
        self._update_tab_tooltip(self.indexOf(widget))
        self.tab_count_changed.emit(self.count())
        return True

    def new_file(self) -> int:
        """新建文件"""
        num = self._get_next_untitled_number()
        return self._create_untitled_tab(num, f"未命名{num}.txt")

    def restore_untitled_file(
        self,
        untitled_number: int,
        display_name: str,
        content: Optional[str] = None,
    ) -> int:
        """3.5.10：按持久化配置恢复未命名标签（沿用原编号并标记已用）。

        content 非 None 时写入内容并标记 dirty（编辑过的未命名现场还原）。
        """
        index = self._create_untitled_tab(untitled_number, display_name or f"未命名{untitled_number}.txt")
        if content is not None:
            tab_id = getattr(self.widget(index), 'tab_id', None)
            if tab_id is not None:
                self.set_tab_content(tab_id, content)
                self.mark_tab_dirty(tab_id)
        return int(index)

    def _create_untitled_tab(self, num: int, title: str) -> int:
        """创建未命名标签页（new_file / restore_untitled_file 共用）"""
        self._used_untitled_numbers.add(num)

        editor = Editor(self.config, theme_engine=self._theme_engine)
        self._connect_editor_signals(editor)
        editor.set_file_type(".txt")

        index = self.addTab(editor, title)

        tab_id = self._generate_tab_id()
        editor.tab_id = tab_id
        self._registry.register(tab_id, TabState(
            tab_id=tab_id,
            filepath=None,
            display_name=title,
            is_new=True,
            untitled_number=num,
            encoding="UTF-8",
            eol=self.config.get_editor_setting("line_ending", "LF"),
            is_markdown=False,
        ))
        self._save_manager.register_tab(tab_id)

        self.setCurrentIndex(index)
        self.tab_count_changed.emit(self.count())
        self._update_tab_tooltip(index)
        return int(index)

    def _is_markdown_file(self, filepath: str) -> bool:
        """判断是否为Markdown文件"""
        ext = os.path.splitext(filepath)[1].lower()
        return ext in ('.md', '.markdown')

    def open_file(
        self,
        filepath: str,
        *,
        activate: bool = True,
        insert_index: int | None = None,
        render_preview: bool = True,
    ) -> int:
        """打开文件"""
        # 检查文件是否已经打开
        for i in range(self.count()):
            widget = self.widget(i)
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is not None:
                state = self._registry.get(tab_id)
                if state and state.filepath == filepath:
                    if activate:
                        self.setCurrentIndex(i)
                    return i

        # 读取文件内容，检测编码
        file_guard = self.config.get_file_guard()

        # 先用原始字节探测行尾（safe_read 使用 universal newline 会丢失行尾信息）
        eol_label = "LF"
        eol_char = "\n"
        try:
            raw_sample = file_guard.safe_read_bytes(
                filepath, context=FileAccessContext.USER_DOCUMENT_READ
            )
            eol_label, eol_char = detect_eol_from_bytes(raw_sample)
        except Exception:
            pass  # 探测失败使用默认 LF

        detected_encoding = "UTF-8"
        content = ""

        try:
            content = file_guard.safe_read(filepath, encoding='utf-8',
                                           context=FileAccessContext.USER_DOCUMENT_READ)
            detected_encoding = "UTF-8"
        except UnicodeDecodeError:
            try:
                content = file_guard.safe_read(filepath, encoding='gbk',
                                               context=FileAccessContext.USER_DOCUMENT_READ)
                detected_encoding = "GBK"
            except UnicodeDecodeError:
                try:
                    content = file_guard.safe_read(filepath, encoding='utf-16',
                                                   context=FileAccessContext.USER_DOCUMENT_READ)
                    detected_encoding = "UTF-16"
                except (UnicodeDecodeError, OSError):
                    try:
                        raw = file_guard.safe_read_bytes(filepath,
                                                         context=FileAccessContext.USER_DOCUMENT_READ)
                        content = raw.decode('utf-8', errors='ignore')
                        detected_encoding = "UTF-8"
                    except Exception as e:
                        get_logger(__name__).error("无法读取文件: %s, %s", filepath, e)
                        ErrorHandler.show_from_exception(e, ErrorCategory.FILE, f"无法读取文件：{filepath}")
                        return -1
        except (FileSizeExceededError, FileOperationTimeoutError) as e:
            get_logger(__name__).error("文件安全检查失败: %s, %s", filepath, e)
            ErrorHandler.show_from_exception(e, ErrorCategory.FILE, f"无法读取文件：{filepath}")
            return -1
        except Exception as e:
            get_logger(__name__).error("打开文件失败: %s", e)
            ErrorHandler.show_from_exception(e, ErrorCategory.FILE, "打开文件失败")
            return -1

        is_md = self._is_markdown_file(filepath)

        if is_md:
            widget = MarkdownPreviewWidget(
                self.config,
                theme_engine=self._theme_engine,
                webengine_runtime=self._webengine_runtime,
            )
            widget.editor.load_content(content)
            self._connect_editor_signals(widget.editor)
            widget.editor.set_file_type(filepath)
            widget.set_base_path(os.path.dirname(os.path.abspath(filepath)))
            if render_preview:
                widget.refresh_preview_now()
        else:
            widget = Editor(self.config, theme_engine=self._theme_engine)
            widget.load_content(content)
            self._connect_editor_signals(widget)
            widget.set_file_type(filepath)

        filename = os.path.basename(filepath)
        if insert_index is not None:
            index = self.insertTab(insert_index, widget, filename)
        else:
            index = self.addTab(widget, filename)

        tab_id = self._generate_tab_id()
        widget.tab_id = tab_id

        # 如果是MarkdownPreviewWidget，也设置editor的tab_id
        if is_md and isinstance(widget, MarkdownPreviewWidget):
            widget.editor.tab_id = tab_id

        self._registry.register(tab_id, TabState(
            tab_id=tab_id,
            filepath=filepath,
            is_new=False,
            encoding=detected_encoding,
            eol=eol_label,
            last_saved_content=content,
            last_saved_chars=len(content),
            last_text_length=len(content),
            is_markdown=is_md,
        ))
        self._save_manager.register_tab(tab_id)

        if activate:
            self.setCurrentIndex(index)
        self.tab_count_changed.emit(self.count())
        self._update_tab_tooltip(index)

        # 恢复书签
        saved_bookmarks = self.config.get_bookmarks(filepath)
        if saved_bookmarks:
            self._restore_bookmarks(widget, filepath, saved_bookmarks)

        # 恢复折叠状态
        saved_folds = self.config.get_folds(filepath)
        if saved_folds:
            self._restore_folds(widget, filepath, saved_folds)

        # 恢复关闭标签页时的位置记忆（重新打开该文件）
        memory = self.config.get_closed_tab_memory(filepath)
        if memory:
            editor = self._get_editor_from_widget(widget)
            if editor is not None:
                cursor_pos = memory.get("cursor_position")
                if cursor_pos is not None:
                    cursor = editor.textCursor()
                    cursor.setPosition(min(cursor_pos, len(editor.toPlainText())))
                    editor.setTextCursor(cursor)
                scroll_pos = memory.get("scroll_position")
                if scroll_pos:
                    vbar = editor.verticalScrollBar()
                    if vbar is not None:
                        vbar.setValue(scroll_pos)
                        if vbar.value() != scroll_pos:
                            # 首帧布局未完成时 setValue 会被 clamp：
                            # 等待滚动范围就绪后重试一次
                            def _apply_scroll(vmin, vmax):
                                if vmax >= scroll_pos:
                                    vbar.setValue(scroll_pos)
                                    try:
                                        vbar.rangeChanged.disconnect(_apply_scroll)
                                    except TypeError:
                                        pass

                            vbar.rangeChanged.connect(_apply_scroll)
            self.config.clear_closed_tab_memory(filepath)

        return int(index)

    def save_current(self) -> Tuple[bool, int]:
        """保存当前文件"""
        widget = self.currentWidget()
        if not widget or not hasattr(widget, 'tab_id'):
            return False, 0

        state = self._registry.get(widget.tab_id)
        if state is None:
            return False, 0

        if not state.filepath or state.is_new:
            return self.save_current_as()

        return self._save_file(widget, state.filepath, state.encoding)

    def save_current_as(self) -> Tuple[bool, int]:
        """另存为"""
        widget = self.currentWidget()
        if not widget:
            return False, 0

        tid = getattr(widget, 'tab_id', None)
        if tid is None:
            return False, 0
        state = self._registry.get(tid)
        if state is None:
            return False, 0

        if state.filepath:
            suggested_name = state.filepath
        else:
            suggested_name = os.path.join(
                self.config.get_notebooks_path(),
                self._strip_tab_suffix(self.tabText(self.currentIndex()))
            )

        current_encoding = state.encoding

        dialog = SaveAsDialog(suggested_name, current_encoding, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False, 0

        filepath = dialog.get_filepath()
        encoding = dialog.get_encoding()

        if not filepath:
            return False, 0

        # PDF 另存为：通过 ExportService 生成可打开的 PDF（当前标签保持原文件）
        if filepath.lower().endswith(".pdf"):
            return self._save_as_pdf(widget, filepath)
        # HTML 另存为：渲染为可打开的 HTML 网页（当前标签保持原文件）
        if filepath.lower().endswith((".html", ".htm")):
            return self._save_as_html(widget, filepath)

        success, chars = self._save_file(
            widget, filepath, encoding, is_copy=not state.is_new
        )

        if success:
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is not None:
                self._pending_save_as_info[tab_id] = {
                    "filepath": filepath,
                    "encoding": encoding,
                    "untitled_number": state.untitled_number if state.is_new else None,
                    # 已有文件另存为 = 副本保存：当前标签保持指向原文件
                    "is_copy": not state.is_new,
                }

        return success, chars

    def save_untitled_to_folder(self, tab_id: int, dest_folder: str) -> Tuple[bool, int]:
        """3.5.11：把未命名标签直接落盘保存到目标文件夹（拖到文件树触发）。

        复用通用保存链路：_save_file + _pending_save_as_info → CLEAN 回调自动完成
        mark_new_saved / 编号释放 / 标题更新（与 save_current_as 一致）。
        同名冲突弹框确认（默认不覆盖）；空内容也直接落盘（行为统一）。
        """
        state = self._registry.get(tab_id)
        if state is None or not state.is_new or state.filepath:
            return False, 0
        widget = None
        for i in range(self.count()):
            w = self.widget(i)
            if getattr(w, 'tab_id', None) == tab_id:
                widget = w
                break
        if widget is None:
            return False, 0

        filename = state.display_name or f"未命名{state.untitled_number or 1}.txt"
        filepath = os.path.join(dest_folder, filename)

        if os.path.exists(filepath):
            reply = QMessageBox.question(
                self,
                "文件已存在",
                f"目标文件夹已存在同名文件：\n{filepath}\n\n是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False, 0

        success, chars = self._save_file(widget, filepath, state.encoding)
        if success:
            self._pending_save_as_info[tab_id] = {
                "filepath": filepath,
                "encoding": state.encoding,
                "untitled_number": state.untitled_number if state.is_new else None,
                "is_copy": False,
            }
        return success, chars

    def _save_as_pdf(self, widget, filepath: str) -> Tuple[bool, int]:
        """另存为 PDF：通过 ExportService 生成可打开的 PDF 文件。

        当前标签保持指向原文件（副本语义），PDF 生成完成后仅提示。
        二进制写入走 FileGuard.safe_write_bytes，遵守路径安全规范。
        """
        from .export_service import ExportService
        from ..security.file_access_context import FileAccessContext

        editor = self._get_editor_from_widget(widget)
        if editor is None:
            return False, 0
        content = editor.toPlainText()
        widget_type = type(widget).__name__ if widget else ""
        is_md = ExportService.is_markdown_content(content, widget_type)

        def _on_pdf_ready(pdf_data):
            if pdf_data:
                try:
                    self.config.get_file_guard().safe_write_bytes(
                        filepath,
                        pdf_data,
                        context=FileAccessContext.USER_DOCUMENT_SAVE,
                    )
                    QMessageBox.information(
                        self, "另存为",
                        f"已导出PDF: {os.path.basename(filepath)}",
                    )
                except Exception as e:
                    ErrorHandler.show_from_exception(
                        e, ErrorCategory.FILE,
                        f"写入PDF文件失败：{os.path.basename(filepath)}",
                    )
            else:
                QMessageBox.warning(self, "另存为", "PDF生成失败")

        try:
            ExportService.export_pdf(
                content,
                is_md,
                self,
                _on_pdf_ready,
                self._theme_engine.get_active_theme().colors,
            )
            return True, 0
        except RuntimeError as e:
            QMessageBox.warning(self, "另存为", str(e))
            return False, 0

    def _save_as_html(self, widget, filepath: str) -> Tuple[bool, int]:
        """另存为 HTML：通过 ExportService 渲染为可打开的 HTML 网页。

        当前标签保持指向原文件（副本语义）。
        渲染内容经 FileGuard.safe_write_bytes 安全写入（UTF-8），
        不直接复用 ExportService.export_html（其内部直接 open 写入）。
        """
        from .export_service import ExportService
        from .secure_markdown_renderer import build_export_html_document
        from ..security.file_access_context import FileAccessContext

        editor = self._get_editor_from_widget(widget)
        if editor is None:
            return False, 0
        content = editor.toPlainText()
        widget_type = type(widget).__name__ if widget else ""
        is_md = ExportService.is_markdown_content(content, widget_type)

        try:
            body_html = ExportService.render_content(content, is_md)
            full_html = build_export_html_document(
                body_html,
                self._theme_engine.get_active_theme().colors,
            )
            self.config.get_file_guard().safe_write_bytes(
                filepath,
                full_html.encode("utf-8"),
                context=FileAccessContext.USER_DOCUMENT_SAVE,
            )
            QMessageBox.information(
                self, "另存为",
                f"已导出HTML: {os.path.basename(filepath)}",
            )
            return True, 0
        except Exception as e:
            ErrorHandler.show_from_exception(
                e, ErrorCategory.FILE,
                f"写入HTML文件失败：{os.path.basename(filepath)}",
            )
            return False, 0

    def _save_file(self, widget, filepath: str, encoding: str = "UTF-8",
                   *, is_copy: bool = False) -> Tuple[bool, int]:
        """保存文件（异步写入磁盘，UI 不冻结）

        通过 SaveTaskManager 管理保存状态：
        - 提交任务后标记 SAVING，不提前标记 CLEAN
        - 保存成功后由 Manager 回调标记 CLEAN，此时才更新副作用
        - 保存失败后由 Manager 回调标记 SAVE_FAILED

        副作用（last_saved_content、last_saved_chars、last_text_length、
        字符收益结算）仅在保存成功回调中执行。

        is_copy：已有文件"另存为副本"时为 True，不改变当前标签的
        encoding（当前标签仍指向原文件）。
        """
        if isinstance(widget, MarkdownPreviewWidget):
            content = widget.editor.toPlainText()
        elif isinstance(widget, Editor):
            content = widget.toPlainText()
        else:
            return False, 0

        tab_id = getattr(widget, 'tab_id', None)
        if tab_id is None:
            return False, 0

        if self._save_manager.is_saving(tab_id):
            return False, 0

        state = self._registry.get(tab_id)
        if state is None:
            return False, 0
        last_chars = state.last_saved_chars

        # EOL 规范化：将编辑器内部的 \n 替换为文档目标行尾
        current_eol_label = state.eol
        target_eol = {"LF": "\n", "CRLF": "\r\n", "CR": "\r"}.get(current_eol_label, "\n")
        from .eol_utils import normalize_eol
        content = normalize_eol(content, target_eol)

        new_chars = max(0, len(content) - last_chars)

        if not is_copy:
            state.encoding = encoding

        self._pending_save_info[tab_id] = {
            "content": content,
            "new_chars": new_chars,
        }

        from PyQt6.QtCore import QThreadPool
        from .save_task import SaveTask
        from .eol_utils import normalize_eol

        task = SaveTask(self.config.get_file_guard(), filepath, content, encoding.lower())
        self._save_manager.submit_task(tab_id, task)
        pool = QThreadPool.globalInstance()
        if pool is not None:
            pool.start(task)

        return True, 0

    def save_all(self) -> int:
        total_chars = 0
        unnamed_indices = []

        for i in range(self.count()):
            widget = self.widget(i)
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is not None:
                state = self._registry.get(tab_id)
                if state and state.is_modified:
                    if state.filepath and not state.is_new:
                        success, chars = self._save_file(widget, state.filepath, state.encoding)
                        if success:
                            total_chars += chars
                    else:
                        unnamed_indices.append(i)

        for i in unnamed_indices:
            self.setCurrentIndex(i)
            success, chars = self.save_current_as()
            if success:
                total_chars += chars

        return total_chars

    def save_all_to_temp(self):
        """保存所有 dirty 文件到暂存目录（通过 TempSessionManager 管理）

        创建者：MainWindow（最小化/自动保存/关闭时调用）
        持有者：TempSessionManager
        完成通知：同步完成，无异步回调
        失败通知：日志记录，不中断流程
        关闭时行为：由 mark_cleanly_closed / cleanup_session 管理
        """
        tab_infos = []
        for i in range(self.count()):
            widget = self.widget(i)
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is None:
                continue

            state = self._registry.get(tab_id)
            if state is None or not state.is_modified:
                continue

            if isinstance(widget, MarkdownPreviewWidget):
                content = widget.editor.toPlainText()
            elif isinstance(widget, Editor):
                content = widget.toPlainText()
            else:
                continue

            tab_infos.append({
                "tab_id": tab_id,
                "filepath": state.filepath,
                "content": content,
                "encoding": state.encoding,
                "is_new": state.is_new,
                "is_modified": True
            })

        if tab_infos:
            self._session_manager.save_dirty_files(tab_infos)

    def clear_temp_files(self):
        """标记正常关闭并清理暂存文件"""
        self._session_manager.mark_cleanly_closed()
        self._session_manager.cleanup_session()
        self._session_manager.cleanup_all_clean_sessions()

    def release_memory(self):
        """释放内存"""
        current = self.currentWidget()

        for i in range(self.count()):
            widget = self.widget(i)
            if widget != current:
                tab_id = getattr(widget, 'tab_id', None)
                if tab_id:
                    state = self._registry.get(tab_id)
                    if state:
                        state.history.clear()
                    editor = self._get_editor_from_widget(widget)
                    if editor:
                        doc = editor.document()
                        if doc is not None:
                            doc.clearUndoRedoStacks()

    def close_current_tab(self):
        if self.count() > 0:
            self._on_tab_close_requested(self.currentIndex())

    def close_all_tabs(self):
        while self.count() > 0:
            if not self._close_tab(0):
                break

    def reopen_closed_tab(self) -> bool:
        if not self._closed_tabs_stack:
            return False
        entry = self._closed_tabs_stack.pop()
        filepath = entry["filepath"]
        cursor_pos = entry.get("cursor_position")
        for i in range(self.count()):
            w = self.widget(i)
            tid = getattr(w, 'tab_id', None) if w is not None else None
            state = self._registry.get(tid) if tid else None
            if state and state.filepath == filepath:
                self.setCurrentIndex(i)
                return True
        index = self.open_file(filepath)
        if index is not None and cursor_pos is not None:
            widget = self.widget(index)
            if isinstance(widget, Editor):
                cursor = widget.textCursor()
                cursor.setPosition(min(cursor_pos, len(widget.toPlainText())))
                widget.setTextCursor(cursor)
            elif isinstance(widget, MarkdownPreviewWidget):
                cursor = widget.editor.textCursor()
                cursor.setPosition(min(cursor_pos, len(widget.editor.toPlainText())))
                widget.editor.setTextCursor(cursor)
        return True

    def close_other_tabs(self, keep_index: int):
        while self.count() > keep_index + 1:
            if not self._close_tab(keep_index + 1):
                break
        while self.count() > 1 and keep_index > 0:
            if not self._close_tab(0):
                break
            keep_index -= 1

    def _apply_theme_colors(self, colors):
        self.setStyleSheet(f"""
    QTabWidget {{
        background-color: {colors.surface};
        border: none;
    }}

    QTabWidget::pane {{
        background-color: {colors.editor_bg};
        border: none;
        top: -1px;
    }}

    QTabBar {{
        background-color: {colors.surface};
        border: none;
    }}

    QTabBar::tab {{
        padding: 8px 15px;
        margin-right: 2px;
        background-color: {colors.surface};
        border: 1px solid {colors.border};
        border-bottom: none;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        color: {colors.text_secondary};
    }}

    QTabBar::tab:selected {{
        background-color: {colors.card};
        border-color: {colors.border};
        border-bottom: 1px solid {colors.card};
        color: {colors.text_primary};
    }}

    QTabBar::tab:hover:!selected {{
        background-color: {colors.primary_light};
        color: {colors.text_primary};
    }}

    QTabBar QToolButton {{
        background-color: {colors.surface};
        color: {colors.text_primary};
        border: 1px solid {colors.border};
        border-radius: 3px;
        margin: 1px;
    }}

    QTabBar QToolButton:hover {{
        background-color: {colors.primary_light};
    }}
    """)
        tab_bar = self.tabBar()
        if tab_bar is not None:
            for i in range(tab_bar.count()):
                btn = tab_bar.tabButton(i, QTabBar.ButtonPosition.RightSide)
                if isinstance(btn, _TabCloseButton):
                    btn._apply_btn_style(colors)

    def _on_tab_close_requested(self, index: int):
        self._close_tab(index)

    def _record_closed_tab(self, filepath: str, widget) -> None:
        """记录关闭标签页的位置：内存栈（Ctrl+Shift+T）+ 持久化记忆（重开恢复）。

        仅记录已保存文件（调用方已确认 filepath 存在）。
        """
        cursor = None
        scroll = 0
        if isinstance(widget, Editor):
            cursor = widget.textCursor().position()
            vbar = widget.verticalScrollBar()
            scroll = vbar.value() if vbar is not None else 0
        elif isinstance(widget, MarkdownPreviewWidget):
            cursor = widget.editor.textCursor().position()
            vbar = widget.editor.verticalScrollBar()
            scroll = vbar.value() if vbar is not None else 0
        self._closed_tabs_stack.append({
            "filepath": filepath,
            "cursor_position": cursor
        })
        if len(self._closed_tabs_stack) > 50:
            self._closed_tabs_stack.pop(0)
        if cursor is not None:
            self.config.set_closed_tab_memory(filepath, cursor, scroll)

    def _close_tab(self, index: int) -> bool:
        widget = self.widget(index)
        if not widget or not hasattr(widget, 'tab_id'):
            self.removeTab(index)
            self.tab_count_changed.emit(self.count())
            return True

        tab_id = widget.tab_id
        state = self._registry.get(tab_id)
        if state is None:
            self.removeTab(index)
            self.tab_count_changed.emit(self.count())
            return True

        if self._save_manager.is_saving(tab_id):
            return False

        if isinstance(widget, MarkdownPreviewWidget):
            content = widget.editor.toPlainText()
        elif isinstance(widget, Editor):
            content = widget.toPlainText()
        else:
            content = ""

        title = self._strip_tab_suffix(self.tabText(index))
        is_new = state.is_new
        is_empty = len(content.strip()) == 0

        if is_new and is_empty:
            self._release_untitled_number(title)
            self._save_manager.unregister_tab(tab_id)
            self._registry.unregister(tab_id)
            self.removeTab(index)
            self.tab_count_changed.emit(self.count())
            return True

        if state.is_modified:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("保存文件")
            if is_new:
                msg_box.setText(f"文件 '{title}' 尚未保存。\n\n是否保存？")
            else:
                msg_box.setText(f"文件 '{title}' 已修改。\n\n是否保存？")
            msg_box.setIcon(QMessageBox.Icon.Question)

            save_btn = msg_box.addButton("保存", QMessageBox.ButtonRole.AcceptRole)
            discard_btn = msg_box.addButton("不保存", QMessageBox.ButtonRole.DestructiveRole)
            cancel_btn = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)

            msg_box.exec()
            clicked = msg_box.clickedButton()

            if clicked == save_btn:
                if is_new:
                    old_index = self.currentIndex()
                    self.setCurrentIndex(index)
                    success, _ = self.save_current_as()
                    if not success:
                        self.setCurrentIndex(old_index)
                        return False
                else:
                    filepath = state.filepath
                    if not filepath:
                        return False
                    success, _ = self._save_file(widget, filepath, state.encoding)
                    if not success:
                        return False
                if self._save_manager.is_saving(tab_id):
                    self._pending_close_tab_ids.add(tab_id)
                    return False
            elif clicked == cancel_btn:
                return False

        if state.is_new:
            self._release_untitled_number(title)
        else:
            filepath = state.filepath
            if filepath and os.path.isfile(filepath):
                self._record_closed_tab(filepath, widget)

        self._save_manager.unregister_tab(tab_id)
        self._registry.unregister(tab_id)
        self.removeTab(index)
        self.tab_count_changed.emit(self.count())
        return True

    def _show_tab_context_menu(self, position):
        tb = self.tabBar()
        if tb is None:
            return
        index = tb.tabAt(position)
        if index < 0:
            return

        menu = QMenu(self)

        save_action = QAction("保存", self)
        save_action.triggered.connect(lambda: self._context_save(index))
        menu.addAction(save_action)

        save_as_action = QAction("另存为", self)
        save_as_action.triggered.connect(lambda: self._context_save_as(index))
        menu.addAction(save_as_action)

        menu.addSeparator()

        rename_action = QAction("重命名", self)
        rename_action.triggered.connect(lambda: self._context_rename(index))
        menu.addAction(rename_action)

        menu.addSeparator()

        close_action = QAction("关闭", self)
        close_action.triggered.connect(lambda: self._close_tab(index))
        menu.addAction(close_action)

        if self.count() > 1:
            close_others = QAction("关闭其他标签", self)
            close_others.triggered.connect(lambda: self.close_other_tabs(index))
            menu.addAction(close_others)

        close_all = QAction("关闭所有标签", self)
        close_all.triggered.connect(self.close_all_tabs)
        menu.addAction(close_all)

        menu.exec(tb.mapToGlobal(position))

    def _context_save(self, index: int):
        old = self.currentIndex()
        self.setCurrentIndex(index)
        self.save_current()
        self.setCurrentIndex(old)

    def _context_save_as(self, index: int):
        old = self.currentIndex()
        self.setCurrentIndex(index)
        self.save_current_as()
        self.setCurrentIndex(old)

    def _context_rename(self, index: int):
        widget = self.widget(index)
        if not widget or not hasattr(widget, 'tab_id'):
            return

        state = self._registry.get(widget.tab_id)
        if state is None:
            return
        filepath = state.filepath

        if not filepath or state.is_new:
            self._context_save_as(index)
            return

        old_name = os.path.basename(filepath)
        new_name, ok = QInputDialog.getText(self, "重命名", "新文件名:", text=old_name)

        if ok and new_name and new_name != old_name:
            new_path = os.path.join(os.path.dirname(filepath), new_name)
            try:
                os.rename(filepath, new_path)
                state.filepath = new_path
                self.setTabText(index, new_name)
                editor = self._get_editor_from_widget(widget)
                if editor:
                    editor.set_file_type(new_path)
            except Exception as e:
                get_logger(__name__).error("重命名失败: %s", e)
                ErrorHandler.show_from_exception(e, ErrorCategory.FILE, "重命名失败")

    def _on_current_changed(self, index: int):
        widget = self.widget(index)

        if isinstance(widget, MarkdownPreviewWidget):
            widget.ensure_preview_rendered()

        if self._find_bar:
            editor = self.current_editor()
            self._find_bar.set_editor(editor)

        self.current_changed.emit(index)

    def _connect_editor_signals(self, editor):
        editor.textChanged.connect(self._on_text_changed)
        editor.cursorPositionChanged.connect(self._on_cursor_position_changed)
        if is_enabled("signal_driven_stats"):
            editor.word_count_recomputed.connect(self._on_word_count_recomputed)

    def _on_cursor_position_changed(self):
        self.cursor_position_changed.emit()

    def _on_word_count_recomputed(self):
        self.word_count_updated.emit()

    _PASTE_THRESHOLD = 50

    def _on_text_changed(self):
        editor_obj = self.sender()
        if editor_obj is None or not hasattr(editor_obj, 'tab_id'):
            return

        editor: Editor = cast(Editor, editor_obj)
        tab_id = editor.tab_id
        if tab_id is None:
            return

        state = self._registry.get(tab_id)
        if state is None:
            return

        doc = editor.document()
        if doc is None:
            return
        current_len = doc.characterCount() - 1
        last_len = state.last_text_length or current_len
        delta = current_len - last_len
        state.last_text_length = current_len

        is_pasting = getattr(editor, '_is_pasting', False)
        is_programmatic = getattr(editor, 'is_programmatic_modify', False)

        if delta > 0 and not is_pasting and not is_programmatic:
            if delta <= self._PASTE_THRESHOLD:
                self.chars_typed.emit(delta)

        last_saved_chars = state.last_saved_chars
        is_modified = doc.isModified()

        if is_modified != state.is_modified:
            state.is_modified = is_modified
            if is_modified:
                self._save_manager.mark_dirty(tab_id)
                for i in range(self.count()):
                    widget = self.widget(i)
                    if getattr(widget, 'tab_id', None) == tab_id:
                        title = self.tabText(i)
                        if not title.endswith(" *") and not title.endswith(" ⏳") and not title.endswith(" !"):
                            self.setTabText(i, title + " *")
                        break
            else:
                for i in range(self.count()):
                    widget = self.widget(i)
                    if getattr(widget, 'tab_id', None) == editor.tab_id:
                        title = self.tabText(i)
                        stripped = self._strip_tab_suffix(title)
                        if stripped != title:
                            self.setTabText(i, stripped)
                        break

        if is_enabled("signal_driven_stats"):
            editor.invalidate_word_count()

        self.content_modified.emit()

    def _on_save_state_changed(self, tab_id: int, state_name: str) -> None:
        save_state = SaveState(state_name)
        state = self._registry.get(tab_id)
        widget = None
        widget_index = -1
        for i in range(self.count()):
            w = self.widget(i)
            if getattr(w, 'tab_id', None) == tab_id:
                widget = w
                widget_index = i
                break
        if widget is None:
            return

        index = self.indexOf(widget)
        base_title = self._strip_tab_suffix(self.tabText(index))

        if save_state == SaveState.CLEAN:
            if state is None:
                return
            save_as_info = self._pending_save_as_info.pop(tab_id, None)
            if save_as_info and save_as_info.get("is_copy"):
                # 已有文件另存为副本：保存成功，但当前标签仍指向原文件。
                # 跳过全部保存副作用（不清 dirty、不改标题、不结算收益），
                # 避免原文件未保存的修改被误标记为已保存（数据安全）。
                self._pending_save_info.pop(tab_id, None)
                # 恢复标题（去除 SAVING 阶段追加的 ⏳ 后缀）
                self.setTabText(index, base_title)
                if tab_id in self._pending_close_tab_ids:
                    self._pending_close_tab_ids.discard(tab_id)
                    self._close_tab_after_save(widget_index)
                return
            state.is_modified = False
            editor = self._get_editor_from_widget(widget)
            if editor:
                doc = editor.document()
                if doc is not None:
                    doc.setModified(False)
            self.setTabText(index, base_title)

            pending = self._pending_save_info.pop(tab_id, None)
            if pending:
                content = pending["content"]
                new_chars = pending["new_chars"]
                state.mark_saved(content)
                if new_chars > 0:
                    self.chars_typed.emit(new_chars)

            if save_as_info:
                # 新建文件首次保存：正式化为该文件
                filepath_new = save_as_info["filepath"]
                encoding_new = save_as_info["encoding"]
                state.mark_new_saved(filepath_new, encoding_new)
                if save_as_info.get("untitled_number"):
                    self._used_untitled_numbers.discard(save_as_info["untitled_number"])
                if editor:
                    editor.set_file_type(filepath_new)
                self.setTabText(index, os.path.basename(filepath_new))

            if state.filepath:
                self._session_manager.remove_autosave_for_file(state.filepath)
            self._update_tab_tooltip(index)
            self.file_saved.emit()
            if tab_id in self._pending_close_tab_ids:
                self._pending_close_tab_ids.discard(tab_id)
                self._close_tab_after_save(widget_index)
        elif save_state == SaveState.SAVING:
            self.setTabText(index, base_title + " ⏳")
        elif save_state == SaveState.SAVE_FAILED:
            save_as_info = self._pending_save_as_info.pop(tab_id, None)
            if save_as_info and save_as_info.get("is_copy"):
                # 副本保存失败：当前标签状态不变（原文件未受影响），恢复标题
                self._pending_save_info.pop(tab_id, None)
                self.setTabText(index, base_title)
                return
            if state is not None:
                state.is_modified = True
            editor = self._get_editor_from_widget(widget)
            if editor:
                doc = editor.document()
                if doc is not None:
                    doc.setModified(True)
            self.setTabText(index, base_title + " !")
            self._pending_save_info.pop(tab_id, None)
            if tab_id in self._pending_close_tab_ids:
                self._pending_close_tab_ids.discard(tab_id)
        elif save_state == SaveState.DIRTY:
            if state is not None:
                state.is_modified = True

    def _on_save_failed(self, tab_id: int, filepath: str, exc: BaseException) -> None:
        basename = os.path.basename(filepath) if filepath else "未知文件"
        ErrorHandler.show_from_exception(exc, ErrorCategory.FILE, f"保存文件失败：{basename}")

    def _close_tab_after_save(self, index: int) -> None:
        widget = self.widget(index)
        if not widget or not hasattr(widget, 'tab_id'):
            return

        tab_id = widget.tab_id
        state = self._registry.get(tab_id)
        title = self._strip_tab_suffix(self.tabText(index))

        if state and state.is_new:
            self._release_untitled_number(title)
        else:
            filepath = state.filepath if state else None
            if filepath and os.path.isfile(filepath):
                self._record_closed_tab(filepath, widget)

        self._save_manager.unregister_tab(tab_id)
        self._registry.unregister(tab_id)
        self.removeTab(index)
        self.tab_count_changed.emit(self.count())

    def current_editor(self) -> Optional[Editor]:
        """获取当前编辑器"""
        widget = self.currentWidget()
        return self._get_editor_from_widget(widget)

    def get_open_filepaths(self) -> list:
        """返回所有已打开文件的路径列表（不含未保存的新文件）。"""
        paths = []
        for i in range(self.count()):
            widget = self.widget(i)
            if widget is None:
                continue
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is None:
                continue
            state = self._registry.get(tab_id)
            if state and state.filepath and not state.is_new:
                paths.append(state.filepath)
        return paths

    def get_current_encoding(self) -> str:
        """获取当前文件的编码"""
        widget = self.currentWidget()
        if widget and hasattr(widget, 'tab_id'):
            state = self._registry.get(widget.tab_id)
            if state:
                return str(state.encoding)
        return "UTF-8"

    def get_current_eol(self) -> str:
        """获取当前文档的行尾类型（LF / CRLF / CR / Mixed）"""
        widget = self.currentWidget()
        if widget and hasattr(widget, 'tab_id'):
            state = self._registry.get(widget.tab_id)
            if state:
                return str(state.eol)
        return "LF"

    def set_current_eol(self, eol: str) -> None:
        """切换当前文档的行尾类型，并标记为已修改"""
        widget = self.currentWidget()
        if widget and hasattr(widget, 'tab_id'):
            state = self._registry.get(widget.tab_id)
            if state is None:
                return
            state.eol = eol
            state.is_modified = True
            editor = self._get_editor_from_widget(widget)
            if editor:
                doc = editor.document()
                if doc is not None:
                    doc.setModified(True)
            # 更新标签页标题（加 * 标记）
            for i in range(self.count()):
                w = self.widget(i)
                if getattr(w, 'tab_id', None) == widget.tab_id:
                    base = self._strip_tab_suffix(self.tabText(i))
                    if not base.endswith(" *"):
                        self.setTabText(i, base + " *")
                    break

    def get_unsaved_files(self) -> List[str]:
        unsaved = []
        for i in range(self.count()):
            widget = self.widget(i)
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is not None:
                state = self._registry.get(tab_id)
                if state and state.is_modified:
                    editor = self._get_editor_from_widget(widget)
                    content = editor.toPlainText() if editor else ""
                    if state.is_new and len(content.strip()) == 0:
                        continue
                    if state.filepath:
                        unsaved.append(os.path.basename(state.filepath))
                    else:
                        unsaved.append(self._strip_tab_suffix(self.tabText(i)))
        return unsaved

    def has_modified_files(self) -> bool:
        for state in self._registry.all_states():
            if state.is_modified:
                return True
        return False

    def get_current_file_info(self) -> Optional[Dict]:
        widget = self.currentWidget()
        if not widget:
            return None
        tab_id = getattr(widget, 'tab_id', None)
        if tab_id is None:
            return None
        state = self._registry.get(tab_id)
        if state is None or not state.filepath:
            return None
        filepath = state.filepath
        editor = self._get_editor_from_widget(widget)
        result: Dict[str, object] = {"filepath": filepath}
        if editor:
            cursor = editor.textCursor()
            result["cursor_position"] = cursor.position()
            vbar = editor.verticalScrollBar()
            if vbar is not None:
                result["scroll_position"] = vbar.value()
        return result

    def get_open_files_info(self) -> List[Dict]:
        # 先把每个标签的实时光标/滚动位置同步到 TabState，再经 registry 导出
        for i in range(self.count()):
            widget = self.widget(i)
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is None:
                continue
            state = self._registry.get(tab_id)
            if state is None:
                continue
            if state.is_new or not state.filepath:
                # 3.5.10：未命名文件（dirty 时）同步内容，随条目恢复编辑现场
                if state.is_modified:
                    editor = self._get_editor_from_widget(widget)
                    if editor is not None:
                        state.export_content = editor.toPlainText()
                continue
            editor = self._get_editor_from_widget(widget)
            if editor is None:
                continue
            cursor = editor.textCursor()
            vbar2 = editor.verticalScrollBar()
            state.cursor_position = cursor.position()
            state.scroll_position = vbar2.value() if vbar2 is not None else 0
        return self._registry.to_open_files_list()

    # === 文档状态公开接口（替代 MainWindow 的私有穿透） ===

    def set_tab_content(self, tab_id: int, content: str) -> bool:
        """将内容恢复到指定标签的编辑器，并重置保存状态。

        供崩溃恢复使用（restore_after_crash）。
        """
        state = self._registry.get(tab_id)
        if state is None:
            return False
        editor = self._editor_for_tab_id(tab_id)
        if editor is None:
            return False
        editor.setPlainText(content)
        doc = editor.document()
        if doc is not None:
            doc.setModified(False)
            doc.clearUndoRedoStacks()
        state.mark_saved(content)
        return True

    def mark_tab_dirty(self, tab_id: int) -> None:
        """将指定标签标记为已修改（供崩溃恢复后的脏标记）。"""
        state = self._registry.get(tab_id)
        if state is None:
            return
        state.is_modified = True
        self._save_manager.mark_dirty(tab_id)

    def get_tab_state(self, tab_id: int) -> Optional[TabState]:
        """获取指定标签的文档状态（只读用途）。"""
        return self._registry.get(tab_id)

    def get_failed_filenames(self, failed_tab_ids: List[int]) -> List[str]:
        """根据失败的 tab_id 列表返回文件名（供关闭流程提示）。"""
        return self._registry.get_failed_filenames(failed_tab_ids)

    def _editor_for_tab_id(self, tab_id: int) -> Optional[Editor]:
        for i in range(self.count()):
            widget = self.widget(i)
            if getattr(widget, 'tab_id', None) == tab_id:
                return self._get_editor_from_widget(widget)
        return None

    def set_wrap_mode_all(self, mode: str):
        for editor in self._iter_editors():
            editor.set_wrap_mode(mode)

    def toggle_md_preview(self):
        """切换当前MD标签的预览"""
        widget = self.currentWidget()
        if isinstance(widget, MarkdownPreviewWidget):
            widget.toggle_preview()

    def toggle_minimap(self):
        """切换当前编辑器的缩略图显示"""
        widget = self.currentWidget()
        editor = self._get_editor_from_widget(widget)
        if editor:
            editor.toggle_minimap()

    def set_minimap_all(self, visible: bool):
        for editor in self._iter_editors():
            editor.set_minimap_visible(visible)

    def apply_auto_minimap_all(self):
        for editor in self._iter_editors():
            editor.apply_auto_minimap()

    def set_line_numbers_all(self, show: bool):
        for editor in self._iter_editors():
            editor.set_show_line_numbers(show)

    def set_highlight_current_line_all(self, enabled: bool):
        for editor in self._iter_editors():
            editor.set_highlight_current_line(enabled)

    def set_completion_enabled_all(self, enabled: bool) -> None:
        """对所有已打开编辑器应用补全开关。"""
        for editor in self._iter_editors():
            editor.set_completion_enabled(enabled)

    def set_font_all(self, family: str, size: int):
        for editor in self._iter_editors():
            editor.set_editor_font(family, size)

    def update_indent_settings_all(self):
        """缩进配置变更后，更新所有已打开编辑器的 Tab 显示宽度"""
        from .indentation import get_indent_width
        for editor in self._iter_editors():
            font_metrics = editor.fontMetrics()
            tab_width = font_metrics.horizontalAdvance(' ') * get_indent_width(editor.config)
            editor.setTabStopDistance(tab_width)

    # === 查找替换 ===

    def show_find_dialog(self):
        """显示查找栏"""
        if self._find_bar:
            editor = self.current_editor()
            self._find_bar.set_editor(editor)
            self._find_bar.show_find()

    def show_replace_dialog(self):
        """显示替换栏"""
        if self._find_bar:
            editor = self.current_editor()
            self._find_bar.set_editor(editor)
            self._find_bar.show_replace()

    # === 文件移动（供标签拖拽使用） ===

    def move_file_to_folder(self, filepath: str, dest_folder: str) -> bool:
        """将文件移动到目标文件夹，更新对应标签页"""
        if not os.path.isfile(filepath) or not os.path.isdir(dest_folder):
            return False

        filename = os.path.basename(filepath)
        new_path = os.path.join(dest_folder, filename)

        if os.path.exists(new_path):
            msg = QMessageBox.question(
                self, "文件已存在",
                f"目标文件夹中已存在 '{filename}'，是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
            )
            if msg != QMessageBox.StandardButton.Yes:
                return False

        try:
            # 先保存再移动
            for i in range(self.count()):
                widget = self.widget(i)
                tab_id = getattr(widget, 'tab_id', None)
                if tab_id is not None:
                    state = self._registry.get(tab_id)
                    if state and state.filepath == filepath:
                        # 保存最新内容
                        if state.is_modified:
                            self._save_file(widget, filepath, state.encoding)
                        break

            import shutil
            shutil.move(filepath, new_path)

            # 更新标签页信息
            for i in range(self.count()):
                widget = self.widget(i)
                tab_id = getattr(widget, 'tab_id', None)
                if tab_id is not None:
                    state = self._registry.get(tab_id)
                    if state and state.filepath == filepath:
                        state.filepath = new_path
                        state.display_name = filename
                        self.setTabText(i, filename)
                        break

            return True
        except Exception as e:
            get_logger(__name__).error("移动文件失败: %s", e)
            ErrorHandler.show_from_exception(e, ErrorCategory.FILE, "移动文件失败")
            return False

    def copy_file_to_folder(self, filepath: str, dest_folder: str) -> bool:
        """将文件复制到目标文件夹（标签已打开且已修改则先保存再复制，不改动原标签）"""
        if not os.path.isfile(filepath) or not os.path.isdir(dest_folder):
            return False

        filename = os.path.basename(filepath)
        new_path = os.path.join(dest_folder, filename)

        if os.path.exists(new_path):
            msg = QMessageBox.question(
                self, "文件已存在",
                f"目标文件夹中已存在 '{filename}'，是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
            )
            if msg != QMessageBox.StandardButton.Yes:
                return False

        try:
            # 若标签打开且已修改，先保存再复制，保证副本包含最新内容
            for i in range(self.count()):
                widget = self.widget(i)
                tab_id = getattr(widget, 'tab_id', None)
                if tab_id is not None:
                    state = self._registry.get(tab_id)
                    if state and state.filepath == filepath:
                        if state.is_modified:
                            self._save_file(widget, filepath, state.encoding)
                        break

            import shutil
            shutil.copy2(filepath, new_path)
            return True
        except Exception as e:
            get_logger(__name__).error("复制文件失败: %s", e)
            ErrorHandler.show_from_exception(e, ErrorCategory.FILE, "复制文件失败")
            return False

    def close_tabs_of_deleted_path(self, path: str, is_dir: bool) -> None:
        """文件树删除文件/文件夹后，同步关闭已打开的对应标签页。

        - 未修改的标签直接关闭；
        - 已修改的标签弹确认（关闭 = 放弃未保存的修改，不重新保存）。
        这是删除语义：此时"保存"只会把已删除的文件重新创建回来。
        """
        norm = os.path.normpath(path)
        indices = []
        for i in range(self.count()):
            widget = self.widget(i)
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is None:
                continue
            state = self._registry.get(tab_id)
            if not state or not state.filepath:
                continue
            fp = os.path.normpath(state.filepath)
            if is_dir:
                matched = fp.startswith(norm + os.sep)
            else:
                matched = fp == norm
            if matched:
                indices.append(i)

        # 从后往前关闭，避免索引随 removeTab 偏移
        for i in reversed(indices):
            self._close_deleted_tab(i)

    def _close_deleted_tab(self, index: int) -> None:
        """关闭单个标签（文件已被删除，不提供"保存"选项）。"""
        widget = self.widget(index)
        tab_id = getattr(widget, 'tab_id', None) if widget else None
        state = self._registry.get(tab_id) if tab_id is not None else None

        if tab_id is None or state is None:
            self.removeTab(index)
            self.tab_count_changed.emit(self.count())
            return

        if state.is_modified:
            name = self._strip_tab_suffix(self.tabText(index))
            msg = QMessageBox(self)
            msg.setWindowTitle("关闭标签")
            msg.setText(f"文件 '{name}' 已在文件树中删除。")
            msg.setInformativeText("标签页有未保存的修改，关闭将放弃这些修改。")
            msg.setIcon(QMessageBox.Icon.Warning)
            close_btn = msg.addButton("关闭标签", QMessageBox.ButtonRole.DestructiveRole)
            msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            msg.setDefaultButton(close_btn)
            msg.exec()
            if msg.clickedButton() is not close_btn:
                return

        if state.is_new:
            title = self._strip_tab_suffix(self.tabText(index))
            self._release_untitled_number(title)
        else:
            filepath = state.filepath
            if filepath and os.path.isfile(filepath):
                self._record_closed_tab(filepath, widget)

        if state.filepath:
            self._session_manager.remove_autosave_for_file(state.filepath)

        self._save_manager.unregister_tab(tab_id)
        self._registry.unregister(tab_id)
        self.removeTab(index)
        self.tab_count_changed.emit(self.count())

    # === 编辑操作代理 ===

    def undo(self) -> bool:
        editor = self.current_editor()
        if editor:
            doc = editor.document()
            if doc is not None and doc.isUndoAvailable():
                editor.undo()
                return True
        return False

    def redo(self):
        editor = self.current_editor()
        if editor:
            editor.redo()

    def cut(self):
        editor = self.current_editor()
        if editor:
            editor.cut()

    def copy(self):
        editor = self.current_editor()
        if editor:
            editor.copy()

    def paste(self):
        editor = self.current_editor()
        if editor:
            editor.paste()

    def select_all(self):
        editor = self.current_editor()
        if editor:
            editor.selectAll()

    def zoom_in(self):
        """放大：字号+1，同步到配置并应用到所有编辑器"""
        current_size = self.config.get_editor_setting("font_size", 12)
        new_size = min(current_size + 1, 48)
        if new_size != current_size:
            self.config.set_editor_setting("font_size", new_size)
            font_family = self.config.get_editor_setting("font_family", "Microsoft YaHei")
            self.set_font_all(font_family, new_size)

    def zoom_out(self):
        """缩小：字号-1，同步到配置并应用到所有编辑器"""
        current_size = self.config.get_editor_setting("font_size", 12)
        new_size = max(current_size - 1, 8)
        if new_size != current_size:
            self.config.set_editor_setting("font_size", new_size)
            font_family = self.config.get_editor_setting("font_family", "Microsoft YaHei")
            self.set_font_all(font_family, new_size)

    def zoom_reset(self):
        """重置缩放：恢复默认字号12"""
        self.config.set_editor_setting("font_size", 12)
        font_family = self.config.get_editor_setting("font_family", "Microsoft YaHei")
        self.set_font_all(font_family, 12)

    # === 行操作代理 ===

    def delete_current_line(self):
        """删除当前行"""
        editor = self.current_editor()
        if editor:
            editor.delete_current_line()

    def copy_line(self):
        """复制当前行到剪贴板"""
        editor = self.current_editor()
        if editor:
            editor.copy_line()

    def paste_line(self):
        """粘贴为新的行"""
        editor = self.current_editor()
        if editor:
            editor.paste_line()

    def move_line_up(self):
        """上移当前行"""
        editor = self.current_editor()
        if editor:
            editor.move_line_up()

    def move_line_down(self):
        """下移当前行"""
        editor = self.current_editor()
        if editor:
            editor.move_line_down()

    # === 大小写转换代理 ===

    def toggle_case(self):
        editor = self.current_editor()
        if editor:
            editor.toggle_case()

    def to_uppercase(self):
        editor = self.current_editor()
        if editor:
            editor.to_uppercase()

    def to_lowercase(self):
        editor = self.current_editor()
        if editor:
            editor.to_lowercase()

    def to_titlecase(self):
        editor = self.current_editor()
        if editor:
            editor.to_titlecase()

    # === 转到行 ===

    def goto_line(self, line_number: int):
        editor = self.current_editor()
        if editor:
            editor.goto_line(line_number)

    def show_goto_line_dialog(self):
        """显示转到行对话框"""
        editor = self.current_editor()
        if not editor:
            return

        doc = editor.document()
        if doc is None:
            return
        max_line = doc.blockCount()
        current_line = editor.textCursor().blockNumber() + 1

        line, ok = QInputDialog.getInt(
            self, "转到行",
            f"输入行号 (1 - {max_line}):",
            current_line, 1, max_line
        )
        if ok:
            editor.goto_line(line)

    # === 文档格式化 ===

    def format_document(self):
        """格式化当前文档"""
        editor = self.current_editor()
        if editor:
            editor.format_document()

    # === 书签持久化 ===

    def _restore_bookmarks(self, widget, filepath: str, lines: list) -> None:
        """恢复已保存的书签到编辑器。"""
        editor = self._get_editor_from_widget(widget)
        if editor is not None:
            editor.set_bookmarks(set(lines))

    def save_all_bookmarks(self) -> None:
        """保存所有已打开标签页的书签到 config。"""
        for i in range(self.count()):
            widget = self.widget(i)
            if widget is None:
                continue
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is None:
                continue
            state = self._registry.get(tab_id)
            if state is None or not state.filepath:
                continue
            editor = self._get_editor_from_widget(widget)
            if editor is not None:
                bookmarks = editor.get_bookmarks()
                self.config.set_bookmarks(state.filepath, list(bookmarks) if bookmarks else [])

    def _restore_folds(self, widget, filepath: str, lines: list) -> None:
        """恢复已保存的折叠状态。"""
        editor = self._get_editor_from_widget(widget)
        if editor is not None and hasattr(editor, '_folding'):
            # 确保折叠区间已计算（load_content 时 _file_type 可能还不是 Markdown）
            editor._refresh_folding()
            editor._folding.set_collapsed_lines(lines)

    def save_all_folds(self) -> None:
        """保存所有已打开标签页的折叠状态到 config。"""
        for i in range(self.count()):
            widget = self.widget(i)
            if widget is None:
                continue
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is None:
                continue
            state = self._registry.get(tab_id)
            if state is None or not state.filepath:
                continue
            editor = self._get_editor_from_widget(widget)
            if editor is not None and hasattr(editor, '_folding'):
                collapsed = editor._folding.get_collapsed_lines()
                self.config.set_folds(state.filepath, collapsed if collapsed else [])
