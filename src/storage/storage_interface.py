# -*- coding: utf-8 -*-
"""
存储接口定义

定义 IStorage 接口，包含数据 CRUD、事务管理及元数据操作的标准方法。
所有存储实现必须实现此接口。
"""

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Dict, List, Optional


class StorageTransaction:
    def __init__(self, storage: "IStorage"):
        self._storage = storage
        self._committed = False
        self._rolled_back = False

    def commit(self) -> None:
        if not self._committed and not self._rolled_back:
            self._storage._do_commit()
            self._committed = True

    def rollback(self) -> None:
        if not self._committed and not self._rolled_back:
            self._storage._do_rollback()
            self._rolled_back = True

    def __enter__(self):
        self._storage._begin_transaction()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        elif not self._committed:
            self.commit()
        return False


class IStorage(ABC):

    @abstractmethod
    def initialize(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, collection: str, key: str, default: Any = None) -> Any:
        raise NotImplementedError

    @abstractmethod
    def set(self, collection: str, key: str, value: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, collection: str, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def exists(self, collection: str, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_keys(self, collection: str) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    def get_collection(self, collection: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def set_collection(self, collection: str, data: Dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_collection(self, collection: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_collections(self) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    def get_meta(self, collection: str, key: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def set_meta(self, collection: str, key: str, meta: Dict[str, Any]) -> None:
        raise NotImplementedError

    @contextmanager
    def transaction(self):
        self._begin_transaction()
        tx = StorageTransaction(self)
        tx._storage = self
        try:
            yield tx
        except Exception:
            if not tx._committed and not tx._rolled_back:
                tx.rollback()
            raise
        else:
            if not tx._committed and not tx._rolled_back:
                tx.commit()

    def _begin_transaction(self) -> None:
        pass

    def _do_commit(self) -> None:
        pass

    def _do_rollback(self) -> None:
        pass
