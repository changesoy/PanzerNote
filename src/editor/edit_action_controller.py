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
