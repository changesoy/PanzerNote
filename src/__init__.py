# -*- coding: utf-8 -*-
"""
PanzerNote - 战车少女主题记事本

版本号唯一真相源（Single Source of Truth）。
所有模块和配置文件应通过引用此处的 __version__ 获取版本号，
而非硬编码版本字符串。

版本更新流程：
1. 仅修改本文件中的 __version__
2. 运行 python scripts/verify_version.py 验证一致性
3. 手动同步 README.md / docs/architecture.md / plugins/plugin_api.md 中的版本号
"""

__version__ = "1.8.1"
__author__ = "Changes"


def get_version() -> str:
    return __version__


def get_version_tuple() -> tuple:
    return tuple(int(x) for x in __version__.split("."))
