"""
Logging configuration for the application.
Provides structured logging with proper formatting and handlers.
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler

from ..config import get_settings


def setup_logging(
    name: str = "surgibot",
    log_file: Optional[str] = None,
    log_level: Optional[str] = None,
    log_format: Optional[str] = None,
) -> logging.Logger:
    """
    Setup logging configuration.

    Args:
        name: Logger name
        log_file: Path to log file (optional)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Log message format string

    Returns:
        Configured logger instance
    """
    settings = get_settings()

    # Get configuration values
    level = log_level or settings.log_level
    file_path = log_file or settings.log_file
    format_str = log_format or settings.log_format

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(format_str)

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (if specified)
    if file_path:
        file_path_obj = Path(file_path)
        file_path_obj.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            file_path, maxBytes=10 * 1024 * 1024, backupCount=5  # 10MB
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_logger(name: str = "surgibot") -> logging.Logger:
    """
    Get or create a logger instance.

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        setup_logging(name)
    return logger


# Module-specific loggers
def get_api_logger() -> logging.Logger:
    """Get logger for API module."""
    return get_logger("surgibot.api")


def get_display_logger() -> logging.Logger:
    """Get logger for display module."""
    return get_logger("surgibot.display")


def get_tts_logger() -> logging.Logger:
    """Get logger for TTS module."""
    return get_logger("surgibot.tts")


def get_sheets_logger() -> logging.Logger:
    """Get logger for Google Sheets module."""
    return get_logger("surgibot.sheets")


def get_client_logger() -> logging.Logger:
    """Get logger for client module."""
    return get_logger("surgibot.client")


def get_registry_logger() -> logging.Logger:
    """Get logger for registry module."""
    return get_logger("surgibot.registry")
