# -*- coding: utf-8 -*-
import json
import os
import tempfile

from src.core.savegame_manager import SavegameManager, SavegameSaveResult
from src.security.crypto_manager import CryptoManager
from src.security.file_guard import FileGuard


def _make_manager(tmp_path, encrypted=False, password=None):
    gamedata_dir = os.path.join(str(tmp_path), "data", "gamedata")
    config_dir = os.path.join(str(tmp_path), "data", "config")
    os.makedirs(gamedata_dir, exist_ok=True)
    os.makedirs(config_dir, exist_ok=True)

    file_guard = FileGuard(max_file_size=10 * 1024 * 1024)
    crypto_manager = CryptoManager(config_dir, gamedata_dir)

    savegame_path = os.path.join(gamedata_dir, "savegame.json")
    with open(savegame_path, "w", encoding="utf-8") as f:
        json.dump(SavegameManager.DEFAULT_SAVEGAME.copy(), f)

    manager = SavegameManager(file_guard, crypto_manager, gamedata_dir)

    if encrypted and password:
        manager.load()
        manager.enable_encryption(password)
        manager.set_encryption_password(password)

    return manager


class TestSavegameManagerLoad:
    def test_load_plaintext(self, tmp_path):
        manager = _make_manager(tmp_path)
        manager.load()
        assert manager.data["resources"]["fuel"] == 3000

    def test_load_encrypted_with_password(self, tmp_path):
        manager = _make_manager(tmp_path, encrypted=True, password="testpass123")
        manager.load()
        assert manager.data["resources"]["fuel"] == 3000

    def test_load_encrypted_without_password(self, tmp_path):
        manager = _make_manager(tmp_path, encrypted=True, password="testpass123")
        manager.set_encryption_password(None)
        manager._encrypted_unread = True
        manager.load()
        assert manager.is_encrypted_unread() is True
        assert manager.data["resources"]["fuel"] == 3000


class TestSavegameManagerSave:
    def test_save_plaintext_returns_success(self, tmp_path):
        manager = _make_manager(tmp_path)
        manager.load()
        result = manager.save()
        assert result == SavegameSaveResult.SUCCESS

    def test_save_encrypted_unlocked_returns_success(self, tmp_path):
        manager = _make_manager(tmp_path, encrypted=True, password="testpass123")
        manager.load()
        result = manager.save()
        assert result == SavegameSaveResult.SUCCESS

    def test_save_encrypted_unread_returns_skipped(self, tmp_path):
        manager = _make_manager(tmp_path, encrypted=True, password="testpass123")
        manager.set_encryption_password(None)
        manager._encrypted_unread = True
        result = manager.save()
        assert result == SavegameSaveResult.SKIPPED_ENCRYPTED_UNREAD

    def test_save_unencrypted_unlocked_returns_success(self, tmp_path):
        manager = _make_manager(tmp_path)
        manager.load()
        assert not manager.is_savegame_encrypted()
        result = manager.save()
        assert result == SavegameSaveResult.SUCCESS

    def test_save_unencrypted_no_password_returns_success(self, tmp_path):
        manager = _make_manager(tmp_path)
        manager.load()
        assert not manager.has_encryption_password()
        result = manager.save()
        assert result == SavegameSaveResult.SUCCESS


class TestSavegameManagerSaveResult:
    def test_result_enum_values(self):
        assert SavegameSaveResult.SUCCESS is not None
        assert SavegameSaveResult.SKIPPED_ENCRYPTED_UNREAD is not None
        assert SavegameSaveResult.ENCRYPTION_FAILED is not None

    def test_result_enum_distinct(self):
        values = list(SavegameSaveResult)
        assert len(set(values)) == len(values)


class TestSavegameManagerStateCombinations:
    def test_encrypted_unlocked_save_preserves_data(self, tmp_path):
        manager = _make_manager(tmp_path, encrypted=True, password="testpass123")
        manager.load()
        manager.add_resource("fuel", 500)
        result = manager.save()
        assert result == SavegameSaveResult.SUCCESS

        manager2 = _make_manager(tmp_path, encrypted=True, password="testpass123")
        manager2.set_encryption_password("testpass123")
        manager2.load()
        assert manager2.data["resources"]["fuel"] == 3500

    def test_encrypted_unread_save_does_not_overwrite(self, tmp_path):
        manager = _make_manager(tmp_path, encrypted=True, password="testpass123")
        manager.load()
        manager.add_resource("fuel", 999)

        manager.set_encryption_password(None)
        manager._encrypted_unread = True
        result = manager.save()
        assert result == SavegameSaveResult.SKIPPED_ENCRYPTED_UNREAD

        manager2 = _make_manager(tmp_path, encrypted=True, password="testpass123")
        manager2.set_encryption_password("testpass123")
        manager2.load()
        assert manager2.data["resources"]["fuel"] == 3000

    def test_unlock_after_skip_allows_save(self, tmp_path):
        manager = _make_manager(tmp_path, encrypted=True, password="testpass123")
        manager.load()
        manager.add_resource("fuel", 500)

        manager.set_encryption_password(None)
        manager._encrypted_unread = True
        result = manager.save()
        assert result == SavegameSaveResult.SKIPPED_ENCRYPTED_UNREAD

        manager.set_encryption_password("testpass123")
        manager._encrypted_unread = False
        result = manager.save()
        assert result == SavegameSaveResult.SUCCESS


class TestSavegameManagerPassword:
    def test_set_encryption_password(self, tmp_path):
        manager = _make_manager(tmp_path)
        manager.load()
        manager.set_encryption_password("mypassword")
        assert manager.has_encryption_password() is True

    def test_clear_encryption_password(self, tmp_path):
        manager = _make_manager(tmp_path)
        manager.load()
        manager.set_encryption_password("mypassword")
        manager.set_encryption_password(None)
        assert manager.has_encryption_password() is False

    def test_is_encrypted_unread(self, tmp_path):
        manager = _make_manager(tmp_path, encrypted=True, password="testpass123")
        manager.set_encryption_password(None)
        manager._encrypted_unread = True
        assert manager.is_encrypted_unread() is True

    def test_verify_password_correct(self, tmp_path):
        manager = _make_manager(tmp_path, encrypted=True, password="testpass123")
        assert manager.verify_encryption_password("testpass123") is True

    def test_verify_password_incorrect(self, tmp_path):
        manager = _make_manager(tmp_path, encrypted=True, password="testpass123")
        assert manager.verify_encryption_password("wrongpass") is False


class TestSavegameManagerResources:
    def test_add_resource(self, tmp_path):
        manager = _make_manager(tmp_path)
        manager.load()
        manager.add_resource("fuel", 100)
        assert manager.get_resources()["fuel"] == 3100

    def test_add_resource_no_negative(self, tmp_path):
        manager = _make_manager(tmp_path)
        manager.load()
        manager.add_resource("fuel", -99999)
        assert manager.get_resources()["fuel"] == 0

    def test_add_cores(self, tmp_path):
        manager = _make_manager(tmp_path)
        manager.load()
        manager.add_cores(10)
        assert manager.get_cores() == 10

    def test_set_cores_no_negative(self, tmp_path):
        manager = _make_manager(tmp_path)
        manager.load()
        manager.set_cores(-5)
        assert manager.get_cores() == 0


class TestSavegameManagerDailyCheckin:
    def test_checkin_first_time(self, tmp_path):
        manager = _make_manager(tmp_path)
        manager.load()
        result = manager.check_daily_checkin()
        assert result is True
        assert manager.data["resources"]["fuel"] == 3100

    def test_checkin_twice_same_day(self, tmp_path):
        manager = _make_manager(tmp_path)
        manager.load()
        manager.check_daily_checkin()
        result = manager.check_daily_checkin()
        assert result is False


class TestSavegameManagerUnlockReload:
    def test_set_password_reloads_original_data(self, tmp_path):
        manager = _make_manager(tmp_path, encrypted=True, password="testpass123")
        manager.load()
        manager.add_resource("fuel", 500)
        manager.save()

        manager.set_encryption_password(None)
        manager._encrypted_unread = True
        assert manager.data["resources"]["fuel"] == 3500

        manager.set_encryption_password("testpass123")
        assert manager.is_encrypted_unread() is False
        assert manager.data["resources"]["fuel"] == 3500

    def test_set_password_wrong_password_stays_encrypted_unread(self, tmp_path):
        manager = _make_manager(tmp_path, encrypted=True, password="testpass123")
        manager.load()
        manager.set_encryption_password(None)
        manager._encrypted_unread = True

        manager.set_encryption_password("wrongpass")
        assert manager.is_encrypted_unread() is True
        assert manager.has_encryption_password() is False

    def test_unlock_then_save_preserves_original_data(self, tmp_path):
        manager = _make_manager(tmp_path, encrypted=True, password="testpass123")
        manager.load()
        manager.add_resource("fuel", 500)
        manager.save()

        manager.set_encryption_password(None)
        manager._encrypted_unread = True
        manager.add_resource("ammo", 200)

        manager.set_encryption_password("testpass123")
        result = manager.save()
        assert result == SavegameSaveResult.SUCCESS

        manager2 = _make_manager(tmp_path, encrypted=True, password="testpass123")
        manager2.set_encryption_password("testpass123")
        manager2.load()
        assert manager2.data["resources"]["fuel"] == 3500
        assert manager2.data["resources"]["ammo"] == 3000

    def test_backup_created_on_encrypted_unread(self, tmp_path):
        manager = _make_manager(tmp_path, encrypted=True, password="testpass123")
        manager.load()

        manager2 = _make_manager(tmp_path, encrypted=True, password="testpass123")
        manager2.set_encryption_password(None)
        manager2._encrypted_unread = True
        manager2.load()

        encrypted_bak = os.path.join(
            str(tmp_path), "data", "gamedata", "savegame.json.encrypted.bak"
        )
        assert os.path.exists(encrypted_bak)
