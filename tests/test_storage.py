# -*- coding: utf-8 -*-
import json
import os
import tempfile

from src.storage.storage_interface import IStorage, StorageTransaction
from src.storage.json_storage import JsonStorage
from src.storage.sqlite_storage import SqliteStorage
from src.storage.storage_factory import StorageFactory
from src.storage.storage_migrator import StorageMigrator


class TestJsonStorage:
    def _make_storage(self, tmp_path):
        storage_dir = os.path.join(str(tmp_path), "json_storage")
        storage = JsonStorage(storage_dir)
        storage.initialize()
        return storage

    def test_initialize(self, tmp_path):
        storage = self._make_storage(tmp_path)
        assert os.path.isdir(os.path.join(str(tmp_path), "json_storage"))

    def test_set_and_get(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set("test_collection", "key1", "value1")
        result = storage.get("test_collection", "key1")
        assert result == "value1"

    def test_get_default(self, tmp_path):
        storage = self._make_storage(tmp_path)
        result = storage.get("nonexistent", "key", "default")
        assert result == "default"

    def test_delete(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set("test", "key1", "val1")
        assert storage.delete("test", "key1") is True
        assert storage.get("test", "key1") is None

    def test_delete_nonexistent(self, tmp_path):
        storage = self._make_storage(tmp_path)
        assert storage.delete("test", "nonexistent") is False

    def test_exists(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set("test", "key1", "val1")
        assert storage.exists("test", "key1") is True
        assert storage.exists("test", "key2") is False

    def test_list_keys(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set("test", "a", 1)
        storage.set("test", "b", 2)
        storage.set("test", "c", 3)
        keys = storage.list_keys("test")
        assert set(keys) == {"a", "b", "c"}

    def test_get_collection(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set("test", "k1", "v1")
        storage.set("test", "k2", "v2")
        data = storage.get_collection("test")
        assert data == {"k1": "v1", "k2": "v2"}

    def test_set_collection(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set_collection("test", {"x": 1, "y": 2})
        assert storage.get("test", "x") == 1
        assert storage.get("test", "y") == 2

    def test_delete_collection(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set("test", "k", "v")
        assert storage.delete_collection("test") is True
        assert storage.list_keys("test") == []

    def test_list_collections(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set("col1", "k", "v")
        storage.set("col2", "k", "v")
        collections = storage.list_collections()
        assert "col1" in collections
        assert "col2" in collections

    def test_meta(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set("test", "key1", "val1")
        storage.set_meta("test", "key1", {"created": "2024-01-01"})
        meta = storage.get_meta("test", "key1")
        assert meta["created"] == "2024-01-01"

    def test_complex_values(self, tmp_path):
        storage = self._make_storage(tmp_path)
        complex_val = {"list": [1, 2, 3], "nested": {"a": True}}
        storage.set("test", "complex", complex_val)
        result = storage.get("test", "complex")
        assert result == complex_val

    def test_persistence(self, tmp_path):
        storage_dir = os.path.join(str(tmp_path), "json_storage_persist")
        storage1 = JsonStorage(storage_dir)
        storage1.initialize()
        storage1.set("test", "persist_key", "persist_val")
        storage1.close()

        storage2 = JsonStorage(storage_dir)
        storage2.initialize()
        result = storage2.get("test", "persist_key")
        assert result == "persist_val"
        storage2.close()

    def test_close(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.close()


class TestSqliteStorage:
    def _make_storage(self, tmp_path):
        db_dir = os.path.join(str(tmp_path), "sqlite_storage")
        db_path = os.path.join(db_dir, "test.db")
        storage = SqliteStorage(db_path)
        storage.initialize()
        return storage

    def test_initialize(self, tmp_path):
        storage = self._make_storage(tmp_path)
        db_dir = os.path.join(str(tmp_path), "sqlite_storage")
        assert os.path.isfile(os.path.join(db_dir, "test.db"))

    def test_set_and_get(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set("test", "key1", "value1")
        result = storage.get("test", "key1")
        assert result == "value1"

    def test_get_default(self, tmp_path):
        storage = self._make_storage(tmp_path)
        result = storage.get("nonexistent", "key", "default")
        assert result == "default"

    def test_delete(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set("test", "key1", "val1")
        assert storage.delete("test", "key1") is True
        assert storage.get("test", "key1") is None

    def test_delete_nonexistent(self, tmp_path):
        storage = self._make_storage(tmp_path)
        assert storage.delete("test", "nonexistent") is False

    def test_exists(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set("test", "key1", "val1")
        assert storage.exists("test", "key1") is True
        assert storage.exists("test", "key2") is False

    def test_list_keys(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set("test", "a", 1)
        storage.set("test", "b", 2)
        storage.set("test", "c", 3)
        keys = storage.list_keys("test")
        assert set(keys) == {"a", "b", "c"}

    def test_get_collection(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set("test", "k1", "v1")
        storage.set("test", "k2", "v2")
        data = storage.get_collection("test")
        assert data == {"k1": "v1", "k2": "v2"}

    def test_set_collection(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set_collection("test", {"x": 1, "y": 2})
        assert storage.get("test", "x") == 1
        assert storage.get("test", "y") == 2

    def test_delete_collection(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set("test", "k", "v")
        assert storage.delete_collection("test") is True
        assert storage.list_keys("test") == []

    def test_list_collections(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set("col1", "k", "v")
        storage.set("col2", "k", "v")
        collections = storage.list_collections()
        assert "col1" in collections
        assert "col2" in collections

    def test_meta(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set("test", "key1", "val1")
        storage.set_meta("test", "key1", {"version": 2})
        meta = storage.get_meta("test", "key1")
        assert meta["version"] == 2

    def test_complex_values(self, tmp_path):
        storage = self._make_storage(tmp_path)
        complex_val = {"list": [1, 2, 3], "nested": {"a": True}}
        storage.set("test", "complex", complex_val)
        result = storage.get("test", "complex")
        assert result == complex_val

    def test_transaction_commit(self, tmp_path):
        storage = self._make_storage(tmp_path)
        with storage.transaction() as tx:
            storage.set("test", "tx_key", "tx_val")
            tx.commit()
        assert storage.get("test", "tx_key") == "tx_val"

    def test_transaction_rollback(self, tmp_path):
        storage = self._make_storage(tmp_path)
        try:
            with storage.transaction():
                storage.set("test", "rb_key", "rb_val")
                raise ValueError("force rollback")
        except ValueError:
            pass
        assert storage.get("test", "rb_key") is None

    def test_upsert(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.set("test", "key1", "val1")
        storage.set("test", "key1", "val2")
        assert storage.get("test", "key1") == "val2"

    def test_close(self, tmp_path):
        storage = self._make_storage(tmp_path)
        storage.close()


class TestStorageFactory:
    def test_create_json(self, tmp_path):
        storage = StorageFactory.create("json", str(tmp_path))
        assert isinstance(storage, JsonStorage)
        storage.close()

    def test_create_sqlite(self, tmp_path):
        storage = StorageFactory.create("sqlite", str(tmp_path))
        assert isinstance(storage, SqliteStorage)
        storage.close()

    def test_create_invalid_type(self, tmp_path):
        try:
            StorageFactory.create("invalid", str(tmp_path))
            assert False, "Should raise ValueError"
        except ValueError:
            pass


class TestStorageMigrator:
    def test_migrate_json_to_sqlite(self, tmp_path):
        json_dir = os.path.join(str(tmp_path), "json_src")
        sqlite_dir = os.path.join(str(tmp_path), "sqlite_dst")

        json_storage = JsonStorage(json_dir)
        json_storage.initialize()
        json_storage.set("settings", "theme", "dark")
        json_storage.set("settings", "font_size", 14)
        json_storage.set("workspace", "last_file", "/test.txt")
        json_storage.close()

        migrator = StorageMigrator()
        result = migrator.migrate_json_to_sqlite(json_dir, sqlite_dir)
        assert result["migrated_collections"] >= 1
        assert result["migrated_keys"] >= 2
        assert len(result["errors"]) == 0

        db_path = os.path.join(sqlite_dir, "panzernote.db")
        sqlite_storage = SqliteStorage(db_path)
        sqlite_storage.initialize()
        assert sqlite_storage.get("settings", "theme") == "dark"
        assert sqlite_storage.get("settings", "font_size") == 14
        assert sqlite_storage.get("workspace", "last_file") == "/test.txt"
        sqlite_storage.close()

    def test_migrate_sqlite_to_json(self, tmp_path):
        sqlite_dir = os.path.join(str(tmp_path), "sqlite_src")
        json_dir = os.path.join(str(tmp_path), "json_dst")

        db_path = os.path.join(sqlite_dir, "panzernote.db")
        sqlite_storage = SqliteStorage(db_path)
        sqlite_storage.initialize()
        sqlite_storage.set("settings", "theme", "light")
        sqlite_storage.set("game", "level", 5)
        sqlite_storage.close()

        migrator = StorageMigrator()
        result = migrator.migrate_sqlite_to_json(sqlite_dir, json_dir)
        assert result["migrated_collections"] >= 1
        assert result["migrated_keys"] >= 2
        assert len(result["errors"]) == 0

        json_storage = JsonStorage(json_dir)
        json_storage.initialize()
        assert json_storage.get("settings", "theme") == "light"
        assert json_storage.get("game", "level") == 5
        json_storage.close()

    def test_migrate_no_overwrite(self, tmp_path):
        json_dir = os.path.join(str(tmp_path), "json_no_overwrite")
        sqlite_dir = os.path.join(str(tmp_path), "sqlite_no_overwrite")

        json_storage = JsonStorage(json_dir)
        json_storage.initialize()
        json_storage.set("test", "key1", "original")
        json_storage.close()

        db_path = os.path.join(sqlite_dir, "panzernote.db")
        sqlite_storage = SqliteStorage(db_path)
        sqlite_storage.initialize()
        sqlite_storage.set("test", "key1", "new_value")
        sqlite_storage.close()

        migrator = StorageMigrator()
        result = migrator.migrate_json_to_sqlite(json_dir, sqlite_dir, overwrite=False)
        assert result["skipped_keys"] >= 1

        sqlite_storage2 = SqliteStorage(db_path)
        sqlite_storage2.initialize()
        assert sqlite_storage2.get("test", "key1") == "new_value"
        sqlite_storage2.close()

    def test_migrate_with_overwrite(self, tmp_path):
        json_dir = os.path.join(str(tmp_path), "json_overwrite")
        sqlite_dir = os.path.join(str(tmp_path), "sqlite_overwrite")

        json_storage = JsonStorage(json_dir)
        json_storage.initialize()
        json_storage.set("test", "key1", "from_json")
        json_storage.close()

        db_path = os.path.join(sqlite_dir, "panzernote.db")
        sqlite_storage = SqliteStorage(db_path)
        sqlite_storage.initialize()
        sqlite_storage.set("test", "key1", "existing")
        sqlite_storage.close()

        migrator = StorageMigrator()
        result = migrator.migrate_json_to_sqlite(json_dir, sqlite_dir, overwrite=True)
        assert result["migrated_keys"] >= 1

        sqlite_storage2 = SqliteStorage(db_path)
        sqlite_storage2.initialize()
        assert sqlite_storage2.get("test", "key1") == "from_json"
        sqlite_storage2.close()
