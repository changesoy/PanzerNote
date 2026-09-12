# -*- coding: utf-8 -*-
"""
记事本设置对话框

v1.5.4 新增
v1.5.5 改动：
  - 「自动缩略图（仅代码文件）」→「自动开关缩略图」
  - 增加字体选择功能（使用本地字体库）
  - 字体大小现在可以正确应用到编辑器
  - 显示行号 / 高亮当前行开关现在可以正确应用
"""

import time

from PyQt6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QPushButton, QSpinBox, QDoubleSpinBox, QComboBox, QGroupBox, QFormLayout,
    QFontComboBox, QSlider, QScrollArea, QApplication
)
from PyQt6.QtCore import QObject, QEvent, QTimer, Qt
from PyQt6.QtGui import QFont, QWheelEvent

from ..core.config import Config
from ..core.settings_store import LINE_SPACING_MAX, LINE_SPACING_MIN
from ..utils.feature_flags import is_enabled as _feature_is_enabled


class _WheelGuard(QObject):
    """按控件类别管理滚轮行为，避免滚动设置对话框时误改取值。

    焦点判据在这里不可用：对话框弹出时焦点默认落在第一个可聚焦控件（数字框）上，
    且 QLineEdit 是 spinbox 的 focus proxy，实测 hasFocus() 恒为真。故改用
    **滚动条是否刚移动过**判定「是否正在滚动」，并按控件类别分流：

    - 数值类（QSpinBox / QSlider）：正在滚动时把滚轮转交滚动区（只滚不改）；
      界面静止时放行，滚轮正常作用于控件（悬停即可调值，无需点击）。
    - 选择类（QComboBox / QFontComboBox）：一律转交滚动区，滚轮永不改选项。

    过滤器还必须覆盖**鼠标实际落点**：QSpinBox / QFontComboBox 的中心是其内部
    QLineEdit（childAt 实测），只装在控件自身不会触发，故登记时一并覆盖内部
    编辑框，并按 parentWidget 链回溯识别受保护控件。
    """

    #: 判定「仍在滚动」的时间窗（秒）
    _SCROLL_QUIET_SECONDS = 0.3

    def __init__(self, scroll_area: QScrollArea, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._viewport = scroll_area.viewport()
        self._value_widgets: set[QWidget] = set()
        self._selection_widgets: set[QWidget] = set()
        self._last_scroll_at = 0.0
        for scrollbar in (
            scroll_area.verticalScrollBar(),
            scroll_area.horizontalScrollBar(),
        ):
            if scrollbar is not None:  # 横向滚动条可能未创建
                scrollbar.valueChanged.connect(self._on_scrolled)

    def guard_value(self, widget: QWidget) -> None:
        """登记数值类控件：界面静止时滚轮可调值"""
        self._value_widgets.add(widget)
        self._install(widget)

    def guard_selection(self, widget: QWidget) -> None:
        """登记选择类控件：滚轮永不改选项"""
        self._selection_widgets.add(widget)
        self._install(widget)

    def _install(self, widget: QWidget) -> None:
        """对控件及其内部编辑框安装过滤器（内部编辑框才是鼠标实际落点）"""
        widget.installEventFilter(self)
        get_line_edit = getattr(widget, "lineEdit", None)
        editor = get_line_edit() if callable(get_line_edit) else None
        if isinstance(editor, QWidget):
            editor.installEventFilter(self)

    def _on_scrolled(self, _value: int) -> None:
        self._last_scroll_at = time.monotonic()

    def _resolve(self, widget: QWidget) -> QWidget | None:
        """沿 parentWidget 链回溯到最近的受保护控件"""
        current: QWidget | None = widget
        while current is not None:
            if current in self._value_widgets or current in self._selection_widgets:
                return current
            current = current.parentWidget()
        return None

    def _should_scroll(self, owner: QWidget) -> bool:
        if owner in self._selection_widgets:
            return True
        return (time.monotonic() - self._last_scroll_at) < self._SCROLL_QUIET_SECONDS

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if isinstance(obj, QWidget) and isinstance(event, QWheelEvent):
            owner = self._resolve(obj)
            if owner is not None and self._should_scroll(owner):
                # 自带的时间戳一并刷新：滚动条已到底/到顶不再移动时，
                # 持续滚轮仍应算作「正在滚动」，不能漏成改值
                self._on_scrolled(0)
                QApplication.sendEvent(self._viewport, event)
                return True
        return super().eventFilter(obj, event)


class _NumericRangeGuard(QObject):
    """数值框只允许数字区域可编辑：单位（前缀/后缀，如 " 空格"/" pt"）不可点击、不可选中。

    QSpinBox / QDoubleSpinBox 把 prefix + 数字 + suffix 放在同一个内部 QLineEdit 里，
    因此点击单位文字也会把光标放进单位内。这里在光标/选区索引越出数字区间时把它收回，
    于是点单位、拖选到单位、按 End 都不会把光标停在单位里，也无法改写单位。

    收回动作必须**延迟到当前回调之后**：QLineEdit 处理鼠标按下时先发
    cursorPositionChanged、再继续完成自身的定位逻辑，若在信号处理里同步改回，
    会被随后的定位覆盖（实测无效）。数字区间按 prefix/cleanText 长度计算，
    与字体、DPI 无关。
    """

    def __init__(self, spin: QSpinBox | QDoubleSpinBox) -> None:
        super().__init__(spin)
        self._spin = spin
        line_edit = spin.lineEdit()
        if line_edit is not None:
            line_edit.cursorPositionChanged.connect(self._schedule_clamp)

    def _schedule_clamp(self, _position: int) -> None:
        QTimer.singleShot(0, self._clamp)

    def _clamp(self) -> None:
        line_edit = self._spin.lineEdit()
        if line_edit is None:
            return
        start = len(self._spin.prefix())
        end = start + len(self._spin.cleanText())
        position = line_edit.cursorPosition()
        if position < start:
            target = start
        elif position > end:
            target = end
        else:
            return
        # 仅在实际越界时移动，避免 setSelection 反复触发信号形成定时器回环
        line_edit.setSelection(target, 0)


class _ComboTextGuard(QObject):
    """组合框文字只作展示：不可编辑、不可选中、不可复制。

    文字要与同列控件对齐，就必须保留内部编辑框：不可编辑的 QComboBox 由样式直接
    把文字画在编辑区左边缘，而同列的 QSpinBox / QLineEdit 内部还有文本内缩，
    偏移量随字体/DPI/样式变化（实测 2~6.5 逻辑像素），无法用固定 padding 补偿。
    故把组合框设为可编辑并保留内部编辑框，沿用与 QSpinBox 相同的渲染路径。

    但只读编辑框仍能被双击/三击/全选选中并复制。这里在任何选区生成时立即撤销
    （选区创建与撤销同在当轮事件处理内，不会闪现），选区无法存在，复制自然无从
    进行；只读已保证文字无法被改写。
    """

    def __init__(self, combo: QComboBox) -> None:
        super().__init__(combo)
        combo.setEditable(True)
        line_edit = combo.lineEdit()
        self._line_edit = line_edit
        if line_edit is None:
            return
        line_edit.setReadOnly(True)
        line_edit.selectionChanged.connect(self._clear_selection)

    def _clear_selection(self) -> None:
        line_edit = self._line_edit
        if line_edit is not None and line_edit.hasSelectedText():
            line_edit.deselect()


class EditorSettingsDialog(QDialog):
    """记事本设置对话框"""

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("记事本设置")
        self.setMinimumWidth(450)
        # 限制最大高度为屏幕可用高度的 85%，超出时滚动区域接管
        screen = QApplication.primaryScreen()
        if screen is not None:
            max_h = int(screen.availableGeometry().height() * 0.85)
            self.setMaximumHeight(max_h)

        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # ── 滚动区域（内容超出屏幕时可滚动） ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        # ── 显示选项 ──
        display_group = QGroupBox("显示")
        display_layout = QFormLayout(display_group)

        self.show_line_numbers_cb = QCheckBox()
        display_layout.addRow("显示行号:", self.show_line_numbers_cb)

        self.highlight_current_line_cb = QCheckBox()
        display_layout.addRow("高亮当前行:", self.highlight_current_line_cb)

        scroll_layout.addWidget(display_group)

        # ── 缩略图选项 ──
        minimap_group = QGroupBox("代码缩略图")
        minimap_layout = QFormLayout(minimap_group)

        self.show_minimap_cb = QCheckBox()
        minimap_layout.addRow("显示缩略图:", self.show_minimap_cb)

        self.auto_minimap_cb = QCheckBox()
        self.auto_minimap_cb.setToolTip(
            "勾选后，仅对代码文件显示缩略图（.txt 和 .md 不显示）"
        )
        minimap_layout.addRow("自动开关缩略图:", self.auto_minimap_cb)

        scroll_layout.addWidget(minimap_group)

        # ── 编辑器选项 ──
        editor_group = QGroupBox("编辑器")
        editor_layout = QFormLayout(editor_group)
        self.auto_pair_brackets_cb = QCheckBox()
        self.auto_pair_brackets_cb.setToolTip("输入 (、[、{、\"、' 时自动补全对应的右括号/引号")
        editor_layout.addRow("括号/引号自动配对:", self.auto_pair_brackets_cb)

        # 缩进大小
        self.indent_size_spin = QSpinBox()
        self.indent_size_spin.setRange(1, 8)
        self.indent_size_spin.setSuffix(" 空格")
        self.indent_size_spin.setToolTip("一级缩进的空格数（1-8）")
        editor_layout.addRow("缩进大小:", self.indent_size_spin)

        # 使用 Tab 缩进
        self.use_tabs_cb = QCheckBox()
        self.use_tabs_cb.setToolTip(
            "勾选后按 Tab 插入制表符（\\t）而非空格，\n"
            "其显示宽度由上方缩进大小决定。\n"
            "每次退格删除一个 Tab 字符。"
        )
        editor_layout.addRow("使用 Tab 缩进:", self.use_tabs_cb)

        # 字体选择（使用本地字体库）
        self.font_family_combo = QFontComboBox()
        self.font_family_combo.setMinimumWidth(200)
        editor_layout.addRow("字体:", self.font_family_combo)

        # 代码字体：作用于编辑器内代码块 / Markdown 预览 / 导出（HTML、PDF）
        self.code_font_combo = QFontComboBox()
        self.code_font_combo.setMinimumWidth(200)
        self.code_font_combo.setToolTip(
            "代码块字体：作用于编辑器内的代码块、Markdown 预览与导出文档。\n"
            "与上方「字体」（正文）相互独立。"
        )
        editor_layout.addRow("代码字体:", self.code_font_combo)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 48)
        self.font_size_spin.setSuffix(" pt")
        editor_layout.addRow("字体大小:", self.font_size_spin)

        # 行距：正文全篇；代码块只作用于预览与导出（编辑器内两者不区分）
        # 区间直接取设置项的校验区间，避免界面与导入校验两套范围互相打架
        self.line_spacing_spin = QDoubleSpinBox()
        self.line_spacing_spin.setRange(LINE_SPACING_MIN, LINE_SPACING_MAX)
        self.line_spacing_spin.setSingleStep(0.05)
        self.line_spacing_spin.setDecimals(2)
        self.line_spacing_spin.setSuffix(" 倍")
        self.line_spacing_spin.setToolTip(
            "正文行距（倍数）：作用于编辑器正文、Markdown 预览与导出文档。"
        )
        editor_layout.addRow("行间距:", self.line_spacing_spin)

        self.code_line_spacing_spin = QDoubleSpinBox()
        self.code_line_spacing_spin.setRange(LINE_SPACING_MIN, LINE_SPACING_MAX)
        self.code_line_spacing_spin.setSingleStep(0.05)
        self.code_line_spacing_spin.setDecimals(2)
        self.code_line_spacing_spin.setSuffix(" 倍")
        self.code_line_spacing_spin.setToolTip(
            "代码块行距（倍数）：作用于 Markdown 预览与导出文档的代码块。\n"
            "编辑器内的代码块与正文共用上方「行间距」。"
        )
        editor_layout.addRow("代码块行间距:", self.code_line_spacing_spin)

        self.wrap_mode_combo = QComboBox()
        self.wrap_mode_combo.addItem("不换行", "no_wrap")
        self.wrap_mode_combo.addItem("限制行宽", "limit_width")
        editor_layout.addRow("行宽模式:", self.wrap_mode_combo)

        self.autosave_spin = QSpinBox()
        self.autosave_spin.setRange(10, 300)
        self.autosave_spin.setSuffix(" 秒")
        editor_layout.addRow("自动保存间隔:", self.autosave_spin)

        # 自动补全
        self.enable_completion_cb = QCheckBox()
        self.enable_completion_cb.setToolTip("输入时根据文档已有词语弹出补全建议")
        editor_layout.addRow("自动补全:", self.enable_completion_cb)

        self.completion_min_chars_spin = QSpinBox()
        self.completion_min_chars_spin.setRange(1, 6)
        self.completion_min_chars_spin.setToolTip("输入多少字符后触发补全提示")
        editor_layout.addRow("补全最少字符数:", self.completion_min_chars_spin)

        scroll_layout.addWidget(editor_group)

        # ── 大文件选项（Wave 4 E3）──
        large_file_group = QGroupBox("大文件")
        large_file_layout = QFormLayout(large_file_group)

        self.large_file_mode_cb = QCheckBox()
        self.large_file_mode_cb.setToolTip(
            "勾选后，达 1 万行的文件自动降级高成本功能：\n"
            "关闭自动补全、跳过折叠计算、隐藏缩略图、暂停预览自动刷新\n"
            "（不修改文件内容，开关可随时回退）"
        )
        large_file_layout.addRow("大文件模式:", self.large_file_mode_cb)

        scroll_layout.addWidget(large_file_group)

        # ── 界面选项（Wave 8 B7：view.motion_level 三档）──
        interface_group = QGroupBox("界面")
        interface_layout = QFormLayout(interface_group)

        self.motion_level_combo = QComboBox()
        self.motion_level_combo.addItem("正常", "normal")
        self.motion_level_combo.addItem("减弱（半速）", "reduced")
        self.motion_level_combo.addItem("关闭", "off")
        self.motion_level_combo.setToolTip(
            "主题切换淡出动画：正常 / 半速减弱 / 关闭（QSS 悬停按压反馈不受影响）"
        )
        interface_layout.addRow("界面动效:", self.motion_level_combo)

        scroll_layout.addWidget(interface_group)

        # ── 小秘书选项 ──
        secretary_group = QGroupBox("小秘书")
        secretary_layout = QFormLayout(secretary_group)

        self.show_secretary_cb = QCheckBox()
        secretary_layout.addRow("显示小秘书:", self.show_secretary_cb)

        size_widget = QWidget()
        size_layout = QHBoxLayout(size_widget)
        size_layout.setContentsMargins(0, 0, 0, 0)

        self.secretary_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.secretary_size_slider.setRange(3, 20)
        self.secretary_size_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.secretary_size_slider.setTickInterval(1)
        size_layout.addWidget(self.secretary_size_slider)

        self.secretary_size_label = QLabel("7%")
        self.secretary_size_label.setMinimumWidth(40)
        size_layout.addWidget(self.secretary_size_label)

        self.secretary_size_slider.valueChanged.connect(
            lambda v: self.secretary_size_label.setText(f"{v}%")
        )

        secretary_layout.addRow("尺寸占比:", size_widget)

        scroll_layout.addWidget(secretary_group)

        # ── 输入控件分组 ──
        # 下面三处登记（守卫、滚轮数值类、滚轮选择类）共用这两个清单，
        # 新增控件只需在此加一次，不会出现「某处漏登记」的静默失效。
        # 数值框带单位，只有数字区域可编辑（单位不可点击、不可选中）。
        numeric_spins = (
            self.indent_size_spin,
            self.font_size_spin,
            self.line_spacing_spin,
            self.code_line_spacing_spin,
            self.autosave_spin,
            self.completion_min_chars_spin,
        )
        # 组合框文字只作展示：不可编辑（否则可键入不存在的字体名等非法值并写进
        # 配置）、不可选中、不可复制。原理见 _ComboTextGuard / _NumericRangeGuard。
        text_combos = (
            self.font_family_combo,
            self.code_font_combo,
            self.wrap_mode_combo,
            self.motion_level_combo,
        )

        # 守卫显式持有：守卫靠父子关系与信号连接存活，收进列表让生命周期一目了然，
        # 也避免「构造了却丢掉引用」被误读成无副作用的空语句。
        self._input_guards: list[QObject] = []
        for numeric_spin in numeric_spins:
            self._input_guards.append(_NumericRangeGuard(numeric_spin))
        for text_combo in text_combos:
            self._input_guards.append(_ComboTextGuard(text_combo))

        # 滚轮守卫：滚动本对话框时不得误改设置
        self._wheel_guard = _WheelGuard(scroll, self)
        # 数值类（数值框 + 尺寸滑块）：滚动中只滚不改，界面静止后滚轮可调值
        for value_widget in (*numeric_spins, self.secretary_size_slider):
            self._wheel_guard.guard_value(value_widget)
        # 选择类：滚轮永不改选项（只滚动对话框）
        for selection_widget in text_combos:
            self._wheel_guard.guard_selection(selection_widget)

        # 收尾滚动区域
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # ── 按钮 ──
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def _load_settings(self):
        """从配置加载当前设置"""
        self.show_line_numbers_cb.setChecked(
            self.config.get_editor_setting("show_line_numbers", True)
        )
        self.highlight_current_line_cb.setChecked(
            self.config.get_editor_setting("highlight_current_line", True)
        )
        self.show_minimap_cb.setChecked(
            self.config.get_editor_setting("show_minimap", True)
        )
        self.auto_minimap_cb.setChecked(
            self.config.get_editor_setting("auto_minimap", False)
        )
        self.auto_pair_brackets_cb.setChecked(
            self.config.get_editor_setting("auto_pair_brackets", True)
        )
        self.indent_size_spin.setValue(
            self.config.get_editor_setting("indent_size", 4)
        )
        self.use_tabs_cb.setChecked(
            self.config.get_editor_setting("use_tabs", False)
        )

        # 字体
        font_family = self.config.get_editor_setting("font_family", "Microsoft YaHei")
        target_font = QFont(font_family)
        self.font_family_combo.setCurrentFont(target_font)

        self.code_font_combo.setCurrentFont(QFont(self.config.get_code_font_family()))

        self.font_size_spin.setValue(
            self.config.get_editor_setting("font_size", 12)
        )

        self.line_spacing_spin.setValue(self.config.get_line_spacing())
        self.code_line_spacing_spin.setValue(self.config.get_code_line_spacing())

        wrap_mode = self.config.get_editor_setting("wrap_mode", "no_wrap")
        index = self.wrap_mode_combo.findData(wrap_mode)
        if index >= 0:
            self.wrap_mode_combo.setCurrentIndex(index)

        self.autosave_spin.setValue(
            self.config.get_editor_setting("auto_save_interval", 30)
        )

        self.enable_completion_cb.setChecked(
            self.config.get_editor_setting("enable_completion", False)
        )
        self.completion_min_chars_spin.setValue(
            self.config.get_editor_setting("completion_min_chars", 2)
        )

        self.show_secretary_cb.setChecked(
            self.config.get_secretary_setting("show_secretary", True)
        )

        # B7：界面动效三档（view 命名空间，默认 normal）
        motion_level = self.config.get_view_setting("motion_level", "normal")
        index = self.motion_level_combo.findData(motion_level)
        if index >= 0:
            self.motion_level_combo.setCurrentIndex(index)

        # E3：大文件模式开关（feature flag，持久化到 feature_flags.json）
        self.large_file_mode_cb.setChecked(_feature_is_enabled("large_file_mode"))

        size_percent = self.config.get_secretary_setting("size_percent", 7)
        self.secretary_size_slider.setValue(size_percent)
        self.secretary_size_label.setText(f"{size_percent}%")

    def get_settings(self) -> dict:
        """获取用户修改后的设置

        返回嵌套字典，按命名空间分组：
        - "editor": 编辑器相关设置
        - "secretary": 小秘书相关设置
        - "view": 界面相关设置（B7：view.motion_level）
        """
        return {
            "editor": {
                "show_line_numbers": self.show_line_numbers_cb.isChecked(),
                "highlight_current_line": self.highlight_current_line_cb.isChecked(),
                "show_minimap": self.show_minimap_cb.isChecked(),
                "auto_minimap": self.auto_minimap_cb.isChecked(),
                "font_family": self.font_family_combo.currentFont().family(),
                "font_size": self.font_size_spin.value(),
                "line_spacing": round(self.line_spacing_spin.value(), 2),
                "code_line_spacing": round(self.code_line_spacing_spin.value(), 2),
                "code_font_family": self.code_font_combo.currentFont().family(),
                "wrap_mode": self.wrap_mode_combo.currentData(),
                "auto_save_interval": self.autosave_spin.value(),
                "auto_pair_brackets": self.auto_pair_brackets_cb.isChecked(),
                "indent_size": self.indent_size_spin.value(),
                "use_tabs": self.use_tabs_cb.isChecked(),
                "enable_completion": self.enable_completion_cb.isChecked(),
                "completion_min_chars": self.completion_min_chars_spin.value(),
            },
            "secretary": {
                "show_secretary": self.show_secretary_cb.isChecked(),
                "size_percent": self.secretary_size_slider.value(),
            },
            "view": {
                "motion_level": self.motion_level_combo.currentData(),
            },
        }
