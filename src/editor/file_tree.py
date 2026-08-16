# -*- coding: utf-8 -*-
"""
文件树组件
显示笔记库文件结构和外部文件

v1.5.4 改动：
  - 支持接受标签拖拽：将文件移动到文件树中的目标文件夹
v1.6.4 改动：
  - 主题感知：订阅 theme_changed 信号
"""

import os
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeView, QLabel, QMenu,
    QInputDialog, QMessageBox,
    QHeaderView, QFrame, QScrollArea, QStyledItemDelegate, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal, QDir, QModelIndex, QMimeData, QSortFilterProxyModel, QTimer
from PyQt6.QtGui import QFont, QAction, QFileSystemModel

from ..core.config import Config
from ..utils.logger import get_logger
from ..utils.error_handler import ErrorHandler, ErrorCategory
from ..security.input_validator import InputValidator, FilenameValidationError
from ..themes.theme_aware_mixin import ThemeAwareMixin
from ..themes.theme_v2.consumer import v2_token


MIME_TAB_FILEPATH = "application/x-panzernote-tab-filepath"
# 3.5.11：与 editor_tabs.py 同值；未命名标签（无 filepath）落盘保存时定位源标签
MIME_TAB_ID = "application/x-panzernote-tab-id"


class AlwaysExpandableModel(QFileSystemModel):

    def hasChildren(self, parent=QModelIndex()):
        if not parent.isValid():
            return True
        if self.isDir(parent):
            return True
        return False


class ExternalFileLabel(QLabel):

    clicked = pyqtSignal(str)

    def __init__(self, filepath: str, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        filename = os.path.basename(filepath)
        self.setText(f"  📄 {filename}")
        self.setToolTip(filepath)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.filepath)
        super().mousePressEvent(event)


class DroppableTreeView(QTreeView):

    file_move_requested = pyqtSignal(str, str)
    file_copy_requested = pyqtSignal(str, str)
    # 3.5.11：(source_tabs, tab_id, dest_folder) 未命名标签落盘保存
    untitled_save_requested = pyqtSignal(object, int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        # B6（8.1 拖拽视觉）：显示拖拽落点指示线（颜色由全局 tree_item
        # recipe 的 drop_indicator 控制）
        self.setDropIndicatorShown(True)

    def _ask_move_or_copy(self, filename: str, dest_folder: str) -> Optional[str]:
        """询问用户移动还是复制文件。返回 "move" / "copy" / None（取消）。"""
        box = QMessageBox(self)
        box.setWindowTitle("移动或复制")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"将「{filename}」放入文件夹：\n{os.path.basename(dest_folder)}")
        box.setInformativeText("请选择要执行的操作。")
        move_btn = box.addButton("移动", QMessageBox.ButtonRole.AcceptRole)
        copy_btn = box.addButton("复制", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(move_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is move_btn:
            return "move"
        if clicked is copy_btn:
            return "copy"
        return None

    def _handle_saved_tab_drop(self, src_filepath: str, dest_folder: str):
        """拖放结束后（异步）询问移动/复制并发出对应请求。"""
        action = self._ask_move_or_copy(os.path.basename(src_filepath), dest_folder)
        if action == "move":
            self.file_move_requested.emit(src_filepath, dest_folder)
        elif action == "copy":
            self.file_copy_requested.emit(src_filepath, dest_folder)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.indexAt(event.pos())
            if not index.isValid():
                sel_model = self.selectionModel()
                if sel_model is not None and sel_model.hasSelection():
                    sel_model.clearSelection()
                self.setCurrentIndex(QModelIndex())
        super().mousePressEvent(event)

    def _is_tab_drag(self, mime: QMimeData) -> bool:
        """标签拖拽：已保存文件（MIME_TAB_FILEPATH）或未命名标签（MIME_TAB_ID）。"""
        return mime.hasFormat(MIME_TAB_FILEPATH) or mime.hasFormat(MIME_TAB_ID)

    def dragEnterEvent(self, event):
        if self._is_tab_drag(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._is_tab_drag(event.mimeData()):
            # PyQt6 拖拽事件没有 pos()（仅 position() 返回 QPointF）
            index = self.indexAt(event.position().toPoint())
            model = self.model()
            if index.isValid() and model:
                if isinstance(model, QFileSystemModel) and model.isDir(index):
                    event.acceptProposedAction()
                    return
                parent_idx = index.parent()
                if parent_idx.isValid():
                    event.acceptProposedAction()
                    return
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if self._is_tab_drag(event.mimeData()):
            data = event.mimeData().data(MIME_TAB_FILEPATH)
            src_filepath = bytes(data).decode('utf-8')
            # 3.5.11：未命名标签无 filepath，通过 tab_id 定位源标签
            tab_id = None
            tab_id_data = event.mimeData().data(MIME_TAB_ID)
            if tab_id_data and not tab_id_data.isEmpty():
                try:
                    tab_id = int(bytes(tab_id_data).decode('utf-8'))
                except (ValueError, UnicodeDecodeError):
                    tab_id = None

            index = self.indexAt(event.position().toPoint())
            model = self.model()
            dest_folder = None

            if index.isValid() and model and isinstance(model, QFileSystemModel):
                if model.isDir(index):
                    dest_folder = model.filePath(index)
                else:
                    parent_idx = index.parent()
                    if parent_idx.isValid():
                        dest_folder = model.filePath(parent_idx)
                    else:
                        dest_folder = model.rootPath()
            else:
                if model and isinstance(model, QFileSystemModel):
                    dest_folder = model.rootPath()

            if dest_folder:
                if src_filepath:
                    if os.path.dirname(os.path.abspath(src_filepath)) != os.path.abspath(dest_folder):
                        # 先完成拖放事件，再异步弹窗询问：
                        # 模态对话框不能嵌套在（Windows 原生）拖拽事件循环内。
                        QTimer.singleShot(
                            0,
                            lambda: self._handle_saved_tab_drop(src_filepath, dest_folder),
                        )
                elif tab_id is not None:
                    # 未命名标签拖到文件树 = 落盘保存（源面板从拖拽发起者父级取）
                    source = event.source()
                    source_tabs = source.parent() if source is not None else None
                    if source_tabs is not None:
                        self.untitled_save_requested.emit(source_tabs, tab_id, dest_folder)

            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class FileTreeWidget(ThemeAwareMixin, QWidget):

    file_open_requested = pyqtSignal(str)
    file_move_requested = pyqtSignal(str, str)
    file_copy_requested = pyqtSignal(str, str)
    # (filepath, is_dir)：删除成功后通知外部同步关闭已打开的标签页
    file_deleted = pyqtSignal(str, bool)
    # 3.5.11：(source_tabs, tab_id, dest_folder) 未命名标签落盘保存
    untitled_save_requested = pyqtSignal(object, int, str)
    # Batch 4：文件树变化（刷新/移动/复制/删除成功后触发）
    tree_changed = pyqtSignal()

    def __init__(self, config: Config, theme_engine, parent=None):
        super().__init__(parent)
        if theme_engine is None:
            raise RuntimeError("FileTreeWidget 必须传入 theme_engine，不允许为 None")
        self.config = config
        self._init_ui()
        self._init_theme(theme_engine)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_frame = QFrame()
        title_layout = QVBoxLayout(title_frame)
        title_layout.setContentsMargins(10, 8, 10, 8)
        self._title_frame = title_frame

        title_label = QLabel("📁 我的笔记")
        title_label.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        title_layout.addWidget(title_label)

        layout.addWidget(title_frame)

        notebooks_path = self.config.get_notebooks_path()
        os.makedirs(notebooks_path, exist_ok=True)

        self.model = AlwaysExpandableModel()
        self.model.setRootPath(notebooks_path)

        self.model.setNameFilters([
            "*.txt", "*.md", "*.py", "*.c", "*.cpp", "*.h", "*.hpp",
            "*.java", "*.js", "*.json", "*.html", "*.css", "*.xml"
        ])
        self.model.setNameFilterDisables(False)

        # QFileSystemModel.readOnly 默认为 True，会导致 dropMimeData 直接返回 False，
        # 树内拖拽（不同子文件夹之间移动/复制）完全无反应。放开只读以启用拖放。
        self.model.setReadOnly(False)

        self.tree_view = DroppableTreeView()
        self.tree_view.setModel(self.model)
        self.tree_view.setRootIndex(self.model.index(notebooks_path))
        self.tree_view.file_move_requested.connect(self._on_file_move_requested)
        self.tree_view.file_copy_requested.connect(self._on_file_copy_requested)
        self.tree_view.untitled_save_requested.connect(self._on_untitled_save_requested)

        self.tree_view.setHeaderHidden(True)
        self.tree_view.hideColumn(1)
        self.tree_view.hideColumn(2)
        self.tree_view.hideColumn(3)

        self.tree_view.setDragEnabled(True)
        self.tree_view.setAcceptDrops(True)
        self.tree_view.setDropIndicatorShown(True)
        # setReadOnly(False) 后文件获得 ItemIsEditable，双击会进入行内重命名；
        # 重命名走右键菜单（QInputDialog），禁用行内编辑避免与双击打开冲突。
        self.tree_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self._show_context_menu)
        self.tree_view.doubleClicked.connect(self._on_double_click)

        layout.addWidget(self.tree_view, 1)

        self.external_container = QWidget()
        external_layout = QVBoxLayout(self.external_container)
        external_layout.setContentsMargins(0, 0, 0, 0)
        external_layout.setSpacing(0)

        self.external_separator = QFrame()
        self.external_separator.setFrameShape(QFrame.Shape.HLine)
        self.external_separator.setFrameShadow(QFrame.Shadow.Sunken)
        external_layout.addWidget(self.external_separator)

        self.external_title = QLabel("📂 外部文件")
        self.external_title.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
        external_layout.addWidget(self.external_title)

        self.external_list = QWidget()
        self.external_list_layout = QVBoxLayout(self.external_list)
        self.external_list_layout.setContentsMargins(0, 5, 0, 5)
        self.external_list_layout.setSpacing(2)
        external_layout.addWidget(self.external_list)

        self.external_container.hide()
        layout.addWidget(self.external_container)

    def _apply_theme_colors(self):
        # B4：文件树消费 v2 token（侧栏 = surface_secondary，标题栏 = surface_primary），
        # 无 v1 回退（B8：字面量 = v1 light 值）
        sidebar_bg = v2_token(self._theme_engine, "surface_secondary", "#FAFAFA")
        surface = v2_token(self._theme_engine, "surface_primary", "#F5F5F5")
        border = v2_token(self._theme_engine, "border_muted", "#E0E0E0")
        text_primary = v2_token(self._theme_engine, "text_primary", "#212121")

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {sidebar_bg};
            }}
        """)
        self._title_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {surface};
                border-bottom: 1px solid {border};
            }}
        """)
        # B4：QTreeView 由全局 tree_item recipe 驱动（v2）/ 全局 v1 QSS（回退），
        # 不再在页面内打补丁（B3 契约 8.1）
        self.external_title.setStyleSheet(f"""
            QLabel {{
                padding: 8px 10px;
                background-color: {surface};
                border-bottom: 1px solid {border};
                color: {text_primary};
            }}
        """)
        self.external_list.setStyleSheet(f"background-color: {sidebar_bg};")

    def _on_file_move_requested(self, src_filepath: str, dest_folder: str):
        self.file_move_requested.emit(src_filepath, dest_folder)

    def _on_file_copy_requested(self, src_filepath: str, dest_folder: str):
        self.file_copy_requested.emit(src_filepath, dest_folder)

    def _on_untitled_save_requested(self, source_tabs, tab_id: int, dest_folder: str):
        self.untitled_save_requested.emit(source_tabs, tab_id, dest_folder)

    def _show_context_menu(self, position):
        index = self.tree_view.indexAt(position)

        menu = QMenu(self)

        if index.isValid():
            filepath = self.model.filePath(index)
            is_dir = self.model.isDir(index)

            if is_dir:
                new_file_action = QAction("新建文件", self)
                new_file_action.triggered.connect(lambda: self._create_new_file(filepath))
                menu.addAction(new_file_action)

                new_folder_action = QAction("新建文件夹", self)
                new_folder_action.triggered.connect(lambda: self._create_new_folder(filepath))
                menu.addAction(new_folder_action)

                menu.addSeparator()
            else:
                open_action = QAction("打开", self)
                open_action.triggered.connect(lambda: self.file_open_requested.emit(filepath))
                menu.addAction(open_action)

                menu.addSeparator()

            rename_action = QAction("重命名", self)
            rename_action.triggered.connect(lambda: self._rename_item(filepath))
            menu.addAction(rename_action)

            delete_action = QAction("删除", self)
            delete_action.triggered.connect(lambda: self._delete_item(filepath, is_dir))
            menu.addAction(delete_action)
        else:
            new_file_action = QAction("新建文件", self)
            new_file_action.triggered.connect(lambda: self._create_new_file(self.config.get_notebooks_path()))
            menu.addAction(new_file_action)

            new_folder_action = QAction("新建文件夹", self)
            new_folder_action.triggered.connect(lambda: self._create_new_folder(self.config.get_notebooks_path()))
            menu.addAction(new_folder_action)

        menu.addSeparator()

        add_external_action = QAction("添加外部文件...", self)
        add_external_action.triggered.connect(self._add_external_file)
        menu.addAction(add_external_action)

        vp = self.tree_view.viewport()
        if vp is not None:
            menu.exec(vp.mapToGlobal(position))

    def _on_double_click(self, index: QModelIndex):
        if not self.model.isDir(index):
            filepath = self.model.filePath(index)
            self.file_open_requested.emit(filepath)

    def _add_external_file(self):
        from PyQt6.QtWidgets import QFileDialog
        filepaths, _ = QFileDialog.getOpenFileNames(
            self, "选择外部文件", "",
            "所有文件 (*);;文本文件 (*.txt *.md *.py *.js *.html *.css *.json *.xml *.yaml *.yml *.toml)"
        )
        for filepath in filepaths:
            if filepath and os.path.isfile(filepath):
                self.config.add_external_file(filepath)
        self.refresh_external_files()

    def _create_new_file(self, parent_dir: str):
        name, ok = QInputDialog.getText(
            self, "新建文件", "文件名:", text="新建文件.txt"
        )
        if ok and name:
            validator = self.config.get_input_validator()
            try:
                name = validator.validate_filename_strict(name)
            except FilenameValidationError as e:
                ErrorHandler.show_from_exception(e, ErrorCategory.FILE, "文件名无效")
                return
            if not name.endswith(('.txt', '.md')):
                name += '.txt'
            filepath = os.path.join(parent_dir, name)
            try:
                file_guard = self.config.get_file_guard()
                file_guard.safe_write(filepath, "")
                self.file_open_requested.emit(filepath)
            except Exception as e:
                get_logger(__name__).error("创建文件失败: %s", e)
                ErrorHandler.show_from_exception(e, ErrorCategory.FILE, "创建文件失败")

    def _create_new_folder(self, parent_dir: str):
        name, ok = QInputDialog.getText(
            self, "新建文件夹", "文件夹名:", text="新建文件夹"
        )
        if ok and name:
            validator = self.config.get_input_validator()
            try:
                name = validator.validate_filename_strict(name)
            except FilenameValidationError as e:
                ErrorHandler.show_from_exception(e, ErrorCategory.FILE, "文件夹名无效")
                return
            folder_path = os.path.join(parent_dir, name)
            try:
                os.makedirs(folder_path, exist_ok=True)
            except Exception as e:
                get_logger(__name__).error("创建文件夹失败: %s", e)
                ErrorHandler.show_from_exception(e, ErrorCategory.FILE, "创建文件夹失败")

    def create_new_folder(self):
        self._create_new_folder(self.config.get_notebooks_path())

    def _rename_item(self, filepath: str):
        old_name = os.path.basename(filepath)
        new_name, ok = QInputDialog.getText(
            self, "重命名", "新名称:", text=old_name
        )
        if ok and new_name and new_name != old_name:
            validator = self.config.get_input_validator()
            try:
                new_name = validator.validate_filename_strict(new_name)
            except FilenameValidationError as e:
                ErrorHandler.show_from_exception(e, ErrorCategory.FILE, "名称无效")
                return
            new_path = os.path.join(os.path.dirname(filepath), new_name)
            try:
                os.rename(filepath, new_path)
            except Exception as e:
                get_logger(__name__).error("重命名失败: %s", e)
                ErrorHandler.show_from_exception(e, ErrorCategory.FILE, "重命名失败")

    def _delete_item(self, filepath: str, is_dir: bool):
        name = os.path.basename(filepath)
        type_str = "文件夹" if is_dir else "文件"

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("确认删除")
        msg_box.setText(f"确定要删除{type_str} '{name}' 吗？")
        msg_box.setIcon(QMessageBox.Icon.Question)

        yes_btn = msg_box.addButton("确定", QMessageBox.ButtonRole.AcceptRole)
        no_btn = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)

        msg_box.exec()

        if msg_box.clickedButton() == yes_btn:
            try:
                try:
                    from send2trash import send2trash
                    # QFileSystemModel 返回正斜杠路径；send2trash 加 \\?\ 前缀后
                    # 混合分隔符会导致 SHFileOperationW 报"找不到文件"，先规范化。
                    send2trash(os.path.normpath(filepath))
                except ImportError:
                    if is_dir:
                        import shutil
                        shutil.rmtree(filepath)
                    else:
                        os.remove(filepath)
            except Exception as e:
                get_logger(__name__).error("删除失败: %s", e)
                ErrorHandler.show_from_exception(e, ErrorCategory.FILE, "删除失败")
            else:
                # 删除成功后再通知外部（同步关闭已打开的标签页）
                self.file_deleted.emit(os.path.normpath(filepath), is_dir)
                # Batch 4：删除成功 → 文件树变化事件
                self.tree_changed.emit()

    def refresh_external_files(self):
        external_files = self.config.get_external_files()

        while self.external_list_layout.count():
            item = self.external_list_layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        valid_files = [f for f in external_files if os.path.exists(f)]

        if valid_files:
            self.external_container.show()

            for filepath in valid_files:
                label = ExternalFileLabel(filepath)
                label.clicked.connect(self.file_open_requested.emit)
                self.external_list_layout.addWidget(label)
        else:
            self.external_container.hide()
        # Batch 4：外部文件列表刷新 → 文件树变化事件
        self.tree_changed.emit()
