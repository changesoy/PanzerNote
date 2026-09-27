# -*- coding: utf-8 -*-
"""EditorTabWidget 文件操作 mixin（从 editor_tabs.py 拆出，纯结构重构不改行为）。

职责：文档文本读取与解码辅助、图片资产迁移粘合（预检 / 执行 / 引用重写 /
冲突提示）、保存落定等待，以及文件树联动操作（移动 / 复制到文件夹、
删除关闭、重命名同步）。

组合契约：本 mixin 由 EditorTabWidget 组合。方法体访问的跨职责状态与
方法在 ``_EditorTabWidgetContract`` 中仅作类型声明——运行时全部由
EditorTabWidget（含 TabSaveFlowMixin 提供的 _save_file）实际提供，
本模块不初始化任何状态。
"""
from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

from PyQt6.QtCore import QEventLoop, QTimer, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QTabWidget

from ..core.shared_document import SaveStatus
from ..security.file_access_context import FileAccessContext
from ..utils.error_handler import ErrorHandler, ErrorCategory
from ..utils.logger import get_logger
from .asset_migration_service import (
    MODE_COPY,
    MODE_MOVE,
    AssetMigrationPlan,
    AssetMigrationService,
)
from .file_open_service import decode_document_bytes
from .image_reference_scanner import rewrite_local_refs

if TYPE_CHECKING:
    from ..core.config import Config
    from ..core.document_registry import DocumentRegistry
    from .editor import Editor
    from .save_task_manager import SaveTaskManager
    from .temp_session_manager import TempSessionManager


class _EditorTabWidgetContract(QTabWidget):
    """EditorTabWidget 组合 TabFileOpsMixin 时必须提供的状态与方法。

    继承 QTabWidget 仅为补齐 mixin 方法体用到的 Qt 基类能力与
    pyqtSignal descriptor 的类型约束；运行时不实例化、不初始化任何状态。
    """

    config: Config
    _document_registry: DocumentRegistry
    _save_manager: SaveTaskManager
    _session_manager: TempSessionManager

    tab_count_changed: pyqtSignal

    def _strip_tab_suffix(self, title: str) -> str:
        raise NotImplementedError

    def _release_untitled_number(self, title: str) -> None: ...
    def _record_closed_tab(self, filepath: str, widget) -> None: ...
    def _close_md_preview(self, widget) -> None: ...
    def _detach_shared_from_widget(self, widget) -> None: ...
    def _disconnect_doc_binding(self, widget) -> None: ...
    def _get_editor_from_widget(self, widget) -> Optional[Editor]: ...
    def _is_markdown_file(self, filepath: str) -> bool:
        raise NotImplementedError

    # 注意：_save_file 的实现由 TabSaveFlowMixin 提供。此处只能用「裸类型注解」
    # 声明——不能写成带 raise 体/空体的 def，否则本契约类在 MRO 中先于
    # TabSaveFlowMixin，会把真实现遮蔽成 NotImplementedError（E3 实测踩坑）。
    _save_file: Callable[..., Tuple[bool, int]]


class TabFileOpsMixin(_EditorTabWidgetContract):
    """文件操作职责：资产迁移粘合 + 文件树联动（移动/复制/删除/重命名）。"""

    def _document_text(self, filepath: str) -> Optional[str]:
        """已打开文档的**编辑器当前内容**（未打开返回 None，回落到磁盘）。

        预检必须看到用户眼里的内容：保存是异步的，刚插入的引用此刻可能还没落盘。
        """
        for i in range(self.count()):
            widget = self.widget(i)
            w_doc = getattr(widget, "shared_doc", None)
            if w_doc is None or w_doc.filepath != filepath:
                continue
            editor = self._get_editor_from_widget(widget)
            if editor is None:
                return None
            return editor.toPlainText()
        return None

    def _plan_asset_migration(
        self, source_md: str, dest_md: str, mode: str
    ) -> Optional[AssetMigrationPlan]:
        """E6c1a：资源迁移预检；服务不可用时返回 None（不阻断文档移动本身）。"""
        if not self._is_markdown_file(source_md):
            return None
        try:
            return AssetMigrationService(self.config).plan(
                source_md, dest_md, mode,
                markdown_text=self._document_text(source_md),
            )
        except Exception as exc:  # noqa: BLE001
            get_logger(__name__).warning("图片资源迁移预检失败，按不迁移处理: %s", exc)
            return None

    def _apply_asset_migration(self, plan: Optional[AssetMigrationPlan]) -> None:
        """执行资源迁移：`copy → verify → delete`；失败只记日志，源文件不丢。

        迁移失败的引用会变成断链，由 E6b 的缺失检测在下次打开 / 基准变化时提示。
        """
        if plan is None or not plan.ok or not plan.items:
            return
        try:
            result = AssetMigrationService(self.config).apply(plan)
        except Exception as exc:  # noqa: BLE001
            get_logger(__name__).error("图片资源迁移执行失败: %s", exc)
            return
        if result.failed:
            get_logger(__name__).warning(
                "有 %d 个图片资源未能迁移（源文件保留）", len(result.failed)
            )

    @staticmethod
    def _decode_document_bytes(
        raw: bytes, encoding: Optional[str]
    ) -> Optional[Tuple[str, str]]:
        """解码文档字节：优先已知编码，未知时按打开文档的同一顺序兜底。

        实现下沉到 file_open_service.decode_document_bytes（供跨文件搜索
        等调用方共享同一口径）。
        """
        return decode_document_bytes(raw, encoding)

    def _rewrite_asset_refs(
        self,
        plan: Optional[AssetMigrationPlan],
        doc_path: str,
        encoding: Optional[str] = None,
        *,
        shared_doc=None,
    ) -> None:
        """冲突改名后，把这一篇文档里的引用改写到新文件名（E6c1b2）。

        只动 `doc_path` 这一篇：Move = 已搬到目标的 `.md`，Copy / Save As = 新写出的
        副本，源文档逐字不动。读写走字节级（解码 → 只替换目标串区间 → 原编码写回），
        BOM / 行尾 / 未改动内容都逐字节保留。
        """
        renames = plan.renames() if plan is not None else {}
        if not renames:
            return
        if shared_doc is not None and shared_doc.dirty:
            # 缓冲区与磁盘不一致（保存未落地）：改写任何一侧都可能丢用户改动。
            # 交给 E6b 缺失检测兜底，不在这里赌。
            get_logger(__name__).warning(
                "文档尚有未保存改动，跳过图片引用改写: %s", doc_path
            )
            return

        guard = self.config.get_file_guard()
        try:
            raw = guard.safe_read_bytes(
                doc_path, context=FileAccessContext.USER_DOCUMENT_READ
            )
        except Exception as exc:  # noqa: BLE001
            get_logger(__name__).warning("读取文档以改写图片引用失败: %s", exc)
            return

        decoded = self._decode_document_bytes(raw, encoding)
        if decoded is None:
            get_logger(__name__).warning("文档编码无法识别，跳过图片引用改写: %s", doc_path)
            return
        text, used_encoding = decoded

        updated, count = rewrite_local_refs(
            text, os.path.dirname(os.path.abspath(doc_path)), renames
        )
        if not count:
            return

        try:
            guard.safe_write_bytes(
                doc_path,
                updated.encode(used_encoding),
                context=FileAccessContext.USER_DOCUMENT_SAVE,
            )
        except Exception as exc:  # noqa: BLE001
            get_logger(__name__).warning("改写文档图片引用失败: %s", exc)
            return

        if shared_doc is not None:
            # 缓冲区必须与磁盘一致，否则标签里的引用仍是旧文件名（D21）。
            # 编辑器内部一律用 LF 表示，故按 LF 归一化后回写 Document。
            from .eol_utils import normalize_eol
            shared_doc.set_content(normalize_eol(updated, "\n"))

    def _warn_asset_conflict(self, title: str, conflicts: List[str]) -> None:
        shown = "、".join(os.path.basename(path) for path in conflicts[:5])
        more = f" 等 {len(conflicts)} 个" if len(conflicts) > 5 else ""
        QMessageBox.warning(
            self, title,
            "目标目录已有同名但内容不同的图片，本次未做任何改动：\n\n"
            f"{shown}{more}\n\n请先处理同名文件后重试。",
        )

    @staticmethod
    def _is_same_folder(filepath: str, dest_folder: str) -> bool:
        """目标文件夹是否就是文件自身所在目录（拖到自身目录 = 原地不动）。"""
        return os.path.normcase(os.path.abspath(dest_folder)) == os.path.normcase(
            os.path.abspath(os.path.dirname(filepath))
        )

    def _await_save_settled(self, shared_doc, timeout_ms: int = 5000) -> bool:
        """等待该 Document 的在途保存落地；返回是否已无在途保存。

        移动 / 复制前必须等：在途保存任务持有的是**旧路径**，文件被移走后它会把
        旧路径重新写出来（幽灵文件 + 新旧位置内容错位）。判定用 Document 级保存
        状态，可一并覆盖分屏中另一面板正在保存同一文档的情形。
        """
        if shared_doc is None or shared_doc.save_status != SaveStatus.SAVING:
            return True

        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)

        def _check(_state: str) -> None:
            if shared_doc.save_status != SaveStatus.SAVING:
                loop.quit()

        shared_doc.saveStateChanged.connect(_check)
        timer.start(timeout_ms)
        try:
            if shared_doc.save_status == SaveStatus.SAVING:
                loop.exec()
        finally:
            timer.stop()
            try:
                shared_doc.saveStateChanged.disconnect(_check)
            except TypeError:
                pass
        return bool(shared_doc.save_status != SaveStatus.SAVING)

    def move_file_to_folder(self, filepath: str, dest_folder: str) -> bool:
        """将文件移动到目标文件夹，更新对应标签页（含图片资源迁移）"""
        if not os.path.isfile(filepath) or not os.path.isdir(dest_folder):
            return False
        # 目标是文件自己所在的文件夹：原地不动。否则会弹「文件已存在，是否覆盖？」
        # 这种自问自答；copy_file_to_folder 更会走到 shutil 的 SameFileError。
        if self._is_same_folder(filepath, dest_folder):
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

        # 资源预检放在「先保存」之后、`.md` 落位之前：预检读的是磁盘内容，
        # 若文档有未保存的改动，必须先落盘才能看到最新引用；冲突则整体中止。
        migration: Optional[AssetMigrationPlan] = None
        try:
            # 先保存再移动（3.5.8 R2：共享 Document 以 Document 侧 dirty 为准）
            shared_doc = None
            for i in range(self.count()):
                widget = self.widget(i)
                # D3b：路径读 Document
                w_doc = getattr(widget, "shared_doc", None)
                if w_doc is not None and w_doc.filepath == filepath:
                    shared_doc = w_doc
                    # D3a：dirty 单一源 = SharedDocument
                    if shared_doc.dirty:
                        self._save_file(widget, filepath, shared_doc.encoding)
                    break

            # 在途保存落地前不得移动文件：保存任务持有旧路径，移动后会把旧路径
            # 重新写出来（幽灵文件 + 新旧位置内容错位）。
            if not self._await_save_settled(shared_doc):
                QMessageBox.warning(self, "无法移动", "文档正在保存，请稍后再试。")
                return False

            # 3.5.8：共享 Document 移动前检查目标路径未被其它 Document 占用
            # （否则移动后两个 Document 指向同一路径，编辑/保存错乱）
            if (shared_doc is not None
                    and self._document_registry.is_path_owned_by_other(
                        shared_doc.document_id, new_path)):
                QMessageBox.warning(
                    self, "无法移动",
                    f"目标文件已在其他面板打开，不能移动：\n{new_path}",
                )
                return False

            migration = self._plan_asset_migration(filepath, new_path, MODE_MOVE)
            if migration is not None and not migration.ok:
                self._warn_asset_conflict("无法移动", migration.conflicts)
                return False

            shutil.move(filepath, new_path)

            # 更新标签页信息（3.5.8：共享 Document 由 registry re-key + bind_path
            # 广播 pathChanged/nameChanged，所有 View 的路径/标题随 Document 同步）
            for i in range(self.count()):
                widget = self.widget(i)
                # D3b：路径读 Document
                w_doc = getattr(widget, "shared_doc", None)
                if w_doc is not None and w_doc.filepath == filepath:
                    self._document_registry.move_path(w_doc, new_path)
                    break

            # .md 已落位后再迁移资源：迁移本身有 copy → verify 保底（源不丢），
            # 万一失败只是新文档断链，不会让原笔记丢图。
            self._apply_asset_migration(migration)
            # 目标同名冲突已改名 → 改写这份文档的引用，并同步编辑器缓冲区
            self._rewrite_asset_refs(
                migration,
                new_path,
                shared_doc.encoding if shared_doc is not None else None,
                shared_doc=shared_doc,
            )
            return True
        except Exception as e:
            get_logger(__name__).error("移动文件失败: %s", e)
            ErrorHandler.show_from_exception(e, ErrorCategory.FILE, "移动文件失败")
            return False

    def copy_file_to_folder(self, filepath: str, dest_folder: str) -> bool:
        """将文件复制到目标文件夹（标签已打开且已修改则先保存再复制，不改动原标签）"""
        if not os.path.isfile(filepath) or not os.path.isdir(dest_folder):
            return False
        # 复制到文件自己所在的文件夹没有意义，且 shutil.copy2 会抛 SameFileError。
        if self._is_same_folder(filepath, dest_folder):
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

        # 资源预检放在「先保存」之后、副本落位之前：预检读磁盘内容，
        # 未保存的改动必须先落盘才能被看到；冲突则整体中止。
        migration: Optional[AssetMigrationPlan] = None
        try:
            # 若标签打开且已修改，先保存再复制，保证副本包含最新内容
            shared_doc = None
            for i in range(self.count()):
                widget = self.widget(i)
                # D3b：路径读 Document
                w_doc = getattr(widget, "shared_doc", None)
                if w_doc is not None and w_doc.filepath == filepath:
                    shared_doc = w_doc
                    if w_doc.dirty:
                        self._save_file(widget, filepath, w_doc.encoding)
                    break

            # 在途保存落地前不得复制：保存任务持有旧路径，源文件内容随后才更新，
            # 副本会拿到保存前的旧内容。
            if not self._await_save_settled(shared_doc):
                QMessageBox.warning(self, "无法复制", "文档正在保存，请稍后再试。")
                return False

            migration = self._plan_asset_migration(filepath, new_path, MODE_COPY)
            if migration is not None and not migration.ok:
                self._warn_asset_conflict("无法复制", migration.conflicts)
                return False

            shutil.copy2(filepath, new_path)
            # 副本已落位后再迁移资源；Copy 语义下源文档仍引用同一张图，
            # 独占判定因此天然得出 COPY（不会把源笔记的图搬走）。
            self._apply_asset_migration(migration)
            # 目标同名冲突已改名 → 只改写这份副本，源文档与打开的标签都不动
            self._rewrite_asset_refs(
                migration,
                new_path,
                shared_doc.encoding if shared_doc is not None else None,
            )
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
        图片标签没有 Document，按 `image_path` 匹配后同样关闭（否则会留一个
        指向已不存在文件的空白/报错标签）。
        """
        norm = os.path.normpath(path)
        indices = []
        for i in range(self.count()):
            widget = self.widget(i)
            image_path = getattr(widget, "image_path", None)
            if image_path:
                matched = os.path.normpath(image_path) == norm or (
                    is_dir and os.path.normpath(image_path).startswith(norm + os.sep)
                )
                if matched:
                    indices.append(i)
                continue
            # D3b：路径读 Document
            w_doc = getattr(widget, "shared_doc", None)
            if w_doc is None or not w_doc.filepath:
                continue
            fp = os.path.normpath(w_doc.filepath)
            if is_dir:
                matched = fp.startswith(norm + os.sep)
            else:
                matched = fp == norm
            if matched:
                indices.append(i)

        # 从后往前关闭，避免索引随 removeTab 偏移
        for i in reversed(indices):
            self._close_deleted_tab(i)

    def update_tabs_of_renamed_path(self, old: str, new: str) -> None:
        """文件树重命名后，同步更新图片标签持有的路径、标题与显示内容。

        只处理图片标签：文档标签的路径由 Document 持有，改名走保存/另存为链路。
        """
        from .image_viewer import ImageViewerWidget

        old_norm = os.path.normpath(old)
        for i in range(self.count()):
            widget = self.widget(i)
            if not isinstance(widget, ImageViewerWidget):
                continue
            image_path = widget.image_path
            if not image_path or os.path.normpath(image_path) != old_norm:
                continue
            widget.reload_to(new)
            self.setTabText(i, os.path.basename(new))
            self.setTabToolTip(i, os.path.abspath(new))

    def _close_deleted_tab(self, index: int) -> None:
        """关闭单个标签（文件已被删除，不提供"保存"选项）。"""
        widget = self.widget(index)
        tab_id = getattr(widget, 'tab_id', None) if widget else None

        if tab_id is None:
            self.removeTab(index)
            self.tab_count_changed.emit(self.count())
            return

        shared_doc = getattr(widget, "shared_doc", None)
        if shared_doc is None:
            self.removeTab(index)
            self.tab_count_changed.emit(self.count())
            return

        # 3.5.8（批次 4c，规格 2.3）：共享 Document 还有其他 View → 直接关本 View
        # （删除语义下同样不弹确认，Document 仍由其它 View 持有）
        doc_id = shared_doc.document_id
        if self._document_registry.view_count(doc_id) > 1:
            self._document_registry.detach_view(doc_id, widget)
            self._detach_shared_from_widget(widget)
            self._disconnect_doc_binding(widget)
            self._save_manager.unregister_tab(tab_id)
            self.removeTab(index)
            self.tab_count_changed.emit(self.count())
            return

        # 3.5.8（D3a）：dirty 单一源 = SharedDocument（同 _close_tab）
        is_modified = shared_doc.dirty
        if is_modified:
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

        # D3b：is_new 语义 = filepath is None（读 Document）
        is_new = shared_doc.filepath is None
        if is_new:
            title = self._strip_tab_suffix(self.tabText(index))
            self._release_untitled_number(title)
        else:
            filepath = shared_doc.filepath
            if filepath and os.path.isfile(filepath):
                self._record_closed_tab(filepath, widget)

        # D3b：autosave 清理路径读 Document
        if shared_doc.filepath:
            self._session_manager.remove_autosave_for_file(shared_doc.filepath)

        self._save_manager.unregister_tab(tab_id)
        self._close_md_preview(widget)
        self.removeTab(index)
        self.tab_count_changed.emit(self.count())
        # 3.5.8（批次 4c）：最后一个 View 关闭（删除语义）→ 销毁 Document
        # 批次 5 修复：最后 View 关闭前断开 Document 依赖，防高亮悬垂
        self._detach_shared_from_widget(widget)
        self._document_registry.release(shared_doc.document_id)

    # === 编辑操作代理 ===
