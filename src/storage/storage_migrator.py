# -*- coding: utf-8 -*-
"""
数据迁移工具

支持不同存储实现间的数据迁移及版本升级。
"""

import os
from typing import Optional

from ..utils.logger import get_logger
from .storage_interface import IStorage
from .json_storage import JsonStorage
from .sqlite_storage import SqliteStorage
from .storage_factory import StorageFactory


class MigrationError(Exception):
    pass


class StorageMigrator:

    def __init__(self):
        self._logger = get_logger(__name__)

    def migrate(
        self,
        source: IStorage,
        target: IStorage,
        collections: Optional[list] = None,
        overwrite: bool = False,
    ) -> dict:
        result = {
            "migrated_collections": 0,
            "migrated_keys": 0,
            "skipped_keys": 0,
            "errors": [],
        }

        source_collections = collections or source.list_collections()

        for collection in source_collections:
            try:
                data = source.get_collection(collection)
                if not data:
                    self._logger.info("跳过空集合: %s", collection)
                    continue

                existing_keys = set(target.list_keys(collection))
                migrated_keys = 0
                skipped_keys = 0

                for key, value in data.items():
                    if not overwrite and key in existing_keys:
                        skipped_keys += 1
                        continue
                    target.set(collection, key, value)
                    migrated_keys += 1

                meta_keys = source.list_keys(f"_meta_{collection}")
                for mk in meta_keys:
                    meta = source.get_meta(collection, mk)
                    if meta:
                        target.set_meta(collection, mk, meta)

                result["migrated_collections"] += 1
                result["migrated_keys"] += migrated_keys
                result["skipped_keys"] += skipped_keys
                self._logger.info(
                    "迁移集合 %s: %d 键已迁移, %d 键已跳过",
                    collection, migrated_keys, skipped_keys
                )

            except Exception as e:
                error_msg = f"迁移集合 {collection} 失败: {e}"
                result["errors"].append(error_msg)
                self._logger.error(error_msg)

        self._logger.info(
            "迁移完成: %d 集合, %d 键已迁移, %d 键已跳过, %d 错误",
            result["migrated_collections"],
            result["migrated_keys"],
            result["skipped_keys"],
            len(result["errors"]),
        )
        return result

    def migrate_json_to_sqlite(
        self,
        json_dir: str,
        sqlite_dir: str,
        overwrite: bool = False,
    ) -> dict:
        json_storage = JsonStorage(json_dir)
        json_storage.initialize()

        db_path = os.path.join(sqlite_dir, "panzernote.db")
        sqlite_storage = SqliteStorage(db_path)
        sqlite_storage.initialize()

        try:
            return self.migrate(json_storage, sqlite_storage, overwrite=overwrite)
        finally:
            json_storage.close()
            sqlite_storage.close()

    def migrate_sqlite_to_json(
        self,
        sqlite_dir: str,
        json_dir: str,
        overwrite: bool = False,
    ) -> dict:
        db_path = os.path.join(sqlite_dir, "panzernote.db")
        sqlite_storage = SqliteStorage(db_path)
        sqlite_storage.initialize()

        json_storage = JsonStorage(json_dir)
        json_storage.initialize()

        try:
            return self.migrate(sqlite_storage, json_storage, overwrite=overwrite)
        finally:
            sqlite_storage.close()
            json_storage.close()
