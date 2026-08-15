#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本一致性验证工具

验证项目中所有版本号引用是否与唯一真相源 (src/__init__.py) 保持一致。

用法：
    python scripts/verify_version.py          # 验证所有版本号一致性
    python scripts/verify_version.py --fix    # 自动修复文档中的版本号

版本更新流程：
1. 仅修改 src/__init__.py 中的 __version__
2. 运行 python scripts/verify_version.py 验证
3. 如有文档不一致，使用 --fix 自动修复或手动修正
"""

import os
import re
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

from src import __version__ as CANONICAL_VERSION


def get_canonical_version():
    return CANONICAL_VERSION


def check_pyproject_toml():
    filepath = os.path.join(APP_DIR, "pyproject.toml")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    issues = []

    static_match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if static_match:
        issues.append({
            "file": filepath,
            "line": "static version field",
            "expected": "dynamic = [\"version\"] (no static version)",
            "actual": f'version = "{static_match.group(1)}"',
            "severity": "error",
            "fix": 'Replace static version with dynamic = ["version"] and add [tool.setuptools.dynamic] section',
        })

    dynamic_match = re.search(r'dynamic\s*=\s*\["version"\]', content)
    if not dynamic_match:
        issues.append({
            "file": filepath,
            "line": "dynamic version",
            "expected": 'dynamic = ["version"]',
            "actual": "not found",
            "severity": "error",
            "fix": 'Add dynamic = ["version"] to [project] section',
        })

    attr_match = re.search(r'version\s*=\s*\{attr\s*=\s*"src\.__version__"\}', content)
    if not attr_match:
        issues.append({
            "file": filepath,
            "line": "setuptools dynamic version",
            "expected": 'version = {attr = "src.__version__"}',
            "actual": "not found",
            "severity": "error",
            "fix": 'Add [tool.setuptools.dynamic] section with version = {attr = "src.__version__"}',
        })

    return issues


def check_python_hardcoded():
    issues = []
    skip_dirs = {".git", "__pycache__", "venv", ".venv", "node_modules", "scripts"}

    for root, dirs, files in os.walk(APP_DIR):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            filepath = os.path.join(root, fname)
            relpath = os.path.relpath(filepath, APP_DIR)

            if relpath == os.path.join("src", "__init__.py"):
                continue

            with open(filepath, "r", encoding="utf-8") as f:
                for lineno, line in enumerate(f, 1):
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    # 跳过 version 赋值（kwarg 或 dict 键），如插件 manifest / 测试 fixture 数据，
                    # 这些不是对应用版本号的引用；min_app_version 等特殊键仍会检查
                    if re.search(r'["\']?version["\']?\s*[=:]', stripped) and not any(
                        k in stripped for k in ("min_app_version", "app_version", "__version__")
                    ):
                        continue
                    matches = re.findall(r'["\'](\d+\.\d+\.\d+)["\']', stripped)
                    for ver in matches:
                        if ver == CANONICAL_VERSION:
                            issues.append({
                                "file": filepath,
                                "line": lineno,
                                "expected": f"reference to src.__version__ (={CANONICAL_VERSION})",
                                "actual": f'hardcoded "{ver}"',
                                "severity": "warning",
                                "fix": "Replace hardcoded version with import from src.__version__",
                            })

    return issues


def check_docs_version(fix=False):
    issues = []
    doc_files = [
        os.path.join(APP_DIR, "README.md"),
        os.path.join(APP_DIR, "\u9879\u76ee\u8bf4\u660e.md"),
    ]

    for filepath in doc_files:
        if not os.path.exists(filepath):
            continue
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        in_changelog = False
        header_versions = set()

        for i, line in enumerate(lines):
            stripped = line.strip()

            if re.match(r'^#{1,3}\s+v\d+\.\d+\.\d+', stripped) or re.match(r'^###\s+v\d+\.\d+\.\d+', stripped):
                in_changelog = True
                continue

            if in_changelog and stripped.startswith("#") and not re.match(r'^#{1,3}\s+v\d+', stripped):
                in_changelog = False

            if in_changelog:
                continue

            version_pattern = r'v(\d+\.\d+\.\d+)'
            matches = re.findall(version_pattern, stripped)
            for ver in matches:
                if ver != CANONICAL_VERSION:
                    header_versions.add(ver)

        if header_versions:
            issues.append({
                "file": filepath,
                "line": "non-changelog sections",
                "expected": f"only v{CANONICAL_VERSION}",
                "actual": f"found outdated versions: {', '.join(sorted(header_versions))}",
                "severity": "warning",
                "fix": f"Update non-changelog version references to v{CANONICAL_VERSION}",
            })

            if fix:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                for old_ver in header_versions:
                    content = content.replace(f"v{old_ver}", f"v{CANONICAL_VERSION}")
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)

    return issues


def check_init_version():
    filepath = os.path.join(APP_DIR, "src", "__init__.py")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
    if not match:
        return [{
            "file": filepath,
            "line": "unknown",
            "expected": "__version__ definition",
            "actual": "not found",
            "severity": "error",
            "fix": "Add __version__ = \"X.Y.Z\" to src/__init__.py",
        }]

    ver = match.group(1)
    parts = ver.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return [{
            "file": filepath,
            "line": "unknown",
            "expected": "semver format (X.Y.Z)",
            "actual": f'"{ver}"',
            "severity": "error",
            "fix": "Use semantic versioning format (e.g., 1.6.5)",
        }]

    return []


def check_runtime_consistency():
    from src.plugins.plugin_base import _app_version, PluginMeta

    issues = []
    if _app_version != CANONICAL_VERSION:
        issues.append({
            "file": "src/plugins/plugin_base.py",
            "line": "import",
            "expected": CANONICAL_VERSION,
            "actual": _app_version,
            "severity": "error",
            "fix": "Ensure plugin_base.py imports __version__ from src",
        })

    meta = PluginMeta(name="test", version="0.0.1", description="test")
    if meta.min_app_version != CANONICAL_VERSION:
        issues.append({
            "file": "src/plugins/plugin_base.py",
            "line": "PluginMeta.min_app_version default",
            "expected": CANONICAL_VERSION,
            "actual": meta.min_app_version,
            "severity": "error",
            "fix": "Ensure PluginMeta.min_app_version defaults to _app_version",
        })

    return issues


def main():
    fix_mode = "--fix" in sys.argv

    print(f"PanzerNote 版本一致性验证")
    print(f"唯一真相源版本: {CANONICAL_VERSION}")
    print("=" * 60)

    all_issues = []

    print("\n[1/5] 检查 src/__init__.py 版本格式...")
    all_issues.extend(check_init_version())

    print("[2/5] 检查 pyproject.toml 动态版本配置...")
    all_issues.extend(check_pyproject_toml())

    print("[3/5] 检查 Python 文件中的硬编码版本号...")
    all_issues.extend(check_python_hardcoded())

    print("[4/5] 检查文档中的版本号引用...")
    all_issues.extend(check_docs_version(fix=fix_mode))

    print("[5/5] 检查运行时版本一致性...")
    all_issues.extend(check_runtime_consistency())

    errors = [i for i in all_issues if i["severity"] == "error"]
    warnings = [i for i in all_issues if i["severity"] == "warning"]

    if all_issues:
        print(f"\n{'=' * 60}")
        print(f"发现 {len(errors)} 个错误, {len(warnings)} 个警告\n")

        for issue in all_issues:
            relpath = os.path.relpath(issue["file"], APP_DIR) if "file" in issue else "?"
            icon = "X" if issue["severity"] == "error" else "!"
            print(f"  {icon} [{issue['severity'].upper()}] {relpath}:{issue.get('line', '?')}")
            print(f"    期望: {issue['expected']}")
            print(f"    实际: {issue['actual']}")
            print(f"    修复: {issue['fix']}")
            print()
    else:
        print(f"\n[OK] 所有版本号引用一致，均为 {CANONICAL_VERSION}")

    if fix_mode and warnings:
        print("已自动修复文档中的版本号引用")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
