# -*- coding: utf-8 -*-
"""
统一异常处理装饰器

所有 except 必须满足三条之一：记录日志、向上抛出、转化为用户可见的友好提示。
@safe_call 装饰器统一了这三种行为，避免 except Exception: pass 的反模式。

用法:
    # 默认：捕获异常并记录日志，返回 None
    @safe_call()
    def load_config():
        ...

    # 捕获异常、记录日志、返回默认值
    @safe_call(default=[])
    def get_recent_files():
        ...

    # 捕获异常、记录日志、弹出用户提示
    @safe_call(show_error="保存文件失败")
    def save_file():
        ...

    # 捕获异常、记录日志、重新抛出
    @safe_call(reraise=True)
    def critical_operation():
        ...

    # 仅捕获特定异常
    @safe_call(catch=(ValueError, IOError))
    def parse_data():
        ...
"""

import functools
import traceback
from typing import Any, Callable, Optional, Tuple, Type, Union

from .logger import get_logger

_CatchType = Union[Type[BaseException], Tuple[Type[BaseException], ...]]


def safe_call(
    *,
    default: Any = None,
    show_error: Optional[str] = None,
    reraise: bool = False,
    catch: _CatchType = Exception,
    log_level: str = "error",
) -> Callable:
    """统一异常处理装饰器

    Args:
        default: 异常发生时的返回值，默认 None
        show_error: 若提供，异常时弹出 QMessageBox 提示用户；
                    字符串作为标题，异常信息附加在后面
        reraise: 是否在记录日志后重新抛出异常
        catch: 要捕获的异常类型，默认 Exception
        log_level: 日志级别，默认 "error"
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger = get_logger(func.__module__)
            log_method = getattr(logger, log_level, logger.error)

            try:
                return func(*args, **kwargs)
            except catch as exc:
                log_method(
                    "%s 失败: %s",
                    func.__qualname__,
                    exc,
                    exc_info=True,
                )

                if show_error is not None:
                    _show_error_dialog(show_error, exc)

                if reraise:
                    raise

                return default

        return wrapper

    return decorator


def _show_error_dialog(title: str, exc: BaseException) -> None:
    """延迟导入 ErrorHandler 以避免循环依赖，使用统一错误提示系统"""
    try:
        from .error_handler import ErrorHandler, ErrorCategory
        ErrorHandler.show_from_exception(
            exception=exc,
            category=ErrorCategory.GENERAL,
            title=title,
        )
    except Exception:
        pass
