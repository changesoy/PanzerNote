# -*- coding: utf-8 -*-
"""文档图片资源落盘服务（Markdown 图片工作流 E1）。

职责：把图片二进制写入「文档同级 PanzerNote_assets/ 目录」，返回可插入 Markdown 的相对路径。

关键设计：
- 落盘目录固定为文档同级的 PanzerNote_assets/：预览以后端资源根（= 当前文档目录）解析相对
  路径，落在文档目录树之外的相对路径无法被预览解析。
- 文件名强制 ASCII 安全：markdown-it 对含空格的图片语法直接解析失败，中文路径会被
  percent-encode 成不可读的 src —— 因此落盘名只保留 [A-Za-z0-9-]，
  其余（含中文/空格）替换为下划线；原名无有效字符时回落为 img_时间戳。
- 写入统一经 FileGuard.safe_write_bytes（原子写 + 大小上限），不做旁路 IO。
- 仅对超过阈值的大图做优化：PNG 无损重存、JPEG 近无损重存（quality="keep"），
  且仅当结果更小才采用；其余格式原样落盘；任何优化异常均回退原字节。
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from PIL import Image

from ..security.file_access_context import FileAccessContext
from ..security.file_guard import FileGuard
from ..utils.logger import get_logger
from .image_formats import WEB_RENDERABLE, is_insertable

logger = get_logger(__name__)

ASSETS_DIRNAME = "PanzerNote_assets"

# 落盘允许的扩展名 = 预览可渲染格式（单一真相源见 image_formats）。
# 非渲染格式（HEIF/TIFF 等）由调用方先用 image_decoder 转码再落盘，
# 因此这里不会、也不应出现它们的扩展名。
SUPPORTED_EXTENSIONS = WEB_RENDERABLE

# 参与大图优化的扩展名；其余（gif/webp/bmp/svg）原样落盘
_PNG_EXTENSIONS = frozenset({".png"})
_JPEG_EXTENSIONS = frozenset({".jpg", ".jpeg"})

DEFAULT_OPTIMIZE_THRESHOLD_BYTES = 2 * 1024 * 1024  # 2 MB
_MAX_DEDUP_ATTEMPTS = 10000

# 非 [A-Za-z0-9-] 的连续字符段统一折叠为单个下划线
_UNSAFE_STEM_CHARS = re.compile(r"[^A-Za-z0-9-]+")


class ImageAssetError(Exception):
    """图片资源落盘失败（不支持的类型、文档未保存、写入失败等）。"""


@dataclass(frozen=True)
class ImageAssetResult:
    """落盘结果：绝对路径 + 供 Markdown 插入的 POSIX 相对路径。"""

    absolute_path: str
    relative_path: str


class ImageAssetService:
    """把图片写入文档同级 PanzerNote_assets/ 目录并返回相对路径。"""

    def __init__(
        self,
        file_guard: FileGuard,
        *,
        optimize_threshold_bytes: int = DEFAULT_OPTIMIZE_THRESHOLD_BYTES,
        access_context: Optional[FileAccessContext] = FileAccessContext.DOCUMENT_ASSET,
    ) -> None:
        self._file_guard = file_guard
        self._optimize_threshold_bytes = optimize_threshold_bytes
        self._access_context = access_context

    # ---------- 公共 API ----------

    @staticmethod
    def is_supported_image(filename: str) -> bool:
        """判断该文件是否允许作为图片插入文档。

        含 HEIF/TIFF 等预览渲染不了的格式——它们由调用方先转码成
        PNG/JPEG 再落盘（见 `image_decoder.convert_to_web`），
        因此这里返回 True 不代表可以直接按原扩展名落盘。
        """
        return is_insertable(filename)

    def save_image(
        self,
        document_path: Optional[str],
        data: bytes,
        original_name: Optional[str] = None,
        *,
        extension: Optional[str] = None,
    ) -> ImageAssetResult:
        """把图片写入文档同级 PanzerNote_assets/，返回绝对路径与相对路径。

        Args:
            document_path: 当前文档路径；为空表示文档尚未保存（拒绝）。
            data: 图片二进制（由调用方产出，如剪贴板 QImage → PNG 字节）。
            original_name: 原始文件名（用于生成 ASCII 安全名）；可空。
            extension: 显式扩展名（如剪贴板无文件名时传 ".png"）；优先于 original_name。

        Raises:
            ImageAssetError: 扩展名不支持、文档未保存、数据为空或写入失败。
        """
        if not document_path:
            raise ImageAssetError("文档尚未保存，无法确定资源目录")
        if not data:
            raise ImageAssetError("图片数据为空")

        ext = self._resolve_extension(original_name, extension)
        document_dir = os.path.dirname(os.path.abspath(document_path))
        assets_dir = os.path.join(document_dir, ASSETS_DIRNAME)

        filename = self._allocate_filename(assets_dir, _sanitize_stem(original_name), ext)
        target = os.path.join(assets_dir, filename)

        # 纵深防御：目标必须落在资源目录内（文件名已 ASCII 化，此处为兜底）
        if os.path.dirname(os.path.abspath(target)) != os.path.abspath(assets_dir):
            raise ImageAssetError("目标路径越界")

        payload = self._maybe_optimize(data, ext)
        try:
            self._file_guard.safe_write_bytes(
                target, payload, context=self._access_context
            )
        except Exception as exc:
            raise ImageAssetError(f"图片写入失败: {exc}") from exc

        logger.debug("图片已落盘: %s (%d 字节)", target, len(payload))
        return ImageAssetResult(
            absolute_path=target,
            relative_path=f"{ASSETS_DIRNAME}/{filename}",
        )

    # ---------- 内部实现 ----------

    def _resolve_extension(
        self, original_name: Optional[str], extension: Optional[str]
    ) -> str:
        if extension:
            ext = extension.lower()
            if not ext.startswith("."):
                ext = "." + ext
        else:
            ext = _split_extension(original_name or "")
        if ext not in SUPPORTED_EXTENSIONS:
            raise ImageAssetError(f"不支持的图片格式: {original_name or extension!r}")
        return ext

    def _allocate_filename(self, assets_dir: str, stem: str, ext: str) -> str:
        base = stem or f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if not os.path.exists(os.path.join(assets_dir, f"{base}{ext}")):
            return f"{base}{ext}"
        for n in range(1, _MAX_DEDUP_ATTEMPTS + 1):
            candidate = f"{base}_{n}{ext}"
            if not os.path.exists(os.path.join(assets_dir, candidate)):
                return candidate
        raise ImageAssetError("同名图片过多，无法生成唯一文件名")

    def _maybe_optimize(self, data: bytes, ext: str) -> bytes:
        if len(data) <= self._optimize_threshold_bytes:
            return data
        if ext not in _PNG_EXTENSIONS and ext not in _JPEG_EXTENSIONS:
            return data
        try:
            optimized = _reencode(data, ext)
        except Exception as exc:
            logger.warning("图片优化失败，回退原字节: %s", exc)
            return data
        # 仅当优化结果确实更小才采用（PNG optimize 在噪声图上可能反而变大）
        if optimized is None or len(optimized) >= len(data):
            return data
        return optimized


def _split_extension(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


def _sanitize_stem(original_name: Optional[str]) -> str:
    """把原始文件名主干转为 ASCII 安全 slug；无有效字符时返回空串。"""
    if not original_name:
        return ""
    stem = os.path.splitext(os.path.basename(original_name))[0]
    return _UNSAFE_STEM_CHARS.sub("_", stem).strip("_")


def _reencode(data: bytes, ext: str) -> Optional[bytes]:
    """PNG 无损 / JPEG 近无损重存；返回 None 表示不适用或格式不匹配。"""
    with Image.open(io.BytesIO(data)) as img:
        if ext in _PNG_EXTENSIONS:
            buffer = io.BytesIO()
            img.save(buffer, format="PNG", optimize=True)
            return buffer.getvalue()
        if ext in _JPEG_EXTENSIONS:
            if img.format != "JPEG":
                return None
            buffer = io.BytesIO()
            # quality="keep" 复用原始量化表，属近无损（非码流级无损）；默认丢弃 EXIF/ICC
            img.save(
                buffer,
                format="JPEG",
                quality="keep",
                subsampling="keep",
                optimize=True,
            )
            return buffer.getvalue()
        return None
