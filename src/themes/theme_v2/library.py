# -*- coding: utf-8 -*-
"""Theme v2 Core Controls 组件库（Wave 8 B3）。

统一视觉实现入口：recipe → resolved style → QSS 片段。

- B3 默认 renderer（default-v1）无 renderer_params，组件外观全部由 QSS 表达；
- ``available()`` 为 False（任一 Core recipe 缺失 / v2 未加载）时，外层
  ``generate_stylesheet`` 整段回退 v1（单次组装原子性，见 B3 设计文档 3.3）；
- Core Controls 只消费 B1 白名单 token + design 变量，不新增硬编码色。
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from ...utils.logger import get_logger
from .constants import COLOR_VALUE_PATTERN
from .service import ThemeV2Service

# 12 类 Core Controls（B3 设计文档 2.1）：Popup 由 combo_box recipe 的 popup_* 键
# 承载，故 recipe 键为 11 个。元组顺序即 QSS 拼接顺序。
CORE_RECIPES: tuple[str, ...] = (
    "button",
    "input",
    "combo_box",
    "menu",
    "context_menu",
    "checkbox",
    "radio",
    "slider",
    "scrollbar",
    "tooltip",
    "tree_item",
)

# 结构辅助 recipe（B3 设计文档 5.2 契约说明）：不在 Core 原子性判据内，存在则输出。
STRUCTURAL_RECIPES: tuple[str, ...] = ("group_box", "dialog")

# 已定义但 QSS 暂无法表达的键（预留：B6 polish 资源提供后启用）。
# arrow_hover 需 hover 态第二张 image；indicator_checked_fg 需勾选图形 image。
# arrow 已接线（combo_box 按 arrow token 颜色生成箭头 SVG）；
# placeholder 已随补漏 C 接线（QSS placeholder-text-color，仅 QLineEdit）。
_PENDING_KEYS: frozenset[str] = frozenset(
    {"arrow_hover", "indicator_checked_fg"}
)

# 箭头 SVG 模板（方向 → polygon 顶点）：颜色由 recipe 的 arrow token 解析值填充。
_ARROW_SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">'
    '<polygon points="{points}" fill="{color}"/></svg>'
)
_ARROW_POINTS = {"down": "5,7 1.5,3 8.5,3", "up": "5,3 1.5,7 8.5,7"}


def _arrow_image_url(color: str, direction: str = "down") -> str:
    """按 arrow token 颜色生成（并缓存）箭头 SVG，返回 QSS image url。

    Qt QSS 的 ``::down-arrow``/``::up-arrow`` 无法给 image 重新上色，故按 token
    颜色落成独立 SVG 文件；颜色变则文件名变，天然跟随主题变体切换。
    生成失败时返回空串（该控件退化为无箭头），并记录警告，不静默吞掉。
    """
    cache_dir = Path(tempfile.gettempdir()) / "PanzerNote" / "theme_icons"
    path = cache_dir / f"{direction}_arrow_{color.lstrip('#').lower()}.svg"
    try:
        if not path.exists():
            cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(
                _ARROW_SVG_TEMPLATE.format(points=_ARROW_POINTS[direction], color=color),
                encoding="utf-8",
            )
    except OSError as e:
        get_logger(__name__).warning("生成箭头图标失败: %s", e)
        return ""
    return str(path).replace("\\", "/")


class ThemeComponentLibrary:
    """唯一视觉实现入口：recipe → resolved style → QSS 片段。"""

    def __init__(self, service: ThemeV2Service) -> None:
        self._service = service

    # ──────────────────────────────────────────────── 可用性
    def available(self) -> bool:
        """Core Controls 是否可整段解析（任一缺失 → False，外层回退 v1）。"""
        if self._service.snapshot() is None:
            return False
        return all(self._service.recipe(key) is not None for key in CORE_RECIPES)

    # ──────────────────────────────────────────────── 解析
    def resolve(self, component: str, variant_id: str | None = None) -> dict[str, Any] | None:
        """recipe.style → 已解析 style（token / 直接色值 / design 引用 → 实际值）。

        ``variant_id`` 指定 variant 时按该变体解析（B3：全局 QSS 需按传入主题
        明暗选色）；未指定时取当前激活 variant。
        """
        recipe = self._service.recipe(component)
        variant = self._service.variant_snapshot(variant_id)
        if recipe is None or variant is None:
            return None
        tokens = variant.tokens
        design = self._service.design()
        out: dict[str, Any] = {}
        for key, value in recipe.style.items():
            if isinstance(value, str) and value in tokens:
                out[key] = tokens[value]
            elif isinstance(value, str) and (
                value == "transparent" or bool(COLOR_VALUE_PATTERN.fullmatch(value))
            ):
                out[key] = value
            elif isinstance(value, str) and design is not None and value.startswith("space_"):
                out[key] = design.spacing.get(value, value)
            elif isinstance(value, str) and design is not None and value.startswith("radius_"):
                out[key] = design.radius.get(value, value)
            else:
                out[key] = value
        return out

    # ──────────────────────────────────────────────── QSS 生成
    def qss(self, component: str, variant_id: str | None = None) -> str:
        s = self.resolve(component, variant_id)
        if s is None:
            return ""
        builder = _QSS_BUILDERS.get(component)
        if builder is None:
            return ""
        return builder(s)

    def all_qss(self, variant_id: str | None = None) -> str:
        parts = []
        for key in CORE_RECIPES:
            s = self.resolve(key, variant_id)
            if s is not None and key in _QSS_BUILDERS:
                parts.append(_QSS_BUILDERS[key](s))
        for key in STRUCTURAL_RECIPES:
            s = self.resolve(key, variant_id)
            if s is not None and key in _QSS_BUILDERS:
                parts.append(_QSS_BUILDERS[key](s))
        return "\n".join(parts)


# ──────────────────────────────────────────────── QSS 模板（default-v1 renderer）
# padding 为垂直基准（px），水平 ×2 展开（B3 设计文档 5.2 契约说明）。


def _b_button(s: Mapping[str, Any]) -> str:
    pad_v, pad_h = s["padding"], s["padding"] * 2
    return f"""
QPushButton {{
    background-color: {s['background']};
    color: {s['text']};
    border: 1px solid {s['border']};
    padding: {pad_v}px {pad_h}px;
    border-radius: {s['radius']}px;
}}
QPushButton:hover {{ background-color: {s['hover_background']}; }}
QPushButton:pressed {{ background-color: {s['pressed_background']}; }}
QPushButton:disabled {{
    background-color: {s['disabled_background']};
    color: {s['disabled_text']};
}}
QPushButton:focus {{ border: 1px solid {s['focus_border']}; }}
"""


def _b_input(s: Mapping[str, Any]) -> str:
    pad_v, pad_h = s["padding"], s["padding"] * 2
    # QSpinBox 上下按钮必须显式声明几何：只给 QSS 基础盒（padding/border）时
    # QStyleSheetStyle 会把 SC_SpinBoxUp/Down 的命中矩形算成「左右并排」，
    # 导致点加号无效（点到的其实是减号）。箭头同样只能靠 token 上色的 SVG。
    # 按钮带几何与 combo_box 的 drop-down 完全一致（宽 24 / origin padding /
    # 右 padding 26），保证同一表单列里两类控件的箭头落在同一竖线上。
    spin_w = 24
    spin_pad_r = 26
    up_url = _arrow_image_url(s["arrow"], "up")
    down_url = _arrow_image_url(s["arrow"], "down")
    arrow_rules = ""
    if up_url and down_url:
        arrow_rules = f"""
QSpinBox::up-arrow {{ image: url("{up_url}"); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url("{down_url}"); width: 10px; height: 10px; }}
"""
    # 补漏 C：placeholder 接线（QSS placeholder-text-color，QSpinBox 无该概念故拆分）
    return f"""
QLineEdit, QSpinBox {{
    background-color: {s['background']};
    border: 1px solid {s['border']};
    border-radius: {s['radius']}px;
    padding: {pad_v}px {pad_h}px;
    color: {s['text']};
    selection-background-color: {s['selection_bg']};
}}
QSpinBox {{ padding-right: {spin_pad_r}px; }}
QSpinBox::up-button {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: {spin_w}px;
    border: none;
    background: transparent;
}}
QSpinBox::down-button {{
    subcontrol-origin: padding;
    subcontrol-position: bottom right;
    width: {spin_w}px;
    border: none;
    background: transparent;
}}
{arrow_rules}QLineEdit {{ placeholder-text-color: {s['placeholder']}; }}
QLineEdit:focus, QSpinBox:focus {{ border-color: {s['focus_border']}; }}
QLineEdit:disabled, QSpinBox:disabled {{
    background-color: {s['disabled_background']};
    color: {s['disabled_text']};
}}
"""


def _b_combo_box(s: Mapping[str, Any]) -> str:
    pad_v, pad_h = s["padding"], s["padding"] * 2
    arrow_url = _arrow_image_url(s["arrow"])
    arrow_rule = f'image: url("{arrow_url}");' if arrow_url else ""
    return f"""
QComboBox, QFontComboBox {{
    background-color: {s['background']};
    border: 1px solid {s['border']};
    border-radius: {s['radius']}px;
    padding: {pad_v}px 26px {pad_v}px {pad_h}px;
    color: {s['text']};
}}
QComboBox:focus, QFontComboBox:focus {{ border-color: {s['focus_border']}; }}
QComboBox::drop-down, QFontComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: right center;
    border: none;
    width: 24px;
}}
QComboBox::down-arrow, QFontComboBox::down-arrow {{
    {arrow_rule}
    width: 10px;
    height: 10px;
}}
QComboBox QAbstractItemView {{
    background-color: {s['popup_background']};
    border: 1px solid {s['popup_border']};
    outline: none;
    selection-background-color: {s['item_selected_bg']};
    selection-color: {s['item_selected_text']};
}}
"""


def _b_menu(s: Mapping[str, Any]) -> str:
    return f"""
QMenu {{
    background-color: {s['background']};
    color: {s['text']};
    border: 1px solid {s['border']};
    border-radius: {s['radius']}px;
    padding: {s['padding']}px;
}}
QMenu::item {{
    padding: {s['padding']}px 32px {s['padding']}px 12px;
}}
QMenu::item:selected {{
    background-color: {s['selected_background']};
    color: {s['selected_text']};
}}
QMenu::item:disabled {{
    color: {s['disabled_text']};
}}
QMenu::separator {{
    height: 1px;
    background-color: {s['separator']};
    margin: {s['padding']}px 8px;
}}
"""


def _b_checkbox(s: Mapping[str, Any]) -> str:
    return f"""
QCheckBox {{
    color: {s['text']};
}}
QCheckBox:disabled {{
    color: {s['disabled_text']};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {s['indicator_border']};
    border-radius: {s['indicator_radius']}px;
    background-color: transparent;
}}
QCheckBox::indicator:hover {{
    border-color: {s['indicator_hover_border']};
}}
QCheckBox::indicator:checked {{
    background-color: {s['indicator_checked_bg']};
    border-color: {s['indicator_checked_bg']};
}}
QCheckBox::indicator:indeterminate {{
    background-color: {s['indicator_checked_bg']};
    border-color: {s['indicator_checked_bg']};
}}
"""


def _b_radio(s: Mapping[str, Any]) -> str:
    return f"""
QRadioButton {{
    color: {s['text']};
}}
QRadioButton:disabled {{
    color: {s['disabled_text']};
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {s['indicator_border']};
    border-radius: {s['indicator_radius']}px;
    background-color: transparent;
}}
QRadioButton::indicator:hover {{
    border-color: {s['indicator_hover_border']};
}}
QRadioButton::indicator:checked {{
    background-color: {s['indicator_checked_bg']};
    border-color: {s['indicator_checked_bg']};
}}
"""


def _b_slider(s: Mapping[str, Any]) -> str:
    return f"""
QSlider::groove:horizontal {{
    background-color: {s['groove_bg']};
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background-color: {s['handle_bg']};
    width: 14px;
    margin: -5px 0;
    border-radius: {s['handle_radius']}px;
}}
QSlider::handle:horizontal:hover {{
    background-color: {s['handle_hover']};
}}
"""


def _b_scrollbar(s: Mapping[str, Any]) -> str:
    w, min_len, margin = s["width"], s["min_len"], s["margin"]
    radius = w // 2
    # Qt QSS 关键点（Windows 下双重验证）：
    # 1) ::handle 设置 margin 会使 border-radius 被忽略（方角）→ 改 margin: 0，
    #    用与 track 同色的 border 做内缩，圆角正常且不可见。
    # 2) 外框 background-color 不足以覆盖 QAbstractScrollArea 的 native gutter
    #    底色（灰竖条）→ 外框透明，groove + add/sub-page 三处统一画 track 色。
    inset = f"border: {margin}px solid {s['track']};"
    return f"""
QScrollBar:vertical {{
    background: transparent;
    width: {w}px;
    margin: 0;
}}
QScrollBar::groove:vertical {{
    background-color: {s['track']};
    border: none;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background-color: {s['track']};
}}
QScrollBar::handle:vertical {{
    background-color: {s['handle']};
    {inset}
    border-radius: {radius}px;
    min-height: {min_len}px;
    margin: 0;
}}
QScrollBar::handle:vertical:hover {{ background-color: {s['handle_hover']}; }}
QScrollBar::handle:vertical:pressed {{ background-color: {s['handle_pressed']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent;
    height: {w}px;
    margin: 0;
}}
QScrollBar::groove:horizontal {{
    background-color: {s['track']};
    border: none;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background-color: {s['track']};
}}
QScrollBar::handle:horizontal {{
    background-color: {s['handle']};
    {inset}
    border-radius: {radius}px;
    min-width: {min_len}px;
    margin: 0;
}}
QScrollBar::handle:horizontal:hover {{ background-color: {s['handle_hover']}; }}
QScrollBar::handle:horizontal:pressed {{ background-color: {s['handle_pressed']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
"""


def _b_tooltip(s: Mapping[str, Any]) -> str:
    pad_v, pad_h = s["padding"], s["padding"] * 2
    return f"""
QToolTip {{
    background-color: {s['background']};
    color: {s['text']};
    border: 1px solid {s['border']};
    border-radius: {s['radius']}px;
    padding: {pad_v}px {pad_h}px;
}}
"""


def _b_tree_item(s: Mapping[str, Any]) -> str:
    # B4：Tree/List 状态（B3 文档 2.1 组件 12 含 QListView/QListWidget）。
    # QListWidget 是 QListView 子类，QTreeView 选择器不覆盖它，故一并列出。
    # B6：补 pressed 态（按下变深，VS Code 列表交互）与拖拽 drop indicator
    # （8.1 拖拽视觉：目标落点线）。drop-indicator 仅 QTreeView 支持样式化。
    #
    # B6 修正（渲染实测）："QTreeView, QListView, QListWidget::xxx" 逗号混排
    # 会让 ::xxx 只附着最后一项，前面的退化为裸类型选择器——子控件规则
    # （::viewport/::item 系列）必须逐选择器独立成段。viewport 不继承
    # view 的 QSS 背景，缺失时无 item 的空白区回落到原生绘制色。
    #
    # 补漏 C：padding 走 recipe（space_1 → 2px 4px，与 button/input 垂直基准 ×2
    # 语义一致）；icon_size 接线为 QSS icon-size（Qt 6 支持 QListView/QTreeView）。
    # indent 键为 QSS 不可表达（QTreeView::indentation 仅代码属性），保留为元数据。
    views = ("QTreeView", "QListView", "QListWidget")
    head = ", ".join(views)
    pad_v = s.get("padding", 2)
    pad_h = pad_v * 2
    icon_size = s.get("icon_size", 16)
    parts = [f"""
{head} {{
    background-color: {s['background']};
    color: {s['text']};
    border: none;
}}"""]
    for v in views:
        parts.append(f"""
{v}::viewport {{
    background-color: {s['background']};
}}""")
        parts.append(f"""
{v}::item {{
    padding: {pad_v}px {pad_h}px;
    icon-size: {icon_size}px;
}}""")
        parts.append(f"""
{v}::item:selected {{
    background-color: {s['selected_background']};
    color: {s['selected_text']};
}}""")
        parts.append(f"""
{v}::item:hover:!selected {{
    background-color: {s['hover_background']};
}}""")
        parts.append(f"""
{v}::item:pressed:!selected {{
    background-color: {s['pressed_background']};
}}""")
    parts.append(f"""
QTreeView::drop-indicator {{
    border: 2px solid {s['drop_indicator']};
}}""")
    return "\n".join(parts) + "\n"


def _b_group_box(s: Mapping[str, Any]) -> str:
    return f"""
QGroupBox {{
    color: {s['text']};
    border: 1px solid {s['border']};
    border-radius: {s['radius']}px;
    margin-top: 2em;
    padding-top: 6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    top: 0.5em;
    left: 8px;
    padding: 0 4px;
}}
"""


def _b_dialog(s: Mapping[str, Any]) -> str:
    return f"""
QDialog {{
    background-color: {s['background']};
    color: {s['text']};
}}
QMessageBox {{
    background-color: {s['background']};
}}
/* 对话框内 QScrollArea 的 viewport/内容容器默认不继承 QDialog 背景，
   会露出 QPalette.Base 浅色（如记事本设置滚动区），需显式覆盖。
   objectName 级规则（如 ThemePreviewArea）优先级更高，不受影响。 */
QDialog QScrollArea {{
    background-color: {s['background']};
    border: none;
}}
QDialog QScrollArea > QWidget,
QDialog QScrollArea > QWidget > QWidget {{
    background-color: {s['background']};
}}
"""


_QSS_BUILDERS: dict[str, Callable[[Mapping[str, Any]], str]] = {
    "button": _b_button,
    "input": _b_input,
    "combo_box": _b_combo_box,
    "menu": _b_menu,
    # QSS 无法区分普通 QMenu 与 Context Menu，context_menu 视觉与 menu 一致，共用模板。
    "context_menu": _b_menu,
    "checkbox": _b_checkbox,
    "radio": _b_radio,
    "slider": _b_slider,
    "scrollbar": _b_scrollbar,
    "tooltip": _b_tooltip,
    "tree_item": _b_tree_item,
    "group_box": _b_group_box,
    "dialog": _b_dialog,
}
