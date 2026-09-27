# -*- coding: utf-8 -*-
"""EditorTabWidget 保存流 mixin（从 editor_tabs.py 拆出，纯结构重构不改行为）。

职责：保存 / 另存为（含 PDF / HTML 导出）/ 批量保存 / 暂存清理，以及
SaveTaskManager 保存状态机回调（CLEAN / SAVING / SAVE_FAILED 的标签标题、
pending 副作用结算、保存后关闭）。

组合契约：本 mixin 由 EditorTabWidget 组合（MRO 首位）。方法体访问的
跨职责状态与方法在 ``_EditorTabWidgetContract`` 中仅作类型声明——运行时
全部由 EditorTabWidget.__init__ / 类体实际提供，本模块不初始化任何状态。
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QDialog, QMessageBox, QTabWidget

from ..utils.error_handler import ErrorHandler, ErrorCategory
from ..themes.theme_v2.consumer import v2_export_colors
from .asset_migration_service import MODE_COPY
from .editor import Editor
from .markdown_preview import MarkdownPreviewWidget
from .save_task_manager import SaveState
from .tab_dialogs import SaveAsDialog

if TYPE_CHECKING:
    from ..core.config import Config
    from ..core.document_registry import DocumentRegistry
    from ..themes.theme_engine import ThemeEngine
    from .asset_migration_service import AssetMigrationPlan
    from .save_task_manager import SaveTaskManager
    from .temp_session_manager import TempSessionManager


class _EditorTabWidgetContract(QTabWidget):
    """EditorTabWidget 组合 TabSaveFlowMixin 时必须提供的状态与方法。

    继承 QTabWidget 仅为补齐 mixin 方法体用到的 Qt 基类能力
    （count / widget / setTabText 等）与 pyqtSignal descriptor 的类型约束；
    运行时不实例化、不初始化任何状态。属性由 EditorTabWidget.__init__
    创建；列出的方法当前留在主类（后续批次再迁）。本声明即保存流对
    组合类的最小依赖面。
    """

    config: Config
    _theme_engine: ThemeEngine
    _panel_name: str
    _document_registry: DocumentRegistry
    _save_manager: SaveTaskManager
    _session_manager: TempSessionManager
    _pending_close_tab_ids: Set[int]
    _pending_save_info: Dict[int, Dict]
    _pending_save_as_info: Dict[int, Dict]
    _used_untitled_numbers: Set[int]

    file_saved: pyqtSignal
    tab_count_changed: pyqtSignal
    chars_typed: pyqtSignal

    def _strip_tab_suffix(self, title: str) -> str:
        raise NotImplementedError

    def _release_untitled_number(self, title: str) -> None: ...
    def _record_closed_tab(self, filepath: str, widget) -> None: ...
    def _close_md_preview(self, widget) -> None: ...
    def _detach_shared_from_widget(self, widget) -> None: ...
    def _get_editor_from_widget(self, widget) -> Optional[Editor]: ...
    def _update_tab_tooltip(self, index: int) -> None: ...
    def _plan_asset_migration(
        self, source_md: str, dest_md: str, mode: str
    ) -> Optional[AssetMigrationPlan]: ...
    def _apply_asset_migration(self, plan: Optional[AssetMigrationPlan]) -> None: ...
    def _rewrite_asset_refs(
        self, plan: Optional[AssetMigrationPlan], doc_path: str,
        encoding: Optional[str] = None,
    ) -> None: ...
    def _warn_asset_conflict(self, title: str, conflicts: List[str]) -> None: ...


class TabSaveFlowMixin(_EditorTabWidgetContract):
    """保存流职责：保存 / 另存为 / 导出 / 批量保存 / 状态机回调。"""

    def save_current(self) -> Tuple[bool, int]:
        """保存当前文件"""
        widget = self.currentWidget()
        if not widget or not hasattr(widget, 'tab_id'):
            return False, 0

        # D3b：路径/编码读 Document（is_new 语义 = filepath is None）
        shared_doc = getattr(widget, "shared_doc", None)
        filepath = shared_doc.filepath if shared_doc is not None else None
        if not filepath:
            return self.save_current_as()
        encoding = shared_doc.encoding if shared_doc is not None else "UTF-8"
        return self._save_file(widget, filepath, encoding)

    def save_current_as(self) -> Tuple[bool, int]:
        """另存为"""
        widget = self.currentWidget()
        if not widget:
            return False, 0

        tid = getattr(widget, 'tab_id', None)
        if tid is None:
            return False, 0
        shared_doc = getattr(widget, "shared_doc", None)

        # D3b：路径/编码读 Document（is_new 语义 = filepath is None）
        if shared_doc is not None and shared_doc.filepath:
            suggested_name = shared_doc.filepath
        else:
            suggested_name = os.path.join(
                self.config.get_notebooks_path(),
                self._strip_tab_suffix(self.tabText(self.currentIndex()))
            )

        current_encoding = shared_doc.encoding if shared_doc is not None else "UTF-8"

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

        # 3.5.8（批次 4d，规格 2.2）：另存为的目标路径已被其它已打开 Document
        # 占用（含副本写向其它面板已打开文件的路径）→ 拒绝，避免两个 Document
        # 指向同一路径。reserve 占位 pending，成功/失败回调负责 commit / cancel。
        shared_doc = getattr(widget, "shared_doc", None)
        if shared_doc is not None:
            if not self._document_registry.reserve_path(shared_doc.document_id, filepath):
                QMessageBox.warning(
                    self,
                    "另存为",
                    f"该文件已在其他面板打开，不能另存为到同一路径：\n{filepath}",
                )
                return False, 0

        # D3b：is_new 语义 = filepath is None；编号/副本判定读 Document
        is_new = shared_doc is None or shared_doc.filepath is None

        # 副本另存为：副本引用的图片资源要一并落到目标目录（COPY 语义）。
        # 预检放在写盘之前——此时 .md 尚未落位，冲突仍可整体中止；
        # Copy 语义不排除源文档，因此源笔记的图不会被搬走。
        migration: Optional[AssetMigrationPlan] = None
        if not is_new and shared_doc is not None and shared_doc.filepath:
            migration = self._plan_asset_migration(shared_doc.filepath, filepath, MODE_COPY)
            if migration is not None and not migration.ok:
                self._warn_asset_conflict("另存为", migration.conflicts)
                self._document_registry.cancel_reservation(
                    shared_doc.document_id, filepath
                )
                return False, 0

        success, chars = self._save_file(
            widget, filepath, encoding, is_copy=not is_new
        )

        if success:
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is not None:
                self._pending_save_as_info[tab_id] = {
                    "filepath": filepath,
                    "encoding": encoding,
                    "untitled_number": (shared_doc.untitled_number if shared_doc is not None else None)
                                       if is_new else None,
                    # 已有文件另存为 = 副本保存：当前标签保持指向原文件
                    "is_copy": not is_new,
                    # 副本落盘成功后才执行（CLEAN 回调），失败不迁移
                    "migration": migration,
                }

        return success, chars

    def save_untitled_to_folder(self, tab_id: int, dest_folder: str) -> Tuple[bool, int]:
        """3.5.11：把未命名标签直接落盘保存到目标文件夹（拖到文件树触发）。

        复用通用保存链路：_save_file + _pending_save_as_info → CLEAN 回调自动完成
        编号释放 / 标题更新（与 save_current_as 一致）。
        同名冲突弹框确认（默认不覆盖）；空内容也直接落盘（行为统一）。
        """
        widget = None
        for i in range(self.count()):
            w = self.widget(i)
            if getattr(w, 'tab_id', None) == tab_id:
                widget = w
                break
        if widget is None:
            return False, 0

        # D3b：is_new 语义 = filepath is None；display_name/编号/编码读 Document
        shared_doc = getattr(widget, "shared_doc", None)
        if shared_doc is None or shared_doc.filepath is not None:
            return False, 0

        filename = shared_doc.display_name or f"未命名{shared_doc.untitled_number or 1}.txt"
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

        success, chars = self._save_file(widget, filepath, shared_doc.encoding)
        if success:
            self._pending_save_as_info[tab_id] = {
                "filepath": filepath,
                "encoding": shared_doc.encoding,
                "untitled_number": shared_doc.untitled_number,
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
                v2_export_colors(self._theme_engine),
                theme_engine=self._theme_engine,
                code_font=self.config.get_code_font_family(),
                line_spacing=self.config.get_line_spacing(),
                code_line_spacing=self.config.get_code_line_spacing(),
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
            body_html = ExportService.render_content(content, is_md, self._theme_engine)
            full_html = build_export_html_document(
                body_html,
                v2_export_colors(self._theme_engine),
                code_font=self.config.get_code_font_family(),
                line_spacing=self.config.get_line_spacing(),
                code_line_spacing=self.config.get_code_line_spacing(),
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

        # 3.5.8（R3 接线）：共享 Document 的保存任务按 document_key 合并——
        # 同一 Document 多个 View 同时保存时只允许一个实际写盘任务，避免
        # 并发写同一文件；未共享时 document_key=None，保持原 tab 级行为。
        shared_doc = getattr(widget, "shared_doc", None)
        document_key = shared_doc.document_id if shared_doc is not None else None

        # 3.5.8（跨面板并发写盘防护）：document_key 合并仅在本面板的
        # SaveTaskManager 内有效（各面板 Manager 相互独立），无法阻止主面板与
        # 分屏并发保存同一共享文件。safe_write 已原子化（临时文件 + os.replace，
        # 文件不会字节交错损坏），但并发时旧快照可能最后落盘覆盖新内容；且
        # Document 级 dirty/保存状态需要单一权威。这里以 Document 级保存状态机
        # （SAVING/IDLE/FAILED）作为跨面板唯一门闩——同一 Document 全局同时
        # 最多一个实际写盘任务，最新内容必然最后落盘。
        # 仅限「写回当前绑定路径」的正常保存；副本另存为 / 未命名首次保存
        # （目标路径尚未绑定）不参与，避免误拦跨路径保存。
        gated = (shared_doc is not None and not is_copy
                 and shared_doc.filepath is not None and filepath == shared_doc.filepath)

        if self._save_manager.is_saving(tab_id):
            # 3.5.8 单槽合并：保存中再次保存请求 → 仅置 pending，不并发写盘
            self._save_manager.request_resave(tab_id, document_key=document_key)
            if gated:
                # 同面板保存中再次请求 → 置 Document 级 pending，由
                # _on_shared_save_finished 统一兜底补保存
                assert shared_doc is not None  # gated 蕴含 shared_doc 非空
                shared_doc.pending_save = True
            return False, 0

        snapshot = None
        if gated:
            assert shared_doc is not None  # gated 蕴含 shared_doc 非空
            snapshot = shared_doc.request_save()
            if snapshot is None:
                # 另一面板正在保存同一 Document：内容共享，本次请求已并入（已置
                # pending_save，保存完成后若内容已变会自动补保存）→ 视为已受理。
                return True, 0

        if shared_doc is None:
            return False, 0
        # D3a：保存统计在 Document 级（内容共享，统计按 Document 维护）
        last_chars = shared_doc.last_saved_chars

        # EOL 规范化：将编辑器内部的 \n 替换为文档目标行尾
        # D3b：eol 读 Document（Document 级语义，切换全局生效）
        current_eol_label = shared_doc.eol
        target_eol = {"LF": "\n", "CRLF": "\r\n", "CR": "\r"}.get(current_eol_label, "\n")
        from .eol_utils import normalize_eol
        content = normalize_eol(content, target_eol)

        new_chars = max(0, len(content) - last_chars)

        if not is_copy:
            # D3b：编码写 Document
            shared_doc.encoding = encoding

        self._pending_save_info[tab_id] = {
            "content": content,
            "new_chars": new_chars,
        }

        from PyQt6.QtCore import QThreadPool
        from .save_task import SaveTask

        task = SaveTask(self.config.get_file_guard(), filepath, content, encoding.lower())
        # 3.5.8：提交时附带内容快照 + 当前内容提供者，保存成功按「当前 == 快照」判定
        # dirty（保存期间继续编辑不误清）；on_resave 用于单槽合并补保存。
        self._save_manager.submit_task(
            tab_id, task,
            snapshot=content,
            provider=lambda: self._current_normalized_content(widget, target_eol),
            on_resave=lambda: self._on_resave_requested(tab_id),
            document_key=document_key,
        )
        if gated:
            # Document 级保存门闩释放：直接连接任务完成信号（在面板 Manager
            # 回调之后触发，连接顺序保证）——即使标签已注销、面板级回调提前
            # 返回，门闩也会释放，避免 Document 卡死 SAVING 使后续保存被永久合并。
            task.signals.finished.connect(
                lambda success, fp, exc, sd=shared_doc, snap=snapshot, tid=tab_id:
                    self._on_shared_save_finished(sd, snap, tid, success)
            )
        pool = QThreadPool.globalInstance()
        if pool is not None:
            pool.start(task)

        return True, 0

    @staticmethod
    def _current_normalized_content(widget, target_eol: str) -> str:
        """当前编辑器内容（按目标 EOL 规范化），用于保存成功时的 snapshot 判定。"""
        if isinstance(widget, MarkdownPreviewWidget):
            raw = widget.editor.toPlainText()
        elif isinstance(widget, Editor):
            raw = widget.toPlainText()
        else:
            return ""
        from .eol_utils import normalize_eol
        return normalize_eol(raw, target_eol)

    def _on_resave_requested(self, tab_id: int) -> None:
        """单槽合并补保存：保存成功但内容已变且保存期间有 pending 请求。

        以最新内容重新提交一次保存；未命名首次保存（filepath 尚为空）期间
        编辑的场景跳过——此时对话框流程尚未完成，下次 Ctrl+S 正常覆盖。
        """
        for i in range(self.count()):
            widget = self.widget(i)
            if getattr(widget, 'tab_id', None) != tab_id:
                continue
            # D3b：路径/编码读 Document
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is not None and shared_doc.filepath:
                self._save_file(widget, shared_doc.filepath, shared_doc.encoding)
            return

    def _on_shared_save_finished(self, shared_doc, snapshot, tab_id: int,
                                 success: bool) -> None:
        """共享 Document 保存完成回调（3.5.8 跨面板保存门闩释放）。

        直接连接 SaveTask.signals.finished（在面板 SaveTaskManager 回调之后
        触发，连接顺序保证，此时面板状态已恢复 idle）：
        - 成功：on_save_succeeded 按「当前内容 == 快照」判定 Document dirty；
          返回 True（保存期间编辑 + pending 请求）→ 以最新内容补保存一次。
        - 失败：on_save_failed → FAILED、保持 dirty，由用户重新触发。
        """
        if success:
            if shared_doc.on_save_succeeded(snapshot):
                self._on_resave_requested(tab_id)
        else:
            shared_doc.on_save_failed()

    def save_all(self) -> int:
        total_chars = 0
        unnamed_indices = []

        for i in range(self.count()):
            widget = self.widget(i)
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is None:
                continue
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is None:
                continue
            # D3a：dirty 单一源 = SharedDocument
            if not shared_doc.dirty:
                continue
            # D3b：路径读 Document（is_new 语义 = filepath is None）
            if shared_doc.filepath:
                success, chars = self._save_file(widget, shared_doc.filepath, shared_doc.encoding)
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

    def save_all_for_close(self) -> bool:
        """保存本面板所有 dirty 标签以关闭（3.5.7）。

        与 save_all 的区别：任一未命名「另存为」被取消或保存提交失败 → 返回
        False（调用方应中止关闭）；已保存文件走异步 `_save_file`，其最终成败由
        SaveTaskManager 的 `all_tasks_finished` / `get_failed_tab_ids` 兜底。
        与 get_unsaved_tab_infos 语义一致：空未命名不弹另存为。
        """
        unnamed_indices = []
        for i in range(self.count()):
            widget = self.widget(i)
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is None:
                continue
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is None:
                continue
            # D3a：dirty 单一源 = SharedDocument
            if not shared_doc.dirty:
                continue
            # D3b：路径/编码读 Document（is_new 语义 = filepath is None）
            if shared_doc.filepath:
                success, _ = self._save_file(widget, shared_doc.filepath, shared_doc.encoding)
                if not success:
                    return False
            else:
                editor = self._get_editor_from_widget(widget)
                content = editor.toPlainText() if editor else ""
                # 空未命名跳过（与 get_unsaved_tab_infos 一致，关闭确认框未列出）
                is_unnamed = shared_doc.filepath is None
                if is_unnamed and len(content.strip()) == 0:
                    continue
                unnamed_indices.append(i)

        for i in unnamed_indices:
            self.setCurrentIndex(i)
            success, _ = self.save_current_as()
            if not success:
                return False

        return True

    def save_all_to_temp(self):
        """保存所有 dirty 文件到暂存目录（通过 TempSessionManager 管理）

        创建者：MainWindow（最小化/自动保存/关闭时调用）
        持有者：TempSessionManager
        完成通知：同步完成，无异步回调
        失败通知：日志记录，不中断流程
        关闭时行为：由 mark_cleanly_closed / cleanup_session 管理
        """
        tab_infos = []
        seen_doc_keys = set()
        for i in range(self.count()):
            widget = self.widget(i)
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is None:
                continue

            # D3a：dirty 单一源 = SharedDocument
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is None or not shared_doc.dirty:
                continue

            if isinstance(widget, MarkdownPreviewWidget):
                content = widget.editor.toPlainText()
            elif isinstance(widget, Editor):
                content = widget.toPlainText()
            else:
                continue

            # 3.5.8（批次 4e）：同一 Document 多个 View 只写一份 autosave——
            # doc_key 稳定（document_id），用于文件名与去重（规格 3.2）
            doc_key = shared_doc.document_id
            if doc_key in seen_doc_keys:
                continue
            seen_doc_keys.add(doc_key)

            tab_infos.append({
                "tab_id": tab_id,
                # D3b：filepath/is_new/encoding 读 Document
                "filepath": shared_doc.filepath,
                "content": content,
                "encoding": shared_doc.encoding,
                "is_new": shared_doc.filepath is None,
                "is_modified": True,
                "doc_key": doc_key,
                "panel": self._panel_name,
            })

        if tab_infos:
            self._session_manager.save_dirty_files(tab_infos)

    def clear_temp_files(self):
        """标记正常关闭并清理暂存文件"""
        self._session_manager.mark_cleanly_closed()
        self._session_manager.cleanup_session()
        self._session_manager.cleanup_all_clean_sessions()


    def _on_save_state_changed(self, tab_id: int, state_name: str) -> None:
        save_state = SaveState(state_name)
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
            save_as_info = self._pending_save_as_info.pop(tab_id, None)
            # D3b：路径 authority 在 Document——取本 View 的共享 Document
            shared_doc = getattr(widget, "shared_doc", None)
            if shared_doc is None:
                return
            if save_as_info and save_as_info.get("is_copy"):
                # 已有文件另存为副本：保存成功，但当前标签仍指向原文件。
                # 跳过全部保存副作用（不清 dirty、不改标题、不结算收益），
                # 避免原文件未保存的修改被误标记为已保存（数据安全）。
                self._pending_save_info.pop(tab_id, None)
                # 3.5.8（批次 4d）：副本路径不属当前 Document → 释放 pending 预留
                self._document_registry.cancel_reservation(
                    shared_doc.document_id, save_as_info["filepath"]
                )
                # 副本已落盘 → 迁移其引用的图片资源（COPY，源笔记的图不动）
                self._apply_asset_migration(save_as_info.get("migration"))
                # 目标同名冲突已改名 → 只改写这份副本（标签仍指向原文件，不动缓冲区）
                self._rewrite_asset_refs(
                    save_as_info.get("migration"),
                    save_as_info["filepath"],
                    save_as_info.get("encoding"),
                )
                # 恢复标题（去除 SAVING 阶段追加的 ⏳ 后缀）
                self.setTabText(index, base_title)
                if tab_id in self._pending_close_tab_ids:
                    self._pending_close_tab_ids.discard(tab_id)
                    self._close_tab_after_save(widget_index)
                return
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
                # D3a：保存统计迁移至 Document 级（on_save_succeeded 同语义）
                shared_doc.last_saved_chars = len(content)
                shared_doc.last_text_length = len(content)
                if new_chars > 0:
                    self.chars_typed.emit(new_chars)

            if save_as_info:
                # 新建文件首次保存：正式化为该文件
                # D3b：Document 由 commit_path + bind_path 正式化
                # （filepath/display_name/encoding 均在 Document）。
                filepath_new = save_as_info["filepath"]
                if save_as_info.get("untitled_number"):
                    self._used_untitled_numbers.discard(save_as_info["untitled_number"])
                if editor:
                    editor.set_file_type(filepath_new)
                self.setTabText(index, os.path.basename(filepath_new))
                # 3.5.8（批次 4d）：pending → path_index，Document 正式绑定新路径
                # （nameChanged/pathChanged 驱动所有 View 标题同步）
                self._document_registry.commit_path(shared_doc, filepath_new)

            # D3b：autosave 清理路径读 Document
            if shared_doc.filepath:
                self._session_manager.remove_autosave_for_file(shared_doc.filepath)
            self._update_tab_tooltip(index)
            self.file_saved.emit()
            if tab_id in self._pending_close_tab_ids:
                self._pending_close_tab_ids.discard(tab_id)
                self._close_tab_after_save(widget_index)
        elif save_state == SaveState.SAVING:
            self.setTabText(index, base_title + " ⏳")
        elif save_state == SaveState.SAVE_FAILED:
            save_as_info = self._pending_save_as_info.pop(tab_id, None)
            # 3.5.8（批次 4d）：另存为失败 → 释放路径预留（副本与非副本一致）
            if save_as_info:
                shared_doc = getattr(widget, "shared_doc", None)
                if shared_doc is not None:
                    self._document_registry.cancel_reservation(
                        shared_doc.document_id, save_as_info["filepath"]
                    )
            if save_as_info and save_as_info.get("is_copy"):
                # 副本保存失败：当前标签状态不变（原文件未受影响），恢复标题
                self._pending_save_info.pop(tab_id, None)
                self.setTabText(index, base_title)
                return
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
            # D3a：Document 已是 dirty（由 qdocument.setModified 驱动），无附加动作
            pass

    @staticmethod
    def _on_save_failed(tab_id: int, filepath: str, exc: BaseException) -> None:
        basename = os.path.basename(filepath) if filepath else "未知文件"
        ErrorHandler.show_from_exception(exc, ErrorCategory.FILE, f"保存文件失败：{basename}")

    def _close_tab_after_save(self, index: int) -> None:
        widget = self.widget(index)
        if not widget or not hasattr(widget, 'tab_id'):
            return

        tab_id = widget.tab_id
        title = self._strip_tab_suffix(self.tabText(index))

        # D3b：is_new 语义 = filepath is None（读 Document）
        shared_doc = getattr(widget, "shared_doc", None)
        if shared_doc is None:
            return
        is_new = shared_doc.filepath is None
        if is_new:
            self._release_untitled_number(title)
        else:
            filepath = shared_doc.filepath
            if filepath and os.path.isfile(filepath):
                self._record_closed_tab(filepath, widget)

        self._save_manager.unregister_tab(tab_id)
        self._close_md_preview(widget)
        self.removeTab(index)
        self.tab_count_changed.emit(self.count())
        # 3.5.8（批次 4c）：保存后关闭的最后 View → 销毁 Document
        doc_id = shared_doc.document_id
        if self._document_registry.view_count(doc_id) <= 1:
            # 批次 5 修复：最后 View 关闭前断开 Document 依赖，防高亮悬垂
            self._detach_shared_from_widget(widget)
            self._document_registry.release(doc_id)
