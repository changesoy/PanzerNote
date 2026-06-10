# -*- coding: utf-8 -*-
"""
快捷键管理系统

提供快捷键的注册、冲突检测、自定义配置和持久化存储。
快捷键配置存储在 settings.json 的 "shortcuts" 段中。

功能:
  - 快捷键注册与集中管理
  - 系统级快捷键冲突检测（Ctrl+C/V 等）
  - 应用内部快捷键冲突检测
  - 用户自定义快捷键并保存
  - 快捷键提示面板数据源

用法:
    from src.core.shortcut_manager import ShortcutManager

    manager = ShortcutManager(config)

    # 注册快捷键
    manager.register("file.new", "新建文件", "Ctrl+N", callback)
    manager.register("file.save", "保存", "Ctrl+S", callback)

    # 检测冲突
    conflicts = manager.check_conflicts("Ctrl+N")

    # 自定义快捷键
    manager.set_shortcut("file.new", "Ctrl+Shift+N")

    # 获取所有快捷键（用于提示面板）
    shortcuts = manager.get_all_shortcuts()
"""

from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtGui import QKeySequence, QAction

from ..core.config import Config
from ..utils.logger import get_logger


_SYSTEM_SHORTCUTS = {
    "Alt+F4": "系统关闭窗口",
    "Alt+Tab": "系统切换窗口",
    "Ctrl+Alt+Delete": "系统任务管理器",
    "Win+D": "系统显示桌面",
    "Win+E": "系统资源管理器",
    "Win+L": "系统锁定",
}


def _build_normalized_system_shortcuts() -> Dict[str, str]:
    result = {}
    for key, desc in _SYSTEM_SHORTCUTS.items():
        parts = key.replace(" ", "").split("+")
        parts = [p.strip().lower() for p in parts]
        modifier_order = {"ctrl": 0, "shift": 1, "alt": 2, "meta": 3}
        modifiers = sorted(
            [p for p in parts if p in modifier_order],
            key=lambda x: modifier_order.get(x, 99)
        )
        keys = [p for p in parts if p not in modifier_order]
        normalized = "+".join(modifiers + keys)
        result[normalized] = desc
    return result


_NORMALIZED_SYSTEM_SHORTCUTS = _build_normalized_system_shortcuts()

_DEFAULT_SHORTCUTS = {
    "file.new": ("新建文件", "Ctrl+N", "文件"),
    "file.new_folder": ("新建文件夹", "", "文件"),
    "file.open": ("打开文件", "Ctrl+O", "文件"),
    "file.save": ("保存", "Ctrl+S", "文件"),
    "file.save_as": ("另存为", "Ctrl+Shift+S", "文件"),
    "file.close_tab": ("关闭当前标签", "Ctrl+W", "文件"),
    "file.exit": ("退出", "Alt+F4", "文件"),
    "edit.undo": ("撤销", "Ctrl+Z", "编辑"),
    "edit.redo": ("重做", "Ctrl+Y", "编辑"),
    "edit.cut": ("剪切", "Ctrl+X", "编辑"),
    "edit.copy": ("复制", "Ctrl+C", "编辑"),
    "edit.paste": ("粘贴", "Ctrl+V", "编辑"),
    "edit.select_all": ("全选", "Ctrl+A", "编辑"),
    "edit.find": ("查找", "Ctrl+F", "编辑"),
    "edit.replace": ("替换", "Ctrl+H", "编辑"),
    "edit.delete_line": ("删除当前行", "Ctrl+Shift+K", "编辑"),
    "edit.move_line_up": ("上移当前行", "Alt+Up", "编辑"),
    "edit.move_line_down": ("下移当前行", "Alt+Down", "编辑"),
    "edit.duplicate_line": ("复制当前行", "Ctrl+Shift+D", "编辑"),
    "edit.goto_line": ("转到行", "Ctrl+G", "编辑"),
    "edit.toggle_case": ("切换大小写", "Ctrl+Shift+U", "编辑"),
    "view.editor": ("切换到记事本", "Ctrl+1", "视图"),
    "view.construction": ("切换到建造", "Ctrl+2", "视图"),
    "view.garage": ("切换到车库", "Ctrl+3", "视图"),
    "view.collection": ("切换到图鉴", "Ctrl+4", "视图"),
    "view.md_preview": ("切换Markdown预览", "Ctrl+Shift+P", "视图"),
    "view.minimap": ("显示/隐藏代码缩略图", "Ctrl+M", "视图"),
    "view.file_tree": ("折叠/展开文件树", "Ctrl+B", "视图"),
    "view.fullscreen": ("全屏模式", "F11", "视图"),
    "view.zoom_in": ("放大", "Ctrl++", "视图"),
    "view.zoom_out": ("缩小", "Ctrl+-", "视图"),
    "view.zoom_reset": ("重置缩放", "Ctrl+0", "视图"),
    "shortcut_panel": ("快捷键提示面板", "Ctrl+/", "帮助"),
}


class ShortcutManager:
    """快捷键管理器

    集中管理所有快捷键的注册、冲突检测和自定义配置。
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._logger = get_logger(__name__)
        self._actions: Dict[str, QAction] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._shortcuts: Dict[str, Tuple[str, str, str]] = dict(_DEFAULT_SHORTCUTS)
        self._load_custom_shortcuts()

    def _load_custom_shortcuts(self) -> None:
        """从配置加载用户自定义快捷键"""
        custom = self._config.get_setting("shortcuts", {})
        for action_id, key_seq in custom.items():
            if action_id in self._shortcuts:
                name, _, category = self._shortcuts[action_id]
                self._shortcuts[action_id] = (name, key_seq, category)

    def _save_custom_shortcuts(self) -> None:
        """保存用户自定义快捷键到配置"""
        custom = {}
        default_map = {k: v[1] for k, v in _DEFAULT_SHORTCUTS.items()}
        for action_id, (name, key_seq, category) in self._shortcuts.items():
            if key_seq != default_map.get(action_id, ""):
                custom[action_id] = key_seq
        self._config.set_setting("shortcuts", custom)
        self._config.save_settings()

    def register(
        self,
        action_id: str,
        name: str,
        default_shortcut: str,
        callback: Callable,
        category: str = "通用",
    ) -> Optional[QAction]:
        """注册快捷键

        Args:
            action_id: 唯一标识符，如 "file.new"
            name: 显示名称
            default_shortcut: 默认快捷键序列
            callback: 触发回调
            category: 功能分类

        Returns:
            创建的 QAction，如果快捷键无效则返回 None
        """
        self._callbacks[action_id] = callback

        if action_id not in self._shortcuts:
            self._shortcuts[action_id] = (name, default_shortcut, category)

        _, key_seq, _ = self._shortcuts[action_id]

        action = QAction(name)
        action.setData(action_id)

        if key_seq:
            conflicts = self.check_conflicts(key_seq, exclude=action_id)
            if conflicts:
                self._logger.warning(
                    "快捷键冲突: %s -> %s (冲突项: %s)",
                    action_id, key_seq, conflicts
                )
            action.setShortcut(QKeySequence(key_seq))

        action.triggered.connect(callback)
        self._actions[action_id] = action
        return action

    def get_action(self, action_id: str) -> Optional[QAction]:
        """获取已注册的 QAction"""
        return self._actions.get(action_id)

    def check_conflicts(
        self, key_sequence: str, exclude: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """检测快捷键冲突

        Args:
            key_sequence: 要检测的快捷键序列
            exclude: 排除的 action_id（通常是自身）

        Returns:
            冲突列表，每项包含 type、action_id、name
        """
        if not key_sequence:
            return []

        conflicts = []
        normalized = self._normalize_key(key_sequence)

        system_name = _NORMALIZED_SYSTEM_SHORTCUTS.get(normalized)
        if system_name:
            conflicts.append({
                "type": "system",
                "action_id": "__system__",
                "name": system_name,
            })

        for action_id, (name, seq, category) in self._shortcuts.items():
            if action_id == exclude or not seq:
                continue
            if self._normalize_key(seq) == normalized:
                conflicts.append({
                    "type": "application",
                    "action_id": action_id,
                    "name": name,
                })

        return conflicts

    def set_shortcut(self, action_id: str, key_sequence: str) -> Tuple[bool, List[Dict[str, str]]]:
        """设置快捷键

        Args:
            action_id: 操作标识符
            key_sequence: 新的快捷键序列

        Returns:
            (成功标志, 冲突列表)
        """
        if action_id not in self._shortcuts:
            return False, []

        conflicts = self.check_conflicts(key_sequence, exclude=action_id)
        if conflicts:
            return False, conflicts

        name, _, category = self._shortcuts[action_id]
        self._shortcuts[action_id] = (name, key_sequence, category)

        if action_id in self._actions:
            action = self._actions[action_id]
            if key_sequence:
                action.setShortcut(QKeySequence(key_sequence))
            else:
                action.setShortcut(QKeySequence())

        self._save_custom_shortcuts()
        return True, []

    def reset_shortcut(self, action_id: str) -> bool:
        """重置快捷键为默认值

        Args:
            action_id: 操作标识符

        Returns:
            是否重置成功
        """
        if action_id not in _DEFAULT_SHORTCUTS:
            return False

        default_seq = _DEFAULT_SHORTCUTS[action_id][1]
        return self.set_shortcut(action_id, default_seq)[0]

    def reset_all(self) -> None:
        """重置所有快捷键为默认值"""
        self._shortcuts = dict(_DEFAULT_SHORTCUTS)
        for action_id, (name, key_seq, category) in self._shortcuts.items():
            if action_id in self._actions:
                action = self._actions[action_id]
                if key_seq:
                    action.setShortcut(QKeySequence(key_seq))
                else:
                    action.setShortcut(QKeySequence())
        self._save_custom_shortcuts()

    def get_shortcut(self, action_id: str) -> Optional[str]:
        """获取指定操作的快捷键序列"""
        if action_id in self._shortcuts:
            return self._shortcuts[action_id][1]
        return None

    def get_all_shortcuts(self) -> Dict[str, Dict[str, Dict[str, str]]]:
        """获取所有快捷键，按分类组织

        Returns:
            {category: {action_id: {"name": str, "shortcut": str}}}
        """
        result: Dict[str, Dict[str, Dict[str, str]]] = {}
        for action_id, (name, key_seq, category) in self._shortcuts.items():
            if category not in result:
                result[category] = {}
            result[category][action_id] = {
                "name": name,
                "shortcut": key_seq,
            }
        return result

    def get_categories(self) -> List[str]:
        """获取所有分类"""
        categories = set()
        for _, (_, _, category) in self._shortcuts.items():
            categories.add(category)
        return sorted(categories)

    @staticmethod
    def _normalize_key(key_sequence: str) -> str:
        """规范化快捷键序列以便比较

        Args:
            key_sequence: 原始快捷键序列

        Returns:
            规范化后的字符串
        """
        parts = key_sequence.replace(" ", "").split("+")
        parts = [p.strip().lower() for p in parts]
        modifier_order = {"ctrl": 0, "shift": 1, "alt": 2, "meta": 3}
        modifiers = sorted(
            [p for p in parts if p in modifier_order],
            key=lambda x: modifier_order.get(x, 99)
        )
        keys = [p for p in parts if p not in modifier_order]
        return "+".join(modifiers + keys)
