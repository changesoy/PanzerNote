# -*- coding: utf-8 -*-
"""
Markdown 扩展语法统一注册（定义列表 / 任务列表 / 脚注 / 前辅文 / 后辅文）

预览（markdown_preview）与导出（secure_markdown_renderer）共用一个注册入口，
避免两侧各自装插件导致语法口径漂移——两侧都只调 ``register_markdown_extras``，
不再各自注册插件（曾出现导出漏注册定义列表、口径与预览不一致的问题）。

能力来源（尽可能复用成熟库，零新增依赖）：
  - 定义列表 / 任务列表：``mdit_py_plugins.deflist`` / ``mdit_py_plugins.tasklists``
  - 脚注：``mdit_py_plugins.footnote``（markdown-it-footnote 的官方移植），
    支持 ``[^1]`` 引用式与 ``^[inline]`` 行内式脚注，定义区自动移到文档末尾。
  - 前辅文（Front Matter）：``mdit_py_plugins.front_matter``
    （markdown-it-front-matter 的官方移植），隐藏文档开头的 ``---…---`` 元数据块。
    库本身只校验「文档开头 + 标记 ≥ 3」，不看块内内容，故这里在其规则外再包一层
    内容守卫：块内必须能解析为 YAML 键值对（dict）才隐藏，否则按普通正文渲染。
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

# front_matter 规则参与的规则链（与库内注册保持一致）
_FRONT_MATTER_ALT = ["paragraph", "reference", "blockquote", "list"]


def register_markdown_extras(md) -> bool:
    """给 markdown-it 实例装上定义列表 / 任务列表 / 脚注 / 前辅文规则。

    预览与导出两个解析器都必须调用，否则两侧语法不一致。
    mdit_py_plugins 缺失时返回 False（相关语法退化为原样文本，不影响其它渲染）。
    """
    try:
        from mdit_py_plugins.deflist import deflist_plugin
        from mdit_py_plugins.footnote import footnote_plugin
        from mdit_py_plugins.front_matter import front_matter_plugin
        from mdit_py_plugins.tasklists import tasklists_plugin
    except ImportError:
        _log.debug(
            "mdit_py_plugins 未安装，扩展语法（定义列表/任务列表/脚注/前辅文）不可用"
        )
        return False

    deflist_plugin(md)
    tasklists_plugin(md)
    footnote_plugin(md)
    front_matter_plugin(md)
    _install_front_matter_guard(md)
    return True


def _install_front_matter_guard(md) -> None:
    """把库注册的 front_matter 规则换成带内容校验的版本（就地替换同名规则）。

    库规则只认「文档开头 + ``---`` 标记 ≥ 3」，不校验块内内容：正文开头写一条
    水平线加一段文字（``---`` / ``说明`` / ``---``）会被整块静默隐藏。
    这里要求块内容经 ``yaml.safe_load`` 解析为 dict（与 ``strip_end_matter``
    同一口径）才隐藏；否则撤销本次识别与状态改动，交给普通块级规则渲染。

    依赖库内私有 ``_front_matter_rule``：取不到时保持库原行为，不阻断渲染。
    """
    try:
        from mdit_py_plugins.front_matter.index import _front_matter_rule
    except ImportError:  # pragma: no cover - 私有符号缺失即退化，不影响其它语法
        _log.debug("front_matter 私有规则不可用，前辅文按库默认行为处理")
        return

    def guarded(state, start_line, end_line, silent):
        if silent:
            return _front_matter_rule(state, start_line, end_line, silent)

        # 库规则在识别成功时会改动 state（line / lineMax / parentType）并压入
        # hidden token；判定为「非元数据」时必须全部撤回，否则块解析器的行游标
        # 会被带偏（parser_block 以 state.line 作为下一轮起点）。
        tokens_before = len(state.tokens)
        line_before = state.line
        line_max_before = state.lineMax
        parent_type_before = state.parentType

        if not _front_matter_rule(state, start_line, end_line, silent):
            return False
        if _is_yaml_mapping(state.tokens[tokens_before].content):
            return True

        del state.tokens[tokens_before:]
        state.line = line_before
        state.lineMax = line_max_before
        state.parentType = parent_type_before
        return False

    md.block.ruler.at("front_matter", guarded, {"alt": _FRONT_MATTER_ALT})


def _is_yaml_mapping(text: str) -> bool:
    """文本是否是可解析为 dict 的 YAML 元数据（与 strip_end_matter 同口径）。"""
    if not HAS_PYYAML or not text.strip():
        return False
    try:
        value = yaml.safe_load(text)
    except Exception:  # noqa: BLE001 - 解析失败即视为普通正文
        return False
    return isinstance(value, dict)


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
