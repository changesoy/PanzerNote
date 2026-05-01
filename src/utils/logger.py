# -*- coding: utf-8 -*-
"""
结构化日志系统

统一日志级别、格式、输出位置（控制台 + 滚动文件）。
所有模块通过 get_logger(__name__) 获取 logger 实例。

用法:
    from src.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("文件已保存")
    logger.error("保存失败", exc_info=True)
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_initialized = False


def setup_logging(
    log_dir: Optional[str] = None,
    level: int = logging.DEBUG,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> None:
    """初始化全局日志配置

    Args:
        log_dir: 日志文件目录，为 None 则仅输出到控制台
        level: 根 logger 级别
        max_bytes: 单个日志文件最大字节数（默认 5MB）
        backup_count: 保留的备份文件数
    """
    global _initialized
    if _initialized:
        return

    root_logger = logging.getLogger("src")
    root_logger.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "panzernote.log"),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger

    自动将 name 映射到 src 命名空间下。
    若尚未调用 setup_logging，则自动以控制台模式初始化。

    Args:
        name: 通常传入 __name__

    Returns:
        logging.Logger 实例
    """
    if not _initialized:
        setup_logging()

    if not name.startswith("src"):
        name = f"src.{name}"

    return logging.getLogger(name)
