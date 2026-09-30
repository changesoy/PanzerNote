# -*- coding: utf-8 -*-
"""
设置存储模块

负责 settings dict 的读写、命名空间设置访问、reset_to_defaults。
SettingsStore 只关心设置本身，路径由 PathResolver 提供。

v1.7.0 改动：
  - 从 Config 拆出 SettingsStore（hotfix 阶段 0）
"""

import copy
import os
from typing import Dict, Any, Optional

from PyQt6.QtCore import QCoreApplication, QTimer

from ..security.file_guard import FileGuard
from .path_resolver import PathResolver, load_json, save_json, merge_dicts


# 代码块字体默认值：编辑器代码块 / Markdown 预览 / 导出文档共用同一真相源
DEFAULT_CODE_FONT_FAMILY = "Courier New"

# 行距默认值（倍数）。正文行距作用于编辑器正文 + 预览 + 导出；代码块行距作用于
# 预览与导出的代码块（编辑器内正文/代码块不区分，见 docs/architecture.md）。
DEFAULT_LINE_SPACING = 1.5
DEFAULT_CODE_LINE_SPACING = 1.35

# 行距可接受区间：与 config_import_service 的校验区间一致，读取时兜底夹取
LINE_SPACING_MIN = 0.5
LINE_SPACING_MAX = 5.0


class SettingsStore:
    """设置存储：settings dict + 命名空间访问"""

    DEFAULT_SETTINGS = {
        "initialized": False,
        "base_path": "",
        "editor": {
            "font_family": "Microsoft YaHei",
            "font_size": 12,
            "code_font_family": DEFAULT_CODE_FONT_FAMILY,
            "line_spacing": DEFAULT_LINE_SPACING,
            "code_line_spacing": DEFAULT_CODE_LINE_SPACING,
            "show_line_numbers": True,
            "auto_wrap": False,
            "wrap_mode": "no_wrap",
            # 预览行宽：与编辑区行宽模式各自独立（用户要求可自主选择），默认限制
            "preview_wrap_mode": "limit_width",
            "highlight_current_line": True,
            "auto_save_interval": 30,
            "max_history_count": 40,
            "default_encoding": "utf-8",
            "line_ending": "LF",
            "code_highlight_theme": "pycharm_light",
            "show_minimap": True,
            "auto_minimap": False,
            "auto_pair_brackets": True,
            "indent_size": 4,
            "use_tabs": False,
            "enable_completion": False,
            "completion_min_chars": 2,
        },
        "game": {
            "typing_reward_rate": 1.0,
            "idle_reward_rate": 1.0,
            "daily_typing_limit": 10000,
            "construction_time_rate": 1.0,
            "construction_slots": 2,
        },
        "secretary": {
            "character_id": None,
            "character_name": None,
            "skin_name": None,
            "state": "正常",
            "user_nickname": "指挥官",
            "secretary_self": "我",
            "enable_voice": False,
            "show_secretary": True,
            "size_percent": 7
        },
        "view": {
            "theme": "light",
            "sidebar_width": 200,
            "show_file_tree": True
        },
        "window": {
            "width": 1200,
            "height": 800,
            "x": 100,
            "y": 100,
            "maximized": False
        },
        "shortcuts": {}
    }

    # 变更即落盘的合并窗口（毫秒）：分割条拖动每像素都会写设置
    # （split_ratio / preview_width 等），窗口太短起不到合并效果，
    # 太长则「改完设置立刻强杀」易丢——300ms 与预览刷新定时器同量级。
    _PERSIST_DEBOUNCE_MS = 300

    def __init__(
        self,
        path_resolver: PathResolver,
        file_guard: FileGuard,
    ):
        self._path_resolver = path_resolver
        self._file_guard = file_guard
        self._settings: Dict[str, Any] = {}
        self._save_timer: Optional[QTimer] = None

    # === 读写 ===

    def load(self) -> None:
        """从 config_dir 加载 settings.json 并合并默认值"""
        config_dir = self._path_resolver.get_config_dir()
        settings_path = os.path.join(config_dir, "settings.json")
        self._settings = merge_dicts(
            self.DEFAULT_SETTINGS,
            load_json(self._file_guard, settings_path, self.DEFAULT_SETTINGS),
        )

    def save(self) -> None:
        """保存 settings.json（同步落盘，取消待刷的合并定时器）"""
        if self._save_timer is not None and self._save_timer.isActive():
            self._save_timer.stop()
        config_dir = self._path_resolver.get_config_dir()
        os.makedirs(config_dir, exist_ok=True)
        save_json(
            self._file_guard,
            os.path.join(config_dir, "settings.json"),
            self._settings,
        )

    def _schedule_save(self) -> None:
        """变更即落盘：短时间内的连续变更合并为一次写盘。

        分割条拖动每像素都会写设置（split_ratio / preview_width 等），
        逐次落盘会造成写盘风暴，故用单次触发的定时器合并；
        无事件循环时（单元测试 / 启动早期）退化为同步落盘，保证语义可预期。
        """
        if QCoreApplication.instance() is None:
            self.save()
            return
        if self._save_timer is None:
            # 无 parent：SettingsStore 非 QObject；靠 Python 引用维持存活
            self._save_timer = QTimer()
            self._save_timer.setSingleShot(True)
            self._save_timer.setInterval(self._PERSIST_DEBOUNCE_MS)
            self._save_timer.timeout.connect(self.save)
        self._save_timer.start()

    def as_dict(self) -> Dict[str, Any]:
        """返回深拷贝，避免调用方拿到内部引用后绕过封装修改状态"""
        return copy.deepcopy(self._settings)

    # === 初始化状态 ===

    def is_initialized(self) -> bool:
        if self._path_resolver.has_base_path() and os.path.exists(self._path_resolver.get_base_path()):
            settings_path = os.path.join(self._path_resolver.get_config_dir(), "settings.json")
            return os.path.exists(settings_path)
        return False

    def set_initialized(self, value: bool) -> None:
        self._settings["initialized"] = value
        self._schedule_save()

    # === 设置访问 ===

    def _get_ns_setting(self, namespace: str, key: str, default: Any = None) -> Any:
        return self._settings.get(namespace, {}).get(key, default)

    def _set_ns_setting(self, namespace: str, key: str, value: Any) -> None:
        if namespace not in self._settings:
            self._settings[namespace] = {}
        self._settings[namespace][key] = value
        self._schedule_save()

    def get_editor_setting(self, key: str, default: Any = None) -> Any:
        return self._get_ns_setting("editor", key, default)

    def get_code_font_family(self) -> str:
        """设置项「代码字体」族名（编辑器代码块 / 预览 / 导出共用的唯一读取入口）。

        空串与未配置都回退到默认值，保证调用方拿到的一定是可用的族名。
        """
        value = self.get_editor_setting("code_font_family", DEFAULT_CODE_FONT_FAMILY)
        return str(value or DEFAULT_CODE_FONT_FAMILY)

    def get_line_spacing(self) -> float:
        """设置项「正文行距」倍数（编辑器 / 预览 / 导出共用的唯一读取入口）。"""
        return self._read_line_spacing("line_spacing", DEFAULT_LINE_SPACING)

    def get_code_line_spacing(self) -> float:
        """设置项「代码块行距」倍数（预览 / 导出代码块共用，编辑器内不区分）。"""
        return self._read_line_spacing("code_line_spacing", DEFAULT_CODE_LINE_SPACING)

    def _read_line_spacing(self, key: str, default: float) -> float:
        """读行距并兜底：非法值回退默认，越界夹取到可接受区间。"""
        try:
            value = float(self.get_editor_setting(key, default))
        except (TypeError, ValueError):
            return default
        return min(LINE_SPACING_MAX, max(LINE_SPACING_MIN, value))

    def set_editor_setting(self, key: str, value: Any) -> None:
        self._set_ns_setting("editor", key, value)

    def get_game_setting(self, key: str, default: Any = None) -> Any:
        return self._get_ns_setting("game", key, default)

    def set_game_setting(self, key: str, value: Any) -> None:
        self._set_ns_setting("game", key, value)

    def get_secretary_setting(self, key: str, default: Any = None) -> Any:
        return self._get_ns_setting("secretary", key, default)

    def set_secretary_setting(self, key: str, value: Any) -> None:
        self._set_ns_setting("secretary", key, value)

    def get_view_setting(self, key: str, default: Any = None) -> Any:
        return self._get_ns_setting("view", key, default)

    def set_view_setting(self, key: str, value: Any) -> None:
        self._set_ns_setting("view", key, value)

    def get_window_setting(self, key: str, default: Any = None) -> Any:
        return self._get_ns_setting("window", key, default)

    def set_window_setting(self, key: str, value: Any) -> None:
        self._set_ns_setting("window", key, value)

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        self._settings[key] = value
        self._schedule_save()

    def reset_to_defaults(self) -> None:
        self._settings = copy.deepcopy(self.DEFAULT_SETTINGS)
        self.save()
