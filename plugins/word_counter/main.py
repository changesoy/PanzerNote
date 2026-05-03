# -*- coding: utf-8 -*-
"""
Word Counter - UI扩展示例插件

展示 UI 扩展和编辑器交互能力。
在激活时提供字数统计功能接口。
"""

from src.plugins.plugin_base import PluginBase, PluginMeta, PluginPermission


class Plugin(PluginBase):

    def get_meta(self) -> PluginMeta:
        return PluginMeta(
            name="word_counter",
            version="1.0.0",
            description="UI扩展示例插件 - 文档字数统计",
            author="PanzerNote Team",
            min_app_version="1.6.4",
            permissions=[
                PluginPermission.READ_SETTINGS,
                PluginPermission.ACCESS_EDITOR,
                PluginPermission.ACCESS_UI,
            ],
            tags=["demo", "ui", "editor"],
        )

    def on_load(self, api) -> None:
        super().on_load(api)
        self._word_count = 0
        self._char_count = 0
        print("[WordCounter] 插件已加载")

    def on_activate(self) -> None:
        super().on_activate()
        print("[WordCounter] 插件已激活 - 字数统计功能可用")

    def on_deactivate(self) -> None:
        super().on_deactivate()
        print("[WordCounter] 插件已停用")

    def on_unload(self) -> None:
        print("[WordCounter] 插件已卸载")
        super().on_unload()

    def count_text(self, text: str) -> dict:
        if not text:
            return {"words": 0, "chars": 0, "chars_no_spaces": 0, "lines": 0}

        lines = text.split('\n')
        line_count = len(lines)
        char_count = len(text)
        chars_no_spaces = len(text.replace(' ', '').replace('\t', '').replace('\n', ''))

        words = text.split()
        word_count = len(words)

        self._word_count = word_count
        self._char_count = char_count

        return {
            "words": word_count,
            "chars": char_count,
            "chars_no_spaces": chars_no_spaces,
            "lines": line_count,
        }

    def get_last_counts(self) -> dict:
        return {
            "words": self._word_count,
            "chars": self._char_count,
        }
