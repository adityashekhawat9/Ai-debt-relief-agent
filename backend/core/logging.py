import logging
import structlog
from core.config import Settings

import logging.handlers
import os
import datetime

class DailyFolderFileHandler(logging.FileHandler):
    """Custom handler that automatically writes to a new YYYY-MM-DD folder every midnight."""
    def __init__(self, base_dir: str, filename: str):
        self.base_dir = base_dir
        self.filename = filename
        self.current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        super().__init__(self._get_log_path(self.current_date))
        
    def _get_log_path(self, date_str: str) -> str:
        log_dir = os.path.join(self.base_dir, date_str)
        os.makedirs(log_dir, exist_ok=True)
        return os.path.join(log_dir, self.filename)

    def emit(self, record: logging.LogRecord) -> None:
        new_date = datetime.datetime.now().strftime("%Y-%m-%d")
        if new_date != self.current_date:
            self.current_date = new_date
            self.close()
            self.baseFilename = os.path.abspath(self._get_log_path(new_date))
            self.stream = self._open()
        super().emit(record)

def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)

def configure_logging(settings: Settings) -> None:
    # Ensure base logs directory exists — fall back gracefully if Docker/permissions block it
    base_log_dir = os.path.join(os.getcwd(), "logs")
    file_logging_enabled = False
    try:
        os.makedirs(base_log_dir, exist_ok=True)
        file_logging_enabled = True
    except PermissionError:
        print(f"[WARNING] Cannot create log directory at '{base_log_dir}'. File logging disabled. Only console logging active.")
    
    # 1. Configure standard python logging
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.getLevelName(settings.LOG_LEVEL.upper()))
    root_logger.handlers.clear()
    
    console_handler = logging.StreamHandler()
    file_handler = DailyFolderFileHandler(base_dir=base_log_dir, filename="ai-voice.log") if file_logging_enabled else None
    
    if settings.LOG_FORMAT == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()
        
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ]
    )
    
    if file_handler:
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 2. Configure structlog to route through standard python logging
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

import asyncio
import traceback
import datetime
import os

async def async_log_error(e: Exception, context: str = ""):
    """Asynchronously append an exception traceback to a log file to avoid blocking the event loop."""
    log_path = os.path.join(os.getcwd(), 'async_errors.log')
    
    def _write_log():
        with open(log_path, 'a') as f:
            f.write(f"\n--- {datetime.datetime.now().isoformat()} ---\n")
            f.write(f"Context: {context}\n")
            f.write(f"Exception: {str(e)}\n")
            f.write(traceback.format_exc())
            f.write("-" * 50 + "\n")
            
    try:
        await asyncio.to_thread(_write_log)
    except Exception:
        pass
