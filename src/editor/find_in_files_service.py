# -*- coding: utf-8 -*-
"""
跨文件搜索后台服务
使用 QThread 在后台遍历目录、读取文件、执行正则/纯文本匹配，
结果通过信号投递到主线程。
"""

import os
import re
from typing import Any, List, Optional, Tuple

from PyQt6.QtCore import QThread, pyqtSignal

from ..utils.logger import get_logger

MatchRecord = Tuple[str, int, int, str]
"""搜索结果元组: (filepath, line_number, column, line_text)"""

_DEFAULT_IGNORE_DIRS = frozenset({
    ".git", ".venv", "venv", ".tox", "node_modules",
    "__pycache__", ".mypy_cache", ".pytest_cache",
    ".idea", ".vscode", ".vs", "dist", "build",
    ".eggs", "site-packages",
})


class FindInFilesWorker(QThread):
    """跨文件搜索工作线程。

    用法：
        worker = FindInFilesWorker(root_dir, query, options)
        worker.result_found.connect(handle_result)
        worker.search_finished.connect(handle_finished)
        worker.start()
    """

    result_found = pyqtSignal(str, int, int, str)
    search_finished = pyqtSignal(int)

    def __init__(
        self,
        root_dir: str,
        query: str,
        *,
        case_sensitive: bool = False,
        whole_word: bool = False,
        use_regex: bool = False,
        include: str = "",
        exclude: str = "",
        max_results: int = 5000,
        file_list: Optional[List[str]] = None,
        parent: Any = None,
    ):
        super().__init__(parent)
        self._root_dir = root_dir
        self._query = query
        self._case_sensitive = case_sensitive
        self._whole_word = whole_word
        self._use_regex = use_regex
        self._include = include
        self._exclude = exclude
        self._max_results = max_results
        self._file_list = file_list
        self._cancelled = False
        self._logger = get_logger(__name__)

    def cancel(self) -> None:
        """请求取消搜索。"""
        self._cancelled = True

    def run(self) -> None:
        total = 0
        pattern = None

        try:
            if self._use_regex:
                pattern = self._compile_regex(self._query)
                if pattern is None:
                    self.search_finished.emit(0)
                    return

            if self._file_list is not None:
                for filepath in self._file_list:
                    if self._cancelled:
                        break
                    if not os.path.isfile(filepath):
                        continue
                    total = self._search_file(filepath, pattern, total)
                    if total >= self._max_results:
                        self.search_finished.emit(total)
                        return
            else:
                include_globs = self._compile_globs(self._include)
                exclude_globs = self._compile_globs(self._exclude)

                for dirpath, dirnames, filenames in os.walk(self._root_dir, followlinks=False):
                    if self._cancelled:
                        break

                    dirnames[:] = self._filter_hidden_dirs(dirnames)

                    for fname in filenames:
                        if self._cancelled:
                            break

                        filepath = os.path.join(dirpath, fname)
                        rel_path = os.path.relpath(filepath, self._root_dir)

                        if not self._pass_glob_filter(rel_path, include_globs, exclude_globs):
                            continue

                        total = self._search_file(filepath, pattern, total)
                        if total >= self._max_results:
                            self.search_finished.emit(total)
                            return
        finally:
            self.search_finished.emit(total)

    def _search_file(self, filepath: str, pattern, total: int) -> int:
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
                for line_num, line_text in enumerate(fh, 1):
                    if self._cancelled:
                        break

                    line_text = line_text.rstrip("\n\r")
                    matches = self._search_line(line_text, pattern)

                    for col, end_col in matches:
                        self.result_found.emit(filepath, line_num, col, line_text)
                        total += 1
                        if total >= self._max_results:
                            return total
        except OSError:
            pass
        return total

    def _search_line(self, line_text: str, pattern: Optional[re.Pattern]) -> List[Tuple[int, int]]:
        """在一行中搜索，返回 [(col, end_col), ...]."""
        results: List[Tuple[int, int]] = []

        if pattern is not None:
            for m in pattern.finditer(line_text):
                if m.start() == m.end():
                    continue
                results.append((m.start() + 1, m.end() + 1))
        else:
            q = self._query
            if not self._case_sensitive:
                line_lower = line_text.lower()
                q = q.lower()
            start = 0
            while True:
                if self._case_sensitive:
                    idx = line_text.find(q, start)
                else:
                    idx = line_lower.find(q, start)
                if idx == -1:
                    break
                end_idx = idx + len(q)

                if self._whole_word:
                    if not self._is_word_bound(line_text, idx, end_idx):
                        start = end_idx
                        continue

                results.append((idx + 1, end_idx + 1))
                start = end_idx

        return results

    @staticmethod
    def _is_word_bound(text: str, start: int, end: int) -> bool:
        left_ok = start == 0 or not text[start - 1].isalnum()
        right_ok = end >= len(text) or not text[end].isalnum()
        return left_ok and right_ok

    @staticmethod
    def _filter_hidden_dirs(dirnames: List[str]) -> List[str]:
        return [d for d in dirnames if d not in _DEFAULT_IGNORE_DIRS and not d.startswith(".")]

    def _compile_regex(self, query: str) -> Optional[re.Pattern]:
        flags = 0
        if not self._case_sensitive:
            flags |= re.IGNORECASE
        try:
            return re.compile(query, flags)
        except re.error as exc:
            self._logger.debug("无效正则: %s — %s", query, exc)
            return None

    @staticmethod
    def _compile_globs(glob_str: str) -> List[re.Pattern]:
        if not glob_str or not glob_str.strip():
            return []
        patterns: List[re.Pattern] = []
        for part in glob_str.split(","):
            part = part.strip()
            if not part:
                continue
            import fnmatch
            regex = fnmatch.translate(part)
            patterns.append(re.compile(regex, re.IGNORECASE))
        return patterns

    @staticmethod
    def _pass_glob_filter(
        path: str,
        includes: List[re.Pattern],
        excludes: List[re.Pattern],
    ) -> bool:
        if excludes and any(p.search(path) for p in excludes):
            return False
        if includes and not any(p.search(path) for p in includes):
            return False
        return True
