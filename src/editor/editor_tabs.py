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
            "文本文件 (*.txt);;Markdown (*.md);;Python (*.py);;所有文件 (*.*)"
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

        # 获取该标签对应的文件路径
        tab_widget = self.parent()  # QTabWidget
        if not tab_widget or not hasattr(tab_widget, '_get_filepath_for_index'):
            super().mouseMoveEvent(event)
            return

        filepath = tab_widget._get_filepath_for_index(self._drag_tab_index)
        if not filepath:
            super().mouseMoveEvent(event)
            return

        # 发起 QDrag
        drag = QDrag(self)
        mime = QMimeData()
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 22)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 10, 1)
        layout.setSpacing(0)

        self._btn = QToolButton()
        self._btn.setObjectName("tabCloseInnerBtn")
        self._btn.setFixedSize(15, 16)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setText("×")
        self._btn.setStyleSheet(
            "#tabCloseInnerBtn { border: none; background: transparent; border-radius: 2px; padding: 0; }"
            "#tabCloseInnerBtn:hover { background: rgba(128,128,128,90); }"
        )
        layout.addWidget(self._btn)
        layout.addStretch()

        self._btn.clicked.connect(self._on_clicked)

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
        theme_engine=None,
        webengine_runtime: WebEngineRuntime | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.config = config
        self._theme_engine = theme_engine
        self._webengine_runtime = webengine_runtime

        self._tab_info: Dict[int, Dict] = {}
        self._next_tab_id = 0
        self._used_untitled_numbers: Set[int] = set()
        self._closed_tabs_stack: List[Dict] = []

        self._save_manager = SaveTaskManager(self)
        self._save_manager.save_state_changed.connect(self._on_save_state_changed)
        self._save_manager.save_failed.connect(self._on_save_failed)

        self._pending_close_tab_ids: Set[int] = set()
        self._pending_save_info: Dict[int, Dict] = {}
        self._pending_save_as_info: Dict[int, Dict] = {}

        self._session_manager = TempSessionManager(config.get_temp_path())

        self._tab_bar = DraggableTabBar(self)
        self.setTabBar(self._tab_bar)

        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)

        self.tabCloseRequested.connect(self._on_tab_close_requested)
        self.currentChanged.connect(self._on_current_changed)

        tb = self.tabBar()
        if tb is not None:
            tb.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            tb.customContextMenuRequested.connect(self._show_tab_context_menu)

        if theme_engine:
            self._init_theme(theme_engine)

        # ── 查找替换栏（嵌入在标签内容上方） ──
        # 不在这里创建，而是由 main_window 在 editor_container 中创建
        self._find_bar: Optional[FindReplaceBar] = None

    def tabInserted(self, index):
        super().tabInserted(index)
        btn = _TabCloseButton(self)
        self.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, btn)  # type: ignore[union-attr]

    def set_find_bar(self, find_bar: FindReplaceBar):
        """设置外部传入的查找替换栏"""
        self._find_bar = find_bar

    @property
    def save_manager(self) -> SaveTaskManager:
        return self._save_manager

    @property
    def session_manager(self) -> TempSessionManager:
        return self._session_manager

    def _get_filepath_for_index(self, index: int) -> Optional[str]:
        """获取指定标签页的文件路径（供 DraggableTabBar 使用）"""
        widget = self.widget(index)
        if widget and hasattr(widget, 'tab_id'):
            info = self._tab_info.get(widget.tab_id, {})
            filepath = info.get("filepath")
            if filepath and not info.get("is_new"):
                return str(filepath)
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

    def new_file(self) -> int:
        """新建文件"""
        num = self._get_next_untitled_number()
        self._used_untitled_numbers.add(num)
        title = f"未命名{num}.txt"

        editor = Editor(self.config, theme_engine=self._theme_engine)
        self._connect_editor_signals(editor)
        editor.set_file_type(".txt")

        index = self.addTab(editor, title)

        tab_id = self._generate_tab_id()
        editor.tab_id = tab_id
        self._tab_info[tab_id] = {
            "filepath": None,
            "is_modified": False,
            "is_new": True,
            "untitled_number": num,
            "encoding": "UTF-8",
            "eol": self.config.get_editor_setting("line_ending", "LF"),
            "last_saved_content": "",
            "last_saved_chars": 0,
            "last_text_length": 0,
            "is_markdown": False,
            "history": []
        }
        self._save_manager.register_tab(tab_id)

        self.setCurrentIndex(index)
        self.tab_count_changed.emit(self.count())
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
                info = self._tab_info.get(tab_id, {})
                if info.get("filepath") == filepath:
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

        self._tab_info[tab_id] = {
            "filepath": filepath,
            "is_modified": False,
            "is_new": False,
            "encoding": detected_encoding,
            "eol": eol_label,
            "last_saved_content": content,
            "last_saved_chars": len(content),
            "last_text_length": len(content),
            "is_markdown": is_md,
            "history": []
        }
        self._save_manager.register_tab(tab_id)

        if activate:
            self.setCurrentIndex(index)
        self.tab_count_changed.emit(self.count())

        # 恢复书签
        saved_bookmarks = self.config.get_bookmarks(filepath)
        if saved_bookmarks:
            self._restore_bookmarks(widget, filepath, saved_bookmarks)

        # 恢复折叠状态
        saved_folds = self.config.get_folds(filepath)
        if saved_folds:
            self._restore_folds(widget, filepath, saved_folds)

        return int(index)

    def save_current(self) -> Tuple[bool, int]:
        """保存当前文件"""
        widget = self.currentWidget()
        if not widget or not hasattr(widget, 'tab_id'):
            return False, 0

        info = self._tab_info.get(widget.tab_id, {})
        filepath = info.get("filepath")

        if not filepath or info.get("is_new"):
            return self.save_current_as()

        encoding = info.get("encoding", "UTF-8")
        return self._save_file(widget, filepath, encoding)

    def save_current_as(self) -> Tuple[bool, int]:
        """另存为"""
        widget = self.currentWidget()
        if not widget:
            return False, 0

        tid = getattr(widget, 'tab_id', None)
        if tid is None:
            return False, 0
        info = self._tab_info.get(tid, {})

        if info.get("filepath"):
            suggested_name = info["filepath"]
        else:
            suggested_name = os.path.join(
                self.config.get_notebooks_path(),
                self._strip_tab_suffix(self.tabText(self.currentIndex()))
            )

        current_encoding = info.get("encoding", "UTF-8")

        dialog = SaveAsDialog(suggested_name, current_encoding, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False, 0

        filepath = dialog.get_filepath()
        encoding = dialog.get_encoding()

        if not filepath:
            return False, 0

        success, chars = self._save_file(widget, filepath, encoding)

        if success:
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is not None:
                self._pending_save_as_info[tab_id] = {
                    "filepath": filepath,
                    "encoding": encoding,
                    "untitled_number": info.get("untitled_number") if info.get("is_new") else None,
                }

        return success, chars

    def _save_file(self, widget, filepath: str, encoding: str = "UTF-8") -> Tuple[bool, int]:
        """保存文件（异步写入磁盘，UI 不冻结）

        通过 SaveTaskManager 管理保存状态：
        - 提交任务后标记 SAVING，不提前标记 CLEAN
        - 保存成功后由 Manager 回调标记 CLEAN，此时才更新副作用
        - 保存失败后由 Manager 回调标记 SAVE_FAILED

        副作用（last_saved_content、last_saved_chars、last_text_length、
        字符收益结算）仅在保存成功回调中执行。
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

        info = self._tab_info.get(tab_id, {})
        last_chars = info.get("last_saved_chars", 0)

        # EOL 规范化：将编辑器内部的 \n 替换为文档目标行尾
        current_eol_label = info.get("eol", "LF")
        target_eol = {"LF": "\n", "CRLF": "\r\n", "CR": "\r"}.get(current_eol_label, "\n")
        from .eol_utils import normalize_eol
        content = normalize_eol(content, target_eol)

        new_chars = max(0, len(content) - last_chars)

        info["encoding"] = encoding

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
                info = self._tab_info.get(tab_id, {})
                if info.get("is_modified"):
                    filepath = info.get("filepath")
                    if filepath and not info.get("is_new"):
                        encoding = info.get("encoding", "UTF-8")
                        success, chars = self._save_file(widget, filepath, encoding)
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

            info = self._tab_info.get(tab_id, {})
            if not info.get("is_modified"):
                continue

            if isinstance(widget, MarkdownPreviewWidget):
                content = widget.editor.toPlainText()
            elif isinstance(widget, Editor):
                content = widget.toPlainText()
            else:
                continue

            tab_infos.append({
                "tab_id": tab_id,
                "filepath": info.get("filepath"),
                "content": content,
                "encoding": info.get("encoding", "UTF-8"),
                "is_new": info.get("is_new", False),
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
                    info = self._tab_info.get(tab_id, {})
                    info["history"] = []
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
            info = self._tab_info.get(tid, {}) if tid else {}
            if info.get("filepath") == filepath:
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

    def _on_tab_close_requested(self, index: int):
        self._close_tab(index)

    def _close_tab(self, index: int) -> bool:
        widget = self.widget(index)
        if not widget or not hasattr(widget, 'tab_id'):
            self.removeTab(index)
            self.tab_count_changed.emit(self.count())
            return True

        tab_id = widget.tab_id
        info = self._tab_info.get(tab_id, {})

        if self._save_manager.is_saving(tab_id):
            return False

        if isinstance(widget, MarkdownPreviewWidget):
            content = widget.editor.toPlainText()
        elif isinstance(widget, Editor):
            content = widget.toPlainText()
        else:
            content = ""

        title = self._strip_tab_suffix(self.tabText(index))
        is_new = info.get("is_new", False)
        is_empty = len(content.strip()) == 0

        if is_new and is_empty:
            self._release_untitled_number(title)
            self._save_manager.unregister_tab(tab_id)
            del self._tab_info[tab_id]
            self.removeTab(index)
            self.tab_count_changed.emit(self.count())
            return True

        if info.get("is_modified"):
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
                    encoding = info.get("encoding", "UTF-8")
                    success, _ = self._save_file(widget, info["filepath"], encoding)
                    if not success:
                        return False
                if self._save_manager.is_saving(tab_id):
                    self._pending_close_tab_ids.add(tab_id)
                    return False
            elif clicked == cancel_btn:
                return False

        if info.get("is_new"):
            self._release_untitled_number(title)
        else:
            filepath = info.get("filepath")
            if filepath and os.path.isfile(filepath):
                cursor = None
                if isinstance(widget, Editor):
                    cursor = widget.textCursor().position()
                elif isinstance(widget, MarkdownPreviewWidget):
                    cursor = widget.editor.textCursor().position()
                self._closed_tabs_stack.append({
                    "filepath": filepath,
                    "cursor_position": cursor
                })
                if len(self._closed_tabs_stack) > 50:
                    self._closed_tabs_stack.pop(0)

        self._save_manager.unregister_tab(tab_id)
        del self._tab_info[tab_id]
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

        info = self._tab_info.get(widget.tab_id, {})
        filepath = info.get("filepath")

        if not filepath or info.get("is_new"):
            self._context_save_as(index)
            return

        old_name = os.path.basename(filepath)
        new_name, ok = QInputDialog.getText(self, "重命名", "新文件名:", text=old_name)

        if ok and new_name and new_name != old_name:
            new_path = os.path.join(os.path.dirname(filepath), new_name)
            try:
                os.rename(filepath, new_path)
                info["filepath"] = new_path
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

        info = self._tab_info.get(tab_id, {})

        doc = editor.document()
        if doc is None:
            return
        current_len = doc.characterCount() - 1
        last_len = info.get("last_text_length", current_len)
        delta = current_len - last_len
        info["last_text_length"] = current_len

        is_pasting = getattr(editor, '_is_pasting', False)
        is_programmatic = getattr(editor, 'is_programmatic_modify', False)

        if delta > 0 and not is_pasting and not is_programmatic:
            if delta <= self._PASTE_THRESHOLD:
                self.chars_typed.emit(delta)

        last_saved_chars = info.get("last_saved_chars", 0)
        is_modified = doc.isModified()

        if is_modified != info.get("is_modified", False):
            info["is_modified"] = is_modified
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
        state = SaveState(state_name)
        info = self._tab_info.get(tab_id, {})
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

        if state == SaveState.CLEAN:
            info["is_modified"] = False
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
                info["last_saved_content"] = content
                info["last_saved_chars"] = len(content)
                info["last_text_length"] = len(content)
                if new_chars > 0:
                    self.chars_typed.emit(new_chars)

            save_as_info = self._pending_save_as_info.pop(tab_id, None)
            if save_as_info:
                filepath_new = save_as_info["filepath"]
                encoding_new = save_as_info["encoding"]
                info["is_new"] = False
                info["filepath"] = filepath_new
                info["encoding"] = encoding_new
                if save_as_info.get("untitled_number"):
                    self._used_untitled_numbers.discard(save_as_info["untitled_number"])
                if editor:
                    editor.set_file_type(filepath_new)
                self.setTabText(index, os.path.basename(filepath_new))

            filepath = info.get("filepath")
            if filepath:
                self._session_manager.remove_autosave_for_file(filepath)
            self.file_saved.emit()
            if tab_id in self._pending_close_tab_ids:
                self._pending_close_tab_ids.discard(tab_id)
                self._close_tab_after_save(widget_index)
        elif state == SaveState.SAVING:
            self.setTabText(index, base_title + " ⏳")
        elif state == SaveState.SAVE_FAILED:
            info["is_modified"] = True
            editor = self._get_editor_from_widget(widget)
            if editor:
                doc = editor.document()
                if doc is not None:
                    doc.setModified(True)
            self.setTabText(index, base_title + " !")
            self._pending_save_info.pop(tab_id, None)
            self._pending_save_as_info.pop(tab_id, None)
            if tab_id in self._pending_close_tab_ids:
                self._pending_close_tab_ids.discard(tab_id)
        elif state == SaveState.DIRTY:
            info["is_modified"] = True

    def _on_save_failed(self, tab_id: int, filepath: str, exc: BaseException) -> None:
        info = self._tab_info.get(tab_id, {})
        basename = os.path.basename(filepath) if filepath else "未知文件"
        ErrorHandler.show_from_exception(exc, ErrorCategory.FILE, f"保存文件失败：{basename}")

    def _close_tab_after_save(self, index: int) -> None:
        widget = self.widget(index)
        if not widget or not hasattr(widget, 'tab_id'):
            return

        tab_id = widget.tab_id
        info = self._tab_info.get(tab_id, {})
        title = self._strip_tab_suffix(self.tabText(index))

        if info.get("is_new"):
            self._release_untitled_number(title)
        else:
            filepath = info.get("filepath")
            if filepath and os.path.isfile(filepath):
                cursor = None
                if isinstance(widget, Editor):
                    cursor = widget.textCursor().position()
                elif isinstance(widget, MarkdownPreviewWidget):
                    cursor = widget.editor.textCursor().position()
                self._closed_tabs_stack.append({
                    "filepath": filepath,
                    "cursor_position": cursor
                })
                if len(self._closed_tabs_stack) > 50:
                    self._closed_tabs_stack.pop(0)

        self._save_manager.unregister_tab(tab_id)
        del self._tab_info[tab_id]
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
            info = self._tab_info.get(tab_id, {})
            fp = info.get("filepath")
            if fp and not info.get("is_new"):
                paths.append(fp)
        return paths

    def get_current_encoding(self) -> str:
        """获取当前文件的编码"""
        widget = self.currentWidget()
        if widget and hasattr(widget, 'tab_id'):
            info = self._tab_info.get(widget.tab_id, {})
            return str(info.get("encoding", "UTF-8"))
        return "UTF-8"

    def get_current_eol(self) -> str:
        """获取当前文档的行尾类型（LF / CRLF / CR / Mixed）"""
        widget = self.currentWidget()
        if widget and hasattr(widget, 'tab_id'):
            info = self._tab_info.get(widget.tab_id, {})
            return str(info.get("eol", "LF"))
        return "LF"

    def set_current_eol(self, eol: str) -> None:
        """切换当前文档的行尾类型，并标记为已修改"""
        widget = self.currentWidget()
        if widget and hasattr(widget, 'tab_id'):
            info = self._tab_info.get(widget.tab_id, {})
            info["eol"] = eol
            info["is_modified"] = True
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
                info = self._tab_info.get(tab_id, {})
                if info.get("is_modified"):
                    editor = self._get_editor_from_widget(widget)
                    content = editor.toPlainText() if editor else ""
                    if info.get("is_new") and len(content.strip()) == 0:
                        continue
                    filepath = info.get("filepath")
                    if filepath:
                        unsaved.append(os.path.basename(filepath))
                    else:
                        unsaved.append(self._strip_tab_suffix(self.tabText(i)))
        return unsaved

    def has_modified_files(self) -> bool:
        for tab_id, info in self._tab_info.items():
            if info.get("is_modified"):
                return True
        return False

    def get_current_file_info(self) -> Optional[Dict]:
        widget = self.currentWidget()
        if not widget:
            return None
        tab_id = getattr(widget, 'tab_id', None)
        if tab_id is None:
            return None
        info = self._tab_info.get(tab_id, {})
        filepath = info.get("filepath")
        if not filepath:
            return None
        editor = self._get_editor_from_widget(widget)
        result = {"filepath": filepath}
        if editor:
            cursor = editor.textCursor()
            result["cursor_position"] = cursor.position()
            vbar = editor.verticalScrollBar()
            if vbar is not None:
                result["scroll_position"] = vbar.value()
        return result

    def get_open_files_info(self) -> List[Dict]:
        files_info = []
        for i in range(self.count()):
            widget = self.widget(i)
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is not None:
                info = self._tab_info.get(tab_id, {})
                filepath = info.get("filepath")
                if filepath and not info.get("is_new"):
                    editor = self._get_editor_from_widget(widget)
                    if editor:
                        cursor = editor.textCursor()
                        vbar2 = editor.verticalScrollBar()
                        files_info.append({
                            "path": filepath,
                            "cursor_position": cursor.position(),
                            "scroll_position": vbar2.value() if vbar2 is not None else 0
                        })
        return files_info

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
                    info = self._tab_info.get(tab_id, {})
                    if info.get("filepath") == filepath:
                        # 保存最新内容
                        if info.get("is_modified"):
                            enc = info.get("encoding", "UTF-8")
                            self._save_file(widget, filepath, enc)
                        break

            import shutil
            shutil.move(filepath, new_path)

            # 更新标签页信息
            for i in range(self.count()):
                widget = self.widget(i)
                tab_id = getattr(widget, 'tab_id', None)
                if tab_id is not None:
                    info = self._tab_info.get(tab_id, {})
                    if info.get("filepath") == filepath:
                        info["filepath"] = new_path
                        self.setTabText(i, filename)
                        break

            return True
        except Exception as e:
            get_logger(__name__).error("移动文件失败: %s", e)
            ErrorHandler.show_from_exception(e, ErrorCategory.FILE, "移动文件失败")
            return False

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
            info = self._tab_info.get(tab_id, {})
            filepath = info.get("filepath")
            if not filepath:
                continue
            editor = self._get_editor_from_widget(widget)
            if editor is not None:
                bookmarks = editor.get_bookmarks()
                self.config.set_bookmarks(filepath, list(bookmarks) if bookmarks else [])

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
            info = self._tab_info.get(tab_id, {})
            filepath = info.get("filepath")
            if not filepath:
                continue
            editor = self._get_editor_from_widget(widget)
            if editor is not None and hasattr(editor, '_folding'):
                collapsed = editor._folding.get_collapsed_lines()
                self.config.set_folds(filepath, collapsed if collapsed else [])
