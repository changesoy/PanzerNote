# -*- coding: utf-8 -*-
"""
PanzerNote 数据存储抽象层

定义 IStorage 接口，提供 JSON 和 SQLite 两种存储实现。
所有模块必须通过 IStorage 接口进行数据操作。
"""

from .storage_interface import IStorage, StorageTransaction
from .json_storage import JsonStorage
from .sqlite_storage import SqliteStorage
from .storage_factory import StorageFactory
from .storage_migrator import StorageMigrator

__all__ = [
    "IStorage",
    "StorageTransaction",
    "JsonStorage",
    "SqliteStorage",
    "StorageFactory",
    "StorageMigrator",
]
