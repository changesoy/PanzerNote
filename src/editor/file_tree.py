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
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTreeView, QLabel, QMenu,
    QAction, QInputDialog, QMessageBox, QFileSystemModel,
    QHeaderView, QFrame, QScrollArea, QStyledItemDelegate
)
from PyQt5.QtCore import Qt, pyqtSignal, QDir, QModelIndex, QSortFilterProxyModel
from PyQt5.QtGui import QFont

from ..core.config import Config
from ..utils.logger import get_logger
from ..utils.error_handler import ErrorHandler, ErrorCategory
from ..security.input_validator import InputValidator, FilenameValidationError
from ..themes.theme_aware_mixin import ThemeAwareMixin


MIME_TAB_FILEPATH = "application/x-panzernote-tab-filepath"


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
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.filepath)
        super().mousePressEvent(event)


class DroppableTreeView(QTreeView):

    file_move_requested = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_TAB_FILEPATH):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(MIME_TAB_FILEPATH):
            index = self.indexAt(event.pos())
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
        if event.mimeData().hasFormat(MIME_TAB_FILEPATH):
            data = event.mimeData().data(MIME_TAB_FILEPATH)
            src_filepath = bytes(data).decode('utf-8')

            index = self.indexAt(event.pos())
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

            if dest_folder and src_filepath:
                if os.path.dirname(os.path.abspath(src_filepath)) != os.path.abspath(dest_folder):
                    self.file_move_requested.emit(src_filepath, dest_folder)

            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class FileTreeWidget(ThemeAwareMixin, QWidget):

    file_open_requested = pyqtSignal(str)
    file_move_requested = pyqtSignal(str, str)

    def __init__(self, config: Config, theme_engine=None, parent=None):
        super().__init__(parent)
        self.config = config
        self._init_ui()
        if theme_engine:
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
        title_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
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

        self.tree_view = DroppableTreeView()
        self.tree_view.setModel(self.model)
        self.tree_view.setRootIndex(self.model.index(notebooks_path))
        self.tree_view.file_move_requested.connect(self._on_file_move_requested)

        self.tree_view.setHeaderHidden(True)
        self.tree_view.hideColumn(1)
        self.tree_view.hideColumn(2)
        self.tree_view.hideColumn(3)

        self.tree_view.setDragEnabled(True)
        self.tree_view.setAcceptDrops(True)
        self.tree_view.setDropIndicatorShown(True)

        self.tree_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self._show_context_menu)
        self.tree_view.doubleClicked.connect(self._on_double_click)

        layout.addWidget(self.tree_view, 1)

        self.external_container = QWidget()
        external_layout = QVBoxLayout(self.external_container)
        external_layout.setContentsMargins(0, 0, 0, 0)
        external_layout.setSpacing(0)

        self.external_separator = QFrame()
        self.external_separator.setFrameShape(QFrame.HLine)
        self.external_separator.setFrameShadow(QFrame.Sunken)
        external_layout.addWidget(self.external_separator)

        self.external_title = QLabel("📂 外部文件")
        self.external_title.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        external_layout.addWidget(self.external_title)

        self.external_list = QWidget()
        self.external_list_layout = QVBoxLayout(self.external_list)
        self.external_list_layout.setContentsMargins(0, 5, 0, 5)
        self.external_list_layout.setSpacing(2)
        external_layout.addWidget(self.external_list)

        self.external_container.hide()
        layout.addWidget(self.external_container)

    def _apply_theme_colors(self, colors):
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {colors.sidebar_bg};
            }}
        """)
        self._title_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {colors.surface};
                border-bottom: 1px solid {colors.border};
            }}
        """)
        self.tree_view.setStyleSheet(f"""
            QTreeView {{
                border: none;
                background-color: {colors.sidebar_bg};
            }}
            QTreeView::item {{
                padding: 5px;
            }}
            QTreeView::item:hover {{
                background-color: {colors.primary_light};
            }}
            QTreeView::item:selected {{
                background-color: {colors.editor_selection};
                color: {colors.text_primary};
            }}
        """)
        self.external_title.setStyleSheet(f"""
            QLabel {{
                padding: 8px 10px;
                background-color: {colors.surface};
                border-bottom: 1px solid {colors.border};
                color: {colors.text_primary};
            }}
        """)
        self.external_list.setStyleSheet(f"background-color: {colors.sidebar_bg};")

    def _on_file_move_requested(self, src_filepath: str, dest_folder: str):
        self.file_move_requested.emit(src_filepath, dest_folder)

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

        menu.exec_(self.tree_view.viewport().mapToGlobal(position))

    def _on_double_click(self, index: QModelIndex):
        if not self.model.isDir(index):
            filepath = self.model.filePath(index)
            self.file_open_requested.emit(filepath)

    def _add_external_file(self):
        from PyQt5.QtWidgets import QFileDialog
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
                file_guard.safe_write(filepath, "", validate_path=False)
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
        msg_box.setIcon(QMessageBox.Question)

        yes_btn = msg_box.addButton("确定", QMessageBox.AcceptRole)
        no_btn = msg_box.addButton("取消", QMessageBox.RejectRole)

        msg_box.exec_()

        if msg_box.clickedButton() == yes_btn:
            try:
                try:
                    from send2trash import send2trash
                    send2trash(filepath)
                except ImportError:
                    if is_dir:
                        import shutil
                        shutil.rmtree(filepath)
                    else:
                        os.remove(filepath)
            except Exception as e:
                get_logger(__name__).error("删除失败: %s", e)
                ErrorHandler.show_from_exception(e, ErrorCategory.FILE, "删除失败")

    def refresh_external_files(self):
        external_files = self.config.get_external_files()

        while self.external_list_layout.count():
            item = self.external_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        valid_files = [f for f in external_files if os.path.exists(f)]

        if valid_files:
            self.external_container.show()

            for filepath in valid_files:
                label = ExternalFileLabel(filepath)
                label.clicked.connect(self.file_open_requested.emit)
                self.external_list_layout.addWidget(label)
        else:
            self.external_container.hide()
