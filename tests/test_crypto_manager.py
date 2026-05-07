# -*- coding: utf-8 -*-
import json
import os
import tempfile

import pytest

from src.security.crypto_manager import (
    CryptoManager,
    CryptoError,
    DecryptionError,
    MigrationError,
)


class TestCryptoManagerEncryptDecrypt:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        config_dir = os.path.join(self.tmp_dir, "data", "config")
        os.makedirs(config_dir, exist_ok=True)
        gamedata_dir = os.path.join(self.tmp_dir, "data", "gamedata")
        os.makedirs(gamedata_dir, exist_ok=True)
        self.manager = CryptoManager(config_dir)
        self.password = "test_password_123"
        self.test_data = {
            "resources": {"fuel": 3000, "ammo": 3000, "steel": 3000, "bauxite": 1000},
            "cores": 5,
            "last_login": "2025-01-01T12:00:00",
        }

    def test_encrypt_decrypt_roundtrip(self):
        encrypted = self.manager.encrypt_data(self.password, self.test_data)
        decrypted = self.manager.decrypt_data(self.password, encrypted)
        assert decrypted == self.test_data

    def test_wrong_password_fails(self):
        encrypted = self.manager.encrypt_data(self.password, self.test_data)
        with pytest.raises(DecryptionError):
            self.manager.decrypt_data("wrong_password", encrypted)

    def test_corrupted_data_fails(self):
        encrypted = self.manager.encrypt_data(self.password, self.test_data)
        with pytest.raises(DecryptionError):
            self.manager.decrypt_data(self.password, encrypted[:-5] + b"XXXXX")

    def test_empty_data(self):
        data = {}
        encrypted = self.manager.encrypt_data(self.password, data)
        decrypted = self.manager.decrypt_data(self.password, encrypted)
        assert decrypted == data

    def test_chinese_data(self):
        data = {"nickname": "指挥官", "state": "正常"}
        encrypted = self.manager.encrypt_data(self.password, data)
        decrypted = self.manager.decrypt_data(self.password, encrypted)
        assert decrypted == data

    def test_different_passwords_produce_different_ciphertext(self):
        encrypted1 = self.manager.encrypt_data("password1", self.test_data)
        encrypted2 = self.manager.encrypt_data("password2", self.test_data)
        assert encrypted1 != encrypted2

    def test_same_password_same_data_different_ciphertext(self):
        encrypted1 = self.manager.encrypt_data(self.password, self.test_data)
        encrypted2 = self.manager.encrypt_data(self.password, self.test_data)
        assert encrypted1 != encrypted2


class TestCryptoManagerFileOperations:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.config_dir = os.path.join(self.tmp_dir, "data", "config")
        self.gamedata_dir = os.path.join(self.tmp_dir, "data", "gamedata")
        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.gamedata_dir, exist_ok=True)
        self.manager = CryptoManager(self.config_dir)
        self.password = "secure_password"
        self.test_data = {"resources": {"fuel": 100}, "cores": 0}

    def test_encrypt_savegame(self):
        self.manager.encrypt_savegame(self.password, self.test_data)
        assert self.manager.is_encrypted()

    def test_decrypt_savegame(self):
        self.manager.encrypt_savegame(self.password, self.test_data)
        result = self.manager.decrypt_savegame(self.password)
        assert result == self.test_data

    def test_decrypt_nonexistent_raises(self):
        with pytest.raises(DecryptionError):
            self.manager.decrypt_savegame(self.password)

    def test_is_encrypted_false_initially(self):
        assert not self.manager.is_encrypted()

    def test_verify_password_correct(self):
        self.manager.encrypt_savegame(self.password, self.test_data)
        assert self.manager.verify_password(self.password)

    def test_verify_password_incorrect(self):
        self.manager.encrypt_savegame(self.password, self.test_data)
        assert not self.manager.verify_password("wrong")

    def test_verify_password_no_encrypted_file(self):
        assert not self.manager.verify_password(self.password)


class TestCryptoManagerMigration:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.config_dir = os.path.join(self.tmp_dir, "data", "config")
        self.gamedata_dir = os.path.join(self.tmp_dir, "data", "gamedata")
        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.gamedata_dir, exist_ok=True)
        self.manager = CryptoManager(self.config_dir)
        self.password = "migration_password"
        self.test_data = {"resources": {"fuel": 500}, "cores": 3}

    def test_migrate_to_encrypted(self):
        savegame_path = os.path.join(self.gamedata_dir, "savegame.json")
        with open(savegame_path, 'w', encoding='utf-8') as f:
            json.dump(self.test_data, f)

        result = self.manager.migrate_to_encrypted(self.password)
        assert result is True
        assert self.manager.is_encrypted()

        decrypted = self.manager.decrypt_savegame(self.password)
        assert decrypted == self.test_data

    def test_migrate_no_plaintext_file(self):
        result = self.manager.migrate_to_encrypted(self.password)
        assert result is False

    def test_migrate_already_encrypted(self):
        self.manager.encrypt_savegame(self.password, self.test_data)
        result = self.manager.migrate_to_encrypted(self.password)
        assert result is False

    def test_migrate_creates_backup(self):
        savegame_path = os.path.join(self.gamedata_dir, "savegame.json")
        with open(savegame_path, 'w', encoding='utf-8') as f:
            json.dump(self.test_data, f)

        self.manager.migrate_to_encrypted(self.password)
        backup_path = savegame_path + ".bak"
        assert os.path.exists(backup_path)

    def test_migrate_to_plaintext(self):
        self.manager.encrypt_savegame(self.password, self.test_data)
        result = self.manager.migrate_to_plaintext(self.password)
        assert result is True
        assert not self.manager.is_encrypted()

        savegame_path = os.path.join(self.gamedata_dir, "savegame.json")
        assert os.path.exists(savegame_path)
        with open(savegame_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data == self.test_data

    def test_migrate_to_plaintext_not_encrypted(self):
        result = self.manager.migrate_to_plaintext(self.password)
        assert result is False

    def test_migrate_to_plaintext_wrong_password(self):
        self.manager.encrypt_savegame(self.password, self.test_data)
        with pytest.raises(MigrationError):
            self.manager.migrate_to_plaintext("wrong_password")


class TestCryptoManagerEdgeCases:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.config_dir = os.path.join(self.tmp_dir, "data", "config")
        self.gamedata_dir = os.path.join(self.tmp_dir, "data", "gamedata")
        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.gamedata_dir, exist_ok=True)
        self.manager = CryptoManager(self.config_dir)
        self.password = "edge_password"
        self.test_data = {"resources": {"fuel": 100}}

    def test_load_salt_nonexistent(self):
        result = self.manager._load_salt()
        assert result is None

    def test_load_salt_corrupted(self):
        salt_path = os.path.join(self.config_dir, "savegame.salt")
        with open(salt_path, 'wb') as f:
            f.write(b"not_valid_base64!!!")
        result = self.manager._load_salt()
        assert result is None

    def test_decrypt_invalid_version(self):
        import base64
        envelope = json.dumps({
            "version": 999,
            "salt": base64.b64encode(os.urandom(32)).decode(),
            "nonce": base64.b64encode(os.urandom(12)).decode(),
            "data": base64.b64encode(os.urandom(64)).decode(),
        }).encode('utf-8')
        with pytest.raises(DecryptionError, match="不支持的加密版本"):
            self.manager.decrypt_data(self.password, envelope)

    def test_decrypt_corrupted_json(self):
        with pytest.raises(DecryptionError):
            self.manager.decrypt_data(self.password, b"not json at all")

    def test_backup_if_exists(self):
        filepath = os.path.join(self.gamedata_dir, "savegame.json")
        with open(filepath, 'w') as f:
            f.write("test")
        self.manager._backup_if_exists(filepath)
        backup = filepath + ".bak"
        assert os.path.exists(backup)

    def test_backup_if_not_exists(self):
        filepath = os.path.join(self.gamedata_dir, "nonexistent.json")
        self.manager._backup_if_exists(filepath)
        assert not os.path.exists(filepath + ".bak")

    def test_encrypt_savegame_creates_backup(self):
        self.manager.encrypt_savegame(self.password, self.test_data)
        self.manager.encrypt_savegame(self.password, self.test_data)
        encrypted_backup = self.manager._encrypted_path + ".bak"
        assert os.path.exists(encrypted_backup)

    def test_migrate_to_plaintext_removes_salt(self):
        self.manager.encrypt_savegame(self.password, self.test_data)
        salt_path = os.path.join(self.config_dir, "savegame.salt")
        assert os.path.exists(salt_path)
        self.manager.migrate_to_plaintext(self.password)
        assert not os.path.exists(salt_path)
