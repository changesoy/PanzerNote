# -*- coding: utf-8 -*-
"""Markdown 本地图片引用的提取、缺失检测与定点改写（图片工作流 E6b / E6c1b2）。

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
- 只读检测，绝不移动 / 删除任何文件；是否提示、怎么提示由调用方决定；
- 另提供引用**位置**与定点改写（`iter_image_ref_spans` / `rewrite_local_refs`）：
  目标同名冲突改名后按 span 替换目标串，文档其余部分逐字保留。
"""

from __future__ import annotations

import os
import re
import urllib.parse
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

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

# 扫描代价控制（4.5 第 5 条）：只读、限单文件大小、限文件数量、跳过隐藏目录
SCAN_MAX_BYTES = 1 * 1024 * 1024
SCAN_MAX_FILES = 5000
_MARKDOWN_EXTS = (".md", ".markdown")


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


def iter_markdown_files(root_dir: str, *, max_files: int = SCAN_MAX_FILES) -> List[str]:
    """递归列出 root_dir 下的 Markdown 文件（跳过隐藏目录，限数量）。"""
    files: List[str] = []
    if not root_dir or not os.path.isdir(root_dir):
        return files
    for current, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        for filename in filenames:
            if not filename.lower().endswith(_MARKDOWN_EXTS):
                continue
            files.append(os.path.join(current, filename))
            if len(files) >= max_files:
                return files
    return files


def resolve_refs_in_text(base_dir: str, markdown_text: str) -> List[str]:
    """由 Markdown 文本解析出的**本地相对资源** canonical 绝对路径（去重、保序）。"""
    resolved: List[str] = []
    seen: set[str] = set()
    for url in extract_local_image_refs(markdown_text):
        path = resolve_local_ref(base_dir, url)
        if path is None or path in seen:
            continue
        seen.add(path)
        resolved.append(path)
    return resolved


def resolve_document_refs(
    markdown_path: str, *, max_bytes: int = SCAN_MAX_BYTES
) -> List[str]:
    """返回某篇 Markdown 引用的**本地相对资源** canonical 绝对路径（去重、保序）。

    只读、限大小；文件读不了或超限一律返回空（扫描代价控制，4.5 第 5 条）。
    供共享判定使用：调用方按 canonical path 比较，不依赖 ledger。

    注意：文档在编辑器里有未保存改动时，磁盘内容不是真相——那种情况下调用方
    应改用 `resolve_refs_in_text(dirname, editor.toPlainText())`。
    """
    try:
        if os.path.getsize(markdown_path) > max_bytes:
            return []
        with open(markdown_path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return []

    return resolve_refs_in_text(os.path.dirname(os.path.abspath(markdown_path)), text)


# ═══════════ 引用位置与定点改写（E6c1b2：目标同名冲突改名后改写引用） ═══════════


def canonical_path_key(path: str) -> str:
    """资源 / 文档路径的 canonical 比较键（与 `resolve_local_ref` 同一口径）。

    跨模块共用一份实现：调用方按这个键比较「引用解析结果」与「真实文件路径」，
    避免大小写 / 分隔符 / 相对段差异造成误判。
    """
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


@dataclass(frozen=True)
class ImageRefSpan:
    """文档中一处图片引用的目标串位置。

    `start` / `end` 是**目标串本身**的字符区间（不含 `<...>` 标点），`raw` 为原文
    写法（可能 percent-encoded），`angle` 表示是否用 `<...>` 包裹。用于改名后定点
    改写：只替换该区间，文档其余部分逐字保留。
    """

    start: int
    end: int
    raw: str
    angle: bool


def _inside_regions(position: int, regions: Sequence[Tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in regions)


def _code_regions(text: str) -> List[Tuple[int, int]]:
    """围栏代码块与行内代码在**原文**中的字符区间（判定示例文本用）。

    与 `_strip_code` 同一套规则（行的 lstrip 以 ``` / ~~~ 开头视为围栏），区别是
    这里保留原文坐标，供定点改写使用。
    """
    regions: List[Tuple[int, int]] = []
    fence: Optional[str] = None
    fence_start = 0
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if fence is None:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                fence = stripped[:3]
                fence_start = offset
        elif stripped.startswith(fence):
            regions.append((fence_start, offset + len(line)))
            fence = None
        offset += len(line)
    if fence is not None:
        regions.append((fence_start, len(text)))

    for match in _INLINE_CODE_RE.finditer(text):
        start, end = match.span()
        if not _inside_regions(start, regions):
            regions.append((start, end))
    return regions


def _dest_span(match: "re.Match[str]") -> ImageRefSpan:
    group = "angle" if match.group("angle") is not None else "plain"
    return ImageRefSpan(
        start=match.start(group),
        end=match.end(group),
        raw=match.group(group) or "",
        angle=group == "angle",
    )


def iter_image_ref_spans(markdown_text: str) -> List[ImageRefSpan]:
    """图片引用目标串的位置列表（行内 + 被图片使用的引用定义；跳过代码里的示例）。

    只给出**图片**引用的位置：引用式语法改的是定义行，且仅当该 label 真被某张图片
    使用（否则改一个没人用的定义是多余动作）。
    """
    regions = _code_regions(markdown_text)
    spans: List[ImageRefSpan] = []
    used_labels: Set[str] = set()

    for match in _INLINE_IMAGE_RE.finditer(markdown_text):
        if _inside_regions(match.start(), regions):
            continue
        span = _dest_span(match)
        if span.raw:
            spans.append(span)

    for match in _FULL_REF_IMAGE_RE.finditer(markdown_text):
        if _inside_regions(match.start(), regions):
            continue
        label = match.group("label") or _unescape(match.group("alt"))
        used_labels.add(_normalize_label(label))

    for match in _SHORTCUT_IMAGE_RE.finditer(markdown_text):
        if _inside_regions(match.start(), regions):
            continue
        used_labels.add(_normalize_label(_unescape(match.group("label"))))

    for match in _REF_DEF_RE.finditer(markdown_text):
        if _inside_regions(match.start(), regions):
            continue
        if _normalize_label(match.group("label")) not in used_labels:
            continue
        span = _dest_span(match)
        if span.raw:
            spans.append(span)

    spans.sort(key=lambda item: item.start)
    return spans


def _format_local_ref(base_dir: str, target_abs: str, *, angle: bool) -> str:
    """绝对路径 → 相对 base_dir 的引用串（保持原有写法风格）。

    原本用 `<...>` 包裹的继续包裹（该形式允许空格与非 ASCII）；裸形式则
    percent-encode，保证在 CommonMark 里始终是合法的裸目标串。
    """
    relative = os.path.relpath(target_abs, base_dir).replace(os.sep, "/")
    if angle:
        return relative
    return urllib.parse.quote(relative)


def rewrite_local_refs(
    markdown_text: str, base_dir: str, mapping: Dict[str, str]
) -> Tuple[str, int]:
    """把指向 mapping 中旧路径的图片引用改写成新路径；返回（新文本, 改写处数）。

    mapping 的键 / 值都是**绝对路径**（键 = 原目标，值 = 改名后的目标）。只替换
    引用目标串区间，文档其余部分逐字保留；代码块 / 行内代码里的示例不动。
    """
    wanted = {canonical_path_key(old): new for old, new in mapping.items()}
    if not wanted:
        return markdown_text, 0

    pieces: List[str] = []
    cursor = 0
    count = 0
    for span in iter_image_ref_spans(markdown_text):
        resolved = resolve_local_ref(base_dir, span.raw)
        if resolved is None:
            continue
        target = wanted.get(canonical_path_key(resolved))
        if target is None:
            continue
        replacement = _format_local_ref(base_dir, target, angle=span.angle)
        if replacement == span.raw:
            continue
        pieces.append(markdown_text[cursor:span.start])
        pieces.append(replacement)
        cursor = span.end
        count += 1

    if not count:
        return markdown_text, 0
    pieces.append(markdown_text[cursor:])
    return "".join(pieces), count
