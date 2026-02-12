"""
utils/logger.py
───────────────
Centralised structured logging for the entire application.

All modules import their logger from here so that
log level, format, and handlers are consistent.
"""

import logging
import config

_configured = False


def get_logger(name: str) -> logging.Logger:
    """
    Return a configured logger for the given module name.

    Usage
    -----
        from utils.logger import get_logger
        log = get_logger(__name__)
        log.info("Fetching NAV for scheme %d", code)
    """
    global _configured
    if not _configured:
        logging.basicConfig(
            level=config.LOG_LEVEL,
            format=config.LOG_FORMAT,
            datefmt=config.LOG_DATE_FORMAT,
        )
        _configured = True

    return logging.getLogger(name)
