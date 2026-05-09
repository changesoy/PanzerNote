# -*- coding: utf-8 -*-
"""
插件基类与元数据定义

定义插件生命周期接口、元数据规范和权限枚举。
所有插件必须继承 PluginBase 并实现生命周期方法。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional

from .. import __version__ as _app_version
from ..utils.logger import get_logger


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
    ACCESS_EDITOR = "access_editor"
    ACCESS_UI = "access_ui"
    ACCESS_NETWORK = "access_network"
    ACCESS_FILESYSTEM = "access_filesystem"
    OPEN_FILE = "open_file"
    SHOW_MESSAGE = "show_message"
    REGISTER_COMMAND = "register_command"
    GET_CONFIG = "get_config"


@dataclass
class PluginMeta:
    name: str
    version: str
    description: str
    author: str = ""
    homepage: str = ""
    min_app_version: str = field(default_factory=lambda: _app_version)
    permissions: List[PluginPermission] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "homepage": self.homepage,
            "min_app_version": self.min_app_version,
            "permissions": [p.value for p in self.permissions],
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginMeta":
        perms = []
        for p in data.get("permissions", []):
            try:
                perms.append(PluginPermission(p))
            except ValueError:
                get_logger(__name__).debug("忽略无效插件权限: %s", p)
        return cls(
            name=data["name"],
            version=data["version"],
            description=data.get("description", ""),
            author=data.get("author", ""),
            homepage=data.get("homepage", ""),
            min_app_version=data.get("min_app_version", _app_version),
            permissions=perms,
            tags=data.get("tags", []),
        )


class PluginBase(ABC):
    def __init__(self):
        self._state: PluginState = PluginState.UNLOADED
        self._api: Optional[Any] = None
        self._meta: Optional[PluginMeta] = None

    @property
    def state(self) -> PluginState:
        return self._state

    @state.setter
    def state(self, value: PluginState):
        self._state = value

    @property
    def api(self) -> Any:
        return self._api

    @api.setter
    def api(self, value: Any):
        self._api = value

    @property
    def meta(self) -> Optional[PluginMeta]:
        return self._meta

    @meta.setter
    def meta(self, value: PluginMeta):
        self._meta = value

    @abstractmethod
    def get_meta(self) -> PluginMeta:
        raise NotImplementedError

    def on_load(self, api: Any) -> None:
        self._api = api
        self._meta = self.get_meta()
        self._state = PluginState.LOADED

    def on_activate(self) -> None:
        self._state = PluginState.ACTIVATED

    def on_deactivate(self) -> None:
        self._state = PluginState.DEACTIVATED

    def on_unload(self) -> None:
        self._state = PluginState.UNLOADED
        self._api = None
