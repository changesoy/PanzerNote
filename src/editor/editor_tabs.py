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
from typing import Optional, List, Dict, Tuple, Set

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QTabBar, QMessageBox,
    QFileDialog, QPlainTextEdit, QTextEdit, QMenu, QAction,
    QInputDialog, QLabel, QDialog, QHBoxLayout, QComboBox,
    QPushButton, QLineEdit, QFormLayout, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal, QMimeData, QPoint, QByteArray
from PyQt5.QtGui import QFont, QTextCursor, QColor, QTextCharFormat, QDrag

from ..core.config import Config
from ..utils.logger import get_logger
from ..security.file_guard import FileSizeExceededError, FileOperationTimeoutError
from ..security.input_validator import InputValidator
from .editor import Editor
from .markdown_preview import MarkdownPreviewWidget
from .find_replace import FindReplaceBar


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
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            self._drag_tab_index = self.tabAt(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
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

        result = drag.exec_(Qt.MoveAction | Qt.CopyAction)
        self._drag_tab_index = -1


# ════════════════════════════════════════════════════════
#  EditorTabWidget
# ════════════════════════════════════════════════════════

class EditorTabWidget(QTabWidget):
    """编辑器标签页管理"""
    
    current_changed = pyqtSignal(int)
    content_modified = pyqtSignal()
    tab_count_changed = pyqtSignal(int)
    
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        
        self._tab_info: Dict[int, Dict] = {}
        self._next_tab_id = 0
        self._used_untitled_numbers: Set[int] = set()

        # 使用可拖拽标签栏
        self._tab_bar = DraggableTabBar(self)
        self.setTabBar(self._tab_bar)

        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        
        self.setStyleSheet("""
            QTabWidget::pane { border: none; }
            QTabBar::tab {
                padding: 8px 15px; margin-right: 2px;
                background-color: #f0f0f0; border: 1px solid #ddd;
                border-bottom: none; border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: white; border-bottom: 1px solid white;
            }
            QTabBar::tab:hover { background-color: #e3f2fd; }
        """)
        
        self.tabCloseRequested.connect(self._on_tab_close_requested)
        self.currentChanged.connect(self._on_current_changed)
        
        self.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabBar().customContextMenuRequested.connect(self._show_tab_context_menu)

        # ── 查找替换栏（嵌入在标签内容上方） ──
        # 不在这里创建，而是由 main_window 在 editor_container 中创建
        self._find_bar = None

    def set_find_bar(self, find_bar: FindReplaceBar):
        """设置外部传入的查找替换栏"""
        self._find_bar = find_bar

    def _get_filepath_for_index(self, index: int) -> Optional[str]:
        """获取指定标签页的文件路径（供 DraggableTabBar 使用）"""
        widget = self.widget(index)
        if widget and hasattr(widget, 'tab_id'):
            info = self._tab_info.get(widget.tab_id, {})
            filepath = info.get("filepath")
            if filepath and not info.get("is_new"):
                return filepath
        return None

    def _get_editor_from_widget(self, widget) -> Optional[Editor]:
        """从标签页widget获取实际的Editor"""
        if isinstance(widget, Editor):
            return widget
        elif isinstance(widget, MarkdownPreviewWidget):
            return widget.editor
        return None
    
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
                pass
    
    def _generate_tab_id(self) -> int:
        tab_id = self._next_tab_id
        self._next_tab_id += 1
        return tab_id
    
    def new_file(self) -> int:
        """新建文件"""
        num = self._get_next_untitled_number()
        self._used_untitled_numbers.add(num)
        title = f"未命名{num}.txt"
        
        editor = Editor(self.config)
        editor.textChanged.connect(self._on_text_changed)
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
            "last_saved_content": "",
            "last_saved_chars": 0,
            "is_markdown": False,
            "history": []
        }
        
        self.setCurrentIndex(index)
        self.tab_count_changed.emit(self.count())
        return index
    
    def _is_markdown_file(self, filepath: str) -> bool:
        """判断是否为Markdown文件"""
        ext = os.path.splitext(filepath)[1].lower()
        return ext in ('.md', '.markdown')
    
    def open_file(self, filepath: str) -> int:
        """打开文件"""
        # 检查文件是否已经打开
        for i in range(self.count()):
            widget = self.widget(i)
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is not None:
                info = self._tab_info.get(tab_id, {})
                if info.get("filepath") == filepath:
                    self.setCurrentIndex(i)
                    return i
        
        # 读取文件内容，检测编码
        content = ""
        detected_encoding = "UTF-8"
        file_guard = self.config.get_file_guard()
        
        try:
            content = file_guard.safe_read(filepath, encoding='utf-8', validate_path=False)
            detected_encoding = "UTF-8"
        except UnicodeDecodeError:
            try:
                content = file_guard.safe_read(filepath, encoding='gbk', validate_path=False)
                detected_encoding = "GBK"
            except UnicodeDecodeError:
                    try:
                        content = file_guard.safe_read(filepath, encoding='utf-16', validate_path=False)
                        detected_encoding = "UTF-16"
                    except (UnicodeDecodeError, OSError):
                        try:
                            raw = file_guard.safe_read_bytes(filepath, validate_path=False)
                            content = raw.decode('utf-8', errors='ignore')
                            detected_encoding = "UTF-8"
                        except Exception as e:
                            get_logger(__name__).error("无法读取文件: %s, %s", filepath, e)
                            QMessageBox.critical(self, "错误", f"无法读取文件：{filepath}\n{str(e)}")
                            return -1
        except (FileSizeExceededError, FileOperationTimeoutError) as e:
            get_logger(__name__).error("文件安全检查失败: %s, %s", filepath, e)
            QMessageBox.critical(self, "错误", f"无法读取文件：{filepath}\n{str(e)}")
            return -1
        except Exception as e:
            get_logger(__name__).error("打开文件失败: %s", e)
            QMessageBox.critical(self, "错误", f"打开文件失败：{str(e)}")
            return -1
        
        is_md = self._is_markdown_file(filepath)
        
        if is_md:
            widget = MarkdownPreviewWidget(self.config)
            widget.editor.load_content(content)
            widget.editor.textChanged.connect(self._on_text_changed)
            widget.editor.set_file_type(filepath)
            widget.set_base_path(os.path.dirname(os.path.abspath(filepath)))
        else:
            widget = Editor(self.config)
            widget.load_content(content)
            widget.textChanged.connect(self._on_text_changed)
            widget.set_file_type(filepath)
        
        filename = os.path.basename(filepath)
        index = self.addTab(widget, filename)
        
        tab_id = self._generate_tab_id()
        widget.tab_id = tab_id
        
        # 如果是MarkdownPreviewWidget，也设置editor的tab_id
        if is_md:
            widget.editor.tab_id = tab_id
        
        self._tab_info[tab_id] = {
            "filepath": filepath,
            "is_modified": False,
            "is_new": False,
            "encoding": detected_encoding,
            "last_saved_content": content,
            "last_saved_chars": len(content),
            "is_markdown": is_md,
            "history": []
        }
        
        self.setCurrentIndex(index)
        self.tab_count_changed.emit(self.count())
        return index
    
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
        
        info = self._tab_info.get(getattr(widget, 'tab_id', None), {})
        
        if info.get("filepath"):
            suggested_name = info["filepath"]
        else:
            suggested_name = os.path.join(
                self.config.get_notebooks_path(),
                self.tabText(self.currentIndex()).rstrip(" *")
            )
        
        current_encoding = info.get("encoding", "UTF-8")
        
        dialog = SaveAsDialog(suggested_name, current_encoding, self)
        if dialog.exec_() != QDialog.Accepted:
            return False, 0
        
        filepath = dialog.get_filepath()
        encoding = dialog.get_encoding()
        
        if not filepath:
            return False, 0
        
        success, chars = self._save_file(widget, filepath, encoding)
        
        if success:
            if info.get("is_new") and info.get("untitled_number"):
                self._used_untitled_numbers.discard(info["untitled_number"])
            info["is_new"] = False
            info["filepath"] = filepath
            info["encoding"] = encoding
            
            # 更新文件类型
            editor = self._get_editor_from_widget(widget)
            if editor:
                editor.set_file_type(filepath)
            
            index = self.indexOf(widget)
            self.setTabText(index, os.path.basename(filepath))
        
        return success, chars
    
    def _save_file(self, widget, filepath: str, encoding: str = "UTF-8") -> Tuple[bool, int]:
        """保存文件"""
        # 获取文本内容
        if isinstance(widget, MarkdownPreviewWidget):
            content = widget.editor.toPlainText()
        elif isinstance(widget, Editor):
            content = widget.toPlainText()
        else:
            return False, 0
        
        try:
            file_guard = self.config.get_file_guard()
            file_guard.safe_write(filepath, content, encoding=encoding.lower(), validate_path=False)
        except (FileSizeExceededError, FileOperationTimeoutError) as e:
            get_logger(__name__).error("文件安全检查失败: %s", e)
            QMessageBox.critical(self, "错误", f"保存文件失败：{str(e)}")
            return False, 0
        except Exception as e:
            get_logger(__name__).error("保存文件失败: %s", e)
            QMessageBox.critical(self, "错误", f"保存文件失败：{str(e)}")
            return False, 0
        
        tab_id = getattr(widget, 'tab_id', None)
        info = self._tab_info.get(tab_id, {})
        last_chars = info.get("last_saved_chars", 0)
        new_chars = max(0, len(content) - last_chars)
        
        info["filepath"] = filepath
        info["is_modified"] = False
        info["encoding"] = encoding
        info["last_saved_content"] = content
        info["last_saved_chars"] = len(content)
        
        index = self.indexOf(widget)
        title = self.tabText(index)
        if title.endswith(" *"):
            self.setTabText(index, title[:-2])
        
        return True, new_chars
    
    def save_all(self) -> int:
        """保存所有文件"""
        total_chars = 0
        
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
                        old_index = self.currentIndex()
                        self.setCurrentIndex(i)
                        success, chars = self.save_current_as()
                        if success:
                            total_chars += chars
                        self.setCurrentIndex(old_index)
        
        return total_chars
    
    def save_all_to_temp(self):
        """保存所有文件到暂存目录"""
        temp_dir = self.config.get_temp_path()
        os.makedirs(temp_dir, exist_ok=True)
        
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = os.path.join(temp_dir, f"session_{session_id}")
        os.makedirs(session_dir, exist_ok=True)
        
        for i in range(self.count()):
            widget = self.widget(i)
            tab_id = getattr(widget, 'tab_id', None)
            if tab_id is not None:
                info = self._tab_info.get(tab_id, {})
                if info.get("is_modified"):
                    if isinstance(widget, MarkdownPreviewWidget):
                        content = widget.editor.toPlainText()
                    elif isinstance(widget, Editor):
                        content = widget.toPlainText()
                    else:
                        continue
                    
                    filepath = info.get("filepath")
                    if filepath:
                        filename = os.path.basename(filepath) + ".autosave"
                    else:
                        filename = f"untitled_{tab_id}.txt.autosave"
                    
                    try:
                        file_guard = self.config.get_file_guard()
                        file_guard.safe_write(
                            os.path.join(session_dir, filename),
                            content, validate_path=False
                        )
                    except Exception:
                        get_logger(__name__).warning("自动保存失败: %s", filename)
    
    def clear_temp_files(self):
        """清理暂存文件"""
        temp_dir = self.config.get_temp_path()
        if os.path.exists(temp_dir):
            import shutil
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                get_logger(__name__).warning("清理暂存文件失败: %s", temp_dir)
    
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
                        editor.document().clearUndoRedoStacks()

    def close_current_tab(self):
        if self.count() > 0:
            self._on_tab_close_requested(self.currentIndex())
    
    def close_all_tabs(self):
        while self.count() > 0:
            if not self._close_tab(0):
                break
    
    def close_other_tabs(self, keep_index: int):
        while self.count() > keep_index + 1:
            if not self._close_tab(keep_index + 1):
                break
        while self.count() > 1 and keep_index > 0:
            if not self._close_tab(0):
                break
            keep_index -= 1
    
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
        
        if isinstance(widget, MarkdownPreviewWidget):
            content = widget.editor.toPlainText()
        elif isinstance(widget, Editor):
            content = widget.toPlainText()
        else:
            content = ""
        
        title = self.tabText(index).rstrip(" *")
        is_new = info.get("is_new", False)
        is_empty = len(content.strip()) == 0
        
        if is_new and is_empty:
            self._release_untitled_number(title)
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
            msg_box.setIcon(QMessageBox.Question)
            
            save_btn = msg_box.addButton("保存", QMessageBox.AcceptRole)
            discard_btn = msg_box.addButton("不保存", QMessageBox.DestructiveRole)
            cancel_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
            
            msg_box.exec_()
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
            elif clicked == cancel_btn:
                return False
        
        if info.get("is_new"):
            self._release_untitled_number(title)
        
        del self._tab_info[tab_id]
        self.removeTab(index)
        self.tab_count_changed.emit(self.count())
        return True
    
    def _show_tab_context_menu(self, position):
        index = self.tabBar().tabAt(position)
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
        
        menu.exec_(self.tabBar().mapToGlobal(position))
    
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
                QMessageBox.critical(self, "错误", f"重命名失败：{str(e)}")
    
    def _on_current_changed(self, index: int):
        # 更新查找替换栏的编辑器
        if self._find_bar:
            editor = self.current_editor()
            self._find_bar.set_editor(editor)
        self.current_changed.emit(index)
    
    def _on_text_changed(self):
        editor = self.sender()
        if not editor or not hasattr(editor, 'tab_id'):
            return
        
        info = self._tab_info.get(editor.tab_id, {})
        
        current_content = editor.toPlainText()
        if current_content != info.get("last_saved_content", ""):
            if not info.get("is_modified"):
                info["is_modified"] = True
                # 找到对应的tab index
                for i in range(self.count()):
                    widget = self.widget(i)
                    if getattr(widget, 'tab_id', None) == editor.tab_id:
                        title = self.tabText(i)
                        if not title.endswith(" *"):
                            self.setTabText(i, title + " *")
                        break
        else:
            if info.get("is_modified"):
                info["is_modified"] = False
                for i in range(self.count()):
                    widget = self.widget(i)
                    if getattr(widget, 'tab_id', None) == editor.tab_id:
                        title = self.tabText(i)
                        if title.endswith(" *"):
                            self.setTabText(i, title[:-2])
                        break
        
        self.content_modified.emit()
    
    def current_editor(self) -> Optional[Editor]:
        """获取当前编辑器"""
        widget = self.currentWidget()
        return self._get_editor_from_widget(widget)
    
    def get_current_encoding(self) -> str:
        """获取当前文件的编码"""
        widget = self.currentWidget()
        if widget and hasattr(widget, 'tab_id'):
            info = self._tab_info.get(widget.tab_id, {})
            return info.get("encoding", "UTF-8")
        return "UTF-8"
    
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
                        unsaved.append(self.tabText(i).rstrip(" *"))
        return unsaved
    
    def has_modified_files(self) -> bool:
        for tab_id, info in self._tab_info.items():
            if info.get("is_modified"):
                return True
        return False
    
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
                        files_info.append({
                            "path": filepath,
                            "cursor_position": cursor.position(),
                            "scroll_position": editor.verticalScrollBar().value()
                        })
        return files_info
    
    def set_wrap_mode_all(self, mode: str):
        """设置所有编辑器的行宽模式"""
        for i in range(self.count()):
            widget = self.widget(i)
            editor = self._get_editor_from_widget(widget)
            if editor:
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
        """设置所有编辑器的缩略图显示"""
        for i in range(self.count()):
            widget = self.widget(i)
            editor = self._get_editor_from_widget(widget)
            if editor:
                editor.set_minimap_visible(visible)

    def apply_auto_minimap_all(self):
        """对所有编辑器应用 auto_minimap 设置"""
        for i in range(self.count()):
            widget = self.widget(i)
            editor = self._get_editor_from_widget(widget)
            if editor:
                editor.apply_auto_minimap()

    def set_line_numbers_all(self, show: bool):
        """设置所有编辑器的行号显示"""
        for i in range(self.count()):
            widget = self.widget(i)
            editor = self._get_editor_from_widget(widget)
            if editor:
                editor.set_show_line_numbers(show)

    def set_highlight_current_line_all(self, enabled: bool):
        """设置所有编辑器的高亮当前行"""
        for i in range(self.count()):
            widget = self.widget(i)
            editor = self._get_editor_from_widget(widget)
            if editor:
                editor.set_highlight_current_line(enabled)

    def set_font_all(self, family: str, size: int):
        """设置所有编辑器的字体"""
        for i in range(self.count()):
            widget = self.widget(i)
            editor = self._get_editor_from_widget(widget)
            if editor:
                editor.set_editor_font(family, size)

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
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if msg != QMessageBox.Yes:
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
            QMessageBox.critical(self, "错误", f"移动文件失败：{str(e)}")
            return False

    # === 编辑操作代理 ===
    
    def undo(self) -> bool:
        editor = self.current_editor()
        if editor and editor.document().isUndoAvailable():
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

    def duplicate_line(self):
        """复制当前行"""
        editor = self.current_editor()
        if editor:
            editor.duplicate_line()

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

        max_line = editor.document().blockCount()
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
