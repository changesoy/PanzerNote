# -*- coding: utf-8 -*-
"""
文件树组件
显示笔记库文件结构和外部文件

v1.5.4 改动：
  - 支持接受标签拖拽：将文件移动到文件树中的目标文件夹
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


# 自定义 MIME 类型（与 editor_tabs 保持一致）
MIME_TAB_FILEPATH = "application/x-panzernote-tab-filepath"


class AlwaysExpandableModel(QFileSystemModel):
    """自定义文件系统模型 - 所有文件夹都可展开"""
    
    def hasChildren(self, parent=QModelIndex()):
        """重写：让所有文件夹都显示展开符号"""
        if not parent.isValid():
            return True
        
        # 如果是目录，总是返回True（显示展开符号）
        if self.isDir(parent):
            return True
        
        return False


class ExternalFileLabel(QLabel):
    """外部文件标签"""
    
    clicked = pyqtSignal(str)
    
    def __init__(self, filepath: str, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        filename = os.path.basename(filepath)
        self.setText(f"  📄 {filename}")
        self.setToolTip(filepath)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QLabel {
                padding: 5px 10px;
                border-radius: 3px;
            }
            QLabel:hover {
                background-color: #e3f2fd;
            }
        """)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.filepath)
        super().mousePressEvent(event)


class DroppableTreeView(QTreeView):
    """支持接受标签拖拽的文件树视图"""

    file_move_requested = pyqtSignal(str, str)  # (src_filepath, dest_folder)

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
                # 判断是否为文件夹
                if isinstance(model, QFileSystemModel) and model.isDir(index):
                    event.acceptProposedAction()
                    return
                # 如果拖到文件上，取其父文件夹
                parent_idx = index.parent()
                if parent_idx.isValid():
                    event.acceptProposedAction()
                    return
            # 根目录也接受
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
                # 不移到同一文件夹
                if os.path.dirname(os.path.abspath(src_filepath)) != os.path.abspath(dest_folder):
                    self.file_move_requested.emit(src_filepath, dest_folder)

            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class FileTreeWidget(QWidget):
    """文件树部件"""
    
    file_open_requested = pyqtSignal(str)
    file_move_requested = pyqtSignal(str, str)  # (src, dest_folder) 向上传递
    
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 标题栏
        title_frame = QFrame()
        title_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border-bottom: 1px solid #ddd;
            }
        """)
        title_layout = QVBoxLayout(title_frame)
        title_layout.setContentsMargins(10, 8, 10, 8)
        
        title_label = QLabel("📁 我的笔记")
        title_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        title_layout.addWidget(title_label)
        
        layout.addWidget(title_frame)
        
        # 确保笔记库目录存在
        notebooks_path = self.config.get_notebooks_path()
        os.makedirs(notebooks_path, exist_ok=True)
        
        # 使用自定义文件系统模型（所有文件夹都可展开）
        self.model = AlwaysExpandableModel()
        self.model.setRootPath(notebooks_path)
        
        # 设置过滤器 - 显示所有支持的文件类型
        self.model.setNameFilters([
            "*.txt", "*.md", "*.py", "*.c", "*.cpp", "*.h", "*.hpp",
            "*.java", "*.js", "*.json", "*.html", "*.css", "*.xml"
        ])
        self.model.setNameFilterDisables(False)
        
        # 树视图（使用可接受拖拽的版本）
        self.tree_view = DroppableTreeView()
        self.tree_view.setModel(self.model)
        self.tree_view.setRootIndex(self.model.index(notebooks_path))
        self.tree_view.file_move_requested.connect(self._on_file_move_requested)
        
        # 隐藏除文件名外的其他列
        self.tree_view.setHeaderHidden(True)
        self.tree_view.hideColumn(1)
        self.tree_view.hideColumn(2)
        self.tree_view.hideColumn(3)
        
        # 设置样式
        self.tree_view.setStyleSheet("""
            QTreeView {
                border: none;
                background-color: white;
            }
            QTreeView::item {
                padding: 5px;
            }
            QTreeView::item:hover {
                background-color: #e3f2fd;
            }
            QTreeView::item:selected {
                background-color: #bbdefb;
                color: black;
            }
        """)
        
        # 启用拖放
        self.tree_view.setDragEnabled(True)
        self.tree_view.setAcceptDrops(True)
        self.tree_view.setDropIndicatorShown(True)
        
        # 右键菜单
        self.tree_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self._show_context_menu)
        
        # 双击打开文件
        self.tree_view.doubleClicked.connect(self._on_double_click)
        
        layout.addWidget(self.tree_view, 1)
        
        # 外部文件区域
        self.external_container = QWidget()
        external_layout = QVBoxLayout(self.external_container)
        external_layout.setContentsMargins(0, 0, 0, 0)
        external_layout.setSpacing(0)
        
        # 分隔线
        self.external_separator = QFrame()
        self.external_separator.setFrameShape(QFrame.HLine)
        self.external_separator.setFrameShadow(QFrame.Sunken)
        external_layout.addWidget(self.external_separator)
        
        # 外部文件标题
        self.external_title = QLabel("📂 外部文件")
        self.external_title.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        self.external_title.setStyleSheet("""
            QLabel {
                padding: 8px 10px;
                background-color: #f5f5f5;
                border-bottom: 1px solid #ddd;
            }
        """)
        external_layout.addWidget(self.external_title)
        
        # 外部文件列表
        self.external_list = QWidget()
        self.external_list_layout = QVBoxLayout(self.external_list)
        self.external_list_layout.setContentsMargins(0, 5, 0, 5)
        self.external_list_layout.setSpacing(2)
        self.external_list.setStyleSheet("background-color: white;")
        external_layout.addWidget(self.external_list)
        
        self.external_container.hide()
        layout.addWidget(self.external_container)

    def _on_file_move_requested(self, src_filepath: str, dest_folder: str):
        """文件移动请求，向上传递给 main_window"""
        self.file_move_requested.emit(src_filepath, dest_folder)

    def _show_context_menu(self, position):
        """显示右键菜单"""
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
        
        menu.exec_(self.tree_view.viewport().mapToGlobal(position))
    
    def _on_double_click(self, index: QModelIndex):
        """双击处理"""
        if not self.model.isDir(index):
            filepath = self.model.filePath(index)
            self.file_open_requested.emit(filepath)
    
    def _create_new_file(self, parent_dir: str):
        """创建新文件"""
        name, ok = QInputDialog.getText(
            self, "新建文件", "文件名:", text="新建文件.txt"
        )
        if ok and name:
            if not name.endswith(('.txt', '.md')):
                name += '.txt'
            filepath = os.path.join(parent_dir, name)
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write("")
                self.file_open_requested.emit(filepath)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"创建文件失败：{str(e)}")
    
    def _create_new_folder(self, parent_dir: str):
        """创建新文件夹"""
        name, ok = QInputDialog.getText(
            self, "新建文件夹", "文件夹名:", text="新建文件夹"
        )
        if ok and name:
            folder_path = os.path.join(parent_dir, name)
            try:
                os.makedirs(folder_path, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"创建文件夹失败：{str(e)}")
    
    def create_new_folder(self):
        """在笔记库根目录创建新文件夹"""
        self._create_new_folder(self.config.get_notebooks_path())
    
    def _rename_item(self, filepath: str):
        """重命名"""
        old_name = os.path.basename(filepath)
        new_name, ok = QInputDialog.getText(
            self, "重命名", "新名称:", text=old_name
        )
        if ok and new_name and new_name != old_name:
            new_path = os.path.join(os.path.dirname(filepath), new_name)
            try:
                os.rename(filepath, new_path)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"重命名失败：{str(e)}")
    
    def _delete_item(self, filepath: str, is_dir: bool):
        """删除"""
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
                if is_dir:
                    import shutil
                    shutil.rmtree(filepath)
                else:
                    os.remove(filepath)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除失败：{str(e)}")
    
    def refresh_external_files(self):
        """刷新外部文件显示"""
        external_files = self.config.get_external_files()
        
        # 清空现有列表
        while self.external_list_layout.count():
            item = self.external_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 过滤存在的文件
        valid_files = [f for f in external_files if os.path.exists(f)]
        
        if valid_files:
            self.external_container.show()
            
            for filepath in valid_files:
                label = ExternalFileLabel(filepath)
                label.clicked.connect(self.file_open_requested.emit)
                self.external_list_layout.addWidget(label)
        else:
            self.external_container.hide()
