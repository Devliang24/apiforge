"""
Centralized logging system for APIForge.

This module provides a structured logging system with configurable output formats
and security features to sanitize sensitive information.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from apiforge.config import settings


class StructuredFormatter(logging.Formatter):
    """
    Custom formatter for structured JSON logging.
    
    Converts log records to structured JSON format with consistent fields
    and optional sanitization of sensitive data.
    """
    
    def __init__(self, sanitize: bool = True):
        """
        Initialize the structured formatter.
        
        Args:
            sanitize: Whether to sanitize sensitive information from logs
        """
        super().__init__()
        self.sanitize = sanitize
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format a log record as structured JSON.
        
        Args:
            record: The log record to format
            
        Returns:
            str: JSON-formatted log entry
        """
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception information if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields from the log record
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message"
            }:
                log_entry[key] = value
        
        # Sanitize sensitive information if enabled
        if self.sanitize:
            log_entry = self._sanitize_log_entry(log_entry)
        
        return json.dumps(log_entry, ensure_ascii=False, separators=(',', ':'))
    
    def _sanitize_log_entry(self, log_entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize sensitive information from log entries.
        
        Args:
            log_entry: The log entry dictionary to sanitize
            
        Returns:
            Dict[str, Any]: Sanitized log entry
        """
        sensitive_keys = {
            "api_key", "apikey", "key", "token", "password", "secret",
            "authorization", "auth", "credential", "openai_api_key"
        }
        
        def sanitize_value(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {
                    k: "[REDACTED]" if k.lower() in sensitive_keys else sanitize_value(v)
                    for k, v in obj.items()
                }
            elif isinstance(obj, list):
                return [sanitize_value(item) for item in obj]
            elif isinstance(obj, str):
                # Redact strings that look like API keys
                if any(key in obj.lower() for key in sensitive_keys):
                    if len(obj) > 10:  # Only redact if it looks like a real key
                        return f"{obj[:4]}...{obj[-4:]}"
                return obj
            else:
                return obj
        
        return sanitize_value(log_entry)


class SimpleFormatter(logging.Formatter):
    """Simple, human-readable formatter for development use."""
    
    def __init__(self):
        """Initialize the simple formatter with a readable format."""
        super().__init__(
            fmt="%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )


def setup_logger(
    name: Optional[str] = None,
    level: Optional[str] = None,
    log_format: Optional[str] = None
) -> logging.Logger:
    """
    Set up and configure a logger instance.
    
    Args:
        name: Logger name (defaults to 'apitestgen')
        level: Log level (defaults to settings.LOG_LEVEL)
        log_format: Format type ('structured' or 'simple', defaults to settings.LOG_FORMAT)
        
    Returns:
        logging.Logger: Configured logger instance
    """
    logger_name = name or "apitestgen"
    log_level = level or settings.log_level
    format_type = log_format or settings.log_format
    
    logger = logging.getLogger(logger_name)
    
    # Only configure if not already configured
    if not logger.handlers:
        logger.setLevel(getattr(logging, log_level.upper()))
        
        # Create console handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(getattr(logging, log_level.upper()))
        
        # Set formatter based on configuration
        if format_type == "structured":
            formatter = StructuredFormatter(sanitize=settings.sanitize_logs)
        else:
            formatter = SimpleFormatter()
        
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        # Prevent duplicate logs from parent loggers
        logger.propagate = False
    
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (defaults to calling module name)
        
    Returns:
        logging.Logger: Configured logger instance
    """
    if name is None:
        # Get the calling module's name
        import inspect
        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get("__name__", "apitestgen")
        else:
            name = "apitestgen"
    
    return setup_logger(name)


# Create the global logger instance
logger = setup_logger()


# Convenience functions for different log levels
def debug(message: str, **kwargs: Any) -> None:
    """Log a debug message with optional extra fields."""
    logger.debug(message, extra=kwargs)


def info(message: str, **kwargs: Any) -> None:
    """Log an info message with optional extra fields."""
    logger.info(message, extra=kwargs)


def warning(message: str, **kwargs: Any) -> None:
    """Log a warning message with optional extra fields."""
    logger.warning(message, extra=kwargs)


def error(message: str, **kwargs: Any) -> None:
    """Log an error message with optional extra fields."""
    logger.error(message, extra=kwargs)


def critical(message: str, **kwargs: Any) -> None:
    """Log a critical message with optional extra fields."""
    logger.critical(message, extra=kwargs)