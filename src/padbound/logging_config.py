"""
Centralized logging configuration using rich.logging.

This module provides a simple way to configure rich logging for the entire
padbound library. Users can call setup_logging() once at the start of their
application to enable rich formatted logging.
"""

import logging
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler

# Global flag to track if logging has been configured
_logging_configured = False


def setup_logging(
    level: int = logging.INFO,
    show_time: bool = True,
    show_path: bool = True,
    rich_tracebacks: bool = True,
    console: Optional[Console] = None,
) -> None:
    """
    Configure rich logging for the padbound library.

    This should be called once at the start of your application.
    Subsequent calls will be ignored to avoid duplicate handlers.

    Args:
        level: Logging level (logging.DEBUG, logging.INFO, etc.)
        show_time: Show timestamp in log messages
        show_path: Show file path in log messages
        rich_tracebacks: Enable rich formatted tracebacks for exceptions
        console: Optional rich Console instance (creates default if None)

    Example:
        >>> from padbound.logging_config import setup_logging
        >>> import logging
        >>> setup_logging(level=logging.DEBUG)
    """
    global _logging_configured

    # Avoid configuring multiple times
    if _logging_configured:
        return

    # Create console if not provided
    if console is None:
        console = Console(stderr=True)

    # Create rich handler
    handler = RichHandler(
        console=console,
        show_time=show_time,
        show_path=show_path,
        rich_tracebacks=rich_tracebacks,
        markup=True,
        log_time_format="[%X]",
    )

    # Configure root logger
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[handler],
        force=True,  # Override any existing configuration
    )

    # Set flag to prevent duplicate configuration
    _logging_configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for the given name.

    This is a convenience wrapper around logging.getLogger() that ensures
    consistent logger naming across the project.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance

    Example:
        >>> from padbound.logging_config import get_logger
        >>> logger = get_logger(__name__)
    """
    return logging.getLogger(name)


def set_module_level(module_name: str, level: int) -> None:
    """
    Set logging level for a specific module.

    Args:
        module_name: Full module name (e.g., 'padbound.controller')
        level: Logging level (logging.DEBUG, logging.INFO, etc.)

    Example:
        >>> from padbound.logging_config import set_module_level
        >>> import logging
        >>> set_module_level('padbound.controller', logging.DEBUG)
    """
    logging.getLogger(module_name).setLevel(level)
