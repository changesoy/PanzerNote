# -*- coding: utf-8 -*-
"""
临时会话管理器
管理异常退出后的文件恢复机制。

核心流程：
  保存：写入 session 目录（manifest.json + autosave 文件）
  关闭：正常退出标记 closed_cleanly=true，清理 autosave
  恢复：启动时扫描旧 session，提示用户恢复未保存内容

目录结构：
  temp/autosave/
    session_20260521_143000/
      manifest.json
      files/
        xxx.autosave
"""

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime
from typing import Any, List, Dict, Optional, cast

from ..utils.logger import get_logger


class TempSessionManager:
    """管理临时会话的保存与恢复

    职责：
    1. 保存 dirty 文件到 session 目录，写入 manifest.json
    2. 正常退出时标记 closed_cleanly=true 并清理
    3. 启动时扫描旧 session，发现异常退出时提供恢复信息
    4. 保存成功后清理对应 autosave 文件

    不在后台线程创建或操作 Qt UI 对象。
    恢复提示由调用方在主线程 window.show() 之后执行。
    """

    MANIFEST_FILENAME = "manifest.json"
    FILES_SUBDIR = "files"

    def __init__(self, temp_base_path: str):
        self._temp_base_path = temp_base_path
        self._current_session_id: Optional[str] = None
        self._current_session_dir: Optional[str] = None

    @property
    def current_session_dir(self) -> Optional[str]:
        return self._current_session_dir

    def _ensure_temp_base(self) -> str:
        os.makedirs(self._temp_base_path, exist_ok=True)
        return self._temp_base_path

    def create_session(self) -> str:
        """创建新的会话目录，返回 session_id"""
        self._ensure_temp_base()
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        session_dir = os.path.join(self._temp_base_path, f"session_{session_id}")
        files_dir = os.path.join(session_dir, self.FILES_SUBDIR)
        os.makedirs(files_dir, exist_ok=True)

        self._current_session_id = session_id
        self._current_session_dir = session_dir

        manifest = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "closed_cleanly": False,
            "files": []
        }
        self._write_manifest(session_dir, manifest)
        return session_id

    def save_dirty_files(self, tab_infos: List[Dict]) -> None:
        """保存 dirty 文件到当前 session

        tab_infos: 列表，每项包含：
          - tab_id: int
          - filepath: Optional[str]  原始文件路径，None 表示未命名
          - content: str  编辑器内容
          - encoding: str
          - is_new: bool
          - is_modified: bool
        """
        if not self._current_session_dir:
            self.create_session()

        assert self._current_session_dir is not None
        manifest = self._read_manifest(self._current_session_dir)
        if manifest is None:
            return

        files_dir = os.path.join(self._current_session_dir, self.FILES_SUBDIR)
        os.makedirs(files_dir, exist_ok=True)

        existing_files = {f.get("original_path"): f for f in manifest.get("files", [])}
        new_files = []

        for info in tab_infos:
            if not info.get("is_modified"):
                continue

            filepath = info.get("filepath")
            content = info.get("content", "")
            encoding = info.get("encoding", "UTF-8")
            is_new = info.get("is_new", False)
            tab_id = info.get("tab_id", 0)

            if filepath:
                path_hash = hashlib.sha256(filepath.encode('utf-8')).hexdigest()[:12]
                basename = os.path.basename(filepath)
                autosave_name = f"{tab_id}_{path_hash}_{basename}.autosave"
                display_name = basename
            else:
                autosave_name = f"untitled_{tab_id}.autosave"
                display_name = f"未命名_{tab_id}"

            autosave_path = os.path.join(files_dir, autosave_name)

            try:
                with open(autosave_path, "w", encoding=encoding, errors="replace") as fh:
                    fh.write(content)
            except Exception as e:
                get_logger(__name__).error("写入 autosave 失败: %s, %s", autosave_path, e)
                continue

            file_entry = {
                "tab_id": tab_id,
                "original_path": filepath or "",
                "autosave_path": autosave_name,
                "display_name": display_name,
                "encoding": encoding,
                "dirty": True,
                "is_new": is_new
            }

            if filepath and filepath in existing_files:
                existing_files[filepath].update(file_entry)
            else:
                new_files.append(file_entry)

        merged = []
        seen_tab_ids = set()
        for f in manifest.get("files", []):
            tid = f.get("tab_id")
            if tid is not None:
                seen_tab_ids.add(tid)
            merged.append(f)

        for f in new_files:
            tid = f.get("tab_id")
            if tid is None or tid not in seen_tab_ids:
                merged.append(f)

        manifest["files"] = merged
        self._write_manifest(self._current_session_dir, manifest)

    def mark_cleanly_closed(self) -> None:
        """标记当前会话为正常关闭"""
        if not self._current_session_dir:
            return

        manifest = self._read_manifest(self._current_session_dir)
        if manifest is not None:
            manifest["closed_cleanly"] = True
            self._write_manifest(self._current_session_dir, manifest)

    def cleanup_session(self) -> None:
        """清理当前会话目录"""
        if self._current_session_dir and os.path.isdir(self._current_session_dir):
            try:
                shutil.rmtree(self._current_session_dir)
            except Exception as e:
                get_logger(__name__).warning("清理会话目录失败: %s, %s", self._current_session_dir, e)
        self._current_session_id = None
        self._current_session_dir = None

    def cleanup_all_clean_sessions(self) -> None:
        """清理所有已正常关闭的旧会话"""
        if not os.path.isdir(self._temp_base_path):
            return

        for entry in os.listdir(self._temp_base_path):
            session_dir = os.path.join(self._temp_base_path, entry)
            if not os.path.isdir(session_dir):
                continue
            manifest = self._read_manifest(session_dir)
            if manifest is not None and manifest.get("closed_cleanly", False):
                try:
                    shutil.rmtree(session_dir)
                except Exception as e:
                    get_logger(__name__).warning("清理旧会话失败: %s, %s", session_dir, e)

    def find_recoverable_sessions(self) -> List[Dict]:
        """扫描所有可恢复的会话

        返回列表，每项包含：
          - session_id: str
          - session_dir: str
          - created_at: str
          - files: list  需要恢复的文件列表
        """
        if not os.path.isdir(self._temp_base_path):
            return []

        recoverable = []

        for entry in os.listdir(self._temp_base_path):
            session_dir = os.path.join(self._temp_base_path, entry)
            if not os.path.isdir(session_dir):
                continue

            manifest = self._read_manifest(session_dir)
            if manifest is None:
                continue

            if manifest.get("closed_cleanly", False):
                continue

            dirty_files = [f for f in manifest.get("files", []) if f.get("dirty", False)]
            if not dirty_files:
                continue

            existing_files = []
            for f in dirty_files:
                autosave_name = f.get("autosave_path", "")
                autosave_full = os.path.join(session_dir, self.FILES_SUBDIR, autosave_name)
                if os.path.isfile(autosave_full):
                    existing_files.append(f)

            if not existing_files:
                continue

            recoverable.append({
                "session_id": manifest.get("session_id", entry),
                "session_dir": session_dir,
                "created_at": manifest.get("created_at", ""),
                "files": existing_files
            })

        recoverable.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return recoverable

    def read_autosave_content(self, session_dir: str, autosave_name: str, encoding: str = "UTF-8") -> Optional[str]:
        """读取 autosave 文件内容"""
        autosave_path = os.path.join(session_dir, self.FILES_SUBDIR, autosave_name)
        if not os.path.isfile(autosave_path):
            return None
        try:
            with open(autosave_path, "r", encoding=encoding, errors="replace") as fh:
                return fh.read()
        except Exception as e:
            get_logger(__name__).error("读取 autosave 失败: %s, %s", autosave_path, e)
            return None

    def remove_recovered_session(self, session_dir: str) -> None:
        """恢复完成后删除指定会话目录"""
        if os.path.isdir(session_dir):
            try:
                shutil.rmtree(session_dir)
            except Exception as e:
                get_logger(__name__).warning("删除已恢复会话失败: %s, %s", session_dir, e)

    def remove_autosave_for_file(self, original_path: str) -> None:
        """保存成功后清理对应 autosave 文件"""
        if not self._current_session_dir:
            return

        manifest = self._read_manifest(self._current_session_dir)
        if manifest is None:
            return

        files_dir = os.path.join(self._current_session_dir, self.FILES_SUBDIR)
        updated_files = []
        changed = False

        for f in manifest.get("files", []):
            if f.get("original_path") == original_path and f.get("dirty", False):
                autosave_name = f.get("autosave_path", "")
                if autosave_name:
                    autosave_full = os.path.join(files_dir, autosave_name)
                    if os.path.isfile(autosave_full):
                        try:
                            os.remove(autosave_full)
                        except Exception:
                            pass
                changed = True
            else:
                updated_files.append(f)

        if changed:
            manifest["files"] = updated_files
            self._write_manifest(self._current_session_dir, manifest)

    def _read_manifest(self, session_dir: str) -> Optional[Dict]:
        manifest_path = os.path.join(session_dir, self.MANIFEST_FILENAME)
        if not os.path.isfile(manifest_path):
            return None
        try:
            with open(manifest_path, "r", encoding="utf-8") as fh:
                return cast(Optional[Dict[str, Any]], json.load(fh))
        except Exception as e:
            get_logger(__name__).error("读取 manifest 失败: %s, %s", manifest_path, e)
            return None

    def _write_manifest(self, session_dir: str, manifest: Dict) -> None:
        manifest_path = os.path.join(session_dir, self.MANIFEST_FILENAME)
        try:
            with open(manifest_path, "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            get_logger(__name__).error("写入 manifest 失败: %s, %s", manifest_path, e)
