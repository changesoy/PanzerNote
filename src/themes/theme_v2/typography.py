# -*- coding: utf-8 -*-
"""TypographyLoader（Wave 8 B1）。

字体栈：Inter（拉丁）+ 思源黑体（中文 fallback）+ JetBrains Mono（代码）。
B1 仅声明契约与 family 映射；字体文件打包与 QFontDatabase 注册在 B2 落地。
零运行时网络依赖。
"""
from __future__ import annotations

from typing import Mapping

#: logical family → 字体名（B1 声明；实际打包见 B2）。
FONT_STACK: Mapping[str, str] = {
    "font_ui": "Inter",
    "font_mono": "JetBrains Mono",
    "font_cjk": "Noto Sans SC",
}


class TypographyLoader:
    """字体加载接口：注册字体并返回 family 名 → 注册后 family id 映射。"""

    @staticmethod
    def register_fonts() -> Mapping[str, str]:
        """B1 阶段返回声明的字体栈（未实际加载）。

        B2 起在此接入 QFontDatabase.addApplicationFont 与真实字体文件，
        返回的映射保持不变，调用方只依赖这份契约。
        """
        return dict(FONT_STACK)
