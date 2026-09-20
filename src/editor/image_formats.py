# -*- coding: utf-8 -*-
"""图片扩展名清单（Markdown 图片工作流的唯一真相源）。

三个集合的语义互不相同，不要混用：

- `WEB_RENDERABLE`：**预览 / 导出（Chromium）能渲染**的格式。也是插入文档时的
  落盘目标格式——只有这些扩展名能出现在 `PanzerNote_assets/` 里，否则预览断图。
- `VIEWABLE`：**查看器能显示**的格式。除 Chromium 那套外，还含 Qt 原生可解码的
  位图格式、HEIF/HEIC（pillow-heif）与 AVIF（Pillow 内置）。
- `INSERTABLE`：**允许插入文档**的输入格式 = `VIEWABLE`。非 `WEB_RENDERABLE` 的
  输入会在落盘前转码成 PNG / JPEG（见 `image_decoder`），源文件只读、绝不改写。

只做扩展名判断，不导入 Qt / Pillow —— 供低层模块安全复用。
"""

from __future__ import annotations

import os

# Chromium 可渲染：插入文档后预览/导出能正常显示
WEB_RENDERABLE = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
)

# Qt 运行时原生可解码（`QImageReader.supportedImageFormats()` 实测子集；
# 已剔除 pdf —— Qt 把它算作 image format，但它不是图片）
QT_NATIVE = frozenset(
    {
        ".bmp", ".cur", ".gif", ".icns", ".ico", ".jfif", ".jpeg", ".jpg",
        ".pbm", ".pgm", ".png", ".ppm", ".svg", ".svgz", ".tga", ".tif",
        ".tiff", ".wbmp", ".webp", ".xbm", ".xpm",
    }
)

# HEIF / HEIC（pillow-heif）
HEIF = frozenset({".heic", ".heif", ".hif"})

# AVIF（Pillow >= 11.3 内置解码）
AVIF = frozenset({".avif"})

# 相机 RAW（cr2/cr3/nef/arw/dng/raf/orf/rw2/pef/srw 等）**不在支持范围**：
# 解码需 LibRaw（rawpy），其传递依赖 numpy（含 numpy.libs）约 54 MB，
# 成本与收益不成比例，故整体砍掉；对应扩展名既不进查看器也不可插入。

# 查看器可显示的全部格式
VIEWABLE = QT_NATIVE | HEIF | AVIF

# 允许插入文档的输入格式（非 WEB_RENDERABLE 者落盘前转码）
INSERTABLE = VIEWABLE


def extension_of(filename: str) -> str:
    """文件名的扩展名（小写、带点）；无扩展名返回空串。"""
    return os.path.splitext(filename)[1].lower()


def is_web_renderable(filename: str) -> bool:
    """该扩展名能否被预览/导出（Chromium）直接渲染。"""
    return extension_of(filename) in WEB_RENDERABLE


def is_viewable(filename: str) -> bool:
    """该扩展名能否在查看器中显示。"""
    return extension_of(filename) in VIEWABLE


def is_insertable(filename: str) -> bool:
    """该扩展名是否允许插入文档（必要时由调用方转码）。"""
    return extension_of(filename) in INSERTABLE


def needs_conversion(filename: str) -> bool:
    """插入时是否需要转码（可插入、但 Chromium 渲染不了）。"""
    ext = extension_of(filename)
    return ext in INSERTABLE and ext not in WEB_RENDERABLE


def filter_patterns(extensions) -> list[str]:
    """扩展名集合 → 文件对话框 / 文件树用的通配符列表（排序稳定）。"""
    return [f"*{ext}" for ext in sorted(extensions)]


def dialog_filter(extensions, label: str) -> str:
    """文件对话框过滤器字符串，如 ``图片 (*.png *.jpg)``。"""
    return f"{label} (" + " ".join(filter_patterns(extensions)) + ")"


def file_stem(filename: str) -> str:
    """去扩展名的文件名主干（用于转码后命名）。"""
    return os.path.splitext(os.path.basename(filename))[0]
