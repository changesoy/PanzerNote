# -*- coding: utf-8 -*-
"""
编辑控制器
集中管理编辑操作编排（原 MainWindow 编辑操作区块 22 个方法）。

创建者：MainWindow（_init_ui 之后构造注入）
持有者：MainWindow
完成通知：无（编辑操作同步完成，UI 反馈经 secretary）
"""

from ..game.secretary_widget import SecretaryWidget

from .editor_tabs import EditorTabWidget


class EditActionController:
    """编辑控制器：集中管理编辑、行操作、大小写、书签/折叠操作编排。

    依赖全部构造注入，不持有 MainWindow 引用。
    """

    def __init__(
        self,
        editor_tabs: EditorTabWidget,
        secretary: SecretaryWidget,
    ) -> None:
        self._editor_tabs = editor_tabs
        self._secretary = secretary

    # === 基础编辑 ===

    def undo(self) -> None:
        """撤销；无操作可撤销时提示。"""
        if not self._editor_tabs.undo():
            self._secretary.show_message("当前没有可撤销的操作")

    def redo(self) -> None:
        """重做"""
        self._editor_tabs.redo()

    def cut(self) -> None:
        """剪切"""
        self._editor_tabs.cut()

    def copy(self) -> None:
        """复制"""
        self._editor_tabs.copy()

    def paste(self) -> None:
        """粘贴"""
        self._editor_tabs.paste()

    def select_all(self) -> None:
        """全选"""
        self._editor_tabs.select_all()

    def find(self) -> None:
        """查找"""
        self._editor_tabs.show_find_dialog()

    def replace(self) -> None:
        """替换"""
        self._editor_tabs.show_replace_dialog()

    # === 插入 ===

    def insert_image(self) -> None:
        """插入图片（落盘到文档同级 PanzerNote_assets/ 后插入相对路径）。"""
        self._editor_tabs.insert_image_from_file()

    def recover_missing_images(self) -> None:
        """恢复断链图片（E6c2：外部移动后按 ledger 线索 + 可证明范围判定）。"""
        self._editor_tabs.recover_missing_images()

    # === 行操作 ===

    def delete_current_line(self) -> None:
        self._editor_tabs.delete_current_line()

    def move_line_up(self) -> None:
        self._editor_tabs.move_line_up()

    def move_line_down(self) -> None:
        self._editor_tabs.move_line_down()

    def copy_line(self) -> None:
        self._editor_tabs.copy_line()

    def paste_line(self) -> None:
        self._editor_tabs.paste_line()

    def goto_line(self) -> None:
        self._editor_tabs.show_goto_line_dialog()

    # === 大小写转换 ===

    def toggle_case(self) -> None:
        self._editor_tabs.toggle_case()

    def to_uppercase(self) -> None:
        self._editor_tabs.to_uppercase()

    def to_lowercase(self) -> None:
        self._editor_tabs.to_lowercase()

    def to_titlecase(self) -> None:
        self._editor_tabs.to_titlecase()

    # === Markdown 编辑（阶段 2：任务列表 / 表格） ===

    def toggle_task_checkbox(self) -> None:
        self._editor_tabs.toggle_task_checkbox()

    def table_insert_row_above(self) -> None:
        self._editor_tabs.table_insert_row_above()

    def table_insert_row_below(self) -> None:
        self._editor_tabs.table_insert_row_below()

    def table_delete_row(self) -> None:
        self._editor_tabs.table_delete_row()

    def table_insert_column_left(self) -> None:
        self._editor_tabs.table_insert_column_left()

    def table_insert_column_right(self) -> None:
        self._editor_tabs.table_insert_column_right()

    def table_delete_column(self) -> None:
        self._editor_tabs.table_delete_column()

    def table_format_align(self) -> None:
        self._editor_tabs.table_format_align()

    def table_align_left(self) -> None:
        self._editor_tabs.table_align_left()

    def table_align_center(self) -> None:
        self._editor_tabs.table_align_center()

    def table_align_right(self) -> None:
        self._editor_tabs.table_align_right()

    def format_bold(self) -> None:
        self._editor_tabs.format_bold()

    def format_italic(self) -> None:
        self._editor_tabs.format_italic()

    def format_inline_code(self) -> None:
        self._editor_tabs.format_inline_code()

    def format_link(self) -> None:
        self._editor_tabs.format_link()

    def set_heading_level(self, level: int) -> None:
        self._editor_tabs.set_heading_level(level)

    # === 书签与折叠 ===

    def toggle_bookmark(self) -> None:
        editor = self._editor_tabs.current_editor()
        if editor:
            editor.toggle_bookmark()

    def next_bookmark(self) -> None:
        editor = self._editor_tabs.current_editor()
        if editor:
            editor.next_bookmark()

    def prev_bookmark(self) -> None:
        editor = self._editor_tabs.current_editor()
        if editor:
            editor.prev_bookmark()

    def toggle_fold_all(self) -> None:
        """折叠/展开全部 Markdown 标题。"""
        editor = self._editor_tabs.current_editor()
        if editor:
            editor.toggle_fold_all()
