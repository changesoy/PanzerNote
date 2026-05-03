# -*- coding: utf-8 -*-
"""
SQLite 数据库存储适配器

基于 SQLite 的 IStorage 实现，支持事务和高效查询。
"""

import json
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger
from .storage_interface import IStorage, StorageTransaction


class SqliteStorage(IStorage):

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._local = threading.local()
        self._lock = threading.RLock()
        self._logger = get_logger(__name__)
        self._initialized = False
        self._transaction_depth = 0

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
            self._local.conn = sqlite3.connect(self._db_path, check_same_thread=False, isolation_level=None)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def initialize(self) -> None:
        if self._initialized:
            return
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS storage_data (
                collection TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (collection, key)
            );
            CREATE TABLE IF NOT EXISTS storage_meta (
                collection TEXT NOT NULL,
                key TEXT NOT NULL,
                meta TEXT NOT NULL,
                PRIMARY KEY (collection, key)
            );
            CREATE INDEX IF NOT EXISTS idx_collection
                ON storage_data(collection);
        """)
        conn.commit()
        self._initialized = True
        self._logger.info("SQLite 存储已初始化: %s", self._db_path)

    def close(self) -> None:
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None
        self._initialized = False
        self._logger.info("SQLite 存储已关闭")

    def get(self, collection: str, key: str, default: Any = None) -> Any:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT value FROM storage_data WHERE collection=? AND key=?",
            (collection, key)
        )
        row = cursor.fetchone()
        if row is None:
            return default
        return json.loads(row["value"])

    def set(self, collection: str, key: str, value: Any) -> None:
        conn = self._get_conn()
        serialized = json.dumps(value, ensure_ascii=False)
        conn.execute(
            "INSERT OR REPLACE INTO storage_data (collection, key, value) VALUES (?, ?, ?)",
            (collection, key, serialized)
        )
        if self._transaction_depth == 0:
            conn.commit()

    def delete(self, collection: str, key: str) -> bool:
        conn = self._get_conn()
        cursor = conn.execute(
            "DELETE FROM storage_data WHERE collection=? AND key=?",
            (collection, key)
        )
        if self._transaction_depth == 0:
            conn.commit()
        return cursor.rowcount > 0

    def exists(self, collection: str, key: str) -> bool:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT 1 FROM storage_data WHERE collection=? AND key=?",
            (collection, key)
        )
        return cursor.fetchone() is not None

    def list_keys(self, collection: str) -> List[str]:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT key FROM storage_data WHERE collection=? ORDER BY key",
            (collection,)
        )
        return [row["key"] for row in cursor.fetchall()]

    def get_collection(self, collection: str) -> Dict[str, Any]:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT key, value FROM storage_data WHERE collection=? ORDER BY key",
            (collection,)
        )
        return {row["key"]: json.loads(row["value"]) for row in cursor.fetchall()}

    def set_collection(self, collection: str, data: Dict[str, Any]) -> None:
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM storage_data WHERE collection=?",
            (collection,)
        )
        for key, value in data.items():
            serialized = json.dumps(value, ensure_ascii=False)
            conn.execute(
                "INSERT INTO storage_data (collection, key, value) VALUES (?, ?, ?)",
                (collection, key, serialized)
            )
        if self._transaction_depth == 0:
            conn.commit()

    def delete_collection(self, collection: str) -> bool:
        conn = self._get_conn()
        cursor = conn.execute(
            "DELETE FROM storage_data WHERE collection=?",
            (collection,)
        )
        conn.execute(
            "DELETE FROM storage_meta WHERE collection=?",
            (collection,)
        )
        if self._transaction_depth == 0:
            conn.commit()
        return cursor.rowcount > 0

    def list_collections(self) -> List[str]:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT DISTINCT collection FROM storage_data ORDER BY collection"
        )
        return [row["collection"] for row in cursor.fetchall()]

    def get_meta(self, collection: str, key: str) -> Dict[str, Any]:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT meta FROM storage_meta WHERE collection=? AND key=?",
            (collection, key)
        )
        row = cursor.fetchone()
        if row is None:
            return {}
        return json.loads(row["meta"])

    def set_meta(self, collection: str, key: str, meta: Dict[str, Any]) -> None:
        conn = self._get_conn()
        serialized = json.dumps(meta, ensure_ascii=False)
        conn.execute(
            "INSERT OR REPLACE INTO storage_meta (collection, key, meta) VALUES (?, ?, ?)",
            (collection, key, serialized)
        )
        if self._transaction_depth == 0:
            conn.commit()

    def _begin_transaction(self) -> None:
        self._transaction_depth += 1
        if self._transaction_depth == 1:
            conn = self._get_conn()
            conn.execute("BEGIN")

    def _do_commit(self) -> None:
        self._transaction_depth = max(0, self._transaction_depth - 1)
        if self._transaction_depth == 0:
            conn = self._get_conn()
            conn.commit()

    def _do_rollback(self) -> None:
        self._transaction_depth = max(0, self._transaction_depth - 1)
        if self._transaction_depth == 0:
            conn = self._get_conn()
            conn.rollback()
