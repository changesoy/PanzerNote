# -*- coding: utf-8 -*-
"""
文件树组件
显示笔记库文件结构和外部文件

v1.5.4 改动：
  - 支持接受标签拖拽：将文件移动到文件树中的目标文件夹
v1.6.4 改动：
  - 主题感知：订阅 theme_committed 信号（v2 manager）
"""

import os
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeView, QLabel, QMenu,
    QInputDialog, QMessageBox,
    QFrame, QAbstractItemView, QStyleOptionViewItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QModelIndex, QMimeData, QRect, QTimer
from PyQt6.QtGui import (
    QColor, QFont, QAction, QFileSystemModel, QDragLeaveEvent, QPaintEvent, QPainter,
)

from ..core.config import Config
from ..utils.logger import get_logger
from ..utils.error_handler import ErrorHandler, ErrorCategory
from ..security.input_validator import FilenameValidationError
from ..themes.theme_aware_mixin import ThemeAwareMixin
from ..themes.theme_v2.consumer import v2_token, v2_color_qcolor
from .image_formats import VIEWABLE, filter_patterns, is_viewable


MIME_TAB_FILEPATH = "application/x-panzernote-tab-filepath"
# 3.5.11：与 editor_tabs.py 同值；未命名标签（无 filepath）落盘保存时定位源标签
MIME_TAB_ID = "application/x-panzernote-tab-id"

# 落点高亮的不透明度（0-255）。主题的 drop_indicator 是纯色强调色（默认取
# focus），整行铺满会过于抢眼；高亮又只能压在该行文字之上（见 drawRow），
# 取约 16% 既能让整行看得出被点亮，文字观感也基本不变。
_DROP_HIGHLIGHT_ALPHA = 40


class AlwaysExpandableModel(QFileSystemModel):

    def hasChildren(self, parent=QModelIndex()):
        if not parent.isValid():
            return True
        if self.isDir(parent):
            return True
        return False

    def canDropMimeData(self, data, action, row, column, parent):
        """让「标签拖拽」在模型侧也被视为可接受。

        标签拖拽只带自定义 MIME（刻意不带 text/uri-list），基类拖拽循环会因
        模型拒绝而给不出「可放置」的光标反馈。放行仅为这一件事：落点提示本身
        已改由 DroppableTreeView 自绘（见 drawRow），实际落盘也由它的 dropEvent
        接管，都不走模型的 dropMimeData。
        """
        if data is not None and (
            data.hasFormat(MIME_TAB_FILEPATH) or data.hasFormat(MIME_TAB_ID)
        ):
            if action == Qt.DropAction.IgnoreAction or not parent.isValid():
                return False
            return self.isDir(parent)
        return super().canDropMimeData(data, action, row, column, parent)


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
        # 落点提示改由本视图自绘（见 set_drop_highlight_color / drawRow）：
        # 原生指示器画的是系统调色板色的整圈边框、不随主题走，且同一张表上
        # 「拖标签」与「树内拖拽」的观感还会因光标落在行中央 / 行边缘而不同
        # （整行框 vs 一条线）。自绘后两者共用同一条路径，只剩整行浅色高亮。
        self.setDropIndicatorShown(False)
        self._drop_target = QModelIndex()
        self._drop_highlight = QColor("#2196F3")

    def _update_viewport(self) -> None:
        """重绘树视图区（PyQt 的 viewport() 返回 Optional，需显式判空）。"""
        viewport = self.viewport()
        if viewport is not None:
            viewport.update()

    def set_drop_highlight_color(self, color: QColor) -> None:
        """设置落点高亮色（主题 drop_indicator，通常带透明通道）。"""
        self._drop_highlight = color
        self._update_viewport()

    def _set_drop_target(self, index: QModelIndex) -> None:
        """记录当前落点行并重绘（落点提示只有这一个来源）。"""
        if index == self._drop_target:
            return
        self._drop_target = index
        self._update_viewport()

    def drawRow(self, painter: Optional[QPainter], option: QStyleOptionViewItem,
                index: QModelIndex) -> None:
        super().drawRow(painter, option, index)
        # 落点高亮只能画在条目之后：QTreeView 在画条目之前会用底色整行铺一次，
        # 画在之前必然被盖掉（实测 drawRow 里先 fillRect，整行像素毫无变化）；
        # 而想插进「底色已铺、图标文字尚未画」那一层，得给视图换一个 style
        # 代理，代价与收益不成比例。代价是该行文字会带上一点高亮色，故高亮
        # 取较低不透明度（见 _DROP_HIGHLIGHT_ALPHA）。
        if painter is not None and self._drop_target.isValid() \
                and index == self._drop_target:
            painter.fillRect(self.visualRect(index), self._drop_highlight)

    def _last_rendered_index(self) -> QModelIndex:
        """树里最后一行（沿已展开的最后一条链走到叶子）。

        从视图根出发：QFileSystemModel 的模型根是整个磁盘（根索引的 children
        是驱动器），与视图用 setRootIndex 设的那个目录不是一回事。
        """
        model = self.model()
        if model is None:
            return QModelIndex()
        index = self.rootIndex()
        count = model.rowCount(index)
        if count == 0:
            return QModelIndex()
        while True:
            index = model.index(count - 1, 0, index)
            count = model.rowCount(index)
            if count == 0 or not self.isExpanded(index):
                return index

    def _drop_area_top(self) -> Optional[int]:
        """落点落在「空白处」（树根）时的可绘制区域顶部；不适用或无可见空区时 None。

        树根不占一行（视图用 setRootIndex 把它设成了根），行高亮画不出来，只能
        在最后一行下方的空白区铺色 —— 否则「拖到空白处会落进笔记库根目录」这件
        事完全没有视觉反馈，而那里确实会落盘。
        """
        viewport = self.viewport()
        if viewport is None or not self._drop_target.isValid() \
                or self._drop_target != self.rootIndex():
            return None
        last = self._last_rendered_index()
        top = 0 if not last.isValid() else self.visualRect(last).bottom() + 1
        return top if top < viewport.height() else None

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        super().paintEvent(event)
        # 空白区提示补在视图自身绘制之后（行高亮走 drawRow，见上）。
        top = self._drop_area_top()
        viewport = self.viewport()
        if top is None or viewport is None:
            return
        painter = QPainter(viewport)
        painter.fillRect(QRect(0, top, viewport.width(), viewport.height() - top),
                         self._drop_highlight)

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

    def _schedule_drop(self, src_filepath: str, dest_folder: str) -> None:
        """拖放结束后再异步询问：模态对话框不能嵌在（Windows 原生）拖拽事件循环里。"""
        QTimer.singleShot(
            0, lambda: self._ask_and_request_drop(src_filepath, dest_folder))

    def _ask_and_request_drop(self, src_filepath: str, dest_folder: str):
        """拖放结束后（异步）询问移动/复制并发出对应请求。"""
        action = self._ask_move_or_copy(os.path.basename(src_filepath), dest_folder)
        if action == "move":
            self.file_move_requested.emit(src_filepath, dest_folder)
        elif action == "copy":
            self.file_copy_requested.emit(src_filepath, dest_folder)

    @staticmethod
    def _can_drop_into(src_filepath: str, dest_folder: str) -> bool:
        """目标文件夹能否接收该条目。

        排除「原地放下」（父目录就是目标）与「文件夹放进自己的子孙目录」——
        后者会把自己的父链搬断。
        """
        src = os.path.abspath(src_filepath)
        dest = os.path.abspath(dest_folder)
        if os.path.dirname(src) == dest or src == dest:
            return False
        return not dest.startswith(src + os.sep)

    def _drop_paths(self, mime: QMimeData) -> list:
        """本次拖拽携带的本地路径（标签拖拽取标签自身的文件路径）。

        标签拖拽刻意不带 text/uri-list，故需单独从 MIME_TAB_FILEPATH 取；未命名
        标签没有路径，返回空列表。
        """
        if mime.hasFormat(MIME_TAB_FILEPATH):
            data = mime.data(MIME_TAB_FILEPATH)
            if data is None or data.isEmpty():
                return []
            path = data.data().decode("utf-8")
            return [path] if path else []
        return [url.toLocalFile() for url in mime.urls() if url.toLocalFile()]

    def _is_droppable(self, mime: QMimeData, dest_folder: Optional[str]) -> bool:
        """当前落点是否真的会落盘 —— 落点提示只在这个前提下显示。

        否则就是「提示过度承诺」：把文件拖回它自己的文件夹（或把文件夹拖进自己
        的子孙目录）时高亮照旧亮起，松手却什么都不发生。
        """
        if not dest_folder:
            return False
        paths = self._drop_paths(mime)
        if not paths:
            # 未命名标签没有路径，拖进文件夹 = 落盘保存，任何文件夹都可放置
            return self._is_tab_drag(mime)
        return any(self._can_drop_into(path, dest_folder) for path in paths)

    def _dest_folder_index_at(self, pos) -> QModelIndex:
        """落点对应的目标文件夹行：命中文件夹用它本身，命中文件用其父目录，
        空白处用树根。

        落盘判定（_dest_folder_at）与落点高亮（_set_drop_target）共用这一份
        判定，避免两处各写一套后「高亮的行」与「实际落到的文件夹」不一致。
        """
        model = self.model()
        if not isinstance(model, QFileSystemModel):
            return QModelIndex()
        index = self.indexAt(pos)
        if index.isValid():
            if model.isDir(index):
                return index
            parent_idx = index.parent()
            if parent_idx.isValid():
                return parent_idx
        root = self.rootIndex()
        if root.isValid():
            return root
        root_path = model.rootPath()
        return model.index(root_path) if root_path else QModelIndex()

    def _dest_folder_path(self, index: QModelIndex) -> Optional[str]:
        """落点行对应的目标文件夹路径（判定规则见 _dest_folder_index_at）。"""
        model = self.model()
        if isinstance(model, QFileSystemModel) and index.isValid():
            return model.filePath(index)
        return None

    def _dest_folder_at(self, pos) -> Optional[str]:
        """落点对应的目标文件夹路径（判定规则见 _dest_folder_index_at）。"""
        return self._dest_folder_path(self._dest_folder_index_at(pos))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.indexAt(event.pos())
            if not index.isValid():
                sel_model = self.selectionModel()
                if sel_model is not None and sel_model.hasSelection():
                    sel_model.clearSelection()
                self.setCurrentIndex(QModelIndex())
        super().mousePressEvent(event)

    @staticmethod
    def _is_tab_drag(mime: QMimeData) -> bool:
        """标签拖拽：已保存文件（MIME_TAB_FILEPATH）或未命名标签（MIME_TAB_ID）。"""
        return mime.hasFormat(MIME_TAB_FILEPATH) or mime.hasFormat(MIME_TAB_ID)

    def dragEnterEvent(self, event):
        if self._is_tab_drag(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        # 落点高亮：拖标签与树内拖拽共用同一处判定 —— 这正是「两种拖拽观感
        # 统一」的落点。先前完全交给基类的原生指示器，于是同一张表上会出现
        # 「整行框」与「一条线」两种结果，拖标签还曾因模型拒绝自定义 MIME
        # 而完全画不出来。
        # 只在该落点真的会落盘时才亮（见 _is_droppable）：把文件拖回它自己的
        # 文件夹、或把文件夹拖进自己的子孙目录，松手都不会有任何动作。
        dest_index = self._dest_folder_index_at(event.position().toPoint())
        if self._is_droppable(event.mimeData(),
                             self._dest_folder_path(dest_index)):
            self._set_drop_target(dest_index)
        else:
            self._set_drop_target(QModelIndex())
        if self._is_tab_drag(event.mimeData()):
            super().dragMoveEvent(event)
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event: Optional[QDragLeaveEvent]):
        # 拖拽离开视图（含拖到窗口外松开）后必须清掉落点，否则高亮会挂在
        # 上一次经过的行上。
        self._set_drop_target(QModelIndex())
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._set_drop_target(QModelIndex())
        mime = event.mimeData()
        pos = event.position().toPoint()
        if self._is_tab_drag(mime):
            data = mime.data(MIME_TAB_FILEPATH)
            src_filepath = bytes(data).decode('utf-8')
            # 3.5.11：未命名标签无 filepath，通过 tab_id 定位源标签
            tab_id = None
            tab_id_data = mime.data(MIME_TAB_ID)
            if tab_id_data and not tab_id_data.isEmpty():
                try:
                    tab_id = int(bytes(tab_id_data).decode('utf-8'))
                except (ValueError, UnicodeDecodeError):
                    tab_id = None

            dest_folder = self._dest_folder_at(pos)
            if dest_folder:
                if src_filepath:
                    if self._can_drop_into(src_filepath, dest_folder):
                        self._schedule_drop(src_filepath, dest_folder)
                elif tab_id is not None:
                    # 未命名标签拖到文件树 = 落盘保存（源面板从拖拽发起者父级取）
                    source = event.source()
                    source_tabs = source.parent() if source is not None else None
                    if source_tabs is not None:
                        self.untitled_save_requested.emit(source_tabs, tab_id, dest_folder)

            event.acceptProposedAction()
            return

        if event.source() is self:
            # 树内拖拽：必须由本视图接管。QFileSystemModel 在 readOnly 放开后能自己
            # 完成落盘（rename/copy），那条默认路径既不询问用户、也不做图片资源
            # 迁移，直接跳过会让两种拖拽行为不一致。
            # 例外：拖的是**文件夹**时仍交回模型 —— 应用层入口只支持文件
            # （move_file_to_folder / copy_file_to_folder 首行要求 os.path.isfile），
            # 接管会让「拖文件夹」变成问完就静默无动作（弹窗收不到任何结果），
            # 而模型本来就能完成目录 rename，这是本次接管前就有的能力。落点守卫
            # （原地放下 / 拖进自己的子孙）仍由这里先判，模型那侧不认这些。
            dest_folder = self._dest_folder_at(pos)
            if dest_folder:
                droppable = [
                    path for path in (url.toLocalFile() for url in mime.urls())
                    if path and self._can_drop_into(path, dest_folder)
                ]
                if droppable:
                    if any(os.path.isdir(path) for path in droppable):
                        super().dropEvent(event)
                        return
                    self._schedule_drop(droppable[0], dest_folder)
                    event.acceptProposedAction()
                    return
            event.ignore()
            return

        super().dropEvent(event)


class FileTreeWidget(ThemeAwareMixin, QWidget):

    file_open_requested = pyqtSignal(str)
    # 图片文件双击时打开查看器
    image_open_requested = pyqtSignal(str)
    file_move_requested = pyqtSignal(str, str)
    file_copy_requested = pyqtSignal(str, str)
    # (filepath, is_dir)：删除成功后通知外部同步关闭已打开的标签页
    file_deleted = pyqtSignal(str, bool)
    # (old_path, new_path)：重命名成功后通知外部同步更新图片标签持有的路径
    file_renamed = pyqtSignal(str, str)
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
            "*.java", "*.js", "*.json", "*.html", "*.css", "*.xml",
            # 图片也进文件树：双击由查看器打开（含 HEIF/AVIF 等，见 image_formats）
            *filter_patterns(VIEWABLE),
        ])
        self.model.setNameFilterDisables(False)

        # QFileSystemModel.readOnly 默认为 True 时条目不接受拖放（ItemIsDropEnabled
        # 不置位），树内拖拽连落点指示都不会画。放开只读仅为「接受拖放」这件事：
        # 实际落盘由 DroppableTreeView.dropEvent 接管（询问移动/复制 + 资源迁移），
        # 不再复用模型的 dropMimeData。
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
        # 落点高亮色由 _apply_theme_colors 按主题设置（见 set_drop_highlight_color）
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
        # 拖拽落点高亮：色值仍由 tree_item recipe 的 drop_indicator 决定
        # （主题作者一侧不变），只是在代码里铺成半透明整行高亮，而不是交给
        # 原生指示器画边框（原生画法不认这个 recipe，见 DroppableTreeView）。
        self.tree_view.set_drop_highlight_color(v2_color_qcolor(
            self._theme_engine, "tree_item", "drop_indicator",
            "#2196F3", alpha=_DROP_HIGHLIGHT_ALPHA,
        ))

        self.setStyleSheet(f"""
            QWidget#FileTreeWidget {{
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
            if is_viewable(filepath):
                self.image_open_requested.emit(filepath)
            else:
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
            else:
                # 重命名成功后再通知外部（同步更新已打开图片标签的路径）
                self.file_renamed.emit(os.path.normpath(filepath),
                                       os.path.normpath(new_path))
                self.tree_changed.emit()

    def _delete_item(self, filepath: str, is_dir: bool):
        name = os.path.basename(filepath)
        type_str = "文件夹" if is_dir else "文件"

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("确认删除")
        msg_box.setText(f"确定要删除{type_str} '{name}' 吗？")
        msg_box.setIcon(QMessageBox.Icon.Question)

        yes_btn = msg_box.addButton("确定", QMessageBox.ButtonRole.AcceptRole)
        msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)

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
