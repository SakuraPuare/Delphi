"""Loguru 统一日志配置。

在应用入口处调用 ``setup_logging()`` 即可完成：
- 移除 loguru 默认 handler
- 添加 stderr sink（带颜色、结构化格式）
- 拦截 stdlib logging → loguru（uvicorn / httpx / 第三方库日志统一收集）
"""

from __future__ import annotations

import logging
import sys

from loguru import logger


class _InterceptHandler(logging.Handler):
    """将 stdlib logging 的日志转发到 loguru。"""

    def emit(self, record: logging.LogRecord) -> None:
        # 获取对应的 loguru level
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 找到真正的调用者
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(*, level: str = "DEBUG", serialize: bool = False) -> None:
    """初始化 loguru 日志系统。

    Parameters
    ----------
    level:
        最低日志级别，默认 DEBUG 以便在 docker logs 中看到尽可能多的信息。
    serialize:
        是否输出 JSON 格式（适合日志采集系统）。
    """
    # 移除默认 handler
    logger.remove()

    # stderr sink — docker logs 直接可见
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        serialize=serialize,
        backtrace=True,
        diagnose=True,
    )

    # 拦截 stdlib logging
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    # 降低第三方库噪音
    for name in ("httpx", "httpcore", "uvicorn.access", "watchfiles"):
        logging.getLogger(name).setLevel(logging.WARNING)
