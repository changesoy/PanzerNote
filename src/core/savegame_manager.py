# -*- coding: utf-8 -*-
"""
游戏存档管理器
负责游戏存档的读写、资源管理、打字统计等
"""

import json
import os
from datetime import datetime
from enum import Enum, auto
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, cast

from ..utils.logger import get_logger
from ..utils.exceptions import safe_call
from ..security.path_validator import PathSecurityError
from ..security.file_guard import FileGuard, FileSizeExceededError, FileOperationTimeoutError
from ..security.file_access_context import FileAccessContext


class SavegameSaveResult(Enum):
    SUCCESS = auto()
    WRITE_FAILED = auto()


class SavegameManager:
    """游戏存档管理器

    从 Config 中拆出，负责所有游戏存档相关的读写和状态管理。
    """

    SAVEGAME_CTX = FileAccessContext.INTERNAL_SAVEGAME

    DEFAULT_SAVEGAME = {
        "resources": {
            "fuel": 3000,
            "ammo": 3000,
            "steel": 3000,
            "bauxite": 1000
        },
        "cores": 0,
        "bauxite_counter": 0,
        "last_login": None,
        "today_date": None,
        "today_chars_typed": 0,
        "total_chars_typed": 0,
        "total_documents": 0,
        "construction_queue": [],
        "owned_characters": {},
        "achievements": [],
        "last_checkin_date": None
    }

    def __init__(
        self,
        file_guard: FileGuard,
        gamedata_dir: str,
    ):
        self._file_guard = file_guard
        self._gamedata_dir = gamedata_dir
        self._savegame: Dict[str, Any] = {}
        self._logger = get_logger(__name__)

    @property
    def data(self) -> Mapping[str, Any]:
        """存档数据只读视图（仅供内部调试/测试，勿修改内部状态）"""
        return MappingProxyType(self._savegame)

    def _get_savegame_path(self) -> str:
        return os.path.join(self._gamedata_dir, "savegame.json")

    def _load_json(self, filepath: str, default: Dict) -> Dict:
        if os.path.exists(filepath):
            try:
                content = self._file_guard.safe_read(filepath, context=self.SAVEGAME_CTX)
                return cast(Dict[str, Any], json.loads(content))
            except (json.JSONDecodeError, IOError, FileSizeExceededError,
                    FileOperationTimeoutError, PathSecurityError) as e:
                self._logger.warning("加载存档文件失败: %s, 错误: %s", filepath, e)
                return default.copy()
        return default.copy()

    def _merge_dict(self, default: Dict, current: Dict) -> Dict:
        result = default.copy()
        for key, value in current.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_dict(result[key], value)
            else:
                result[key] = value
        return result

    def load(self) -> None:
        self._savegame = self._load_json(
            self._get_savegame_path(),
            self.DEFAULT_SAVEGAME,
        )
        self._savegame = self._merge_dict(self.DEFAULT_SAVEGAME, self._savegame)

    def save(self) -> SavegameSaveResult:
        try:
            os.makedirs(self._gamedata_dir, exist_ok=True)
            self._save_json(self._get_savegame_path(), self._savegame)
            return SavegameSaveResult.SUCCESS
        except Exception as e:
            self._logger.error("保存游戏存档失败: %s", e)
            return SavegameSaveResult.WRITE_FAILED

    def _save_json(self, filepath: str, data: Dict):
        content = json.dumps(data, ensure_ascii=False, indent=2)
        self._file_guard.safe_write(filepath, content, context=self.SAVEGAME_CTX)

    # === 存档数据访问 ===

    def get_savegame(self) -> Mapping[str, Any]:
        """返回存档数据的只读视图（仅供内部调试/查看，勿用于业务读写）

        外部代码请使用 get_savegame_field() / set_savegame_field()，
        避免拿到 dict 引用后绕过封装修改内部状态。
        """
        return MappingProxyType(self._savegame)

    def get_savegame_field(self, key: str, default: Any = None) -> Any:
        return self._savegame.get(key, default)

    def set_savegame_field(self, key: str, value: Any) -> None:
        self._savegame[key] = value

    def get_resources(self) -> Dict[str, int]:
        default: Dict[str, int] = {"fuel": 0, "ammo": 0, "steel": 0, "bauxite": 0}
        # 返回拷贝，避免调用方（插件等）拿到内部 resources dict 引用后修改
        return cast(Dict[str, int], dict(self._savegame.get("resources", default)))

    def set_resources(self, resources: Dict[str, int]):
        self._savegame["resources"] = resources

    def add_resource(self, resource_type: str, amount: int):
        if "resources" not in self._savegame:
            self._savegame["resources"] = {"fuel": 0, "ammo": 0, "steel": 0, "bauxite": 0}
        current = self._savegame["resources"].get(resource_type, 0)
        self._savegame["resources"][resource_type] = max(0, current + amount)

    def get_cores(self) -> int:
        return int(self._savegame.get("cores", 0))

    def set_cores(self, amount: int):
        self._savegame["cores"] = max(0, amount)

    def add_cores(self, amount: int):
        current = self.get_cores()
        self.set_cores(current + amount)

    def get_today_chars_typed(self) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        saved_date = self._savegame.get("today_date")
        if saved_date != today:
            self._savegame["today_date"] = today
            self._savegame["today_chars_typed"] = 0
        return int(self._savegame.get("today_chars_typed", 0))

    def add_chars_typed(self, count: int):
        self.get_today_chars_typed()
        self._savegame["today_chars_typed"] = self._savegame.get("today_chars_typed", 0) + count
        self._savegame["total_chars_typed"] = self._savegame.get("total_chars_typed", 0) + count

    def get_total_documents(self) -> int:
        return int(self._savegame.get("total_documents", 0))

    def set_total_documents(self, count: int):
        self._savegame["total_documents"] = count

    def update_last_login(self):
        self._savegame["last_login"] = datetime.now().isoformat()

    def get_last_login(self) -> Optional[str]:
        return self._savegame.get("last_login")

    def migrate_bauxite_counter(self, old_val: Any) -> None:
        if old_val is not None:
            self._savegame["bauxite_counter"] = old_val
            self._logger.info("已迁移 bauxite_counter (%s) 从 settings 到 savegame", old_val)

    def check_daily_checkin(self) -> bool:
        today = datetime.now().strftime("%Y-%m-%d")
        if self._savegame.get("last_checkin_date") == today:
            return False
        self._savegame["last_checkin_date"] = today
        reward = {"fuel": 100, "ammo": 100, "steel": 100, "bauxite": 100}
        for res, amount in reward.items():
            self.add_resource(res, amount)
        self.save()
        return True
