# -*- coding: utf-8 -*-
"""
游戏存档管理器
负责游戏存档的读写、资源管理、打字统计等
"""

import json
import os
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, Optional

from ..utils.logger import get_logger
from ..utils.exceptions import safe_call
from ..security.path_validator import PathSecurityError
from ..security.file_guard import FileGuard, FileSizeExceededError, FileOperationTimeoutError
from ..security.crypto_manager import CryptoManager, DecryptionError


class SavegameSaveResult(Enum):
    SUCCESS = auto()
    SKIPPED_ENCRYPTED_UNREAD = auto()
    ENCRYPTION_FAILED = auto()


class SavegameManager:
    """游戏存档管理器

    从 Config 中拆出，负责所有游戏存档相关的读写和状态管理。
    """

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
        crypto_manager: CryptoManager,
        gamedata_dir: str,
    ):
        self._file_guard = file_guard
        self._crypto_manager = crypto_manager
        self._gamedata_dir = gamedata_dir
        self._savegame: Dict[str, Any] = {}
        self._encryption_password: Optional[str] = None
        self._encrypted_unread: bool = False
        self._logger = get_logger(__name__)

    @property
    def data(self) -> Dict[str, Any]:
        return self._savegame

    def _get_savegame_path(self) -> str:
        return os.path.join(self._gamedata_dir, "savegame.json")

    def _load_json(self, filepath: str, default: Dict) -> Dict:
        if os.path.exists(filepath):
            try:
                content = self._file_guard.safe_read(filepath, validate_path=False)
                return json.loads(content)
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

    def load(self):
        if self._crypto_manager.is_encrypted():
            try:
                if self._encryption_password:
                    self._savegame = self._crypto_manager.decrypt_savegame(
                        self._encryption_password
                    )
                else:
                    self._backup_encrypted_file()
                    self._savegame = self.DEFAULT_SAVEGAME.copy()
                    self._encrypted_unread = True
                    self._logger.info("存档已加密，需要密码才能解密")
            except DecryptionError as e:
                self._logger.warning("存档解密失败: %s", e)
                self._backup_encrypted_file()
                self._savegame = self.DEFAULT_SAVEGAME.copy()
                self._encrypted_unread = True
        else:
            self._savegame = self._load_json(
                self._get_savegame_path(),
                self.DEFAULT_SAVEGAME
            )

        self._savegame = self._merge_dict(self.DEFAULT_SAVEGAME, self._savegame)

    def save(self) -> SavegameSaveResult:
        if self._encrypted_unread:
            self._logger.warning("存档已加密但未解锁，跳过保存以防止覆写")
            return SavegameSaveResult.SKIPPED_ENCRYPTED_UNREAD
        os.makedirs(self._gamedata_dir, exist_ok=True)
        if self._encryption_password and self._crypto_manager.is_encrypted():
            try:
                self._crypto_manager.encrypt_savegame(
                    self._encryption_password, self._savegame
                )
                return SavegameSaveResult.SUCCESS
            except Exception as e:
                self._logger.warning("存档加密保存失败，回退到明文: %s", e)
                self._save_json(self._get_savegame_path(), self._savegame)
                return SavegameSaveResult.ENCRYPTION_FAILED
        else:
            self._save_json(self._get_savegame_path(), self._savegame)
            return SavegameSaveResult.SUCCESS

    def _save_json(self, filepath: str, data: Dict):
        content = json.dumps(data, ensure_ascii=False, indent=2)
        self._file_guard.safe_write(filepath, content, validate_path=False)

    def _backup_encrypted_file(self):
        import shutil
        encrypted_path = self._get_savegame_path() + ".encrypted"
        if os.path.exists(encrypted_path):
            backup_path = encrypted_path + ".bak"
            try:
                shutil.copy2(encrypted_path, backup_path)
                self._logger.info("已备份加密存档: %s", backup_path)
            except Exception as e:
                self._logger.warning("备份加密存档失败: %s", e)

    def set_encryption_password(self, password: str) -> None:
        was_encrypted_unread = self._encrypted_unread
        self._encryption_password = password
        self._encrypted_unread = False

        if was_encrypted_unread and password:
            try:
                self._savegame = self._crypto_manager.decrypt_savegame(password)
                self._savegame = self._merge_dict(self.DEFAULT_SAVEGAME, self._savegame)
                self._logger.info("存档已从加密状态重新加载")
            except DecryptionError as e:
                self._logger.error("解锁后重新解密存档失败: %s", e)
                self._encrypted_unread = True
                self._encryption_password = None

    def has_encryption_password(self) -> bool:
        return self._encryption_password is not None

    def is_encrypted_unread(self) -> bool:
        return self._encrypted_unread

    def is_savegame_encrypted(self) -> bool:
        return self._crypto_manager.is_encrypted()

    def enable_encryption(self, password: str) -> bool:
        try:
            self._crypto_manager.migrate_to_encrypted(password)
            self._encryption_password = password
            self._encrypted_unread = False
            self._logger.info("存档加密已启用")
            return True
        except Exception as e:
            self._logger.error("启用存档加密失败: %s", e)
            return False

    def disable_encryption(self, password: str) -> bool:
        try:
            self._crypto_manager.migrate_to_plaintext(password)
            self._encryption_password = None
            self._logger.info("存档加密已禁用")
            return True
        except Exception as e:
            self._logger.error("禁用存档加密失败: %s", e)
            return False

    def verify_encryption_password(self, password: str) -> bool:
        return self._crypto_manager.verify_password(password)

    # === 存档数据访问 ===

    def get_savegame(self) -> Dict:
        return self._savegame

    def get_resources(self) -> Dict[str, int]:
        return self._savegame.get("resources", {
            "fuel": 0, "ammo": 0, "steel": 0, "bauxite": 0
        })

    def set_resources(self, resources: Dict[str, int]):
        self._savegame["resources"] = resources

    def add_resource(self, resource_type: str, amount: int):
        if "resources" not in self._savegame:
            self._savegame["resources"] = {"fuel": 0, "ammo": 0, "steel": 0, "bauxite": 0}
        current = self._savegame["resources"].get(resource_type, 0)
        self._savegame["resources"][resource_type] = max(0, current + amount)

    def get_cores(self) -> int:
        return self._savegame.get("cores", 0)

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
        return self._savegame.get("today_chars_typed", 0)

    def add_chars_typed(self, count: int):
        self.get_today_chars_typed()
        self._savegame["today_chars_typed"] = self._savegame.get("today_chars_typed", 0) + count
        self._savegame["total_chars_typed"] = self._savegame.get("total_chars_typed", 0) + count

    def get_total_documents(self) -> int:
        return self._savegame.get("total_documents", 0)

    def set_total_documents(self, count: int):
        self._savegame["total_documents"] = count

    def update_last_login(self):
        self._savegame["last_login"] = datetime.now().isoformat()

    def get_last_login(self) -> Optional[str]:
        return self._savegame.get("last_login")

    def migrate_bauxite_counter(self, settings: Dict):
        old_val = settings.get("game", {}).pop("bauxite_counter", None)
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
