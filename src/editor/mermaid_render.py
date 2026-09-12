# -*- coding: utf-8 -*-
"""Mermaid 图表渲染（vendor 资产 + 注入片段）。

Mermaid 作为随包 vendor 资产放在 data/assets/vendor/mermaid/（12.0.0，MIT），
运行期零网络。

为什么是**懒注入**而不是像 KaTeX 那样始终内联：mermaid.min.js 约 5.58 MB
（对照 KaTeX 自包含 645 KB）。预览模板只在首屏加载一次，若模板内联，则每篇
文稿都要背这份体积（navigate_to_string 的大字符串 + 解析开销），而绝大多数
文稿没有图表。故：

- 预览侧：首次出现 ```mermaid 时才经 run_javascript 把 vendor 注入一次
  （widget 级缓存；整页重载后 JS 上下文重置，缓存随之失效）；
- 导出侧：build_export_html_document 按 has_mermaid 判定后内联。

异步性（与 KaTeX 的关键差异）：Mermaid 渲染返回 Promise，导航完成只保证文档
装载、不保证 SVG 已生成。故导出文档带 <meta name="pn-async">，页面渲染结束后
经 WebView2 官方消息通道回传 READY_MESSAGE；PDF 导出适配器据此新增第二道门，
否则图表位置会印出未渲染的源码文本。
"""

from __future__ import annotations

import functools
import os
import re
import sys

from ..utils.logger import get_logger

_log = get_logger(__name__)

# vendor 资产相对应用根目录的位置（随包分发，见 PanzerNote.spec 的 datas）
VENDOR_REL_PARTS = ("data", "assets", "vendor", "mermaid")

# 围栏语言名（```mermaid）
LANG = "mermaid"

# 图表容器 class。
#
# 刻意**不用** mermaid 约定的 "mermaid"：库自带「文档就绪后自动渲染所有
# .mermaid 元素」的行为，而我们的渲染时机由 Python 控制（懒注入、主题切换
# 重渲染），自动渲染会先一步把 SVG 写进节点，随后我们的 run 再对同一节点
# 渲染一次 —— 双重渲染。用私有 class 后自动渲染找不到目标，行为完全由
# 我们掌控；显式 run(nodes) 并不要求节点带 "mermaid"。
CONTAINER_CLASS = "pn-mermaid"

_CONTAINER_RE = re.compile(r'<div class="' + CONTAINER_CLASS + r'[ "]')

# 导出文档声明「本页有异步渲染」；适配器据此决定是否为 PDF 打印加第二道门
ASYNC_META_TAG = '<meta name="pn-async" content="mermaid">'

# 导出文档声明「图表库不内联，由宿主注入」。
#
# 为什么 PDF 导出必须这样：WebView2 的 NavigateToString 对文档有 **2 MB 上限**
# （官方文档原文 "may not be larger than 2 MB"），而内联 Mermaid 后文档约 5.6 MB，
# 会以 E_INVALIDARG 直接失败（真机复现）。改为适配器经
# add_script_to_execute_on_document_created_async 注入：该接口实测可承载 5.6 MB，
# 且脚本在页面自身脚本之前执行，页面里的 pnMermaidBoot 照常工作。
#
# 注意只有 PDF 这条路需要它：HTML 导出写的是磁盘文件，由用户浏览器打开，
# 不经过 NavigateToString，故仍内联以保持单文件自包含。
EXTERNAL_VENDOR_META_TAG = '<meta name="pn-mermaid-vendor" content="external">'

# 页面异步渲染就绪信号（经 chrome.webview.postMessage 回传）
READY_MESSAGE = "__pnready__"

_BOOTSTRAP_JS = r"""
window.pnMermaidDark = __PN_DARK__;
window.pnMermaidSetDark = function (dark) { window.pnMermaidDark = !!dark; };

// 每次渲染前重新 initialize：主题可能已切换（切主题走整篇重渲染路径，旧 SVG
// 随 innerHTML 替换而消失，此处拿到的是全新节点）。
// securityLevel=strict：图表源码里的 HTML 一律转义，与「不渲染原始 HTML」一致。
// startOnLoad=false 同时关掉库自身的自动渲染（本文件顶部说明了为什么还要用
// 私有 class 再兜一层）。
window.pnMermaidApply = function () {
  window.mermaid.initialize({
    startOnLoad: false,
    theme: window.pnMermaidDark ? 'dark' : 'default',
    securityLevel: 'strict'
  });
};

// 渲染 #content（或指定根）下所有尚未渲染的图表。
// 幂等：同一元素重复调用会因 data-pn-graph 标记而跳过 —— 首次懒注入与紧随其后的
// 内容更新脚本都会调用本函数，两者的执行顺序不确定（前者是独立的 execute_script），
// 幂等标记保证无论谁先到都只渲染一次。
window.pnRenderMermaid = function (root) {
  root = root || document.getElementById('content') || document.body;
  if (!window.mermaid || !root) { return Promise.resolve(0); }
  var nodes = root.querySelectorAll('.__PN_CLASS__');
  var pending = [];
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    if (el.getAttribute('data-pn-graph')) { continue; }
    el.setAttribute('data-pn-graph', '1');
    var src = (el.textContent || '').replace(/^\s+|\s+$/g, '');
    if (!src) { continue; }
    el.textContent = src;
    pending.push(el);
  }
  if (!pending.length) { return Promise.resolve(0); }
  window.pnMermaidApply();
  return window.mermaid.run({ nodes: pending, suppressErrors: true }).then(function () {
    // 图表高度与源码文本不同，锚点缓存与滚动位置都要重算
    if (window.resyncAfterLayout) { window.resyncAfterLayout(); }
    return pending.length;
  });
};

// 仅导出文档（带 pn-async 声明）回传就绪信号：预览页不需要，HTML 导出文档
// 也没有 pn-async（它由用户浏览器打开，无宿主可回传）。
window.pnMermaidBoot = function () {
  var done = function () {
    if (!document.querySelector('meta[name="pn-async"]')) { return; }
    try {
      if (window.chrome && window.chrome.webview) {
        window.chrome.webview.postMessage('__PN_READY__');
      }
    } catch (e) {}
  };
  // pnRenderMermaid 内部有同步阶段（查询/标记节点、pnMermaidApply），
  // 同步抛错时 .then(done, done) 不会被触发 —— 就绪信号会永久缺失，
  // 导出侧只能等 8s 超时降级。此处兜住同步异常并照常回传就绪。
  try {
    window.pnRenderMermaid().then(done, done);
  } catch (e) { done(); }
};

window.pnMermaidApply();
""".replace("__PN_READY__", READY_MESSAGE).replace("__PN_CLASS__", CONTAINER_CLASS)


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


@functools.lru_cache(maxsize=1)
def script_text() -> str:
    """vendor 脚本正文；资产缺失返回空串（图表不渲染但不崩）。"""
    path = os.path.join(_vendor_dir(), "mermaid.min.js")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        _log.warning("图表资源读取失败，图表将不渲染: %s (%s)", path, exc)
        return ""


def is_mermaid_fence(info: str) -> bool:
    """判断 fence token 的 info 是否为 mermaid（预览构建代码块序号时用）。"""
    return (info or "").strip().split(" ")[0].lower() == LANG


def has_mermaid(html_text: str) -> bool:
    """判断渲染产物里是否有图表容器。"""
    return bool(_CONTAINER_RE.search(html_text))


def needs_async_render(html: str) -> bool:
    """导出文档是否声明了异步渲染（PDF 打印是否需要等就绪信号）。"""
    return ASYNC_META_TAG.lower() in html.lower()


def needs_vendor_injection(html: str) -> bool:
    """文档是否声明「图表库由宿主注入」（PDF 导出路径，见 EXTERNAL_VENDOR_META_TAG）。"""
    return EXTERNAL_VENDOR_META_TAG.lower() in html.lower()


def vendor_js() -> str:
    """vendor 脚本文本（供适配器经文档级脚本注入）。"""
    return script_text()


def script_fragment(is_dark: bool = False, include_vendor: bool = True) -> str:
    """引导脚本片段，vendor 可按需内联。

    - include_vendor=True：单文件自包含（HTML 导出、预览懒注入载荷），
      在 <body> 末尾执行首次也是唯一一次渲染；
    - include_vendor=False：只出引导脚本，配合 EXTERNAL_VENDOR_META_TAG，
      由 WebView2 经文档级脚本注入提供 vendor（PDF 导出路径，避开 2 MB 导航上限）。

    vendor 缺失时返回空串（图表不渲染但不崩）；include_vendor=False 时
    只要引导脚本可生成就有意义 —— 此时 vendor 由宿主负责。
    """
    script = script_text() if include_vendor else ""
    if include_vendor and not script:
        return ""
    boot = _BOOTSTRAP_JS.replace(
        "__PN_DARK__", "true" if is_dark else "false"
    )
    return f"<script>{script}{boot}window.pnMermaidBoot();</script>"


def lazy_load_js(is_dark: bool = False) -> str:
    """预览侧懒注入载荷（去掉 <script> 外壳，供 run_javascript 直接执行）。"""
    fragment = script_fragment(is_dark)
    if not fragment:
        return ""
    return fragment[len("<script>"):-len("</script>")]


def content_update_js(is_dark: bool = False) -> str:
    """预览内容更新 / 主题切换后的重渲染调用（未注入 vendor 时是空操作）。"""
    return (
        "if (window.pnMermaidSetDark) { window.pnMermaidSetDark("
        + ("true" if is_dark else "false")
        + "); }"
        "if (window.pnRenderMermaid) {"
        " window.pnRenderMermaid(document.getElementById('content')); }"
    )
