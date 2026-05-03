# -*- coding: utf-8 -*-
"""
JSON 文件存储适配器

基于 JSON 文件的 IStorage 实现，兼容现有数据格式。
"""

import json
import os
import shutil
import threading
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger
from .storage_interface import IStorage


class JsonStorage(IStorage):

    def __init__(self, base_dir: str):
        self._base_dir = base_dir
        self._data: Dict[str, Dict[str, Any]] = {}
        self._meta: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._lock = threading.RLock()
        self._logger = get_logger(__name__)
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        os.makedirs(self._base_dir, exist_ok=True)
        self._load_all()
        self._initialized = True
        self._logger.info("JSON 存储已初始化: %s", self._base_dir)

    def close(self) -> None:
        if self._initialized:
            self._save_all()
            self._initialized = False
            self._logger.info("JSON 存储已关闭")

    def get(self, collection: str, key: str, default: Any = None) -> Any:
        with self._lock:
            coll = self._data.get(collection, {})
            return coll.get(key, default)

    def set(self, collection: str, key: str, value: Any) -> None:
        with self._lock:
            if collection not in self._data:
                self._data[collection] = {}
            self._data[collection][key] = value
            self._persist_collection(collection)

    def delete(self, collection: str, key: str) -> bool:
        with self._lock:
            coll = self._data.get(collection, {})
            if key not in coll:
                return False
            del coll[key]
            self._persist_collection(collection)
            return True

    def exists(self, collection: str, key: str) -> bool:
        with self._lock:
            return key in self._data.get(collection, {})

    def list_keys(self, collection: str) -> List[str]:
        with self._lock:
            return list(self._data.get(collection, {}).keys())

    def get_collection(self, collection: str) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data.get(collection, {}))

    def set_collection(self, collection: str, data: Dict[str, Any]) -> None:
        with self._lock:
            self._data[collection] = dict(data)
            self._persist_collection(collection)

    def delete_collection(self, collection: str) -> bool:
        with self._lock:
            if collection not in self._data:
                return False
            del self._data[collection]
            filepath = self._collection_filepath(collection)
            if os.path.exists(filepath):
                os.remove(filepath)
            if collection in self._meta:
                del self._meta[collection]
            meta_path = self._meta_filepath(collection)
            if os.path.exists(meta_path):
                os.remove(meta_path)
            return True

    def list_collections(self) -> List[str]:
        with self._lock:
            return list(self._data.keys())

    def get_meta(self, collection: str, key: str) -> Dict[str, Any]:
        with self._lock:
            coll_meta = self._meta.get(collection, {})
            return dict(coll_meta.get(key, {}))

    def set_meta(self, collection: str, key: str, meta: Dict[str, Any]) -> None:
        with self._lock:
            if collection not in self._meta:
                self._meta[collection] = {}
            self._meta[collection][key] = dict(meta)
            self._persist_meta(collection)

    def _collection_filepath(self, collection: str) -> str:
        return os.path.join(self._base_dir, f"{collection}.json")

    def _meta_filepath(self, collection: str) -> str:
        return os.path.join(self._base_dir, f"_{collection}_meta.json")

    def _load_all(self) -> None:
        if not os.path.isdir(self._base_dir):
            return
        for filename in os.listdir(self._base_dir):
            if not filename.endswith('.json'):
                continue
            if filename.startswith('_') and filename.endswith('_meta.json'):
                continue
            filepath = os.path.join(self._base_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                collection_name = filename[:-5]
                if isinstance(data, dict):
                    self._data[collection_name] = data
                else:
                    self._logger.warning("跳过非字典数据: %s", filename)
            except (json.JSONDecodeError, OSError) as e:
                self._logger.warning("加载 %s 失败: %s", filename, e)

        for filename in os.listdir(self._base_dir):
            if filename.startswith('_') and filename.endswith('_meta.json'):
                filepath = os.path.join(self._base_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    collection_name = filename[1:-10]
                    if isinstance(data, dict):
                        self._meta[collection_name] = data
                except (json.JSONDecodeError, OSError) as e:
                    self._logger.warning("加载元数据 %s 失败: %s", filename, e)

    def _save_all(self) -> None:
        with self._lock:
            for collection in self._data:
                self._persist_collection(collection)
            for collection in self._meta:
                self._persist_meta(collection)

    def _persist_collection(self, collection: str) -> None:
        filepath = self._collection_filepath(collection)
        try:
            data = self._data.get(collection, {})
            content = json.dumps(data, ensure_ascii=False, indent=2)
            tmp_path = filepath + ".tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.write(content)
            shutil.move(tmp_path, filepath)
        except OSError as e:
            self._logger.error("持久化集合 %s 失败: %s", collection, e)

    def _persist_meta(self, collection: str) -> None:
        filepath = self._meta_filepath(collection)
        try:
            data = self._meta.get(collection, {})
            content = json.dumps(data, ensure_ascii=False, indent=2)
            tmp_path = filepath + ".tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.write(content)
            shutil.move(tmp_path, filepath)
        except OSError as e:
            self._logger.error("持久化元数据 %s 失败: %s", collection, e)
