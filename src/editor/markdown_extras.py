# -*- coding: utf-8 -*-
"""
Markdown 扩展语法统一注册（脚注 / 前辅文 / 后辅文）

预览（markdown_preview）与导出（secure_markdown_renderer）共用一个注册入口，
避免两侧各自装插件导致语法口径漂移。

能力来源（尽可能复用成熟库，零新增依赖）：
  - 脚注：``mdit_py_plugins.footnote``（markdown-it-footnote 的官方移植），
    支持 ``[^1]`` 引用式与 ``^[inline]`` 行内式脚注，定义区自动移到文档末尾。
  - 前辅文（Front Matter）：``mdit_py_plugins.front_matter``
    （markdown-it-front-matter 的官方移植），隐藏文档开头的 ``---…---`` 元数据块。
  - 后辅文（End Matter）：无现成插件，这里自写 ``strip_end_matter``——
    Markdown 引擎按"行扫描"处理块级语法，天然没有"文档末尾区块"的概念，
    故放在渲染前做文本级剥离：识别文档末尾的 ``---…---`` YAML 块，
    且内容必须经 PyYAML 解析为 dict（键值元数据）才剥离，
    防止把正文末尾的 ``hr`` / 段落误判成元数据。
"""

import re

from ..utils.logger import get_logger

try:
    import yaml
    HAS_PYYAML = True
except ImportError:  # pragma: no cover - 项目依赖含 PyYAML，此处仅防御
    HAS_PYYAML = False

_log = get_logger(__name__)

# 独占一行的 ---（≥3 个连字符，允许尾随空白）：front/end matter 的边界标记
_DASH_LINE_RE = re.compile(r"^-{3,}\s*$")


def register_markdown_extras(md) -> bool:
    """给 markdown-it 实例装上脚注与前辅文规则。

    预览与导出两个解析器都必须调用，否则两侧语法不一致。
    mdit_py_plugins 缺失时返回 False（相关语法退化为原样文本，不影响其它渲染）。
    """
    try:
        from mdit_py_plugins.footnote import footnote_plugin
        from mdit_py_plugins.front_matter import front_matter_plugin
    except ImportError:
        _log.debug("mdit_py_plugins 未安装，脚注 / 前辅文语法不可用")
        return False

    footnote_plugin(md)
    front_matter_plugin(md)
    return True


def strip_end_matter(text: str) -> str:
    """剥离 Markdown 末尾的 YAML 后辅文块（``---…---``），返回剩余正文。

    判定规则（全部满足才剥离，否则原样返回）：

    1. 去掉尾部空白后，最后一行是独占一行的 ``---``（≥3 个连字符）；
    2. 从该行向前找到最近的 ``---`` 起始行；
    3. 两者之间的内容非空，且经 ``yaml.safe_load`` 解析为 **dict**。

    第 3 条是关键防线：正文末尾常见的 ``hr``（单个 ``---``）与
    ``正文…---``（第二个 ``---`` 是表格分隔线 / 嵌套列表）都不会被误判；
    YAML 合法但不是键值对（如纯列表 / 标量）也保守地不剥离。

    只影响"显示"：源码里的后辅文仍保留在编辑器中，用户随时可见、可改。
    """
    if not text or not HAS_PYYAML:
        return text

    lines = text.split("\n")
    # 跳过尾部空行，定位末行
    end = len(lines)
    while end > 0 and not lines[end - 1].strip():
        end -= 1
    if end == 0 or not _DASH_LINE_RE.match(lines[end - 1]):
        return text

    # 向前找最近的起始 ---
    start = end - 2
    while start >= 0:
        if _DASH_LINE_RE.match(lines[start]):
            break
        start -= 1
    if start < 0:
        return text

    body = "\n".join(lines[start + 1 : end - 1])
    if not body.strip():
        return text

    try:
        value = yaml.safe_load(body)
    except Exception:  # noqa: BLE001 - 解析失败即视为普通正文，保守不剥离
        _log.debug("后辅文 YAML 解析失败，按普通正文保留: %r", body[:80])
        return text
    if not isinstance(value, dict):
        return text

    # 剥离：正文（start 之前）+ start 之后的尾部空行（end 之后原本只有空白）
    return "\n".join(lines[:start] + lines[end:])
