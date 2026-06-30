# -*- coding: utf-8 -*-
"""
行尾（EOL）探测与规范化纯函数

编辑器内部统一使用 Qt 的 \\n 表示换行，EOL 转换仅在落盘前发生。
"""

from typing import Tuple


EOL_MAP = {"LF": "\n", "CRLF": "\r\n", "CR": "\r"}
"""显示标签到实际换行符的映射"""


def detect_eol(text: str) -> Tuple[str, str]:
    """探测文本的行尾类型

    参数：
      text：原始文本（可能包含混合行尾）

    返回：
      (显示标签, 主导行尾) 二元组
      显示标签： "LF" / "CRLF" / "CR" / "Mixed"
      主导行尾：  "\\n" / "\\r\\n" / "\\r"

    规则：
      - 无换行符 → ("LF", "\\n")
      - 只有一种换行符 → ("LF"/"CRLF"/"CR", 对应换行符)
      - 多种换行符同时存在 → 按出现次数取主导，显示 ("Mixed", 主导行尾)
    """
    if not text:
        return ("LF", "\n")

    crlf_count = text.count("\r\n")
    # 统计纯 CR（排除 CRLF 中的 CR）
    cr_count = text.count("\r") - crlf_count
    # 统计纯 LF（排除 CRLF 中的 LF）
    lf_count = text.count("\n") - crlf_count

    return _classify_counts(lf_count, crlf_count, cr_count)


def detect_eol_from_bytes(data: bytes) -> Tuple[str, str]:
    """从原始字节探测行尾类型（不依赖文本解码）

    适用于 safe_read 使用 universal newline 模式会丢失行尾信息的场景。
    在本阶段读取少量字节即可完成探测。
    """
    if not data:
        return ("LF", "\n")

    crlf_count = data.count(b"\r\n")
    cr_count = data.count(b"\r") - crlf_count
    lf_count = data.count(b"\n") - crlf_count

    return _classify_counts(lf_count, crlf_count, cr_count)


def _classify_counts(lf_count: int, crlf_count: int, cr_count: int) -> Tuple[str, str]:
    """根据三种换行符的计数返回 (显示标签, 主导行尾)"""
    counts = {
        "LF": lf_count,
        "CRLF": crlf_count,
        "CR": cr_count,
    }

    present = {k: v for k, v in counts.items() if v > 0}

    if not present:
        return ("LF", "\n")

    if len(present) == 1:
        label = next(iter(present))
        return (label, EOL_MAP[label])

    # 多种换行符 → 取计数最多的
    dominant = max(present, key=present.get)  # type: ignore[arg-type]
    return ("Mixed", EOL_MAP[dominant])


def normalize_eol(text: str, target_eol: str) -> str:
    """将文本中的所有换行符统一为指定的行尾

    参数：
      text：待规范化的文本（使用 \\n 内部表示）
      target_eol：目标行尾，\"\\n\" / \"\\r\\n\" / \"\\r\"
    """
    # 注意：输入文本在编辑器内已经是统一的 \\n，
    # 但有些场景（如直接读取原始文件）可能包含混合行尾。
    # 安全起见，先统一所有 CRLF → LF
    normalized = text.replace("\r\n", "\n")
    # 再统一所有 CR → LF
    normalized = normalized.replace("\r", "\n")
    # 最后替换为目标行尾
    return normalized.replace("\n", target_eol)
