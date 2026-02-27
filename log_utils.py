import logging
from datetime import datetime
from pathlib import Path
from typing import Union


LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_daily_file_logging(script_path: Union[str, Path], prefix: str) -> Path:
    """配置控制台 + 按天日志文件输出，返回当天日志文件路径。"""
    script_path = Path(script_path).resolve()
    log_dir = script_path.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"{prefix}-{datetime.now().strftime('%Y-%m-%d')}.log"
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # 仅添加一个控制台 handler，避免重复日志
    has_stream_handler = any(
        isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
        for handler in root_logger.handlers
    )
    if not has_stream_handler:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

    # 当天文件 handler 不重复添加
    has_file_handler = any(
        isinstance(handler, logging.FileHandler)
        and Path(getattr(handler, "baseFilename", "")) == log_file
        for handler in root_logger.handlers
    )
    if not has_file_handler:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    return log_file
