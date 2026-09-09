# -*- coding: utf-8 -*-
"""PanzerNote 源码发布包构建脚本（Wave 8 B9 packaging，B3-1）。

产出：dist/PanzerNote-<version>-src.zip（源码 + 运行资源，可解压后直接
`python main.py` 运行，依赖见 requirements.txt）。

排除项：.venv/.git/tests/docs/scripts/__pycache__/*.pyc/desktop.ini 等开发与
本机工件。冻结可执行（PyInstaller .spec）不在本轮范围（见 roadmap）。

用法：
    .venv\\Scripts\\python.exe scripts/build_package.py
"""
from __future__ import annotations

import fnmatch
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "dist"

#: 需要打包的顶层条目（相对仓库根）
TOP_LEVEL = ["main.py", "src", "data", "themes", "plugins"]
#: 附带文档/元数据
META_FILES = [
    "requirements.txt",
    "pyproject.toml",
    "LICENSE",
    "README.md",
    "CHANGELOG.md",
    "项目说明.md",
]
#: 排除的路径片段 / glob（开发与运行无关工件）
EXCLUDE_PARTS = (
    "__pycache__",
    ".venv",
    ".git",
    ".idea",
    ".pytest_cache",
    ".mypy_cache",
)
EXCLUDE_GLOBS = ["*.pyc", "*.pyo", "desktop.ini", "Thumbs.db"]
EXCLUDE_ROOT = ("tests", "docs", "scripts", "dist", "benchmarks", "data/logs")


def _excluded(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    if any(p in EXCLUDE_PARTS for p in parts):
        return True
    if parts[0] in EXCLUDE_ROOT:
        return True
    return any(fnmatch.fnmatch(parts[-1], g) for g in EXCLUDE_GLOBS)


def _iter_files() -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for name in TOP_LEVEL:
        path = ROOT / name
        if path.is_file():
            rel = path.relative_to(ROOT).as_posix()
            if not _excluded(rel):
                files.append((rel, path))
        elif path.is_dir():
            for child in path.rglob("*"):
                if not child.is_file():
                    continue
                rel = child.relative_to(ROOT).as_posix()
                if not _excluded(rel):
                    files.append((rel, child))
    for name in META_FILES:
        path = ROOT / name
        if path.is_file():
            files.append((name, path))
    return files


def main() -> None:
    from src import __version__

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"PanzerNote-{__version__}-src.zip"
    files = _iter_files()
    count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, path in sorted(files):
            zf.write(path, f"PanzerNote-{__version__}/{rel}")
            count += 1
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"已生成 {out_path}")
    print(f"文件数 {count}，大小 {size_mb:.1f} MB")
    print("冒烟验证：解压后运行 `python main.py`（依赖见 requirements.txt）")


if __name__ == "__main__":
    sys.exit(main())
