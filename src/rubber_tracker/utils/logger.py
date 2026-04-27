import os
import logging
import logging.handlers
from threading import Lock
from datetime import datetime

from .utils import load_config


class LogTypeFilter(logging.Filter):
    def __init__(self, log_type: str):
        super().__init__()
        self.log_type = log_type

    def filter(self, record: logging.LogRecord) -> bool:
        # 기본은 process 로그로 처리
        return getattr(record, "log_type", "process") == self.log_type

class LogColor:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    GRAY = "\033[90m"

class ColorFormatter(logging.Formatter):
    def format(self, record):
        msg = super().format(record)
        color = getattr(record, "color", None)

        if color:
            return f"{color}{msg}{LogColor.RESET}"
        return msg

class Logger:
    """
    Logger class that provides centralized logging functionality for the application.
    """
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        config = load_config()
        if self._initialized:
            return

        # Create logs directory if it doesn't exist
        logs_dir = config["log_dir"]["root"]
        process_folder = config["log_dir"].get("process", "process")
        monitor_folder = config["log_dir"].get("monitor", "monitor")
        process_log_dir = os.path.join(logs_dir, process_folder)
        monitor_log_dir = os.path.join(logs_dir, monitor_folder)
        os.makedirs(process_log_dir, exist_ok=True)
        os.makedirs(monitor_log_dir, exist_ok=True)

        # 실행 시각 기준 파일명
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        self.process_log_file = os.path.join(
            process_log_dir, f"{timestamp}.log"
        )
        self.monitor_log_file = os.path.join(
            monitor_log_dir, f"{timestamp}.log"
        )

        # Configure root logger
        self.logger = logging.getLogger()
        self.logger.propagate = False

        # Clear existing handlers to avoid duplicate logging
        if self.logger.handlers:
            self.logger.handlers.clear()

        # Handlers
        self.process_handler = self._create_process_handler()
        self.monitor_handler = self._create_monitor_handler()
        self.console_handler = logging.StreamHandler()
        self.console_handler.addFilter(LogTypeFilter("process"))

        # Formatter
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        console_formatter = ColorFormatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        self.process_handler.setFormatter(file_formatter)
        self.monitor_handler.setFormatter(file_formatter)
        self.console_handler.setFormatter(console_formatter)

        # Add handlers
        self.logger.addHandler(self.process_handler)
        self.logger.addHandler(self.monitor_handler)
        self.logger.addHandler(self.console_handler)

        self.set_level(logging.INFO)
        self._initialized = True

        self.info(
            "logger",
            f"Logger initialized: {self.process_log_file}, {self.monitor_log_file}",
        )

    def _create_process_handler(self):
        handler = logging.handlers.TimedRotatingFileHandler(
            filename=self.process_log_file,
            when="midnight",
            interval=1,
            backupCount=0,
            encoding="utf-8",
            utc=False,
        )
        handler.suffix = "%Y-%m-%d"
        handler.addFilter(LogTypeFilter("process"))
        return handler

    def _create_monitor_handler(self):
        handler = logging.handlers.TimedRotatingFileHandler(
            filename=self.monitor_log_file,
            when="midnight",
            interval=1,
            backupCount=0,
            encoding="utf-8",
            utc=False,
        )
        handler.suffix = "%Y-%m-%d"
        handler.addFilter(LogTypeFilter("monitor"))
        return handler

    # ---- Logging API ----

    def info(self, module, message, *, log_type="process", color=None):
        self.logger.info(
            f"[{module}] {message}",
            extra={"log_type": log_type, "color": color},
        )

    def warning(self, module, message, *, log_type="process", color=None):
        self.logger.warning(
            f"[{module}] {message}",
            extra={"log_type": log_type, "color": color},
        )

    def error(self, module, message, *, log_type="process", color=None, exc_info=False):
        self.logger.error(
            f"[{module}] {message}",
            exc_info=exc_info,
            extra={"log_type": log_type, "color": color},
        )

    def debug(self, module, message, *, log_type="process", color=None):
        self.logger.debug(
            f"[{module}] {message}",
            extra={"log_type": log_type, "color": color},
        )

    def critical(self, module, message, *, log_type="process", color=None):
        self.logger.critical(
            f"[{module}] {message}",
            extra={"log_type": log_type, "color": color},
        )

    def set_level(self, level):
        self.logger.setLevel(level)
        self.console_handler.setLevel(level)
        self.process_handler.setLevel(level)
        self.monitor_handler.setLevel(level)


# Create singleton instance
logger = Logger()

class ProcessLogger:
    def __init__(self, name):
        self.name = name

    def log_debug(self, message, color=None):
        logger.debug(self.name, message, color=color)

    def log_info(self, message, color=None):
        logger.info(self.name, message, color=color)

    def log_warning(self, message, color=None):
        logger.warning(self.name, message, color=color)

    def log_error(self, message, color=None, exc_info=False):
        logger.error(self.name, message, color=color, exc_info=exc_info)

    def log_critical(self, message, color=None):
        logger.critical(self.name, message, color=color)

class MonitorLogger:
    def __init__(self, name):
        self.name = name

    def log_debug(self, message, color=None):
        logger.debug(self.name, message, color=color, log_type="monitor")

    def log_info(self, message, color=None):
        logger.info(self.name, message, color=color, log_type="monitor")

    def log_warning(self, message, color=None):
        logger.warning(self.name, message, color=color, log_type="monitor")

    def log_error(self, message, color=None):
        logger.error(self.name, message, color=color, log_type="monitor")

    def log_critical(self, message, color=None):
        logger.critical(self.name, message, color=color, log_type="monitor")