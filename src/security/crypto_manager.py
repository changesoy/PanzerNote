# -*- coding: utf-8 -*-
"""
存档数据加密系统

基于 PBKDF2 密钥派生 + AES-GCM 加密模式，保护 savegame.json 数据安全。
提供自动迁移工具，支持未加密存档向加密格式的无缝迁移。

用法:
    from src.security.crypto_manager import CryptoManager

    manager = CryptoManager(config_dir)
    manager.encrypt_savegame(password, savegame_data)
    data = manager.decrypt_savegame(password)
"""

import base64
import json
import os
import shutil
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from ..utils.logger import get_logger


class CryptoError(Exception):
    pass


class DecryptionError(CryptoError):
    pass


class MigrationError(CryptoError):
    pass


_CRYPTO_VERSION = 1
_PBKDF2_ITERATIONS = 600_000
_SALT_LENGTH = 32
_NONCE_LENGTH = 12
_KEY_LENGTH = 32
_ENCRYPTED_SUFFIX = ".encrypted"


class CryptoManager:
    def __init__(self, config_dir: str, savegame_dir: Optional[str] = None):
        self._config_dir = config_dir
        gamedata_dir = savegame_dir or os.path.join(config_dir, "..", "gamedata")
        self._savegame_path = os.path.join(gamedata_dir, "savegame.json")
        self._encrypted_path = self._savegame_path + _ENCRYPTED_SUFFIX
        self._salt_path = os.path.join(config_dir, "savegame.salt")
        self._logger = get_logger(__name__)

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """使用 PBKDF2 从密码派生加密密钥"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=_KEY_LENGTH,
            salt=salt,
            iterations=_PBKDF2_ITERATIONS,
        )
        return kdf.derive(password.encode('utf-8'))

    def _generate_salt(self) -> bytes:
        """生成随机盐值"""
        return os.urandom(_SALT_LENGTH)

    def _save_salt(self, salt: bytes) -> None:
        """保存盐值到文件"""
        os.makedirs(os.path.dirname(self._salt_path), exist_ok=True)
        with open(self._salt_path, 'wb') as f:
            f.write(base64.b64encode(salt))
        self._logger.debug("盐值已保存")

    def _load_salt(self) -> Optional[bytes]:
        """从文件加载盐值"""
        if not os.path.exists(self._salt_path):
            return None
        try:
            with open(self._salt_path, 'rb') as f:
                return base64.b64decode(f.read())
        except Exception as e:
            self._logger.error("加载盐值失败: %s", e)
            return None

    def encrypt_data(self, password: str, data: Dict[str, Any]) -> bytes:
        """加密数据

        Args:
            password: 用户密码
            data: 要加密的字典数据

        Returns:
            加密后的二进制数据
        """
        salt = self._generate_salt()
        key = self._derive_key(password, salt)
        nonce = os.urandom(_NONCE_LENGTH)

        plaintext = json.dumps(data, ensure_ascii=False).encode('utf-8')

        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        encrypted = json.dumps({
            "version": _CRYPTO_VERSION,
            "salt": base64.b64encode(salt).decode('ascii'),
            "nonce": base64.b64encode(nonce).decode('ascii'),
            "data": base64.b64encode(ciphertext).decode('ascii'),
        }, ensure_ascii=False).encode('utf-8')

        self._save_salt(salt)
        self._logger.info("数据加密完成 (v%d)", _CRYPTO_VERSION)
        return encrypted

    def decrypt_data(self, password: str, encrypted: bytes) -> Dict[str, Any]:
        """解密数据

        Args:
            password: 用户密码
            encrypted: 加密的二进制数据

        Returns:
            解密后的字典数据

        Raises:
            DecryptionError: 解密失败（密码错误或数据损坏）
        """
        try:
            envelope = json.loads(encrypted.decode('utf-8'))
            version = envelope.get("version", 0)
            if version != _CRYPTO_VERSION:
                raise DecryptionError(f"不支持的加密版本: {version}")

            salt = base64.b64decode(envelope["salt"])
            nonce = base64.b64decode(envelope["nonce"])
            ciphertext = base64.b64decode(envelope["data"])

            key = self._derive_key(password, salt)

            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)

            result = json.loads(plaintext.decode('utf-8'))
            self._logger.info("数据解密完成")
            return result

        except DecryptionError:
            raise
        except Exception as e:
            raise DecryptionError(f"解密失败: {e}") from e

    def is_encrypted(self) -> bool:
        """检查存档是否已加密"""
        return os.path.exists(self._encrypted_path)

    def encrypt_savegame(self, password: str, data: Dict[str, Any]) -> None:
        """加密并保存存档文件

        加密前自动创建备份。

        Args:
            password: 用户密码
            data: 存档数据
        """
        self._backup_if_exists(self._encrypted_path)

        encrypted = self.encrypt_data(password, data)

        os.makedirs(os.path.dirname(self._encrypted_path), exist_ok=True)
        with open(self._encrypted_path, 'wb') as f:
            f.write(encrypted)

        self._logger.info("存档已加密保存: %s", self._encrypted_path)

    def decrypt_savegame(self, password: str) -> Dict[str, Any]:
        """从加密文件解密存档

        Args:
            password: 用户密码

        Returns:
            存档数据字典

        Raises:
            DecryptionError: 解密失败
        """
        if not os.path.exists(self._encrypted_path):
            raise DecryptionError("加密存档文件不存在")

        with open(self._encrypted_path, 'rb') as f:
            encrypted = f.read()

        return self.decrypt_data(password, encrypted)

    def migrate_to_encrypted(self, password: str) -> bool:
        """将未加密存档迁移为加密格式

        步骤：
        1. 检查未加密存档是否存在
        2. 创建备份
        3. 读取未加密数据
        4. 加密并保存
        5. 验证加密数据可正确解密
        6. 删除未加密原文件

        Args:
            password: 用户密码

        Returns:
            是否迁移成功
        """
        savegame_path = os.path.normpath(self._savegame_path)

        if not os.path.exists(savegame_path):
            self._logger.info("未加密存档不存在，无需迁移")
            return False

        if self.is_encrypted():
            self._logger.info("存档已加密，跳过迁移")
            return False

        try:
            self._backup_if_exists(savegame_path)

            with open(savegame_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.encrypt_savegame(password, data)

            verification = self.decrypt_savegame(password)
            if verification != data:
                raise MigrationError("加密验证失败：解密数据与原始数据不一致")

            backup_path = savegame_path + ".bak"
            shutil.move(savegame_path, backup_path)

            self._logger.info("存档迁移完成，原文件备份: %s", backup_path)
            return True

        except MigrationError:
            raise
        except Exception as e:
            raise MigrationError(f"存档迁移失败: {e}") from e

    def migrate_to_plaintext(self, password: str) -> bool:
        """将加密存档迁移回明文格式

        Args:
            password: 用户密码

        Returns:
            是否迁移成功
        """
        if not self.is_encrypted():
            self._logger.info("存档未加密，跳过迁移")
            return False

        try:
            data = self.decrypt_savegame(password)

            savegame_path = os.path.normpath(self._savegame_path)
            os.makedirs(os.path.dirname(savegame_path), exist_ok=True)
            with open(savegame_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            os.remove(self._encrypted_path)

            salt_path = self._salt_path
            if os.path.exists(salt_path):
                os.remove(salt_path)

            self._logger.info("存档已迁移为明文格式")
            return True

        except Exception as e:
            raise MigrationError(f"明文迁移失败: {e}") from e

    def _backup_if_exists(self, filepath: str) -> None:
        """如果文件存在则创建备份"""
        if os.path.exists(filepath):
            backup_path = filepath + ".bak"
            shutil.copy2(filepath, backup_path)
            self._logger.debug("已创建备份: %s", backup_path)

    def verify_password(self, password: str) -> bool:
        """验证密码是否正确

        Args:
            password: 待验证密码

        Returns:
            密码是否正确
        """
        if not self.is_encrypted():
            return False
        try:
            self.decrypt_savegame(password)
            return True
        except DecryptionError:
            return False
