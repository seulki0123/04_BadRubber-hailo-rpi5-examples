import os
import sys
import logging
import logging.handlers
from threading import Lock
from datetime import datetime

from .utils import load_config


class LogTypeFilter(logging.Filter):
    """
    특정 log_type 에 해당하는 레코드만 통과시키는 필터.

    기존에는 단일 문자열만 받았으나(process / monitor),
    branch / join 처럼 여러 타입을 같은 핸들러로 받아야 하는 경우가 생겨
    문자열 또는 iterable 을 모두 허용하도록 확장.
      - process.log 는 여전히 모든 트래킹 이벤트를 통합 기록해야 하므로
        ["process", "branch", "join"] 을 받게 된다.

    플랫폼 독립성: 표준 logging.Filter 만 확장했으므로 로컬(Mac)과
    운영 서버(Raspberry Pi/Hailo) 모두 동일하게 동작한다.
    """
    def __init__(self, log_types):
        super().__init__()
        if isinstance(log_types, str):
            self.log_types = {log_types}
        else:
            self.log_types = set(log_types)

    def filter(self, record: logging.LogRecord) -> bool:
        # 기본은 process 로그로 처리
        return getattr(record, "log_type", "process") in self.log_types

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

    플랫폼 독립성:
      - 표준 logging / logging.handlers / os / datetime 만 사용.
      - 로컬 개발(Mac) 과 운영 서버(Raspberry Pi / Hailo 장비) 모두 동일하게 동작한다.
      - 동작에 필요한 디렉토리는 os.makedirs(exist_ok=True) 로 생성하며,
        실패 시 해당 split 만 비활성화(fallback)되고 나머지 로그는 영향받지 않는다.
    """
    _instance = None
    _initialized = False

    # 허용되는 log_type 집합. 호출부에서 오타/임의 값이 들어와도 메시지가 유실되지 않도록
    # Logger.info/warning/... 에서 이 집합에 없으면 기본 "process" 로 fallback 한다.
    _VALID_LOG_TYPES = frozenset({"process", "monitor", "branch", "join"})

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        config = load_config()
        if self._initialized:
            return

        # Create logs directory if it doesn't exist
        log_dir_cfg = config.get("log_dir", {}) or {}
        logs_dir = log_dir_cfg["root"]
        process_folder = log_dir_cfg.get("process", "process")
        monitor_folder = log_dir_cfg.get("monitor", "monitor")
        # branch / join 폴더명. null/미설정이면 해당 split 핸들러 생성하지 않는다.
        branch_folder = log_dir_cfg.get("branch")
        join_folder = log_dir_cfg.get("join")

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

        # branch / join split 로그 파일 (enabled 시에만 설정)
        # 폴더 생성 실패(권한/디스크 부족 등) 시 해당 split 만 비활성화하고
        # 나머지 로깅(process/monitor)은 정상 진행되도록 fallback 처리한다.
        self.branch_log_file = None
        self.join_log_file = None
        self.branch_log_file = self._prepare_split_log_file(
            logs_dir, branch_folder, timestamp, label="branch"
        )
        self.join_log_file = self._prepare_split_log_file(
            logs_dir, join_folder, timestamp, label="join"
        )

        # Configure root logger
        self.logger = logging.getLogger()
        self.logger.propagate = False

        # Clear existing handlers to avoid duplicate logging
        if self.logger.handlers:
            self.logger.handlers.clear()

        # Handlers
        # process 핸들러는 기존 '통합 로그' 역할을 유지해야 하므로
        # process + branch + join 모두 수용한다.
        self.process_handler = self._create_process_handler()
        self.monitor_handler = self._create_monitor_handler()
        self.console_handler = logging.StreamHandler()
        self.console_handler.addFilter(LogTypeFilter(["process", "branch", "join"]))

        # branch / join 전용 핸들러 (설정에 해당 폴더가 있을 때만 생성)
        self.branch_handler = None
        self.join_handler = None
        if self.branch_log_file:
            self.branch_handler = self._create_split_handler(self.branch_log_file, "branch")
        if self.join_log_file:
            self.join_handler = self._create_split_handler(self.join_log_file, "join")

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
        if self.branch_handler is not None:
            self.branch_handler.setFormatter(file_formatter)
        if self.join_handler is not None:
            self.join_handler.setFormatter(file_formatter)

        # Add handlers
        self.logger.addHandler(self.process_handler)
        self.logger.addHandler(self.monitor_handler)
        self.logger.addHandler(self.console_handler)
        if self.branch_handler is not None:
            self.logger.addHandler(self.branch_handler)
        if self.join_handler is not None:
            self.logger.addHandler(self.join_handler)

        self.set_level(logging.INFO)
        self._initialized = True

        init_msg = f"Logger initialized: {self.process_log_file}, {self.monitor_log_file}"
        if self.branch_log_file:
            init_msg += f", {self.branch_log_file}"
        if self.join_log_file:
            init_msg += f", {self.join_log_file}"
        self.info("logger", init_msg)

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
        # process.log 는 통합 로그. 기본 process 타입 외에 branch/join 분기 이벤트도 함께 받는다.
        handler.addFilter(LogTypeFilter(["process", "branch", "join"]))
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

    def _prepare_split_log_file(self, logs_dir, folder, timestamp, label):
        """
        branch / join 분기 로그용 디렉토리를 준비하고 로그 파일 경로를 돌려준다.

        실패 유형 및 대응:
          - folder 가 null 또는 빈 문자열 → 해당 split 비활성 (반환 None, 경고 없음).
          - folder 가 문자열이 아님 (config 오타) → 경고 출력 후 None 반환.
          - 디렉토리 생성 실패 (권한/디스크 등) → 경고 출력 후 None 반환.

        반환이 None 이면 해당 split 핸들러는 만들어지지 않고,
        해당 zone 이벤트는 통합 process.log 에만 기록된다 (fallback).
        """
        if folder is None or folder == "":
            return None
        if not isinstance(folder, str):
            sys.stderr.write(
                f"[Logger] log_dir.{label} must be a string, got "
                f"{type(folder).__name__!r}. Split logging disabled for '{label}'.\n"
            )
            return None
        log_dir = os.path.join(logs_dir, folder)
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError as e:
            sys.stderr.write(
                f"[Logger] Failed to create split log dir '{log_dir}': {e}. "
                f"Split logging disabled for '{label}'. "
                f"'{label}_*' zone events will still be written to the combined process log.\n"
            )
            return None
        return os.path.join(log_dir, f"{timestamp}.log")

    def _create_split_handler(self, log_file: str, log_type: str):
        """
        branch / join 전용 로그 파일을 위한 핸들러.
        해당 log_type 레코드만 필터링해서 별도 파일로 저장한다.
        process.log 의 중복 기록을 막지는 않는다(통합 로그는 그대로 유지).
        """
        handler = logging.handlers.TimedRotatingFileHandler(
            filename=log_file,
            when="midnight",
            interval=1,
            backupCount=0,
            encoding="utf-8",
            utc=False,
        )
        handler.suffix = "%Y-%m-%d"
        handler.addFilter(LogTypeFilter(log_type))
        return handler

    # ---- Logging API ----

    def _normalize_log_type(self, log_type):
        """알 수 없는 log_type 이 넘어오면 기본 'process' 로 복구.

        주의: 잘못된 값이 LogTypeFilter 에 그대로 전달되면 어떤 핸들러에도
        match 하지 않아 메시지가 유실될 수 있다. 오타/버그로 인한 로그 소실을
        막기 위해 집합 밖의 값은 조용히 process 로 떨어뜨리고 stderr 에 경고.
        (stderr 로만 쓰는 이유: 로깅 자체가 망가진 상황일 수 있어서 재귀적으로
        self.logger 를 다시 부르면 문제를 키울 수 있음.)
        """
        if log_type in self._VALID_LOG_TYPES:
            return log_type
        sys.stderr.write(
            f"[Logger] Unknown log_type={log_type!r}; falling back to 'process'. "
            f"Valid types: {sorted(self._VALID_LOG_TYPES)}\n"
        )
        return "process"

    def info(self, module, message, *, log_type="process", color=None):
        log_type = self._normalize_log_type(log_type)
        self.logger.info(
            f"[{module}] {message}",
            extra={"log_type": log_type, "color": color},
        )

    def warning(self, module, message, *, log_type="process", color=None):
        log_type = self._normalize_log_type(log_type)
        self.logger.warning(
            f"[{module}] {message}",
            extra={"log_type": log_type, "color": color},
        )

    def error(self, module, message, *, log_type="process", color=None):
        log_type = self._normalize_log_type(log_type)
        self.logger.error(
            f"[{module}] {message}",
            extra={"log_type": log_type, "color": color},
        )

    def debug(self, module, message, *, log_type="process", color=None):
        log_type = self._normalize_log_type(log_type)
        self.logger.debug(
            f"[{module}] {message}",
            extra={"log_type": log_type, "color": color},
        )

    def critical(self, module, message, *, log_type="process", color=None):
        log_type = self._normalize_log_type(log_type)
        self.logger.critical(
            f"[{module}] {message}",
            extra={"log_type": log_type, "color": color},
        )

    def set_level(self, level):
        self.logger.setLevel(level)
        self.console_handler.setLevel(level)
        self.process_handler.setLevel(level)
        self.monitor_handler.setLevel(level)
        if self.branch_handler is not None:
            self.branch_handler.setLevel(level)
        if self.join_handler is not None:
            self.join_handler.setLevel(level)


# Create singleton instance
logger = Logger()

class ProcessLogger:
    """
    프로세스 로그 전용 래퍼.

    log_type 키워드 인자는 기본 "process". EventService 처럼 이벤트의 zone 에 따라
    branch / join 으로 분기 기록이 필요할 때만 호출부에서 log_type 을 넘겨준다.
    다른 모듈은 인자를 주지 않아도 기존과 동일하게 동작한다.
    """
    def __init__(self, name):
        self.name = name

    def log_debug(self, message, color=None, log_type="process"):
        logger.debug(self.name, message, color=color, log_type=log_type)

    def log_info(self, message, color=None, log_type="process"):
        logger.info(self.name, message, color=color, log_type=log_type)

    def log_warning(self, message, color=None, log_type="process"):
        logger.warning(self.name, message, color=color, log_type=log_type)

    def log_error(self, message, color=None, log_type="process"):
        logger.error(self.name, message, color=color, log_type=log_type)

    def log_critical(self, message, color=None, log_type="process"):
        logger.critical(self.name, message, color=color, log_type=log_type)

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