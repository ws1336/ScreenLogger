"""
日志系统模块
提供统一的日志记录功能，同时输出到文件和通过 PySide6 信号发射到 UI。
采用单例模式 + 自定义 logging.Handler 实现。
"""
from pathlib import Path
import logging
import os
from datetime import datetime

from PySide6.QtCore import QObject, Signal


class LogSignalEmitter(QObject):
    """
    日志信号发射器
    通过 PySide6 信号机制将日志消息发射到 UI 层，供日志查看器绑定显示。
    """
    log_emitted = Signal(int, str, str)  # level(int), message(str), timestamp(str)

    def emit_log(self, level: int, message: str, timestamp: str):
        self.log_emitted.emit(level, message, timestamp)


class _SignalLogHandler(logging.Handler):
    """
    自定义 logging Handler，将日志记录路由到 LogSignalEmitter 信号。
    """

    def __init__(self, emitter: LogSignalEmitter):
        super().__init__()
        self._emitter = emitter

    def emit(self, record: logging.LogRecord):
        level = record.levelno
        message = self.format(record)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._emitter.emit_log(level, message, timestamp)


DEFAULT_LOG_DIR = str(Path.home() / ".cache" / "ScreenLogger" / "logs")


class LogManager:
    """
    日志管理器（单例模式）
    配置 Python logging，同时输出到文件和 LogSignalEmitter 信号。
    """
    _instance = None
    _initialized = False

    def __new__(cls, log_dir: str = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, log_dir: str = None):
        if LogManager._initialized:
            return
        LogManager._initialized = True

        if log_dir is None:
            log_dir = DEFAULT_LOG_DIR
        self._setup_logging(log_dir)

    def _setup_logging(self, log_dir: str):
        """配置日志输出到指定目录"""
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        self._logger = logging.getLogger("ScreenLogger")
        self._logger.setLevel(logging.DEBUG)
        self._logger.handlers.clear()

        log_format = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s",
                                       datefmt="%Y-%m-%d %H:%M:%S")

        # 文件处理器
        log_file = log_path / "screenlogger.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(log_format)
        self._logger.addHandler(file_handler)

        # 信号发射器
        self._emitter = LogSignalEmitter()
        signal_handler = _SignalLogHandler(self._emitter)
        signal_handler.setLevel(logging.DEBUG)
        signal_handler.setFormatter(log_format)
        self._logger.addHandler(signal_handler)

    def reconfigure(self, log_dir: str):
        """
        重新配置日志目录（在 Settings 初始化后调用，使用根目录派生路径）
        Args:
            log_dir: 新的日志目录路径
        """
        if not LogManager._initialized:
            self.__init__(log_dir)
            return
        self._logger.handlers.clear()
        self._setup_logging(log_dir)

    def _get_logger(self) -> logging.Logger:
        """获取内部 logging.Logger 实例，确保单例已初始化"""
        return logging.getLogger("ScreenLogger")

    def debug(self, message: str):
        """记录 DEBUG 级别日志"""
        self._get_logger().debug(message)

    def info(self, message: str):
        """记录 INFO 级别日志"""
        self._get_logger().info(message)

    def warning(self, message: str):
        """记录 WARNING 级别日志"""
        self._get_logger().warning(message)

    def error(self, message: str):
        """记录 ERROR 级别日志"""
        self._get_logger().error(message)

    def get_emitter(self) -> LogSignalEmitter:
        """返回 LogSignalEmitter 实例，供 UI 层绑定信号"""
        return self._emitter


# 模块级单例
log_manager = LogManager()