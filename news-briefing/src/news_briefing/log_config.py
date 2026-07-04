"""统一日志配置。

格式: YYYY-MM-DD HH:MM:SS,mmm [LEVEL] module: message
"""

import logging
import sys
from pathlib import Path


def setup_logging(
    level: int = logging.INFO,
    log_dir: str = "logs",
    log_file: str = "app.log",
) -> None:
    """初始化日志系统。

    Args:
        level: 日志级别。默认 INFO。
        log_dir: 日志目录。
        log_file: 日志文件名。
    """
    # 确保日志目录存在
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # 日志格式
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    # 根 logger
    root = logging.getLogger()
    root.setLevel(level)

    # 清除已有的 handler
    root.handlers.clear()

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root.addHandler(console_handler)

    # 文件 handler
    log_path = Path(log_dir) / log_file
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root.addHandler(file_handler)

    # 降低第三方库的日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    root.info("日志系统初始化完成")
