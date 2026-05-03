# -*- coding: utf-8 -*-
"""
存储工厂

根据配置创建合适的存储实现实例。
"""

import os
from typing import Optional

from ..utils.logger import get_logger
from .storage_interface import IStorage
from .json_storage import JsonStorage
from .sqlite_storage import SqliteStorage


class StorageFactory:
    TYPE_JSON = "json"
    TYPE_SQLITE = "sqlite"

    @staticmethod
    def create(
        storage_type: str,
        base_dir: str,
        config=None,
    ) -> IStorage:
        logger = get_logger(__name__)

        if storage_type == StorageFactory.TYPE_JSON:
            storage_dir = os.path.join(base_dir, "storage_json")
            storage = JsonStorage(storage_dir)
        elif storage_type == StorageFactory.TYPE_SQLITE:
            db_path = os.path.join(base_dir, "storage_sqlite", "panzernote.db")
            storage = SqliteStorage(db_path)
        else:
            raise ValueError(f"不支持的存储类型: {storage_type}")

        storage.initialize()
        logger.info("存储实例已创建: %s", storage_type)
        return storage

    @staticmethod
    def create_from_config(config) -> IStorage:
        storage_type = config.get_setting("storage_type", StorageFactory.TYPE_JSON)
        base_dir = config.get_base_path()
        return StorageFactory.create(storage_type, base_dir, config)
