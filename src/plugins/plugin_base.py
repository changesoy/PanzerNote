# -*- coding: utf-8 -*-
"""
插件基类与元数据定义

定义插件生命周期接口、元数据规范和权限枚举。
所有插件必须继承 PluginBase 并实现生命周期方法。

Wave 5（Batch 1）变更：
- manifest 权限字段由 permissions 改为 capabilities（能力 id 列表，D6）；
  插件清单不再出现 permissions 字段。
- PluginPermission 重组为保留能力所需的最小集（GET_CONFIG / ACCESS_* 移除，
  ACCESS_* 细化在 Batch 2 以 EDITOR_READ 等替代）。
- PluginBase 暴露 ctx（PluginContext），原 PluginAPI 命名废弃（D4）。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .. import __version__ as _app_version

if TYPE_CHECKING:
    from .plugin_context import PluginContext


class PluginState(Enum):
    UNLOADED = auto()
    LOADED = auto()
    ACTIVATED = auto()
    DEACTIVATED = auto()
    ERROR = auto()


class PluginPermission(Enum):
    READ_SETTINGS = "read_settings"
    READ_SAVEGAME = "read_savegame"
    READ_WORKSPACE = "read_workspace"
    READ_FILE_TREE = "read_file_tree"
    OPEN_FILE = "open_file"
    SHOW_MESSAGE = "show_message"
    REGISTER_COMMAND = "register_command"
    EDITOR_READ = "editor_read"
    EDITOR_WRITE = "editor_write"
    UI_NOTIFY = "ui_notify"
    REGISTER_MENU = "register_menu"
    EVENT_SUBSCRIBE = "event_subscribe"


@dataclass
class PluginMeta:
    name: str
    version: str
    description: str
    author: str = ""
    homepage: str = ""
    min_app_version: str = field(default_factory=lambda: _app_version)
    capabilities: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "homepage": self.homepage,
            "min_app_version": self.min_app_version,
            "capabilities": list(self.capabilities),
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginMeta":
        capabilities = data.get("capabilities", [])
        if not isinstance(capabilities, list):
            capabilities = []
        return cls(
            name=data["name"],
            version=data["version"],
            description=data.get("description", ""),
            author=data.get("author", ""),
            homepage=data.get("homepage", ""),
            min_app_version=data.get("min_app_version", _app_version),
            capabilities=[str(c) for c in capabilities],
            tags=data.get("tags", []),
        )


class PluginBase(ABC):
    def __init__(self):
        self._state: PluginState = PluginState.UNLOADED
        self._ctx: Optional["PluginContext"] = None
        self._meta: Optional[PluginMeta] = None

    @property
    def state(self) -> PluginState:
        return self._state

    @state.setter
    def state(self, value: PluginState):
        self._state = value

    @property
    def ctx(self) -> Optional["PluginContext"]:
        return self._ctx

    @ctx.setter
    def ctx(self, value: Optional["PluginContext"]):
        self._ctx = value

    @property
    def meta(self) -> Optional[PluginMeta]:
        return self._meta

    @meta.setter
    def meta(self, value: PluginMeta):
        self._meta = value

    @abstractmethod
    def get_meta(self) -> PluginMeta:
        raise NotImplementedError

    def on_load(self, ctx: "PluginContext") -> None:
        self._ctx = ctx
        self._meta = self.get_meta()
        self._state = PluginState.LOADED

    def on_activate(self) -> None:
        self._state = PluginState.ACTIVATED

    def on_deactivate(self) -> None:
        self._state = PluginState.DEACTIVATED

    def on_unload(self) -> None:
        self._state = PluginState.UNLOADED
        self._ctx = None
