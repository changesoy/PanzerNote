# -*- coding: utf-8 -*-
"""
主题预览对话框

提供实时预览、主题切换和自定义调整功能。
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QSplitter, QWidget, QScrollArea, QFrame,
    QGroupBox, QFormLayout, QCheckBox, QDialogButtonBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette

from .theme_engine import ThemeEngine, ThemeDefinition, ThemeColorScheme
from .theme_aware_mixin import ThemeAwareMixin
from .theme_v2.consumer import v2_color, v2_token


class ThemePreviewWidget(QWidget):
    theme_applied = pyqtSignal(str)

    def __init__(self, theme_engine: ThemeEngine, parent=None):
        super().__init__(parent)
        self._engine = theme_engine
        self._current_theme_id = None
        self._setup_ui()

    def _setup_ui(self):
        self.setObjectName("ThemePreviewWidget")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setObjectName("ThemePreviewSplitter")
        layout.addWidget(self._splitter)

        left_panel = QWidget()
        left_panel.setObjectName("ThemePreviewLeftPanel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._available_label = QLabel("可用主题")
        self._available_label.setObjectName("ThemePreviewSectionLabel")
        left_layout.addWidget(self._available_label)

        self._theme_list = QListWidget()
        self._theme_list.setObjectName("ThemeList")
        # 列表与面板同色无边框（VS Code 侧栏列表语义）：QSS border:none
        # 对 QFrame 原生 frame 绘制不生效，需显式去掉 frame
        self._theme_list.setFrameShape(QFrame.Shape.NoFrame)
        self._theme_list.currentItemChanged.connect(self._on_theme_selected)
        left_layout.addWidget(self._theme_list)

        self._apply_btn = QPushButton("应用主题")
        self._apply_btn.setObjectName("ApplyThemeButton")
        self._apply_btn.clicked.connect(self._on_apply)
        left_layout.addWidget(self._apply_btn)

        self._splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_panel.setObjectName("ThemePreviewRightPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._preview_area = QScrollArea()
        self._preview_area.setObjectName("ThemePreviewArea")
        self._preview_area.setWidgetResizable(True)
        self._preview_content = QWidget()
        self._preview_content.setObjectName("ThemePreviewContent")
        self._preview_layout = QVBoxLayout(self._preview_content)
        self._preview_area.setWidget(self._preview_content)
        right_layout.addWidget(self._preview_area)

        self._info_label = QLabel("选择一个主题进行预览")
        self._info_label.setObjectName("ThemeInfoLabel")
        right_layout.addWidget(self._info_label)

        self._splitter.addWidget(right_panel)
        self._splitter.setSizes([200, 500])

        self._refresh_theme_list()

    def _refresh_theme_list(self):
        self._theme_list.clear()
        themes = self._engine.get_all_themes()
        for theme_id, theme in themes.items():
            item = QListWidgetItem(theme.name)
            item.setData(Qt.ItemDataRole.UserRole, theme_id)
            if theme.is_dark:
                item.setText(f"{theme.name} (深色)")
            self._theme_list.addItem(item)

        active = self._engine.get_active_theme()
        for i in range(self._theme_list.count()):
            theme_item = self._theme_list.item(i)
            if theme_item is not None and theme_item.data(Qt.ItemDataRole.UserRole) == active.id:
                self._theme_list.setCurrentItem(theme_item)
                break

    def _on_theme_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        if current is None:
            return
        theme_id = current.data(Qt.ItemDataRole.UserRole)
        theme = self._engine.get_theme(theme_id)
        if theme:
            self._current_theme_id = theme_id
            self._update_preview(theme)

    def _update_preview(self, theme: ThemeDefinition):
        while self._preview_layout.count():
            child = self._preview_layout.takeAt(0)
            if child is not None:
                w = child.widget()
                if w is not None:
                    w.deleteLater()

        info_group = QGroupBox("主题信息")
        info_layout = QFormLayout()
        info_layout.addRow("名称:", QLabel(theme.name))
        info_layout.addRow("版本:", QLabel(theme.version))
        info_layout.addRow("作者:", QLabel(theme.author or "未知"))
        info_layout.addRow("描述:", QLabel(theme.description or "无"))
        is_dark_label = QLabel("是" if theme.is_dark else "否")
        info_layout.addRow("深色模式:", is_dark_label)
        info_group.setLayout(info_layout)
        self._preview_layout.addWidget(info_group)

        c = theme.colors
        # B5：色块边框统一用当前 UI 主题的边框色（light/dark 下观感一致），
        # 色块内部填充仍展示被预览主题的色值。
        ui_border = v2_token(self._engine, "border_muted",
                             self._engine.get_active_theme().colors.border)

        # ── 颜色预览辅助：所有 section 同一构造函数，保证列对齐一致 ──
        def _build_swatch_row(label_text, color_hex):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.setContentsMargins(0, 0, 0, 0)
            swatch = QLabel()
            swatch.setObjectName("ColorSwatch")
            swatch.setProperty("swatchColor", color_hex)
            swatch.setFixedSize(48, 22)
            swatch.setStyleSheet(
                f"background-color: {color_hex}; "
                f"border: 1px solid {ui_border}; border-radius: 3px;"
            )
            label = QLabel(label_text)
            label.setMinimumWidth(170)
            hex_label = QLabel(color_hex)
            hex_label.setFont(QFont("Consolas", 9))
            hex_label.setMinimumWidth(70)
            hex_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(swatch, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            row.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            row.addStretch(1)
            row.addWidget(hex_label, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
            return row

        def _add_swatch_section(title, items):
            group = QGroupBox(title)
            vbox = QVBoxLayout()
            vbox.setSpacing(4)
            vbox.setContentsMargins(9, 6, 9, 6)
            for label_text, color_hex in items:
                vbox.addLayout(_build_swatch_row(label_text, color_hex))
            group.setLayout(vbox)
            self._preview_layout.addWidget(group)

        # 通用 / 编辑器 / UI 三个子 section 和 资源/交互状态 等保持同级，
        # 不额外嵌套外层 QGroupBox，保证每列的起始 X 坐标全局一致。
        _add_swatch_section("通用颜色", [
            ("主色 (Primary)", c.primary),
            ("主色深色 (Primary Dark)", c.primary_dark),
            ("主色浅色 (Primary Light)", c.primary_light),
            ("强调色 (Accent)", c.accent),
            ("背景色 (Background)", c.background),
            ("表面色 (Surface)", c.surface),
            ("卡片色 (Card)", c.card),
            ("主文本 (Text)", c.text_primary),
            ("次文本 (Text Secondary)", c.text_secondary),
            ("禁用文本 (Text Disabled)", c.text_disabled),
            ("边框色 (Border)", c.border),
            ("分割线 (Divider)", c.divider),
            ("错误色 (Error)", c.error),
            ("警告色 (Warning)", c.warning),
            ("成功色 (Success)", c.success),
            ("信息色 (Info)", c.info),
        ])

        _add_swatch_section("编辑器颜色", [
            ("编辑器背景", c.editor_bg),
            ("行号颜色", c.editor_line_number),
            ("当前行高亮", c.editor_current_line),
            ("文本选中", c.editor_selection),
            ("括号匹配背景", c.editor_bracket_match_bg),
            ("括号匹配前景", c.editor_bracket_match_fg),
            ("未匹配括号", c.editor_bracket_unmatched),
        ])

        _add_swatch_section("UI 区域颜色", [
            ("侧边栏背景", c.sidebar_bg),
            ("状态栏背景", c.statusbar_bg),
            ("菜单栏背景", c.menubar_bg),
            ("对话框背景", c.dialog_bg),
            ("缩略图背景", c.minimap_bg),
            ("缩略图视口", c.minimap_viewport),
            ("小秘书气泡背景", c.secretary_bubble_bg),
            ("小秘书气泡边框", c.secretary_bubble_border),
        ])

        _add_swatch_section("资源颜色", [
            ("燃料", c.resource_fuel),
            ("弹药", c.resource_ammo),
            ("钢材", c.resource_steel),
            ("铝材", c.resource_bauxite),
        ])

        _add_swatch_section("交互状态", [
            ("强调色前景", c.accent_fg),
            ("悬停背景", c.hover_bg),
            ("激活背景", c.active_bg),
            ("聚焦边框", c.focus_border),
            ("选区背景", c.selection_bg),
            ("选区前景", c.selection_fg),
        ])

        _add_swatch_section("搜索高亮", [
            ("查找命中背景", c.search_match_bg),
            ("当前命中背景", c.search_current_bg),
            ("当前命中前景", c.search_current_fg),
        ])

        _add_swatch_section("书签与折叠", [
            ("书签背景", c.editor_bookmark_bg),
            ("书签前景", c.editor_bookmark_fg),
            ("折叠标记", c.editor_fold_marker),
            ("折叠标记(已折叠)", c.editor_fold_marker_collapsed),
        ])

        _add_swatch_section("代码块", [
            ("代码块背景", c.bg_codeblock),
            ("代码块边框", c.codeblock_border),
        ])

        _add_swatch_section("游戏图标", [
            ("建造图标", c.game_build),
            ("车库图标", c.game_garage),
            ("图鉴图标", c.game_collection),
        ])

        _add_swatch_section("Markdown 高亮", [
            ("标题 H1", c.md_h1_fg),
            ("标题 H2", c.md_h2_fg),
            ("标题 H3", c.md_h3_fg),
            ("标题 H4-6", c.md_h456_fg),
            ("粗体", c.md_bold_fg),
            ("斜体", c.md_italic_fg),
            ("行内代码", c.md_code_fg),
            ("行内代码背景", c.md_code_bg),
            ("链接", c.md_link_fg),
            ("图片", c.md_image_fg),
            ("列表", c.md_list_fg),
            ("引用", c.md_quote_fg),
            ("分隔线", c.md_hr_fg),
            ("代码围栏", c.md_fence_fg),
            ("代码块文字", c.md_code_block_fg),
            ("代码块背景", c.md_code_block_bg),
        ])

        _add_swatch_section("语法高亮", [
            ("关键字", c.syntax_keyword),
            ("类型关键字", c.syntax_keyword_type),
            ("内置名称", c.syntax_builtin),
            ("类名", c.syntax_class),
            ("函数名", c.syntax_function),
            ("变量", c.syntax_variable),
            ("标签", c.syntax_tag),
            ("命名空间", c.syntax_namespace),
            ("字符串", c.syntax_string),
            ("字符串转义", c.syntax_string_escape),
            ("字符串前缀", c.syntax_string_affix),
            ("文档字符串", c.syntax_string_doc),
            ("数字", c.syntax_number),
            ("注释", c.syntax_comment),
            ("运算符", c.syntax_operator),
            ("标点", c.syntax_punctuation),
            ("文本", c.syntax_text),
            ("错误", c.syntax_error),
            ("已删除", c.syntax_deleted),
            ("已插入", c.syntax_inserted),
            ("标题", c.syntax_heading),
            ("输出", c.syntax_output),
        ])

        self._preview_layout.addStretch()

        self._info_label.setText(
            f"预览主题: {theme.name} | "
            f"颜色数: {len(c.to_dict())} | "
            f"{'深色' if theme.is_dark else '浅色'}模式"
        )

    def _on_apply(self):
        if self._current_theme_id:
            self._engine.set_active_theme(self._current_theme_id)
            self.theme_applied.emit(self._current_theme_id)


class ThemePreviewDialog(ThemeAwareMixin, QDialog):
    theme_applied = pyqtSignal(str)

    def __init__(self, theme_engine: ThemeEngine, parent=None):
        super().__init__(parent)
        self._engine = theme_engine
        self._setup_ui()
        self._init_theme(self._engine)

    def _setup_ui(self):
        self.setObjectName("ThemePreviewDialog")
        self.setWindowTitle("主题管理")
        self.setMinimumSize(700, 500)

        layout = QVBoxLayout(self)

        self._preview_widget = ThemePreviewWidget(self._engine, self)
        self._preview_widget.theme_applied.connect(self._on_theme_applied)
        layout.addWidget(self._preview_widget)

        self._button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self._button_box.setObjectName("ThemeDialogButtonBox")
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

    def _apply_theme_colors(self, colors: ThemeColorScheme):
        """应用主题管理弹窗的局部样式（B5）。

        只处理全局 QSS 未覆盖的结构区域：面板容器背景、次级标签、预览滚动区。
        QDialog/QListWidget/QGroupBox/QCheckBox/QPushButton/QScrollBar/QSplitter
        由全局 recipe（dialog/tree_item/group_box/checkbox/button/scrollbar）驱动。
        色块 swatch 展示的是被预览主题自身的色值，属于功能内容，不在此主题化。
        """
        dialog_bg = v2_color(self._engine, "dialog", "background", colors.dialog_bg)
        text_primary = v2_token(self._engine, "text_primary", colors.text_primary)
        text_secondary = v2_token(self._engine, "text_secondary", colors.text_secondary)
        border = v2_token(self._engine, "border_muted", colors.border)
        self.setStyleSheet(f"""
    QWidget#ThemePreviewWidget,
    QWidget#ThemePreviewLeftPanel,
    QWidget#ThemePreviewRightPanel,
    QWidget#ThemePreviewContent {{
        background-color: {dialog_bg};
        color: {text_primary};
    }}

    QLabel#ThemePreviewSectionLabel,
    QLabel#ThemeInfoLabel {{
        color: {text_secondary};
    }}

    /* B6：预览区不设边框——左面板无边框，右侧保留 1px 边框会在
       左面板边缘露出一道细线，观感不对称；分组结构由 QGroupBox 承担。 */
    QScrollArea#ThemePreviewArea {{
        background-color: {dialog_bg};
        border: none;
        border-radius: 4px;
    }}

    QScrollArea#ThemePreviewArea > QWidget {{
        background-color: {dialog_bg};
    }}

    /* 左右面板同为 dialog 背景时 splitter 分隔线多余（B6）：
       覆盖全局结构段的 handle 背景；拖拽调宽功能不受影响。 */
    QSplitter::handle {{
        background-color: transparent;
    }}
    """)

        # B5：切 UI 主题时即时刷新色块边框（swatch 为动态生成，点击主题才会重建）
        swatch_border = v2_token(self._engine, "border_muted", colors.border)
        for swatch in self.findChildren(QLabel, "ColorSwatch"):
            color_hex = swatch.property("swatchColor")
            if color_hex:
                swatch.setStyleSheet(
                    f"background-color: {color_hex};"
                    f" border: 1px solid {swatch_border}; border-radius: 2px;"
                )

        # QScrollArea 的 viewport 有时不会完全继承父级背景，显式补一次。
        preview_widget = getattr(self, "_preview_widget", None)
        preview_area = getattr(preview_widget, "_preview_area", None)
        preview_content = getattr(preview_widget, "_preview_content", None)

        if preview_area is not None:
            preview_area.viewport().setStyleSheet(
                f"background-color: {dialog_bg};"
            )

        if preview_content is not None:
            preview_content.setStyleSheet(
                f"background-color: {dialog_bg};"
            )

    def _on_theme_applied(self, theme_id: str):
        self.theme_applied.emit(theme_id)
