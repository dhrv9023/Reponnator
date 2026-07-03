"""
utils/logger.py — CodeAutopsy Centralized Logging

Provides a get_logger() factory that produces loggers writing to both
the console (with optional ANSI color) and to the per-repo fetch.log file.

Usage:
    from utils.logger import get_logger
    logger = get_logger(__name__)
"""

import logging
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# ANSI color codes for terminal output
# ---------------------------------------------------------------------------
_COLORS: dict[str, str] = {
    "RESET":    "\033[0m",
    "BOLD":     "\033[1m",
    "DEBUG":    "\033[36m",   # cyan
    "INFO":     "\033[32m",   # green
    "WARNING":  "\033[33m",   # yellow
    "ERROR":    "\033[31m",   # red
    "CRITICAL": "\033[35m",   # magenta
}


class _ColorFormatter(logging.Formatter):
    """Formatter that prepends ANSI color codes to each log level."""

    def __init__(self, fmt: str, datefmt: str, use_color: bool = True) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self._use_color = use_color

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        message = super().format(record)
        if not self._use_color:
            return message
        level = record.levelname
        color = _COLORS.get(level, _COLORS["RESET"])
        reset = _COLORS["RESET"]
        return f"{color}{message}{reset}"


# ---------------------------------------------------------------------------
# Module-level state: one file handler per log file path
# ---------------------------------------------------------------------------
_file_handlers: dict[str, logging.FileHandler] = {}
_active_log_file: Optional[Path] = None


def set_log_file(log_path: Path) -> None:
    """
    Configure the global log file for subsequent get_logger() calls.

    This must be called before the first get_logger() invocation for any
    module that should write to the per-repo fetch.log.

    Args:
        log_path: Absolute path to the target log file.  Parent directories
                  will be created if they do not already exist.
    """
    global _active_log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _active_log_file = log_path


def get_logger(name: str) -> logging.Logger:
    """
    Return (or create) a named logger that writes to console + optional file.

    Args:
        name: Logger name, conventionally ``__name__``.

    Returns:
        A configured :class:`logging.Logger` instance.
    """
    from config import LOG_FORMAT, LOG_DATE_FORMAT, LOG_LEVEL_DEFAULT  # local import to avoid circular

    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL_DEFAULT, logging.INFO))
    logger.propagate = False

    use_color = sys.stdout.isatty()

    # --- Console handler ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(
        _ColorFormatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT, use_color=use_color)
    )
    logger.addHandler(console_handler)

    # --- File handler (if log file configured) ---
    if _active_log_file is not None:
        file_path_str = str(_active_log_file)
        if file_path_str not in _file_handlers:
            fh = logging.FileHandler(_active_log_file, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(
                logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
            )
            _file_handlers[file_path_str] = fh

        logger.addHandler(_file_handlers[file_path_str])

    return logger


def configure_for_repo(repo_folder: Path) -> None:
    """
    Set up logging so all subsequent loggers also write to the repo's fetch.log.

    Call this once right after the repo output directory has been created.

    Args:
        repo_folder: Root folder for the repo  (e.g. data/repos/pallets__flask/).
    """
    log_file = repo_folder / "fetch.log"
    set_log_file(log_file)

    # Flush any existing loggers to also write to the new file handler
    file_path_str = str(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    from config import LOG_FORMAT, LOG_DATE_FORMAT
    fh.setFormatter(logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    _file_handlers[file_path_str] = fh

    # Attach to every existing logger in the hierarchy
    for existing_logger in logging.Logger.manager.loggerDict.values():
        if isinstance(existing_logger, logging.Logger) and not existing_logger.propagate:
            # Check if this file handler not already attached
            already_attached = any(
                isinstance(h, logging.FileHandler) and h.baseFilename == str(log_file)
                for h in existing_logger.handlers
            )
            if not already_attached:
                existing_logger.addHandler(fh)
