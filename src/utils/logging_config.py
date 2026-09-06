import contextvars
import logging
import os
import sys

from loguru import logger as loguru_logger

from src.utils.datetime_utils import shanghai_now

SAVE_DIR = os.getenv("SAVE_DIR") or "saves"
DATETIME = shanghai_now().strftime("%Y-%m-%d")
LOG_FILE = f"{SAVE_DIR}/logs/yuxi-{DATETIME}.log"

# 请求 ID 贯通：中间件 set，LoguruHandler/patch 读取，前后端凭同一 ID 对账
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class LoguruHandler(logging.Handler):
    """将 Python logging 桥接到 loguru 的 handler"""

    def emit(self, record: logging.LogRecord):
        level_map = {
            logging.DEBUG: "DEBUG",
            logging.INFO: "INFO",
            logging.WARNING: "WARNING",
            logging.ERROR: "ERROR",
            logging.CRITICAL: "CRITICAL",
        }
        level = level_map.get(record.levelno, "DEBUG")
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        loguru_logger.opt(depth=1, exception=record.exc_info).bind(
            request_id=request_id_var.get()
        ).log(level, msg)


def _setup_logging_bridge():
    """桥接根 logger 与常见第三方库 → loguru（全仓 logging.getLogger(__name__) 自动进文件）"""
    loguru_handler = LoguruHandler()
    loguru_handler.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    loguru_handler.setFormatter(formatter)

    # 根 logger：全仓 logging.getLogger(__name__) 的输出进 loguru
    root = logging.getLogger()
    root.addHandler(loguru_handler)
    root.setLevel(logging.INFO)
    root.propagate = False

    # 桥接 LightRAG 日志
    lightrag_logger = logging.getLogger("lightrag")
    lightrag_logger.addHandler(loguru_handler)
    lightrag_logger.setLevel(logging.DEBUG)
    lightrag_logger.propagate = False

    # 桥接其他常见第三方库（降低级别减少噪音）
    for lib in ["httpx", "openai", "neo4j", "urllib3"]:
        lib_logger = logging.getLogger(lib)
        lib_logger.addHandler(loguru_handler)
        lib_logger.setLevel(logging.WARNING)
        lib_logger.propagate = False


def setup_logger(name, level="DEBUG", console=True):
    """使用 loguru 设置日志记录器"""
    os.makedirs(f"{SAVE_DIR}/logs", exist_ok=True)

    # 移除默认的 handler
    loguru_logger.remove()

    # 添加文件日志（无颜色，带请求 ID）
    loguru_logger.add(
        LOG_FILE,
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss} - {level} - [{extra[request_id]}] - {file}:{line} - {message}",
        encoding="utf-8",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        enqueue=True,
        filter=lambda r: r["extra"].get("request_id", "-"),
    )

    # 添加控制台日志（有颜色）
    if console:
        loguru_logger.add(
            sys.stderr,
            level=level,
            format=(
                "<green>{time:MM-DD HH:mm:ss}</green> "
                "<level>{level}</level> "
                "[{extra[request_id]}] "
                "<cyan>{file}:{line}</cyan>: "
                "<level>{message}</level>"
            ),
            colorize=True,
            enqueue=True,
        )

    # 所有 loguru 输出自动携带 request_id（默认 '-'）
    loguru_logger.configure(extra={"request_id": "-"})

    return loguru_logger


# 设置根日志记录器
logger = setup_logger("Yuxi")

# 初始化 logging 桥接
_setup_logging_bridge()

__all__ = ["logger", "request_id_var"]
