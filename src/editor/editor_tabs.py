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
from typing import Optional, List, Dict, Tuple, Set, cast

from PyQt6.QtWidgets import (
    QTabWidget, QTabBar, QMessageBox, QMenu, QInputDialog, QDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction

from ..core.config import Config
from ..core import workspace_entries
from ..core.document_registry import DocumentRegistry
from ..core.document_view_binding import DocumentViewBinding
from ..core.shared_document import ViewState
from ..utils.logger import get_logger
from ..utils.error_handler import ErrorHandler, ErrorCategory
from ..utils.feature_flags import is_enabled
from ..security.file_guard import FileSizeExceededError, FileOperationTimeoutError
from ..security.file_access_context import FileAccessContext
from ..themes.theme_aware_mixin import ThemeAwareMixin
from .editor import Editor
from .markdown_preview import MarkdownPreviewWidget
from .find_replace import FindReplaceBar
from .save_task_manager import SaveTaskManager
from .tab_save_flow import TabSaveFlowMixin
from .tab_file_ops import TabFileOpsMixin
from .temp_session_manager import TempSessionManager
from .eol_utils import detect_eol_from_bytes
from .image_reference_scanner import find_missing_local_images
from .asset_recovery_dialog import AssetRecoveryDialog
from .asset_recovery_service import AssetRecoveryService
from .draggable_tab_bar import (
    MIME_TAB_FILEPATH,
    MIME_TAB_ID,
    DraggableTabBar,
    TabCloseButton,
)

# ════════════════════════════════════════════════════════
#  EditorTabWidget
# ════════════════════════════════════════════════════════

class EditorTabWidget(TabFileOpsMixin, TabSaveFlowMixin, ThemeAwareMixin, QTabWidget):
    """编辑器标签页管理"""

    current_changed = pyqtSignal(int)
    content_modified = pyqtSignal()
    tab_count_changed = pyqtSignal(int)
    chars_typed = pyqtSignal(int)
    cursor_position_changed = pyqtSignal()
    word_count_updated = pyqtSignal()
    file_saved = pyqtSignal()
    # Batch 4：文档打开/关闭事件（filepath；未命名文档不触发）
    document_opened = pyqtSignal(str)
    document_closed = pyqtSignal(str)
    # E6b：文档引用的本地图片缺失（filepath, 缺失资源的规范化绝对路径列表）
    missing_images_detected = pyqtSignal(str, list)
    # E6c2：断链恢复执行完成（filepath, 已恢复并删源数, 已复制恢复数, 仍未恢复数）
    asset_recovery_finished = pyqtSignal(str, int, int, int)
    # 1.4：预览后端不可用（用户可读原因）——任意一个 md 标签的预览后端故障
    # 都会发出，供主窗口送上状态栏常驻指示
    preview_backend_failed = pyqtSignal(str)

    def __init__(
        self,
        config: Config,
        theme_engine,
        document_registry=None,
        session_manager=None,
        panel_name: str = "main",
        parent=None,
    ):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("EditorTabs 必须传入 theme_engine，不允许为 None")
        self.config = config
        self._theme_engine = theme_engine
        # 3.5.8（R6）：面板标识——崩溃恢复时 autosave 按此字段路由回原面板
        # （主面板 "main"，分屏 "split_0" / "split_1" ...）
        self._panel_name = panel_name
        # 3.5.8（批次 4a）：跨面板共享 DocumentRegistry——主面板与分屏注入同一实例，
        # 多 View 打开同一文件时共享同一 Document（规格 2.1）。未传入时自建（独立使用）。
        self._document_registry = document_registry or DocumentRegistry()

        self._next_tab_id = 0
        self._used_untitled_numbers: Set[int] = set()
        self._closed_tabs_stack: List[Dict] = []

        self._save_manager = SaveTaskManager(self)
        self._save_manager.save_state_changed.connect(self._on_save_state_changed)
        self._save_manager.save_failed.connect(self._on_save_failed)

        self._pending_close_tab_ids: Set[int] = set()
        self._pending_save_info: Dict[int, Dict] = {}
        self._pending_save_as_info: Dict[int, Dict] = {}

        # 3.5.8（批次 4e）：分屏注入主面板的 TempSessionManager——所有面板写同一
        # session，同一 Document 的 autosave 只写一份（规格 3.2）；未传入时自建。
        self._session_manager = (
            session_manager
            or TempSessionManager(config.get_temp_path(), config.get_file_guard())
        )

        self._tab_bar = DraggableTabBar(self)
        self.setTabBar(self._tab_bar)

        self.setTabsClosable(True)
        # 3.5.8（R6）：禁用原生 movable——原生拖拽扫过其它标签会实时 moveTab
        # "替换"拖拽对象。内部 reorder 由 DraggableTabBar 自行接管（释放时落位）。
        self.setMovable(False)
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
        btn = TabCloseButton(self._theme_engine, self)
        self.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, btn)  # type: ignore[union-attr]
        # 3.5.12：迁移过来的标签 tab_id 已存在，先刷新 tooltip（未注册时显示「未保存」）
        self._update_tab_tooltip(index)

    def _update_tab_tooltip(self, index: int) -> None:
        """3.5.12：标签 tooltip 区分已保存（完整路径）与未保存（「未保存」）。"""
        widget = self.widget(index)
        # D3b：路径读 Document（is_new 语义 = filepath is None）
        shared_doc = getattr(widget, "shared_doc", None)
        if shared_doc is not None and shared_doc.filepath:
            self.setTabToolTip(index, shared_doc.filepath)
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
    def document_registry(self):
        """跨面板共享的 DocumentRegistry（3.5.8：Document 生命周期全局唯一）"""
        return self._document_registry

    def _get_filepath_for_index(self, index: int) -> Optional[str]:
        """获取指定标签页的文件路径（供 DraggableTabBar 使用）"""
        widget = self.widget(index)
        if widget:
            # D3b：路径读 Document（is_new 语义 = filepath is None）
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is not None and shared_doc.filepath:
                return str(shared_doc.filepath)
        return None

    @staticmethod
    def _get_editor_from_widget(widget) -> Optional[Editor]:
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
        # 图片标签无 Document / 无 tab_id，走独立分支：只搬 widget 本身
        image_path = getattr(widget, 'image_path', None)
        if image_path is not None:
            return self._migrate_image_tab_from(source_tabs, index, str(image_path))
        tab_id = getattr(widget, 'tab_id', None)
        if tab_id is None:
            return False
        if source_tabs._save_manager.is_saving(tab_id):
            return False  # 保存中拒绝迁移，避免跨面板保存状态机竞态
        title = source_tabs.tabText(index)

        # 3.5.8（批次 4e，规格 2.5）：目标面板已有同一 Document 的 View →
        # 合并：源直接关闭（不迁移 widget），保留目标已有 View 的 ViewState。
        # 不销毁 Document（目标仍持有）；未命名编号不动（编号属 Document）。
        # D1：合并不触碰目标 widget，目标 view_state（cursor/scroll）天然保留，
        # 符合「View 位置状态单一源」契约。
        shared_doc = getattr(widget, "shared_doc", None)
        if shared_doc is not None:
            target_has_same_doc = any(
                getattr(self.widget(i), "shared_doc", None) is shared_doc
                for i in range(self.count())
            )
            if target_has_same_doc:
                source_tabs.removeTab(index)
                source_tabs._save_manager.unregister_tab(tab_id)
                source_tabs._document_registry.detach_view(
                    shared_doc.document_id, widget
                )
                source_tabs._detach_shared_from_widget(widget)
                source_tabs._disconnect_doc_binding(widget)
                source_tabs.tab_count_changed.emit(source_tabs.count())
                for i in range(self.count()):
                    if getattr(self.widget(i), "shared_doc", None) is shared_doc:
                        self.setCurrentIndex(i)
                        break
                return True

        # 3.5.7：迁移前断开源面板的信号绑定，否则编辑器 textChanged 仍指向源面板
        # （源面板已注销该 tab → 槽内直接返回），脏标记/标题更新失效。
        editor = source_tabs._get_editor_from_widget(widget)
        if editor is not None:
            source_tabs._disconnect_editor_signals(editor)

        # 源：移除标签（removeTab 为原生方法，不触发关闭确认）
        source_tabs.removeTab(index)
        source_tabs._save_manager.unregister_tab(tab_id)
        # 3.5.8（批次 5，规格 2.6）：共享 Document 信号绑定随 View 迁移——
        # 源面板断开本 View 绑定（目标面板 addTab 后 _connect_doc_binding 重建）。
        shared_doc = getattr(widget, "shared_doc", None)
        if shared_doc is not None:
            source_tabs._disconnect_doc_binding(widget)
        source_tabs.tab_count_changed.emit(source_tabs.count())

        # 目标：添加标签（tabInserted 自动重建关闭按钮；Document 绑定按 View 重建）
        self.addTab(widget, title)
        self._save_manager.register_tab(tab_id)
        if editor is not None:
            self._connect_editor_signals(editor)
        self._connect_doc_binding(widget)  # 重建 Document 信号绑定（按 View 粒度）
        # 3.5.11：未命名标签迁移，编号随标签转移（源释放、目标占用）
        # D3b：编号读 Document（is_new 语义 = filepath is None）
        if (shared_doc is not None and shared_doc.filepath is None
                and shared_doc.untitled_number is not None):
            source_tabs._used_untitled_numbers.discard(shared_doc.untitled_number)
            self._used_untitled_numbers.add(shared_doc.untitled_number)
        # 关键：每个面板 _next_tab_id 独立计数，提升避免未来生成重复 tab_id
        self._next_tab_id = max(self._next_tab_id, tab_id + 1)
        self._update_tab_tooltip(self.indexOf(widget))
        self.tab_count_changed.emit(self.count())
        return True

    def _migrate_image_tab_from(
        self, source_tabs: "EditorTabWidget", index: int, image_path: str
    ) -> bool:
        """图片标签跨分屏迁移：无 Document / 无 tab_id，只搬 widget 本身。

        不涉及保存状态机与 Document 注册表（图片标签本就不在两者中）；
        迁移后 `_close_tab` 仍走「无 tab_id」分支直接移除，不弹保存确认。
        tooltip 需显式设为图片路径——`_update_tab_tooltip` 对无 Document 的
        标签会写「未保存」，对图片标签是错的。
        """
        if source_tabs is self:
            return False
        widget = source_tabs.widget(index)
        if widget is None:
            return False
        title = source_tabs.tabText(index)
        source_tabs.removeTab(index)
        source_tabs.tab_count_changed.emit(source_tabs.count())
        new_index = self.addTab(widget, title)
        self.setTabToolTip(new_index, image_path)
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
        """创建未命名标签页（new_file / restore_untitled_file 共用）

        3.5.8（R4 未命名共享入口）：未命名 tab 也创建共享 Document 并 attach——
        生命周期与具名文件统一（close 决策树 / Save As / 迁移 / 编号释放全部
        作用 Document），为「未命名文件跨面板共享」铺路。
        """
        self._used_untitled_numbers.add(num)

        # R4：未命名 Document（is_new=True，无路径）；编号沿用面板编号池
        shared_doc = self._document_registry.create_untitled(
            untitled_number=num,
            display_name=title,
        )

        editor = Editor(self.config, theme_engine=self._theme_engine)
        editor.attach_shared_document(shared_doc)
        self._connect_editor_signals(editor)
        self._connect_doc_binding(editor)
        editor.set_file_type(".txt")

        index = self.addTab(editor, title)

        tab_id = self._generate_tab_id()
        editor.tab_id = tab_id
        setattr(editor, "view_state", ViewState.new())  # 3.5.8（批次 5，ViewState 接线）
        self._save_manager.register_tab(tab_id)
        self._document_registry.attach_view(shared_doc.document_id, editor)

        self.setCurrentIndex(index)
        self.tab_count_changed.emit(self.count())
        self._update_tab_tooltip(index)
        return int(index)

    @staticmethod
    def _is_markdown_file(filepath: str) -> bool:
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
        # 检查文件是否已经打开（D3b：路径比较读 Document）
        for i in range(self.count()):
            widget = self.widget(i)
            if widget is None:
                continue
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is not None and shared_doc.filepath == filepath:
                if activate:
                    self.setCurrentIndex(i)
                return i

        # 3.5.8（批次 4b，规格 2.1 自动共享）：另一面板已打开同一文件 →
        # 不重新读盘，直接新建 View attach 到共享 Document（内容/编码/eol 属 Document）。
        shared_doc = self._document_registry.get_by_path(filepath)
        if shared_doc is not None:
            return self._create_shared_view(
                shared_doc,
                activate=activate,
                insert_index=insert_index,
                render_preview=render_preview,
            )

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

        # 3.5.8（批次 4b）：Document 全局唯一——读盘成功后注册共享 Document，
        # 所有 View attach 到同一 QTextDocument（内容/编码/eol 属 Document）。
        # 若 registry 已命中（另一面板已打开），会走上方共享分支，不会到这里。
        shared_doc = self._document_registry.create_from_path(
            filepath,
            content,
            encoding=detected_encoding,
            eol=eol_label,
            is_markdown=is_md,
        )

        if is_md:
            widget = MarkdownPreviewWidget(
                self.config,
                theme_engine=self._theme_engine,
            )
            widget.backend_failed.connect(self.preview_backend_failed)
            widget.editor.attach_shared_document(shared_doc)
            widget.editor.load_content(content)  # 幂等重建补全词集/折叠（内容相同）
            self._connect_editor_signals(widget.editor)
            self._connect_doc_binding(widget)
            widget.editor.set_file_type(filepath)
            widget.set_base_path(os.path.dirname(os.path.abspath(filepath)))
            # E3 大文件模式：打开时不自动渲染预览（大文件 md 全量渲染高成本）；
            # 需要渲染时用「视图 → 刷新预览」（EditorTabWidget.refresh_md_preview）。
            if render_preview and not widget.editor.is_large_file_mode():
                widget.refresh_preview_now()
        else:
            widget = Editor(self.config, theme_engine=self._theme_engine)
            widget.attach_shared_document(shared_doc)
            widget.load_content(content)  # 幂等重建补全词集/折叠（内容相同）
            self._connect_editor_signals(widget)
            self._connect_doc_binding(widget)
            widget.set_file_type(filepath)

        filename = os.path.basename(filepath)
        if insert_index is not None:
            index = self.insertTab(insert_index, widget, filename)
        else:
            index = self.addTab(widget, filename)

        tab_id = self._generate_tab_id()
        widget.tab_id = tab_id
        setattr(widget, "view_state", ViewState.new())  # 3.5.8（批次 5，ViewState 接线）

        # 如果是MarkdownPreviewWidget，也设置editor的tab_id
        if is_md and isinstance(widget, MarkdownPreviewWidget):
            widget.editor.tab_id = tab_id

        self._save_manager.register_tab(tab_id)
        self._document_registry.attach_view(shared_doc.document_id, widget)

        if activate:
            self.setCurrentIndex(index)
        self.tab_count_changed.emit(self.count())
        self._update_tab_tooltip(index)
        # Batch 4：文档打开事件（仅带路径文档）
        self.document_opened.emit(filepath)
        if is_md:
            self._notify_missing_images(widget, filepath)

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

    def _create_shared_view(
        self,
        shared_doc,
        *,
        activate: bool = True,
        insert_index: int | None = None,
        render_preview: bool = True,
    ) -> int:
        """为已有共享 Document 创建新 View（规格 2.1 自动共享）。

        跨面板打开同一文件时由 open_file 调用：不重新读盘——内容、编码、eol
        均属 Document（SharedDocument 已持有）；View 只 attach 共享 QTextDocument，
        编辑/undo 与其它 View 天然同步。
        """
        is_md = shared_doc.is_markdown
        widget: "Editor | MarkdownPreviewWidget"
        if is_md:
            widget = MarkdownPreviewWidget(
                self.config,
                theme_engine=self._theme_engine,
            )
            widget.backend_failed.connect(self.preview_backend_failed)
            editor = widget.editor
        else:
            widget = Editor(self.config, theme_engine=self._theme_engine)
            editor = widget

        editor.attach_shared_document(shared_doc)
        self._connect_editor_signals(editor)
        self._connect_doc_binding(widget)
        if shared_doc.filepath:
            editor.set_file_type(shared_doc.filepath)
        if is_md:
            md_widget = cast(MarkdownPreviewWidget, widget)
            md_widget.set_base_path(
                os.path.dirname(os.path.abspath(shared_doc.filepath or "."))
            )
            if render_preview and not editor.is_large_file_mode():
                md_widget.refresh_preview_now()

        filename = shared_doc.display_name
        if insert_index is not None:
            index = self.insertTab(insert_index, widget, filename)
        else:
            index = self.addTab(widget, filename)

        tab_id = self._generate_tab_id()
        widget.tab_id = tab_id
        editor.tab_id = tab_id
        setattr(widget, "view_state", ViewState.new())  # 3.5.8（批次 5，ViewState 接线）

        self._save_manager.register_tab(tab_id)
        self._document_registry.attach_view(shared_doc.document_id, widget)

        if activate:
            self.setCurrentIndex(index)
        self.tab_count_changed.emit(self.count())
        self._update_tab_tooltip(index)
        # Batch 4：跨面板共享视图打开同一文档也视为 document.opened
        if shared_doc.filepath:
            self.document_opened.emit(shared_doc.filepath)
            if is_md:
                self._notify_missing_images(widget, shared_doc.filepath)
        return int(index)

    def open_image_tab(self, filepath: str, file_guard, *, activate: bool = True) -> int:
        """以标签页形式打开图片（只读查看器）。

        图片标签与文档标签同族但无 Document：不带 `tab_id` / `shared_doc`，
        因此关闭走 `_close_tab` 的「无 tab_id」分支（直接移除，不涉及保存/脏确认）；
        编辑类命令经 `current_editor()` 返回 None 自然失效。
        同一张图片已打开时聚焦既有标签，不重复开。
        """
        from .image_viewer import ImageViewerWidget

        target = os.path.abspath(filepath)
        for i in range(self.count()):
            widget = self.widget(i)
            if getattr(widget, "image_path", None) == target:
                if activate:
                    self.setCurrentIndex(i)
                return i

        viewer = ImageViewerWidget(target, file_guard)
        index = self.addTab(viewer, os.path.basename(target))
        self.setTabToolTip(index, target)
        if activate:
            self.setCurrentIndex(index)
        self.tab_count_changed.emit(self.count())
        return int(index)

    def release_memory(self):
        """释放内存"""
        current = self.currentWidget()

        for i in range(self.count()):
            widget = self.widget(i)
            if widget != current:
                # D3c：history 字段已删（release_memory 只清撤销栈）
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

    def force_close_all_tabs(self):
        """无确认强制关闭全部标签（3.5.7：分屏「不保存并关闭」路径）。

        已由调用方弹过汇总确认，此处跳过逐标签确认框（避免二次弹窗）；
        清理逻辑与 _close_tab 一致（释放未命名编号、注销注册表）。
        """
        while self.count() > 0:
            if not self._close_tab(0, force=True):
                break

    def reopen_closed_tab(self) -> bool:
        """D1：Ctrl+Shift+T 重开关闭的标签——恢复光标 + 滚动位置（view_state 快照）。"""
        if not self._closed_tabs_stack:
            return False
        entry = self._closed_tabs_stack.pop()
        filepath = entry["filepath"]
        cursor_pos = entry.get("cursor_position")
        scroll_pos = entry.get("scroll_position", 0)
        for i in range(self.count()):
            w = self.widget(i)
            if w is None:
                continue
            # D3b：路径读 Document
            shared_doc = getattr(w, "shared_doc", None)
            if shared_doc is not None and shared_doc.filepath == filepath:
                self.setCurrentIndex(i)
                return True
        index = self.open_file(filepath)
        if index == -1:
            return False
        widget = self.widget(index)
        editor = self._get_editor_from_widget(widget)
        if editor is not None:
            if cursor_pos is not None:
                cursor = editor.textCursor()
                cursor.setPosition(min(cursor_pos, len(editor.toPlainText())))
                editor.setTextCursor(cursor)
            if scroll_pos:
                self._restore_scroll_position(editor, scroll_pos)
        return True

    def close_other_tabs(self, keep_index: int):
        while self.count() > keep_index + 1:
            if not self._close_tab(keep_index + 1):
                break
        while self.count() > 1 and keep_index > 0:
            if not self._close_tab(0):
                break
            keep_index -= 1

    def _apply_theme_colors(self):
        # B8：tabs 消费 v2 tab recipe
        # 补漏 C：统一走 resolve()（color/design 数值一次解析），消除 padding/radius 字面量
        style = self._theme_engine.components.resolve("tab") or {}
        tab_bg = style.get("background", "#F5F5F5")
        active_bg = style.get("active_background", "#FFFFFF")
        pane_bg = style.get("pane_background", "#FFFFFF")
        tab_fg = style.get("text", "#757575")
        active_fg = style.get("active_text", "#212121")
        hover_bg = style.get("hover_background", "#BBDEFB")
        pressed_bg = style.get("pressed_background", "#E0E0E0")
        border = style.get("border", "#E0E0E0")
        radius = style.get("radius", 3)

        self.setStyleSheet(f"""
    QTabWidget {{
        background-color: {tab_bg};
        border: none;
    }}

    QTabWidget::pane {{
        background-color: {pane_bg};
        border: none;
        top: -1px;
    }}

    QTabBar {{
        background-color: {tab_bg};
        border: none;
    }}

    QTabBar::tab {{
        padding: 8px 15px;
        margin-right: 2px;
        background-color: {tab_bg};
        border: 1px solid {border};
        /* 所有 tab 统一无左边框：tab 栏最左侧与正文左边缘齐平（pane 无
           边框，视觉连续）；tab 间分隔由前一个 tab 的右边框承担。
           不用 :first 伪状态——实测在真实 QTabBar 上匹配不可靠。 */
        border-left: none;
        border-bottom: 1px solid {tab_bg};
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        color: {tab_fg};
    }}

    QTabBar::tab:selected {{
        background-color: {active_bg};
        border-color: {border};
        border-bottom: 1px solid {active_bg};
        color: {active_fg};
    }}

    QTabBar::tab:hover:!selected {{
        background-color: {hover_bg};
        color: {active_fg};
    }}

    /* B6 pressed 态：仅当 hover AND pressed 同时生效，避免 Qt 在 tab 增删时
       pressed 伪状态在相邻 tab 上残留，导致"某 tab 颜色莫名变深"。 */
    QTabBar::tab:hover:pressed:!selected {{
        background-color: {pressed_bg};
    }}

    /* tab 栏左下角/右下角 corner（文档模式下的左右空白区域）：
       与 tab 栏同色，避免 tab 最左侧/最右侧出现 pane 背景的竖向色条。 */
    QTabWidget::left-corner, QTabWidget::right-corner {{
        background-color: {tab_bg};
    }}

    QTabBar QToolButton {{
        background-color: {tab_bg};
        color: {active_fg};
        border: 1px solid {border};
        border-radius: {radius}px;
        margin: 1px;
    }}

    QTabBar QToolButton:hover {{
        background-color: {hover_bg};
    }}
    """)
        tab_bar = self.tabBar()
        if tab_bar is not None:
            for i in range(tab_bar.count()):
                btn = tab_bar.tabButton(i, QTabBar.ButtonPosition.RightSide)
                if isinstance(btn, TabCloseButton):
                    btn._apply_btn_style()

    def _on_tab_close_requested(self, index: int):
        self._close_tab(index)

    def _record_closed_tab(self, filepath: str, widget) -> None:
        """记录关闭标签页的位置：内存栈（Ctrl+Shift+T）+ 持久化记忆（重开恢复）。

        仅记录已保存文件（调用方已确认 filepath 存在）。
        D1：View 位置状态单一源 = widget.view_state——先实时捕获写入 view_state，
        内存栈与持久化记忆都从同一处取值（cursor + scroll 一并记录）。
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
        # 3.5.8（批次 5，ViewState 接线）：View 级位置快照 → view_state
        # （workspace 导出经 get_open_files_info 实时捕获 view_state）。
        view_state = getattr(widget, "view_state", None)
        if view_state is not None:
            view_state.cursor_position = cursor
            view_state.scroll_position = scroll
        self._closed_tabs_stack.append({
            "filepath": filepath,
            "cursor_position": cursor,
            "scroll_position": scroll,
        })
        if len(self._closed_tabs_stack) > 50:
            self._closed_tabs_stack.pop(0)
        if cursor is not None:
            self.config.set_closed_tab_memory(filepath, cursor, scroll)

    @staticmethod
    def _restore_scroll_position(editor, scroll_pos: int) -> None:
        """恢复编辑器滚动位置。

        首帧布局未完成时 setValue 会被 clamp：等待滚动范围就绪后重试一次
        （与 open_file 的 closed_tabs_memory 恢复逻辑一致）。
        """
        vbar = editor.verticalScrollBar()
        if vbar is None or not scroll_pos:
            return
        vbar.setValue(scroll_pos)
        if vbar.value() == scroll_pos:
            return

        def _retry(vmin, vmax):
            if vmax >= scroll_pos:
                vbar.setValue(scroll_pos)
                try:
                    vbar.rangeChanged.disconnect(_retry)
                except TypeError:
                    pass

        vbar.rangeChanged.connect(_retry)

    @staticmethod
    def _detach_shared_from_widget(widget) -> None:
        """解除 widget 与共享 Document 的 attach（Editor 或 Markdown 预览组件）。

        3.5.8（批次 4c）：非最后 View 关闭前调用，避免 View 残留对共享
        qdocument 的引用；SharedDocument 仍由其它 View 持有。
        """
        editor = getattr(widget, "editor", None)
        if editor is not None:
            editor.detach_shared_document()
        elif isinstance(widget, Editor):
            widget.detach_shared_document()

    def _connect_doc_binding(self, widget) -> None:
        """为 View 建立 Document-level 信号绑定（3.5.8 批次 5，规格 2.6）。

        每个 View 一个 DocumentViewBinding（生命周期与 View 一致）：
        dirtyChanged → 标题与脏标记；nameChanged → 标题跟随；
        pathChanged → Markdown 预览 base_path 跟随（规格 2.8）。
        替代 R2 面板级「面板 × Document」连接：按 View 粒度管理，关闭/迁移即断，
        无 UniqueConnection 残留边界问题。迁移到本面板时先清旧绑定再重建。
        """
        shared_doc = getattr(widget, "shared_doc", None)
        if shared_doc is None:
            return
        self._disconnect_doc_binding(widget)  # 幂等：避免重复 binding
        binding = DocumentViewBinding(shared_doc, parent=widget)
        binding.bind("dirtyChanged", lambda dirty: self._on_view_dirty(widget, dirty))
        binding.bind("nameChanged", lambda name: self._on_view_renamed(widget, name))
        binding.bind("pathChanged", lambda path: self._on_view_path_changed(widget, path))
        binding.attach()
        widget._doc_binding = binding

    @staticmethod
    def _disconnect_doc_binding(widget) -> None:
        """解除 View 的 Document 信号绑定（关闭/迁移前调用，幂等）。"""
        binding = getattr(widget, "_doc_binding", None)
        if binding is not None:
            binding.detach()
            widget._doc_binding = None

    def _on_view_dirty(self, widget, dirty: bool) -> None:
        """Document dirty 变化 → 本 View 标题与脏标记同步（dirty 单一源在 Document）。

        3.5.8（批次 5，规格 2.6）：替代 R2 面板级 _on_shared_doc_dirty——按 View
        粒度更新自己的标题，无需遍历面板内所有 View（面板内同 Document 至多一 View）。
        """
        tab_id = getattr(widget, "tab_id", None)
        index = self.indexOf(widget)
        if tab_id is None or index < 0:
            return
        # D3a：dirty 单一源在 Document——这里只做副作用的单一入口
        # （保存状态机 mark_dirty + 标题更新）。
        if dirty:
            self._save_manager.mark_dirty(tab_id)
        title = self.tabText(index)
        stripped = self._strip_tab_suffix(title)
        if dirty and not stripped.endswith(" *"):
            self.setTabText(index, stripped + " *")
        elif not dirty and stripped != title:
            self.setTabText(index, stripped)

    def _on_view_renamed(self, widget, name: str) -> None:
        """Document 更名（Save As / 首次保存）→ 本 View 标题跟随（规格 2.2）。"""
        index = self.indexOf(widget)
        if index < 0:
            return
        title = self.tabText(index)
        if title == name:
            return
        stripped = self._strip_tab_suffix(title)
        self.setTabText(index, name + title[len(stripped):])

    def _notify_missing_images(self, widget, filepath: str) -> None:
        """E6b：扫描文档引用的本地图片，缺失则发出信号（提示形态由接收方决定）。

        只读检测，不与渲染循环绑定；触发点为文档打开与资源根（base_path）变化。
        检测失败不得影响打开 / 渲染，故异常仅记 debug 日志。
        """
        if not filepath or not self._is_markdown_file(filepath):
            return
        editor = self._get_editor_from_widget(widget)
        if editor is None:
            return
        base_dir = os.path.dirname(os.path.abspath(filepath))
        try:
            missing = find_missing_local_images(base_dir, editor.toPlainText())
        except Exception as exc:
            get_logger(__name__).debug("图片引用缺失检测失败: %s", exc)
            return
        if missing:
            self.missing_images_detected.emit(filepath, missing)

    def _on_view_path_changed(self, widget, path: str) -> None:
        """Document.pathChanged → 本 View 预览基准跟随（规格 2.8）。

        D3b：路径 authority 在 Document——pathChanged 由 bind_path 广播给所有
        View 时无需再回写状态（路径读点全部走 Document）。
        保留预览 widget 的 base_path / invalidate 副作用；
        E6b：资源根变化后按新基准复核图片引用缺失。
        """
        if not isinstance(widget, MarkdownPreviewWidget):
            return
        base = os.path.dirname(os.path.abspath(path)) if path else "."
        widget.set_base_path(base)
        widget.invalidate_preview()  # 下次激活/内容变化时以新基准重渲染
        self._notify_missing_images(widget, path)

    @staticmethod
    def _close_md_preview(widget) -> None:
        """关闭标签时释放 Markdown 预览后端（WebView2 controller 等原生资源）。

        QTabWidget.removeTab 不删除页面控件、也不触发 closeEvent，预览的
        controller 若不经显式 teardown 会随标签累积、永不回收（H2）。
        迁移路径（分屏合并/移动）不调用本方法：widget 迁移到目标面板继续使用。
        """
        if isinstance(widget, MarkdownPreviewWidget):
            widget.shutdown_preview()

    def _close_tab(self, index: int, *, force: bool = False) -> bool:
        """关闭标签页。

        force=True：跳过 dirty 确认框（调用方已确认），仅用于分屏
        「不保存并关闭」的批量关闭。
        """
        widget = self.widget(index)
        if not widget or not hasattr(widget, 'tab_id'):
            self._close_md_preview(widget)
            self.removeTab(index)
            self.tab_count_changed.emit(self.count())
            return True

        tab_id = widget.tab_id
        shared_doc = getattr(widget, "shared_doc", None)
        if shared_doc is None:
            self._close_md_preview(widget)
            self.removeTab(index)
            self.tab_count_changed.emit(self.count())
            return True

        if self._save_manager.is_saving(tab_id):
            return False

        # 3.5.8（批次 4c，规格 2.3）：共享 Document 还有其他 View →
        # 直接关本 View：不弹确认、不销毁 Document、不动未命名编号（编号属 Document）。
        # 只有最后一个 View 关闭才走 dirty 确认，成功后 release 销毁 Document。
        doc_id = shared_doc.document_id
        if self._document_registry.view_count(doc_id) > 1:
            self._document_registry.detach_view(doc_id, widget)
            self._detach_shared_from_widget(widget)
            self._disconnect_doc_binding(widget)
            self._save_manager.unregister_tab(tab_id)
            self._close_md_preview(widget)
            self.removeTab(index)
            self.tab_count_changed.emit(self.count())
            return True

        if isinstance(widget, MarkdownPreviewWidget):
            content = widget.editor.toPlainText()
        elif isinstance(widget, Editor):
            content = widget.toPlainText()
        else:
            content = ""

        title = self._strip_tab_suffix(self.tabText(index))
        # D3b：is_new 语义 = filepath is None（读 Document）
        is_new = shared_doc.filepath is None
        is_empty = len(content.strip()) == 0

        if is_new and is_empty:
            self._release_untitled_number(title)
            self._save_manager.unregister_tab(tab_id)
            self._close_md_preview(widget)
            self.removeTab(index)
            self.tab_count_changed.emit(self.count())
            # 批次 5 修复：最后 View 关闭前断开 Document 依赖——否则共享高亮
            # 随 Document 销毁后 widget 仍悬垂引用（切主题报 C++ deleted）
            self._detach_shared_from_widget(widget)
            self._document_registry.release(shared_doc.document_id)
            return True

        # D3a：dirty 单一源 = SharedDocument（关闭最后一个 View 时其它 View 的
        # 编辑也会置脏，不能只看本 View 的旧状态）。
        is_modified = shared_doc.dirty

        if is_modified and not force:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("保存文件")
            if is_new:
                msg_box.setText(f"文件 '{title}' 尚未保存。\n\n是否保存？")
            else:
                msg_box.setText(f"文件 '{title}' 已修改。\n\n是否保存？")
            msg_box.setIcon(QMessageBox.Icon.Question)

            save_btn = msg_box.addButton("保存", QMessageBox.ButtonRole.AcceptRole)
            msg_box.addButton("不保存", QMessageBox.ButtonRole.DestructiveRole)
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
                    # D3b：路径/编码读 Document
                    filepath = shared_doc.filepath
                    encoding = shared_doc.encoding
                    if not filepath:
                        return False
                    success, _ = self._save_file(widget, filepath, encoding)
                    if not success:
                        return False
                if self._save_manager.is_saving(tab_id):
                    self._pending_close_tab_ids.add(tab_id)
                    return False
            elif clicked == cancel_btn:
                return False

        # D3b：is_new 语义 = filepath is None（读 Document）
        is_new_now = shared_doc.filepath is None
        if is_new_now:
            self._release_untitled_number(title)
        else:
            filepath = shared_doc.filepath
            if filepath and os.path.isfile(filepath):
                self._record_closed_tab(filepath, widget)

        self._save_manager.unregister_tab(tab_id)
        self._close_md_preview(widget)
        self.removeTab(index)
        self.tab_count_changed.emit(self.count())
        # Batch 4：最后一个 View 关闭 → document.closed（未命名文档不触发）
        if shared_doc.filepath:
            self.document_closed.emit(shared_doc.filepath)
        # 3.5.8（批次 4c）：最后一个 View 关闭 → 销毁 Document
        # 批次 5 修复：最后 View 关闭前断开 Document 依赖，防高亮悬垂
        self._detach_shared_from_widget(widget)
        self._document_registry.release(shared_doc.document_id)
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

        # D3b：路径/is_new 读 Document（is_new 语义 = filepath is None）
        shared_doc = getattr(widget, "shared_doc", None)
        if shared_doc is None:
            return
        filepath = shared_doc.filepath
        is_new = filepath is None

        if not filepath or is_new:
            self._context_save_as(index)
            return

        old_name = os.path.basename(filepath)
        new_name, ok = QInputDialog.getText(self, "重命名", "新文件名:", text=old_name)

        if ok and new_name and new_name != old_name:
            new_path = os.path.join(os.path.dirname(filepath), new_name)
            # 3.5.8（修复）：目标路径已被其它已打开 Document 占用 → 拒绝（与移动 /
            # Save As 同规则，避免两个 Document 指向同一路径的非法形态）。
            if self._document_registry.is_path_owned_by_other(
                    shared_doc.document_id, new_path):
                QMessageBox.warning(
                    self, "无法重命名",
                    f"目标文件已在其他面板打开，不能重命名到同一路径：\n{new_path}",
                )
                return
            if os.path.exists(new_path):
                msg = QMessageBox.question(
                    self, "文件已存在",
                    f"目标文件夹中已存在 '{new_name}'，是否覆盖？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if msg != QMessageBox.StandardButton.Yes:
                    return
            try:
                os.rename(filepath, new_path)
                editor = self._get_editor_from_widget(widget)
                # 3.5.8（修复）：共享 Document 由 registry re-key + bind_path 广播
                # pathChanged / nameChanged——所有面板 View 的路径/标题/预览基准
                # 随 Document 同步（否则其它面板仍持旧路径，保存会写回旧文件）。
                self._document_registry.move_path(shared_doc, new_path)
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
        # 3.5.8（批次 5，规格 2.6）：Document dirty/name/path 信号改由
        # DocumentViewBinding 按 View 粒度接入（_connect_doc_binding）——
        # 不再面板级 UniqueConnection，避免 open→close 循环后残留连接。

    def _disconnect_editor_signals(self, editor):
        """解除编辑器与本面板的信号绑定（跨面板迁移前调用，3.5.7）。

        标签拖到另一面板时，编辑器 widget 被 reparent，但 textChanged 等信号
        仍指向源面板的槽；源面板已注销该 tab，脏标记/标题更新全部失效。
        """
        try:
            editor.textChanged.disconnect(self._on_text_changed)
        except (TypeError, RuntimeError):
            pass
        try:
            editor.cursorPositionChanged.disconnect(self._on_cursor_position_changed)
        except (TypeError, RuntimeError):
            pass
        if is_enabled("signal_driven_stats"):
            try:
                editor.word_count_recomputed.disconnect(self._on_word_count_recomputed)
            except (TypeError, RuntimeError):
                pass

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

        shared_doc = getattr(editor, "shared_doc", None)
        if shared_doc is None:
            return

        doc = editor.document()
        if doc is None:
            return
        current_len = doc.characterCount() - 1
        # D3a：字数增量统计在 Document 级（内容共享，跨 View 连续输入 delta 正确）
        last_len = shared_doc.last_text_length or current_len
        delta = current_len - last_len
        shared_doc.last_text_length = current_len

        is_pasting = getattr(editor, '_is_pasting', False)
        is_programmatic = getattr(editor, 'is_programmatic_modify', False)

        if delta > 0 and not is_pasting and not is_programmatic:
            if delta <= self._PASTE_THRESHOLD:
                self.chars_typed.emit(delta)

        if is_enabled("signal_driven_stats"):
            editor.invalidate_word_count()

        self.content_modified.emit()

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
            # D3b：路径读 Document（is_new 语义 = filepath is None）
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is not None and shared_doc.filepath:
                paths.append(shared_doc.filepath)
        return paths

    def get_open_dirty_filepaths(self) -> list:
        """返回「打开且未保存」的文件路径列表（不含未保存的新文件）。

        供批量磁盘操作（如旧 assets 迁移）排除：这类文档磁盘内容不是真相，
        重写磁盘后编辑器内存里的旧引用一旦保存就会断链。
        """
        paths = []
        for i in range(self.count()):
            widget = self.widget(i)
            if widget is None:
                continue
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is not None and shared_doc.filepath and shared_doc.dirty:
                paths.append(shared_doc.filepath)
        return paths

    def get_current_encoding(self) -> str:
        """获取当前文件的编码"""
        widget = self.currentWidget()
        if widget:
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is not None:
                return str(shared_doc.encoding)
        return "UTF-8"

    def get_current_eol(self) -> str:
        """获取当前文档的行尾类型（LF / CRLF / CR / Mixed）"""
        widget = self.currentWidget()
        if widget:
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is not None:
                return str(shared_doc.eol)
        return "LF"

    def set_current_eol(self, eol: str) -> None:
        """切换当前文档的行尾类型（可撤销，1.8）。

        D3b：eol 写 Document（Document 级语义，多 View 一致）。行尾变更不产生
        Qt 撤销步，故由 Document 记账（可撤销 + 置脏）；标签 ` *` 标记经
        dirtyChanged → _on_view_dirty 自动跟随，无需在此手动改标题。
        """
        widget = self.currentWidget()
        if not widget or not hasattr(widget, 'tab_id'):
            return
        shared_doc = getattr(widget, "shared_doc", None)
        if shared_doc is None:
            return
        shared_doc.record_eol_change(eol)

    def get_unsaved_tab_infos(self) -> List[Dict]:
        """返回本面板未保存标签的结构化信息（3.5.7 关闭确认用）。

        跳过空未命名标签，返回
        `{"title": str, "filepath": Optional[str], "document_id": Optional[str]}` 列表，
        供「未保存文件确认对话框」展示。document_id 供多面板聚合时去重
        （共享 Document 在主面板与分屏各有一个 View，退出确认应只列一次）。
        """
        infos: List[Dict[str, Optional[str]]] = []
        seen_docs = set()
        for i in range(self.count()):
            widget = self.widget(i)
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is None:
                continue
            # D3a：dirty 单一源 = SharedDocument（其它 View 编辑置脏时本 View
            # 旧状态不维护，直接以 Document 为准）；同一共享 Document 在本面板
            # 只列一次（跨面板去重由调用方按 document_id 做）
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is None:
                continue
            doc_id = shared_doc.document_id
            is_modified = shared_doc.dirty
            if doc_id is not None:
                if doc_id in seen_docs:
                    continue
                seen_docs.add(doc_id)
            if not is_modified:
                continue
            editor = self._get_editor_from_widget(widget)
            content = editor.toPlainText() if editor else ""
            # D3b：is_new 语义 = filepath is None（读 Document）
            is_new = shared_doc.filepath is None
            filepath = shared_doc.filepath
            if is_new and len(content.strip()) == 0:
                continue
            if filepath:
                infos.append({
                    "title": os.path.basename(filepath),
                    "filepath": filepath,
                    "document_id": doc_id,
                })
            else:
                infos.append({
                    "title": self._strip_tab_suffix(self.tabText(i)),
                    "filepath": None,
                    "document_id": doc_id,
                })
        return infos

    def has_modified_files(self) -> bool:
        """是否有未保存修改（D3a：dirty 单一源 = SharedDocument.dirty，逐 widget 查询）。

        3.5.8（R2）：其它面板的 View 编辑也会置脏，同 Document 去重后按 dirty 判定。
        """
        seen_docs = set()
        for i in range(self.count()):
            widget = self.widget(i)
            shared = getattr(widget, "shared_doc", None)
            if shared is not None and shared.document_id not in seen_docs:
                seen_docs.add(shared.document_id)
                if shared.dirty:
                    return True
        return False

    def get_open_files_info(self) -> List[Dict]:
        """导出为 workspace.json 的 open_files 条目（D3c：经 D2 适配层导出）。

        View 位置状态单一源 = widget.view_state：先实时捕获 cursor/scroll
        写入 view_state，再经 workspace_entries 纯函数导出（named / untitled
        逐键等价现 schema）；未命名 dirty 内容即时从 Document 读取。
        """
        entries: List[Dict] = []
        for i in range(self.count()):
            widget = self.widget(i)
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is None:
                continue
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is None:
                continue
            # 共享 Document：View 位置实时捕获写入 view_state
            editor = self._get_editor_from_widget(widget)
            if editor is not None:
                cursor = editor.textCursor().position()
                vbar = editor.verticalScrollBar()
                scroll = vbar.value() if vbar is not None else 0
                view_state = getattr(widget, "view_state", None)
                if view_state is not None:
                    view_state.cursor_position = cursor
                    view_state.scroll_position = scroll
            if shared_doc.filepath is None:
                # 未命名条目：dirty 时携带即时内容（恢复编辑现场）
                content = shared_doc.to_plain_text() if shared_doc.dirty else None
                entries.append(workspace_entries.untitled_entry(
                    shared_doc.display_name, shared_doc.untitled_number, content))
            else:
                if editor is None:
                    continue
                cursor = editor.textCursor().position()
                vbar = editor.verticalScrollBar()
                entries.append(workspace_entries.named_entry(
                    shared_doc.filepath, cursor,
                    vbar.value() if vbar is not None else 0))
        return entries

    # === 文档状态公开接口（替代 MainWindow 的私有穿透） ===

    def set_tab_content(self, tab_id: int, content: str) -> bool:
        """将内容恢复到指定标签的编辑器，并重置保存状态。

        供崩溃恢复使用（restore_after_crash）。
        3.5.8（批次 4e）：共享 Document → Document 级 set_content，所有 View 同步。
        """
        editor = self._editor_for_tab_id(tab_id)
        if editor is None:
            return False
        shared_doc = editor.shared_doc
        if shared_doc is None:
            return False
        # D3a：set_content 已复位 Document 级保存统计（last_saved_*）
        shared_doc.set_content(content)
        return True

    def mark_tab_dirty(self, tab_id: int) -> None:
        """将指定标签标记为已修改（供崩溃恢复后的脏标记）。

        D3a：dirty 单一源 = SharedDocument——qdocument.setModified(True)
        驱动 dirtyChanged → 各 View 标题与保存状态机同步。
        """
        self._save_manager.mark_dirty(tab_id)
        editor = self._editor_for_tab_id(tab_id)
        if editor is not None and editor.shared_doc is not None:
            editor.shared_doc.qdocument.setModified(True)

    def get_failed_filenames(self, failed_tab_ids: List[int]) -> List[str]:
        """根据失败的 tab_id 列表返回文件名（供关闭流程提示）。

        D3c：tab_id → widget → Document 的 display_name
        （未命名用 display_name，具名用 basename）。
        """
        names: List[str] = []
        for tab_id in failed_tab_ids:
            widget = self._widget_for_tab_id(tab_id)
            if widget is None:
                continue
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is None:
                continue
            if shared_doc.filepath:
                names.append(os.path.basename(shared_doc.filepath))
            else:
                names.append(shared_doc.display_name)
        return names

    def _widget_for_tab_id(self, tab_id: int):
        for i in range(self.count()):
            widget = self.widget(i)
            if getattr(widget, 'tab_id', None) == tab_id:
                return widget
        return None

    def _editor_for_tab_id(self, tab_id: int) -> Optional[Editor]:
        for i in range(self.count()):
            widget = self.widget(i)
            if getattr(widget, 'tab_id', None) == tab_id:
                return self._get_editor_from_widget(widget)
        return None

    def set_wrap_mode_all(self, mode: str):
        for editor in self._iter_editors():
            editor.set_wrap_mode(mode)

    def set_preview_wrap_mode_all(self, mode: str):
        """把「预览行宽」设置广播到所有 Markdown 预览（与编辑区行宽互不影响）。"""
        for i in range(self.count()):
            widget = self.widget(i)
            if isinstance(widget, MarkdownPreviewWidget):
                widget.set_preview_wrap_mode(mode)

    def toggle_md_preview(self):
        """切换当前MD标签的预览"""
        widget = self.currentWidget()
        if isinstance(widget, MarkdownPreviewWidget):
            widget.toggle_preview()

    def refresh_md_preview(self):
        """强制刷新本面板全部标签的 Markdown 预览（「视图 → 刷新预览」）。

        全局刷新语义：遍历本面板所有 Markdown 预览标签逐个渲染（大文件模式下
        占位页随真实内容渲染复位）。本面板没有预览标签时安全 no-op；跨面板
        （主面板 + 各分屏）的遍历由 ViewCoordinator 负责。
        """
        for i in range(self.count()):
            widget = self.widget(i)
            if isinstance(widget, MarkdownPreviewWidget):
                widget.refresh_preview_now()

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

    def set_code_font_all(self, family: str):
        """对所有已打开编辑器应用「代码字体」（编辑器侧改 Markdown 高亮器的
        代码 format；预览侧见 refresh_preview_typography_all）。
        """
        for editor in self._iter_editors():
            editor.set_code_font(family)

    def set_line_spacing_all(self, spacing: float):
        """对所有已打开编辑器应用「正文行距」。

        编辑器内正文与代码块不区分（同一文本流按块设行距，切分代码块代价高），
        代码块行距只作用于预览与导出，见 refresh_preview_typography_all。
        """
        for editor in self._iter_editors():
            editor.set_line_spacing(spacing)

    def refresh_preview_typography_all(self):
        """刷新所有 Markdown 预览的排版 CSS（代码字体 / 正文行距 / 代码块行距）。

        这三项只存在于 CSS：已加载的预览就地更新变量，未加载的由首屏整页灌入。
        三者共用一次刷新，避免设置应用时重复整页重建。
        """
        for i in range(self.count()):
            widget = self.widget(i)
            if isinstance(widget, MarkdownPreviewWidget):
                widget.refresh_typography_settings()

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

    def undo(self) -> bool:
        """撤销。行尾切换属文档级元数据（不在 Qt 撤销栈内），可撤销判定须一并看它。"""
        editor = self.current_editor()
        if editor is None:
            return False
        shared_doc = editor.shared_doc
        eol_pending = shared_doc is not None and shared_doc.has_pending_eol_undo()
        doc = editor.document()
        if eol_pending or (doc is not None and doc.isUndoAvailable()):
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

    # === 插入图片代理 ===

    def insert_image_from_file(self):
        """插入图片：委托当前编辑器写入 PanzerNote_assets/ 并插入相对路径。"""
        editor = self.current_editor()
        if editor:
            editor.insert_image_from_file()

    # === 图片恢复代理（E6c2） ===

    def recover_missing_images(self) -> bool:
        """恢复当前文档断链的图片。

        流程：预检（ledger 线索 + 可证明范围独占判定）→ 对话框确认 → 执行。
        执行沿用迁移服务的 `copy → verify → delete` 保底，失败不丢源文件。
        """
        widget = self.currentWidget()
        if widget is None:
            return False
        shared_doc = getattr(widget, "shared_doc", None)
        filepath = shared_doc.filepath if shared_doc is not None else None
        editor = self._get_editor_from_widget(widget)
        if editor is None or not filepath or not self._is_markdown_file(filepath):
            QMessageBox.information(
                self, "恢复缺失的图片", "仅已保存的 Markdown 文档支持图片恢复。"
            )
            return False

        # 预检读编辑器当前内容：保存是异步的，刚插入的引用此刻可能还没落盘
        if shared_doc is not None and shared_doc.dirty:
            self._save_file(widget, filepath, shared_doc.encoding)
            if not self._await_save_settled(shared_doc):
                QMessageBox.warning(self, "无法恢复", "文档正在保存，请稍后再试。")
                return False

        service = AssetRecoveryService(self.config)
        try:
            plan = service.plan(filepath, editor.toPlainText())
        except Exception as exc:  # noqa: BLE001
            get_logger(__name__).warning("图片恢复预检失败: %s", exc)
            return False
        if not plan.items:
            QMessageBox.information(
                self, "恢复缺失的图片", "当前文档没有缺失的图片资源。"
            )
            return False

        dialog = AssetRecoveryDialog(plan, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        try:
            result = service.apply(plan)
        except Exception as exc:  # noqa: BLE001
            get_logger(__name__).error("图片恢复执行失败: %s", exc)
            return False

        # 汇总仍缺失的项：本就判为需人工 + 执行时失败 / 目标被占用的
        remaining = len(plan.needs_user) + result.failed + result.skipped
        self.asset_recovery_finished.emit(
            filepath, result.moved, result.copied, remaining
        )
        return True

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

    # === Markdown 编辑代理（阶段 2：任务列表 / 表格） ===

    def toggle_task_checkbox(self):
        editor = self.current_editor()
        if editor:
            editor.toggle_task_checkbox()

    def table_insert_row_above(self):
        editor = self.current_editor()
        if editor:
            editor.table_insert_row_above()

    def table_insert_row_below(self):
        editor = self.current_editor()
        if editor:
            editor.table_insert_row_below()

    def table_delete_row(self):
        editor = self.current_editor()
        if editor:
            editor.table_delete_row()

    def table_insert_column_left(self):
        editor = self.current_editor()
        if editor:
            editor.table_insert_column_left()

    def table_insert_column_right(self):
        editor = self.current_editor()
        if editor:
            editor.table_insert_column_right()

    def table_delete_column(self):
        editor = self.current_editor()
        if editor:
            editor.table_delete_column()

    def table_format_align(self):
        editor = self.current_editor()
        if editor:
            editor.table_format_align()

    def table_align_left(self):
        editor = self.current_editor()
        if editor:
            editor.table_align_left()

    def table_align_center(self):
        editor = self.current_editor()
        if editor:
            editor.table_align_center()

    def table_align_right(self):
        editor = self.current_editor()
        if editor:
            editor.table_align_right()

    # === 行内格式 / 标题代理（阶段 2 G2/G5） ===

    def format_bold(self):
        editor = self.current_editor()
        if editor:
            editor.format_bold()

    def format_italic(self):
        editor = self.current_editor()
        if editor:
            editor.format_italic()

    def format_inline_code(self):
        editor = self.current_editor()
        if editor:
            editor.format_inline_code()

    def format_link(self):
        editor = self.current_editor()
        if editor:
            editor.format_link()

    def set_heading_level(self, level: int):
        editor = self.current_editor()
        if editor:
            editor.set_heading_level(level)

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
            # D3b：路径读 Document
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is None or not shared_doc.filepath:
                continue
            editor = self._get_editor_from_widget(widget)
            if editor is not None:
                bookmarks = editor.get_bookmarks()
                self.config.set_bookmarks(shared_doc.filepath, list(bookmarks) if bookmarks else [])

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
            # D3b：路径读 Document
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is None or not shared_doc.filepath:
                continue
            editor = self._get_editor_from_widget(widget)
            if editor is not None and hasattr(editor, '_folding'):
                collapsed = editor._folding.get_collapsed_lines()
                self.config.set_folds(shared_doc.filepath, collapsed if collapsed else [])
