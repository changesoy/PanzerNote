# -*- coding: utf-8 -*-
"""
跨文件搜索后台服务
使用 QThread 在后台遍历目录、读取文件、执行正则/纯文本匹配，
结果通过信号投递到主线程。
"""

import fnmatch
import os
import re
import time
from typing import Any, List, Optional, Pattern, Tuple

from PyQt6.QtCore import QThread, pyqtSignal

from ..utils.logger import get_logger
from .file_open_service import _is_binary_file

MatchRecord = Tuple[str, int, int, str]
"""搜索结果元组: (filepath, line_number, column, line_text)"""

_DEFAULT_IGNORE_DIRS = frozenset({
    ".git", ".venv", "venv", ".tox", "node_modules",
    "__pycache__", ".mypy_cache", ".pytest_cache",
    ".idea", ".vscode", ".vs", "dist", "build",
    ".eggs", "site-packages",
})

# gitignore 规则：正则 + 是否仅目录（dir_only，以 "/" 结尾）
_GitignoreRule = Tuple[Pattern[str], bool]


def _find_git_root(path: str) -> Optional[str]:
    """从 path 向上找最近的含 .git 目录（git 仓库根），找不到返回 None。"""
    current = os.path.normpath(path)
    while True:
        if os.path.isdir(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _translate_git_glob(pattern: str) -> str:
    """gitignore glob → 正则片段。'*' 不跨 '/', '**' 跨任意，'?' 单字符，'[...]' 字符类。"""
    i, n = 0, len(pattern)
    out: List[str] = []
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                if i + 2 < n and pattern[i + 2] == "/":
                    # '**/' 匹配任意层（含零层）
                    out.append("(?:.*/)?")
                    i += 3
                else:
                    out.append(".*")
                    i += 2
            else:
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            j = pattern.find("]", i + 1)
            if j == -1:
                out.append(re.escape("["))
                i += 1
            else:
                cls = pattern[i + 1:j]
                if cls.startswith("!"):
                    cls = "^" + cls[1:]
                out.append("[" + cls + "]")
                i = j + 1
        else:
            out.append(re.escape(c))
            i += 1
    return "".join(out)


def _parse_gitignore_lines(content: str, prefix: str) -> List[_GitignoreRule]:
    """解析一份 .gitignore 内容为规则列表。

    prefix：该 .gitignore 所在目录相对搜索根的路径（空串 = 搜索根自身）。
    支持：注释、空行、通配（* / ** / ? / [...]）、目录模式（尾部 '/'）。
    '!' 否定规则不支持，跳过。
    """
    rules: List[_GitignoreRule] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        dir_only = line.endswith("/")
        pattern = line.rstrip("/")
        if not pattern:
            continue
        if "/" in pattern:
            # 含斜杠 → 相对该 .gitignore 所在目录（剥前导 '/'，prefix 为空则为搜索根）
            pat = pattern.lstrip("/")
            rel = (prefix + "/" + pat).strip("/") if prefix else pat
            regex = re.compile("^" + _translate_git_glob(rel) + r"(?:/|$)")
        else:
            # 无斜杠 → 匹配任意层级同名段
            regex = re.compile(r"(?:^|/)" + _translate_git_glob(pattern) + r"(?:/|$)")
        rules.append((regex, dir_only))
    return rules


def _load_gitignore_rules(root_dir: str) -> List[_GitignoreRule]:
    """收集 git 根到搜索根路径上各层 .gitignore 的规则（仅在 git 仓库内生效）。

    规则按 gitignore 所在目录相对搜索根的路径偏移，应用于相对搜索根的路径。
    """
    root_dir = os.path.normpath(root_dir)
    git_root = _find_git_root(root_dir)
    if git_root is None:
        return []
    rules: List[_GitignoreRule] = []
    # 搜索根 → git 根逐层收集（含搜索根自身与 git 根）
    level = root_dir
    seen: set[str] = set()
    while True:
        if level in seen:
            break
        seen.add(level)
        ignore_file = os.path.join(level, ".gitignore")
        if os.path.isfile(ignore_file):
            try:
                with open(ignore_file, "r", encoding="utf-8", errors="ignore") as fh:
                    prefix = os.path.relpath(level, root_dir)
                    if prefix == ".":
                        prefix = ""
                    rules.extend(_parse_gitignore_lines(fh.read(), prefix))
            except OSError:
                pass
        if level == git_root:
            break
        parent = os.path.dirname(level)
        if parent == level:
            break
        level = parent
    return rules


def _is_gitignored(rel_path: str, is_dir: bool, rules: List[_GitignoreRule]) -> bool:
    if not rules:
        return False
    rel_path = rel_path.replace(os.sep, "/")
    for regex, dir_only in rules:
        if dir_only and not is_dir:
            continue
        if regex.search(rel_path):
            return True
    return False


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
        timeout: float = 0.0,
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
        self._timeout = timeout
        self._file_list = file_list
        self._cancelled = False
        self._timed_out = False
        self._logger = get_logger(__name__)

    @property
    def timed_out(self) -> bool:
        """是否因超时自动停止（仅 run() 结束后可读）。"""
        return self._timed_out

    def cancel(self) -> None:
        """请求取消搜索。"""
        self._cancelled = True

    def run(self) -> None:
        total = 0
        pattern = None
        start_time = time.monotonic()
        finished_emitted = False

        try:
            if self._use_regex:
                pattern = self._compile_regex(self._query)
                if pattern is None:
                    self.search_finished.emit(0)
                    finished_emitted = True
                    return

            if self._file_list is not None:
                for filepath in self._file_list:
                    if self._cancelled:
                        break
                    if self._expired(start_time):
                        break
                    if not os.path.isfile(filepath):
                        continue
                    total = self._search_file(filepath, pattern, total)
                    if total >= self._max_results:
                        self.search_finished.emit(total)
                        finished_emitted = True
                        return
            else:
                include_globs = self._compile_globs(self._include)
                exclude_globs = self._compile_globs(self._exclude)
                gitignore_rules = _load_gitignore_rules(self._root_dir)

                for dirpath, dirnames, filenames in os.walk(self._root_dir, followlinks=False):
                    if self._cancelled or self._expired(start_time):
                        break

                    dirnames[:] = self._filter_hidden_dirs(dirnames)
                    dirnames[:] = [
                        d for d in dirnames
                        if not _is_gitignored(
                            os.path.relpath(os.path.join(dirpath, d), self._root_dir),
                            is_dir=True,
                            rules=gitignore_rules,
                        )
                    ]

                    for fname in filenames:
                        if self._cancelled or self._expired(start_time):
                            break

                        filepath = os.path.join(dirpath, fname)
                        rel_path = os.path.relpath(filepath, self._root_dir)

                        if _is_gitignored(rel_path, is_dir=False, rules=gitignore_rules):
                            continue
                        if not self._pass_glob_filter(rel_path, include_globs, exclude_globs):
                            continue

                        total = self._search_file(filepath, pattern, total)
                        if total >= self._max_results:
                            self.search_finished.emit(total)
                            finished_emitted = True
                            return
        finally:
            if not finished_emitted:
                self.search_finished.emit(total)

    def _expired(self, start_time: float) -> bool:
        if self._timeout <= 0:
            return False
        if time.monotonic() - start_time > self._timeout:
            self._timed_out = True
            return True
        return False

    def _search_file(self, filepath: str, pattern, total: int) -> int:
        try:
            if _is_binary_file(filepath):
                return total
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
