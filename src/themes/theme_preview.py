# -*- coding: utf-8 -*-
"""
主题预览对话框（B4：多包 + 变体选择）

提供实时预览、主题切换功能。
B4 起完全消费 v2：包列表 = themes/*/theme.json 目录，变体 = variants/*.json；
预览色块展示所选包/变体的 token 值（syntax 色合并 palette + overrides；
游戏侧 7 色固定读取 game_palette.json，不随明暗）。
"""

import json
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QSplitter, QWidget, QScrollArea, QFrame,
    QGroupBox, QFormLayout, QDialogButtonBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from ..utils.logger import get_logger
from ..game.game_palette import game_palette
from .theme_engine import ThemeEngine
from .theme_aware_mixin import ThemeAwareMixin
from .theme_v2.consumer import v2_active_variant, v2_color, v2_token
from .theme_v2.loader import ThemePackageLoader
from .theme_v2.renderer_registry import RendererRegistry
from .theme_v2.resources import PaletteRegistry, ThemeResourceContract
from .theme_v2.types import ThemeSnapshot
from .theme_v2.validator import ThemeValidator

_logger = get_logger(__name__)

#: v2 主题根目录（themes/，与 game_palette 同模式定位）。
_THEMES_ROOT = Path(__file__).resolve().parents[2] / "themes"

#: 包/变体显示辅助
def _variant_display_name(variant_id: str) -> str:
    if variant_id == "light":
        return "浅色 (light)"
    if variant_id == "dark":
        return "深色 (dark)"
    return variant_id


def _active_package_id(engine: ThemeEngine) -> str:
    """当前激活包 id（无 manager 时回退 default）。"""
    manager = getattr(engine, "theme_manager", None)
    pkg = getattr(manager, "active_package_id", None)
    return pkg or "default"


#: token 色块分组（B4：直接展示 v2 token 名，不依赖 v1 字段）
_TOKEN_SECTIONS: tuple[tuple[str, list[tuple[str, str]]], ...] = (
    ("通用颜色", [
        ("主色 (Accent)", "accent"),
        ("主色浅色 (Accent Soft)", "accent_soft"),
        ("强调前景 (On Accent)", "on_accent"),
        ("聚焦边框 (Focus)", "focus"),
        ("错误色 (Danger)", "danger"),
        ("背景色 (Surface Primary)", "surface_primary"),
        ("表面色 (Surface Secondary)", "surface_secondary"),
        ("浮层色 (Surface Raised)", "surface_raised"),
        ("主文本 (Text Primary)", "text_primary"),
        ("次文本 (Text Secondary)", "text_secondary"),
        ("禁用文本 (Text Muted)", "text_muted"),
        ("边框色 (Border Muted)", "border_muted"),
        ("强边框 (Border Strong)", "border_strong"),
    ]),
    ("编辑器颜色", [
        ("编辑器背景", "editor_background"),
        ("行号颜色", "editor_line_number"),
        ("当前行高亮", "editor_current_line"),
        ("括号匹配背景", "editor_bracket_match_bg"),
        ("括号匹配前景", "editor_bracket_match_fg"),
        ("未匹配括号", "editor_bracket_unmatched"),
    ]),
    ("UI 区域", [
        ("缩略图视口", "minimap_viewport"),
    ]),
    ("搜索高亮", [
        ("查找命中背景", "search_match_bg"),
        ("当前命中背景", "search_current_bg"),
        ("当前命中前景", "search_current_fg"),
    ]),
    ("书签与折叠", [
        ("书签背景", "editor_bookmark_bg"),
        ("书签前景", "editor_bookmark_fg"),
        ("折叠标记", "editor_fold_marker"),
        ("折叠标记(已折叠)", "editor_fold_marker_collapsed"),
    ]),
    ("代码块", [
        ("代码块背景", "md_preview_code_block_bg"),
        ("代码块边框", "md_preview_code_block_border"),
    ]),
    ("Markdown 高亮", [
        ("标题 H1", "md_h1_fg"),
        ("标题 H2", "md_h2_fg"),
        ("标题 H3", "md_h3_fg"),
        ("标题 H4-6", "md_h456_fg"),
        ("粗体", "md_bold_fg"),
        ("斜体", "md_italic_fg"),
        ("行内代码", "md_code_fg"),
        ("行内代码背景", "md_code_bg"),
        ("链接", "md_link_fg"),
        ("图片", "md_image_fg"),
        ("列表", "md_list_fg"),
        ("引用", "md_quote_fg"),
        ("分隔线", "md_hr_fg"),
        ("代码围栏", "md_fence_fg"),
        ("代码块文字", "md_code_block_fg"),
        ("代码块背景", "md_code_block_bg"),
    ]),
)

#: 语法高亮色块（值 = palette + overrides）
_SYNTAX_SECTION: tuple[str, list[tuple[str, str]]] = ("语法高亮", [
    ("关键字", "syntax_keyword"),
    ("类型关键字", "syntax_keyword_type"),
    ("内置名称", "syntax_builtin"),
    ("类名", "syntax_class"),
    ("函数名", "syntax_function"),
    ("变量", "syntax_variable"),
    ("标签", "syntax_tag"),
    ("命名空间", "syntax_namespace"),
    ("字符串", "syntax_string"),
    ("字符串转义", "syntax_string_escape"),
    ("字符串前缀", "syntax_string_affix"),
    ("文档字符串", "syntax_string_doc"),
    ("数字", "syntax_number"),
    ("注释", "syntax_comment"),
    ("运算符", "syntax_operator"),
    ("标点", "syntax_punctuation"),
    ("文本", "syntax_text"),
    ("错误", "syntax_error"),
    ("已删除", "syntax_deleted"),
    ("已插入", "syntax_inserted"),
    ("标题", "syntax_heading"),
    ("输出", "syntax_output"),
])

#: 游戏侧固定色（D28：值 = game_palette.json，不随明暗）
_GAME_SECTIONS: tuple[tuple[str, list[tuple[str, str]]], ...] = (
    ("游戏图标（固定）", [
        ("建造图标", "game_build"),
        ("车库图标", "game_garage"),
        ("图鉴图标", "game_collection"),
    ]),
    ("资源颜色（固定）", [
        ("燃料", "resource_fuel"),
        ("弹药", "resource_ammo"),
        ("钢材", "resource_steel"),
        ("铝材", "resource_bauxite"),
    ]),
)


class ThemePreviewWidget(QWidget):
    """多包 + 变体两级浏览 + 实时预览（B4）。"""

    #: 请求应用（package_id, variant_id）
    theme_applied = pyqtSignal(str, str)

    def __init__(self, theme_engine: ThemeEngine, parent=None):
        super().__init__(parent)
        self._engine = theme_engine
        self._current_package_id: str | None = None
        self._current_variant_id: str | None = None
        self._snapshot_cache: dict[str, ThemeSnapshot | None] = {}
        self._palettes: dict[str, dict[str, str]] | None = None
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

        self._package_label = QLabel("主题包")
        self._package_label.setObjectName("ThemePreviewSectionLabel")
        left_layout.addWidget(self._package_label)

        self._package_list = QListWidget()
        self._package_list.setObjectName("ThemeList")
        # 列表与面板同色无边框（VS Code 侧栏列表语义）：QSS border:none
        # 对 QFrame 原生 frame 绘制不生效，需显式去掉 frame
        self._package_list.setFrameShape(QFrame.Shape.NoFrame)
        self._package_list.currentItemChanged.connect(self._on_package_selected)
        left_layout.addWidget(self._package_list, 3)

        self._variant_label = QLabel("变体")
        self._variant_label.setObjectName("ThemePreviewSectionLabel")
        left_layout.addWidget(self._variant_label)

        self._variant_list = QListWidget()
        self._variant_list.setObjectName("ThemeList")
        self._variant_list.setFrameShape(QFrame.Shape.NoFrame)
        self._variant_list.currentItemChanged.connect(self._on_variant_selected)
        left_layout.addWidget(self._variant_list, 2)

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

        self._refresh_package_list()

    # ──────────────────────────────────────────────── 包 / 变体浏览
    def _scan_packages(self) -> list[tuple[str, str]]:
        """扫描 themes/*/theme.json → [(package_id, 包名)]，按目录名排序。"""
        packages: list[tuple[str, str]] = []
        for manifest in sorted(_THEMES_ROOT.glob("*/theme.json")):
            pkg_id = manifest.parent.name
            name = pkg_id
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("name"):
                    name = str(data["name"])
            except (OSError, ValueError):
                _logger.warning("读取包清单 %s 失败", manifest)
            packages.append((pkg_id, name))
        return packages

    def _refresh_package_list(self):
        self._package_list.blockSignals(True)
        self._package_list.clear()
        for pkg_id, name in self._scan_packages():
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, pkg_id)
            self._package_list.addItem(item)
        active = _active_package_id(self._engine)
        self._package_list.blockSignals(False)
        row = 0
        for i in range(self._package_list.count()):
            it = self._package_list.item(i)
            if it is not None and it.data(Qt.ItemDataRole.UserRole) == active:
                row = i
                break
        self._package_list.setCurrentRow(row)
        self._on_package_selected(self._package_list.currentItem())

    def _refresh_variant_list(self, package_id: str):
        self._variant_list.blockSignals(True)
        self._variant_list.clear()
        snapshot = self._load_package_snapshot(package_id)
        active: str | None = None
        if snapshot is not None:
            for vid in snapshot.variants:
                item = QListWidgetItem(_variant_display_name(vid))
                item.setData(Qt.ItemDataRole.UserRole, vid)
                self._variant_list.addItem(item)
            if package_id == _active_package_id(self._engine):
                active = v2_active_variant(self._engine)
            if active not in snapshot.variants:
                active = next(iter(snapshot.variants))
        self._variant_list.blockSignals(False)
        row = 0
        for i in range(self._variant_list.count()):
            it = self._variant_list.item(i)
            if it is not None and it.data(Qt.ItemDataRole.UserRole) == active:
                row = i
                break
        self._variant_list.setCurrentRow(row)
        self._on_variant_selected(self._variant_list.currentItem())

    def _on_package_selected(self, current: QListWidgetItem | None, previous=None):
        if current is None:
            return
        pkg_id = current.data(Qt.ItemDataRole.UserRole)
        self._current_package_id = pkg_id
        self._refresh_variant_list(pkg_id)

    def _on_variant_selected(self, current: QListWidgetItem | None, previous=None):
        if current is None:
            return
        if self._current_package_id is None:
            return
        vid = current.data(Qt.ItemDataRole.UserRole)
        self._current_variant_id = vid
        self._update_preview(self._current_package_id, vid)

    # ──────────────────────────────────────────────── 预览数据加载
    def _syntax_palettes(self) -> dict[str, dict[str, str]]:
        """共享 syntax palette（复用 service 已注册集合，只读缓存）。"""
        if self._palettes is None:
            svc = getattr(self._engine, "theme_v2", None)
            raw = svc.syntax_palettes() if svc is not None else {}
            self._palettes = {pid: dict(p) for pid, p in raw.items()}
        return self._palettes

    def _load_package_snapshot(self, package_id: str) -> ThemeSnapshot | None:
        """独立加载指定包为只读 snapshot（不激活，仅供预览）。失败返回 None。"""
        if package_id in self._snapshot_cache:
            return self._snapshot_cache[package_id]
        snapshot: ThemeSnapshot | None = None
        try:
            palettes = self._syntax_palettes()
            registry = PaletteRegistry()
            for pid, data in palettes.items():
                registry.register(pid, data)
            package = ThemePackageLoader().load(_THEMES_ROOT / package_id)
            validator = ThemeValidator(
                registry=RendererRegistry(),
                palette_registry=registry,
                resource_contract=ThemeResourceContract(
                    shared_root=_THEMES_ROOT / "syntax"
                ),
            )
            snapshot = validator.validate(package)
        except Exception:
            _logger.warning("预览加载包失败: %s", package_id, exc_info=True)
        self._snapshot_cache[package_id] = snapshot
        return snapshot

    # ──────────────────────────────────────────────── 预览渲染
    def _update_preview(self, package_id: str, variant_id: str):
        while self._preview_layout.count():
            child = self._preview_layout.takeAt(0)
            if child is not None:
                w = child.widget()
                if w is not None:
                    # deleteLater 延迟到下次事件循环才销毁；而下方立即 addWidget 会
                    # 在同一轮内插入新 group，旧 group 仍挂在父 widget 上被绘制，
                    # 造成新旧两个同位置 QGroupBox 标题"双重影"的视觉bug。
                    # setParent(None) 立即从可见层级移除，保证不参与本轮渲染。
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()

        snapshot = self._load_package_snapshot(package_id)
        if snapshot is None:
            self._info_label.setText(f"包 '{package_id}' 加载失败")
            return
        variant = snapshot.variants.get(variant_id)
        if variant is None:
            self._info_label.setText(f"包 '{package_id}' 无变体 '{variant_id}'")
            return

        tokens = dict(variant.tokens)
        syntax = dict(self._syntax_palettes().get(variant.syntax.palette, {}))
        syntax.update(variant.syntax.overrides)
        game = game_palette()
        is_dark = "dark" in variant_id

        info_group = QGroupBox("主题信息")
        info_layout = QFormLayout()
        info_layout.addRow("包:", QLabel(snapshot.name))
        info_layout.addRow("变体:", QLabel(_variant_display_name(variant_id)))
        info_layout.addRow("深色模式:", QLabel("是" if is_dark else "否"))
        info_group.setLayout(info_layout)
        self._preview_layout.addWidget(info_group)

        # B5：色块边框统一用当前 UI 主题的边框色（light/dark 下观感一致），
        # 色块内部填充仍展示被预览主题的色值。
        ui_border = v2_token(self._engine, "border_muted", "#E0E0E0")

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

        # 通用 / 编辑器 / UI 等子 section 保持同级，不额外嵌套外层
        # QGroupBox，保证每列的起始 X 坐标全局一致。
        for title, items in _TOKEN_SECTIONS:
            _add_swatch_section(title, [
                (label, tokens.get(key, "#000000")) for label, key in items
            ])
        _add_swatch_section(_SYNTAX_SECTION[0], [
            (label, syntax.get(key, "#000000")) for label, key in _SYNTAX_SECTION[1]
        ])
        for title, items in _GAME_SECTIONS:
            _add_swatch_section(title, [
                (label, game.get(key, "#000000")) for label, key in items
            ])

        self._preview_layout.addStretch()

        color_count = len(tokens) + len(syntax) + len(game)
        self._info_label.setText(
            f"预览: {snapshot.name} / {_variant_display_name(variant_id)} | "
            f"颜色数: {color_count} | {'深色' if is_dark else '浅色'}模式"
        )

    def _on_apply(self):
        """B7：对话框只发请求应用信号，不自行应用（9.1）。

        ``theme_applied`` 语义从「已应用」改为「请求应用」——切换序列统一
        收口到 main_window（唯一编排点），事务边界清晰。
        """
        if self._current_package_id and self._current_variant_id:
            self.theme_applied.emit(self._current_package_id, self._current_variant_id)


class ThemePreviewDialog(ThemeAwareMixin, QDialog):
    theme_applied = pyqtSignal(str, str)

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

    def _apply_theme_colors(self):
        """应用主题管理弹窗的局部样式（B5，根因 3 补全）。

        局部 QSS 对弹窗内动态生成内容（色块行标签、hex 值、分组标题、列表、
        按钮、滚动区）显式声明文字/背景色，深色下自洽可读；控件完整视觉
        （按钮 hover、列表选中态、滚动条滑块等）仍由全局 recipe 驱动。
        色块 swatch 展示的是被预览主题自身的色值，属于功能内容，不在此主题化。
        """
        # B8：字面量 = v1 light 值（dialog_bg/text_primary/text_secondary/border）
        dialog_bg = v2_color(self._engine, "dialog", "background", "#FFFFFF")
        text_primary = v2_token(self._engine, "text_primary", "#212121")
        text_secondary = v2_token(self._engine, "text_secondary", "#757575")
        border = v2_token(self._engine, "border_muted", "#E0E0E0")
        self.setStyleSheet(f"""
    QDialog {{
        background-color: {dialog_bg};
        color: {text_primary};
    }}

    QWidget#ThemePreviewWidget,
    QWidget#ThemePreviewLeftPanel,
    QWidget#ThemePreviewRightPanel,
    QWidget#ThemePreviewContent {{
        background-color: {dialog_bg};
        color: {text_primary};
    }}

    /* 根因 3：动态生成内容全部显式声明颜色，不依赖全局 QSS 恰好生效。 */
    QLabel {{
        color: {text_primary};
    }}

    QListWidget {{
        background-color: {dialog_bg};
        color: {text_primary};
        border: none;
    }}

    QGroupBox {{
        color: {text_primary};
    }}

    QPushButton {{
        color: {text_primary};
    }}

    QScrollBar {{
        background-color: {dialog_bg};
    }}

    QDialogButtonBox {{
        background-color: {dialog_bg};
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
        swatch_border = v2_token(self._engine, "border_muted", "#E0E0E0")
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

    def _on_theme_applied(self, package_id: str, variant_id: str):
        self.theme_applied.emit(package_id, variant_id)
