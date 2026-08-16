# -*- coding: utf-8 -*-
"""Theme v2 Core Controls 组件库（Wave 8 B3）。

统一视觉实现入口：recipe → resolved style → QSS 片段。

- B3 默认 renderer（default-v1）无 renderer_params，组件外观全部由 QSS 表达；
- ``available()`` 为 False（任一 Core recipe 缺失 / v2 未加载）时，外层
  ``generate_stylesheet`` 整段回退 v1（单次组装原子性，见 B3 设计文档 3.3）；
- Core Controls 只消费 B1 白名单 token + design 变量，不新增硬编码色。
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Mapping

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

# 已定义但 QSS 暂无法表达的键（预留：B6 polish / icons 资源提供后启用）。
# arrow/arrow_hover 需 image 资源；placeholder 需 palette 路径；indicator_checked_fg
# 需勾选图形 image。
_PENDING_KEYS: frozenset[str] = frozenset(
    {"arrow", "arrow_hover", "placeholder", "indicator_checked_fg"}
)


class ComponentState(Enum):
    """统一状态模型（B3 设计文档 2.2）。

    业务状态归 Stable Host 所有；视觉层只表现状态，不拥有状态。
    """

    NORMAL = "normal"
    HOVER = "hover"
    PRESSED = "pressed"
    FOCUS = "focus"
    DISABLED = "disabled"
    SELECTED = "selected"
    CHECKED = "checked"
    ACTIVE = "active"
    INDETERMINATE = "indeterminate"


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
    return f"""
QLineEdit, QSpinBox {{
    background-color: {s['background']};
    border: 1px solid {s['border']};
    border-radius: {s['radius']}px;
    padding: {pad_v}px {pad_h}px;
    color: {s['text']};
    selection-background-color: {s['selection_bg']};
}}
QLineEdit:focus, QSpinBox:focus {{ border-color: {s['focus_border']}; }}
QLineEdit:disabled, QSpinBox:disabled {{
    background-color: {s['disabled_background']};
    color: {s['disabled_text']};
}}
"""


def _b_combo_box(s: Mapping[str, Any]) -> str:
    pad_v, pad_h = s["padding"], s["padding"] * 2
    return f"""
QComboBox {{
    background-color: {s['background']};
    border: 1px solid {s['border']};
    border-radius: {s['radius']}px;
    padding: {pad_v}px {pad_h}px;
    color: {s['text']};
}}
QComboBox:focus {{ border-color: {s['focus_border']}; }}
QComboBox::drop-down {{
    border: none;
    width: 20px;
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
    return f"""
QScrollBar:vertical {{
    background-color: {s['track']};
    width: {w}px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background-color: {s['handle']};
    border-radius: {radius}px;
    min-height: {min_len}px;
    margin: {margin}px;
}}
QScrollBar::handle:vertical:hover {{ background-color: {s['handle_hover']}; }}
QScrollBar::handle:vertical:pressed {{ background-color: {s['handle_pressed']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background-color: {s['track']};
    height: {w}px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background-color: {s['handle']};
    border-radius: {radius}px;
    min-width: {min_len}px;
    margin: {margin}px;
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
    views = ("QTreeView", "QListView", "QListWidget")
    head = ", ".join(views)
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
    padding: 2px 4px;
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
    margin-top: 8px;
    padding-top: 16px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
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
