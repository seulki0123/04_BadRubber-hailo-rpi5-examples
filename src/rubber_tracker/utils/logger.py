import os
import logging
import logging.handlers
from threading import Lock
from datetime import datetime

from .utils import load_config

class Logger:
    """
    Logger class that provides centralized logging functionality for the application.
    """
    _instance = None
    _initialized = False
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        config = load_config()
        if self._initialized:
            return
            
        # Create logs directory if it doesn't exist
        self.logs_dir = config["log_dir"]["root"]
        temp_logs_dir = os.path.join(self.logs_dir, config["log_dir"]["temp"])
        
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(temp_logs_dir, exist_ok=True)
        
        # Get current timestamp for log file name
        temp_num = len(os.listdir(temp_logs_dir))
        self.current_log_file = os.path.join(temp_logs_dir, f'temp_{temp_num}.log')
        
        # Configure root logger
        self.logger = logging.getLogger()
        # self.logger.setLevel(logging.INFO)
        
        # Clear existing handlers to avoid duplicate logging
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        # Initialize handlers
        self.file_handler = self._create_file_handler()
        self.console_handler = logging.StreamHandler()
        # self.console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.file_handler.setFormatter(formatter)
        self.console_handler.setFormatter(formatter)
        
        # Add handlers to logger
        self.logger.addHandler(self.file_handler)
        self.logger.addHandler(self.console_handler)

        self.set_level(logging.INFO)
        self._initialized = True
        self.info("logger", f"Logger initialized with temp log file {self.current_log_file}, logger set level DEBUG")

    def _create_file_handler(self):
        """Create a new rotating file handler"""
        handler = logging.handlers.RotatingFileHandler(
            self.current_log_file, 
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        # handler.setLevel(logging.INFO)
        return handler
    
    def debug(self, module, message):
        """Log debug message"""
        self.logger.debug(f"[{module}] {message}")
    
    def info(self, module, message):
        """Log info message"""
        self.logger.info(f"[{module}] {message}")
    
    def warning(self, module, message):
        """Log warning message"""
        self.logger.warning(f"[{module}] {message}")
    
    def error(self, module, message):
        """Log error message"""
        self.logger.error(f"[{module}] {message}")
    
    def critical(self, module, message):
        """Log critical message"""
        self.logger.critical(f"[{module}] {message}")

    def set_level(self, level):
        """Set the logging level"""
        self.logger.setLevel(level)
        self.console_handler.setLevel(level)
        self.file_handler.setLevel(level)

# Create a singleton instance
logger = Logger()

# Module Logger
class ModuleLogger:
    COLOR_MAP = {
        "red": "\033[91m",
        "yellow": "\033[93m",
        "orange": "\033[38;5;208m",  # ANSI 256-color orange
        None: ""  # 기본
    }

    def __init__(self, name, highlight=False):
        self.name = name
        self.highlight = highlight

        self.highlight_color = "\033[92m" if highlight else ""
        self.reset_color = "\033[0m"

    def _apply_color(self, message, color):
        if not self.highlight_color and color in self.COLOR_MAP:
            return self.COLOR_MAP[color] + message + self.reset_color
        return self.highlight_color + message + self.reset_color

    def log_debug(self, message, color=None):
        logger.debug(self.name, self._apply_color(message, color))

    def log_info(self, message, color=None):
        logger.info(self.name, self._apply_color(message, color))

    def log_warning(self, message, color=None):
        logger.warning(self.name, self._apply_color(message, color))

    def log_error(self, message, color=None):
        logger.error(self.name, self._apply_color(message, color))

    def log_critical(self, message, color=None):
        logger.critical(self.name, self._apply_color(message, color))

# Switch log file to now
def switch_log_file_to_now():
    """
    Change the log file to a new file.
    Safe to call from multiple threads.
    """
    with logger._lock:
        
        # Create new file handler
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        new_log_file = os.path.join(logger.logs_dir, f'app_{timestamp}.log')

        old_log_file = logger.current_log_file
        logger.info("logger", f"Log file changed to {new_log_file}")

        # Remove old file handler
        logger.logger.removeHandler(logger.file_handler)
        
        logger.current_log_file = new_log_file
        new_file_handler = logger._create_file_handler()
        
        # Formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        new_file_handler.setFormatter(formatter)
        
        # Add new handler
        logger.logger.addHandler(new_file_handler)
        
        # Update reference
        logger.file_handler = new_file_handler

        logger.set_level(logging.INFO)
        logger.info("logger", f"Log file changed from {old_log_file}, set logger level INFO")