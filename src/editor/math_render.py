# -*- coding: utf-8 -*-
"""数学公式渲染（KaTeX）资源与注入片段。

KaTeX 作为随包 vendor 资产放在 data/assets/vendor/katex/（版本 0.18.7），
应用运行期零网络：

- 字体以 data URI 内联进 CSS —— 预览模板与导出的 HTML 都是自包含的，
  导出文件拷到别的机器、断网打开也能正常显示公式；
- base64 烘焙在内存里做一次并缓存（lru_cache），仓库里不落生成物，
  升级 KaTeX 只需替换 vendor 目录里的文件。

公式在 **markdown 解析阶段**（mdit_py_plugins 的 dollarmath）就被识别成
``<span class="math inline">`` / ``<div class="math block">``，KaTeX 只负责把
其中的 TeX 渲染出来。为什么不走「渲染后由 auto-render 扫 $…$」的路子：

- markdown 的转义规则会吃掉公式里的标点命令 —— ``$a\\,b$`` 变成 ``a,b``、
  ``$\\begin{matrix}a \\\\ b\\end{matrix}$`` 的换行变成单个反斜杠；
- markdown 的强调规则会撕开公式 —— ``$a*b$`` 被渲成 ``a<em>b</em>``；
- auto-render 没有 pandoc 的定界符规则，「价格 $5 与 $3 元」会被当成公式
  并以报错色渲染出来。

在词法层识别同时解决了这三件事，代码量反而更小（JS 只做「把 .math 里的
TeX 交给 katex.render」）。定界符规则取 pandoc/GitHub 口径：开 ``$`` 后不接
空白，闭 ``$`` 前不接空白且其后不接数字。

注入方式：调用方在自己的文档模板里留 `{math_style}` / `{math_script}` 格式位，
由 style_fragment() / script_fragment() 填充（预览模板始终内联一次，导出文档按
has_math 按需内联），避免无公式的文档白背约 645 KB。

为什么是 KaTeX 而不是 MathJax（2026-09 决策，详见 111.md C4）：
体积 645KB 对 2.01MB；公式是真实 HTML 文本（可选中 / 可复制 / 可搜索），
MathJax 单文件方案只能输出 SVG 路径；同步渲染，PDF 导出无需新增
「页面 JS 渲染完成」握手。
"""

from __future__ import annotations

import base64
import functools
import os
import re
import sys
from typing import TYPE_CHECKING

from ..utils.logger import get_logger

if TYPE_CHECKING:
    from markdown_it import MarkdownIt

_log = get_logger(__name__)

# vendor 资产相对应用根目录的位置（随包分发，见 PanzerNote.spec 的 datas）
VENDOR_REL_PARTS = ("data", "assets", "vendor", "katex")

# dollarmath 产物：公式容器带 class="math inline" / class="math block"
_MATH_CONTAINER_RE = re.compile(r'class="math(?:\s+(?:inline|block))?"')

_FONT_WOFF2_RE = re.compile(r"url\(fonts/(?P<name>[^)]+\.woff2)\)")
_FONT_FALLBACK_RE = re.compile(
    r',url\(fonts/[^)]+\.(?:woff|ttf)\) format\("(?:woff|truetype)"\)'
)

_INITIAL_ROOT_TOKEN = "__PN_INITIAL_ROOT__"

# 渲染入口：内容区更新后由 Python 侧再次调用（预览路径）
_RENDER_JS = r"""
window.pnRenderMath = function (root) {
  root = root || document.body;
  if (!root || !window.katex) { return; }
  var nodes = root.querySelectorAll('.math');
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    // 幂等：同一元素重复渲染会对着 KaTeX 产物再解析一次
    if (el.getAttribute('data-pn-math')) { continue; }
    el.setAttribute('data-pn-math', '1');
    // dollarmath 的块级公式（含行内书写的 $$…$$）用 <div>，行内公式用 <span>；
    // 以标签名判断显示模式，比 class 更能反映它实际的换行语义
    window.katex.render(el.textContent || '', el, {
      displayMode: el.tagName === 'DIV',
      throwOnError: false
    });
  }
};
window.pnRenderMath(__PN_INITIAL_ROOT__);
""".replace(_INITIAL_ROOT_TOKEN, "{root}")


@functools.lru_cache(maxsize=1)
def _app_dir() -> str:
    """应用根目录（与 main.py 的 APP_DIR 同一约定，见 main.py:15-18）。

    不引 Config / PathResolver：本模块被纯渲染函数调用，不该反向依赖配置层。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )


def _vendor_dir() -> str:
    return os.path.join(_app_dir(), *VENDOR_REL_PARTS)


def _read_text(rel_path: str) -> str:
    path = os.path.join(_vendor_dir(), rel_path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        _log.warning("公式资源读取失败，公式将不渲染: %s (%s)", path, exc)
        return ""


def _read_bytes(rel_path: str) -> bytes | None:
    path = os.path.join(_vendor_dir(), rel_path)
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        _log.warning("公式字体读取失败，该字体将回退: %s (%s)", path, exc)
        return None


def register(md: MarkdownIt) -> bool:
    """给 markdown-it 实例装上 ``$…$`` / ``$$…$$`` 公式规则。

    预览与导出两个解析器都必须调用，否则两侧公式语法不一致。
    mdit_py_plugins 缺失时返回 False（公式退化为原样文本，不影响其它渲染）。
    """
    try:
        from mdit_py_plugins.dollarmath import dollarmath_plugin
    except ImportError:
        _log.debug("mdit_py_plugins 未安装，数学公式语法不可用")
        return False

    dollarmath_plugin(
        md,
        # pandoc/GitHub 口径：$ 与空白、数字相邻时不算公式（避免把价格当公式）
        allow_space=False,
        allow_digits=False,
        # 公式编号不是本项目的能力，关掉以免尾随的 (eq1) 被变成锚点
        allow_labels=False,
        # 允许 ``$$…$$`` 写在一行中间（GitHub/Obsidian 同样如此）
        double_inline=True,
    )
    return True


@functools.lru_cache(maxsize=1)
def katex_style() -> str:
    """KaTeX 样式文本（字体已内联为 data URI）；资产缺失返回空串。"""
    css = _read_text("katex.min.css")
    if not css:
        return ""

    def _embed(match: re.Match[str]) -> str:
        name = match.group("name")
        data = _read_bytes(os.path.join("fonts", name))
        if data is None:
            return match.group(0)
        b64 = base64.b64encode(data).decode("ascii")
        return f"url(data:font/woff2;base64,{b64})"

    css = _FONT_WOFF2_RE.sub(_embed, css)
    # 只带 woff2：woff/ttf 回退在离线文档里必然 404，去掉更干净
    return _FONT_FALLBACK_RE.sub("", css)


@functools.lru_cache(maxsize=1)
def katex_script() -> str:
    """KaTeX 主脚本文本；资产缺失返回空串。"""
    return _read_text("katex.min.js")


def style_fragment() -> str:
    css = katex_style()
    return f"<style>{css}</style>" if css else ""


def script_fragment(initial_root_js: str = "document.body") -> str:
    """脚本片段：定义 window.pnRenderMath 并对 initial_root_js 首次渲染。"""
    script = katex_script()
    if not script:
        return ""
    render = _RENDER_JS.replace("{root}", initial_root_js)
    return f"<script>{script}{render}</script>"


def content_update_js() -> str:
    """预览内容区更新后的重渲染调用（模板未内联库时是空操作）。"""
    return (
        "if (window.pnRenderMath) {"
        " window.pnRenderMath(document.getElementById('content')); }"
    )


def has_math(html_text: str) -> bool:
    """判断渲染产物里是否有公式（dollarmath 的容器 class 是唯一判据）。"""
    return bool(_MATH_CONTAINER_RE.search(html_text))
