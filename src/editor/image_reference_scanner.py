# -*- coding: utf-8 -*-
"""Markdown 本地图片引用的提取与缺失检测（Markdown 图片工作流 E6b）。

定位：要检测的是「Markdown 指向的本地资源是否还存在」——这是**文件系统问题，
不是浏览器问题**，故在 Python 侧只读扫描，而不是靠页面 `img.onerror`：后者会把
「文件不存在」与「文件存在但解码失败」混为一谈，还要引入 JS → Python 异步通道。

范围与口径（与实施规则一致）：
- 解析文档里**所有**本地相对图片引用，不限定目录 —— `PanzerNote_assets/`、
  legacy `assets/` 与手工写的跨目录 `../xxx/a.png` 一并计入；
- 覆盖行内 `![alt](dest)`、完整引用式 `![alt][label]`、collapsed `![alt][]`
  与快捷引用式 `![label]`（label 需有对应链接引用定义）；
- 围栏代码块 / 行内代码里的示例（如说明文档中的 `![](PanzerNote_assets/x.png)`）
  是示例文本而非真实引用，先剔除再扫描；
- 引用先做 URL decode（渲染器会把非 ASCII / 空格 percent-encode），再按
  **规范化后的实际路径**比较；带 scheme（http / https / file / data…）或绝对
  路径的引用不算本地相对资源；
- 只读检测，绝不移动 / 删除任何文件；是否提示、怎么提示由调用方决定。
"""

from __future__ import annotations

import os
import re
import urllib.parse
from typing import Dict, List, Optional, Tuple

# 行内图片 ![alt](dest "title")：alt 允许反斜杠转义（插入图片会对 ] 等做转义），
# dest 支持 <...> 包裹（含空格时使用）与裸形式。
_INLINE_IMAGE_RE = re.compile(
    r"!\[(?:\\[^\n]|[^\]\\])*\]"
    r"\(\s*"
    r"(?:<(?P<angle>[^>\n]*)>|(?P<plain>[^)\s]+))"
    r"(?:\s+(?:\"[^\"\n]*\"|'[^'\n]*'))?"
    r"\s*\)"
)

# 完整引用式图片 ![alt][label]（label 为空 = collapsed，取 alt 作 label）
_FULL_REF_IMAGE_RE = re.compile(
    r"!\[(?P<alt>(?:\\[^\n]|[^\]\\])*)\]\[(?P<label>[^\]\n]*)\]"
)

# 快捷引用式 ![label]：其后不能紧跟 ( 或 [，否则属行内 / 完整引用式
_SHORTCUT_IMAGE_RE = re.compile(
    r"!\[(?P<label>(?:\\[^\n]|[^\]\\])*)\](?![\[(])"
)

# 链接引用定义：[label]: dest "title"
_REF_DEF_RE = re.compile(
    r"^[ \t]{0,3}\[(?P<label>[^\]\n]+)\]:[ \t]*"
    r"(?:<(?P<angle>[^>\n]*)>|(?P<plain>\S+))"
    r"(?:[ \t]+(?:\"[^\"\n]*\"|'[^'\n]*'|\([^)\n]*\)))?[ \t]*$",
    re.MULTILINE,
)

# 带 scheme 的绝对引用（http: / https: / file: / data: / 盘符 C: …）
_URL_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)

# 行内代码 `code` / ``code``
_INLINE_CODE_RE = re.compile(r"(?P<ticks>`+)(?P<body>[^\n]*?)(?P=ticks)")

_ESCAPE_RE = re.compile(r"\\(.)")


def _normalize_label(label: str) -> str:
    """引用标签归一化：折叠空白 + 忽略大小写（CommonMark 语义）。"""
    return " ".join(label.split()).casefold()


def _unescape(text: str) -> str:
    return _ESCAPE_RE.sub(r"\1", text)


def _strip_code(markdown_text: str) -> str:
    """剔除围栏代码块与行内代码，避免把示例文本当真实引用。"""
    lines_out: List[str] = []
    fence: Optional[str] = None
    for line in markdown_text.splitlines():
        stripped = line.lstrip()
        if fence is None:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                fence = stripped[:3]
                lines_out.append("")
                continue
            lines_out.append(_INLINE_CODE_RE.sub(" ", line))
        else:
            if stripped.startswith(fence):
                fence = None
            lines_out.append("")
    return "\n".join(lines_out)


def _collect_reference_definitions(markdown_text: str) -> Dict[str, str]:
    """收集链接引用定义：[label]: dest "title" → {归一化 label: dest}。"""
    definitions: Dict[str, str] = {}
    for match in _REF_DEF_RE.finditer(markdown_text):
        dest = match.group("angle")
        if dest is None:
            dest = match.group("plain")
        label = _normalize_label(match.group("label"))
        if label and dest and label not in definitions:
            definitions[label] = dest
    return definitions


def extract_local_image_refs(markdown_text: str) -> List[str]:
    """提取文档里所有图片引用的原始目标串（不做本地 / 远程过滤，保序）。"""
    text = _strip_code(markdown_text)
    definitions = _collect_reference_definitions(text)

    found: List[Tuple[int, str]] = []

    for match in _INLINE_IMAGE_RE.finditer(text):
        dest = match.group("angle")
        if dest is None:
            dest = match.group("plain")
        if dest:
            found.append((match.start(), dest))

    for match in _FULL_REF_IMAGE_RE.finditer(text):
        label = match.group("label") or _unescape(match.group("alt"))
        dest = definitions.get(_normalize_label(label))
        if dest:
            found.append((match.start(), dest))

    for match in _SHORTCUT_IMAGE_RE.finditer(text):
        dest = definitions.get(_normalize_label(_unescape(match.group("label"))))
        if dest:
            found.append((match.start(), dest))

    found.sort(key=lambda item: item[0])
    return [dest for _, dest in found]


def resolve_local_ref(base_dir: str, url: str) -> Optional[str]:
    """本地相对引用 → 规范化后的绝对路径；非本地相对引用返回 None。

    返回 None 的情形：空引用、带 scheme（含盘符写法 `C:…`）、协议相对
    （`//host/…`）、根路径（前导 `/` 或 `\\`）。
    """
    if not base_dir or not url:
        return None
    if url.startswith("//") or _URL_SCHEME_RE.match(url):
        return None
    # 去掉片段与查询串后再 percent-decode（渲染器会对非 ASCII / 空格编码）
    path_part = url.split("#", 1)[0].split("?", 1)[0]
    decoded = urllib.parse.unquote(path_part)
    if not decoded:
        return None
    # 前导斜杠是根路径，不是"本地相对引用"。不依赖 os.path.isabs：
    # Python 3.13+ 的 ntpath 对「单个前导斜杠 / 反斜杠、无盘符」返回 False。
    if decoded.startswith(("/", "\\")) or os.path.isabs(decoded):
        return None
    decoded = decoded.replace("/", os.sep)
    return os.path.normpath(os.path.join(base_dir, decoded))


def find_missing_local_images(base_dir: str, markdown_text: str) -> List[str]:
    """返回文档引用但实际不存在的本地图片（规范化绝对路径，去重、保序）。"""
    missing: List[str] = []
    seen: set[str] = set()
    for url in extract_local_image_refs(markdown_text):
        resolved = resolve_local_ref(base_dir, url)
        if resolved is None or resolved in seen:
            continue
        seen.add(resolved)
        if not os.path.isfile(resolved):
            missing.append(resolved)
    return missing
