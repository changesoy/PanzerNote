# -*- coding: utf-8 -*-
"""图片解码（查看器 / 插入转码）统一入口。

分派策略（按扩展名）：

1. **Qt 原生格式** —— 先试 `QImageReader`（`setAutoTransform` 处理 EXIF 方向）；
2. **HEIF/HEIC**（`pillow-heif`）与 **AVIF**（Pillow 内置），以及 Qt 认不出/解不开的
   格式 —— 交给 Pillow 兜底（`ImageOps.exif_transpose` 处理 EXIF 方向）。

铁律 **只看不改**：解码全程只读，绝不写回、绝不重编码源文件。EXIF 方向仅作用于
内存中的显示，文件字节不受影响。字节读取一律经 `FileGuard`，不旁路安全校验。

可选依赖缺失时（如未装 pillow-heif）对应格式返回失败原因，不影响其余格式。
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageOps
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
from PyQt6.QtGui import QImage, QImageReader

from ..security.file_access_context import FileAccessContext
from ..security.file_guard import FileGuard
from ..utils.logger import get_logger
from . import image_formats as fmt

logger = get_logger(__name__)

# 转码目标：无 alpha 的照片走 JPEG（体积可控），带 alpha 的走 PNG（保透明）
_JPEG_QUALITY = 92

_DECODE_FAILED = "无法解码图片（格式不受支持或文件已损坏）"


@dataclass(frozen=True)
class DecodeResult:
    """解码结果：成功时 `image` 非空；失败时 `reason` 为面向用户的短句。"""

    image: Optional[QImage] = None
    reason: str = ""
    via: str = ""

    @property
    def ok(self) -> bool:
        return self.image is not None


@dataclass(frozen=True)
class EncodedImage:
    """转码结果：Chromium 可渲染的字节 + 目标扩展名。"""

    data: bytes
    extension: str
    width: int
    height: int


# ═══════════════ 解码 ═══════════════


def decode_image_file(
    filepath: str,
    file_guard: FileGuard,
    *,
    exif_orientation: bool = True,
) -> DecodeResult:
    """解码任意受支持图片为 QImage（只读；方向修正仅在内存中生效）。"""
    ext = fmt.extension_of(filepath)
    if not os.path.isfile(filepath):
        return DecodeResult(reason="文件不存在")
    if not fmt.is_viewable(filepath):
        return DecodeResult(reason=f"不支持的图片格式：{ext or '无扩展名'}")

    try:
        file_guard.validate_read_access(filepath)
        data = file_guard.safe_read_bytes(
            filepath, context=FileAccessContext.USER_DOCUMENT_READ
        )
    except Exception as exc:  # noqa: BLE001 - 读取失败即报告，不抛给 UI
        logger.warning("图片读取失败 %s: %s", filepath, exc)
        return DecodeResult(reason=f"无法读取图片：{exc}")

    if ext in fmt.QT_NATIVE:
        image = _decode_qt(data, exif_orientation)
        if image is not None:
            return DecodeResult(image=image, via="qt")

    # HEIF / AVIF / Qt 解不了的格式交给 Pillow
    return _decode_pillow(data, exif_orientation)


def _decode_qt(data: bytes, exif_orientation: bool) -> Optional[QImage]:
    """Qt 原生解码（`QImageReader`）；失败返回 None。"""
    buffer = QBuffer()
    buffer.setData(QByteArray(data))
    if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
        return None
    try:
        reader = QImageReader(buffer)
        # 仅影响内存中的显示方向，不修改源文件
        reader.setAutoTransform(exif_orientation)
        image = reader.read()
    finally:
        buffer.close()
    if image.isNull():
        return None
    return image


def _ensure_heif_support() -> bool:
    """注册 HEIF 打开器（幂等）；未安装 pillow-heif 时返回 False。"""
    try:
        import pillow_heif
    except ImportError:
        return False
    try:
        pillow_heif.register_heif_opener()
    except Exception as exc:  # noqa: BLE001 - 注册失败按不支持处理
        logger.warning("HEIF 解码器注册失败: %s", exc)
        return False
    return True


def _decode_pillow(data: bytes, exif_orientation: bool) -> DecodeResult:
    """Pillow 解码（HEIF / AVIF / 其它 Qt 不认的格式）。"""
    _ensure_heif_support()
    try:
        with Image.open(io.BytesIO(data)) as img:
            source: Image.Image = img
            if exif_orientation:
                # 仅作用于内存中的图像对象，不回写文件
                source = ImageOps.exif_transpose(img) or img
            return DecodeResult(image=_pil_to_qimage(source), via="pillow")
    except Exception as exc:  # noqa: BLE001 - 解码失败统一报告
        logger.debug("Pillow 解码失败: %s", exc)
        return DecodeResult(reason=_DECODE_FAILED)


def _pil_to_qimage(img: Image.Image) -> QImage:
    """PIL → QImage（内存转换，无文件 IO）。"""
    if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info:
        converted = img.convert("RGBA")
        return QImage(
            converted.tobytes(),
            converted.width,
            converted.height,
            converted.width * 4,
            QImage.Format.Format_RGBA8888,
        ).copy()
    if img.mode in ("1", "L", "I", "I;16", "F"):
        converted = img.convert("L")
        return QImage(
            converted.tobytes(),
            converted.width,
            converted.height,
            converted.width,
            QImage.Format.Format_Grayscale8,
        ).copy()
    converted = img.convert("RGB")
    return QImage(
        converted.tobytes(),
        converted.width,
        converted.height,
        converted.width * 3,
        QImage.Format.Format_RGB888,
    ).copy()


# ═══════════════ 转码（插入非渲染格式时用） ═══════════════


def encode_for_web(image: QImage) -> EncodedImage:
    """把已解码图像转成 Chromium 可渲染的字节：带 alpha → PNG，否则 → JPEG。"""
    pil = _qimage_to_pil(image)
    buffer = io.BytesIO()
    if pil.mode == "RGBA":
        pil.save(buffer, format="PNG", optimize=True)
        extension = ".png"
    else:
        pil.save(buffer, format="JPEG", quality=_JPEG_QUALITY)
        extension = ".jpg"
    return EncodedImage(
        data=buffer.getvalue(),
        extension=extension,
        width=pil.width,
        height=pil.height,
    )


def convert_to_web(
    filepath: str,
    file_guard: FileGuard,
    *,
    exif_orientation: bool = True,
) -> tuple[Optional[EncodedImage], str]:
    """解码后转码为可渲染字节（源文件只读，绝不改写）。

    Returns:
        (转码结果, 失败原因)；成功时原因为空串。
    """
    decoded = decode_image_file(
        filepath, file_guard, exif_orientation=exif_orientation
    )
    if decoded.image is None:
        return None, decoded.reason or _DECODE_FAILED
    try:
        return encode_for_web(decoded.image), ""
    except Exception as exc:  # noqa: BLE001 - 编码失败如实报告
        logger.warning("图片转码失败 %s: %s", filepath, exc)
        return None, f"图片转码失败：{exc}"


def _qimage_to_pil(image: QImage) -> Image.Image:
    """QImage → PIL（内存转换）；按是否真带 alpha 通道决定 RGBA / RGB。

    注意：QImage 每行按 4 字节对齐，`bytesPerLine()` 可能大于 `width*通道数`。
    必须逐行取 `constScanLine` 剥掉行尾 padding——按 `width*height*通道数`
    整块截断只让**总长度**对上，每行仍按未补齐的步长解析，错位逐行累加，
    表现为图片斜切扭曲（宽度不是 4 的倍数时必现）。
    """
    if image.hasAlphaChannel():
        converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
        mode, channels = "RGBA", 4
    else:
        converted = image.convertToFormat(QImage.Format.Format_RGB888)
        mode, channels = "RGB", 3

    width, height = converted.width(), converted.height()
    row_bytes = width * channels
    buffer = converted.constBits()
    if buffer is None:  # pragma: no cover - Qt 保证非空
        raise ValueError("QImage 数据不可读")

    if converted.bytesPerLine() == row_bytes:
        data = bytes(buffer.asarray(converted.sizeInBytes()))[: width * height * channels]
    else:
        data = b"".join(
            bytes(converted.constScanLine(y).asarray(row_bytes)) for y in range(height)
        )
    return Image.frombytes(mode, (width, height), data)
