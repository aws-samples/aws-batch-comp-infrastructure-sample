"""Standard logging manager for this project."""

import logging
import sys
from typing import List


class LoggingManager:
    """
    Manage your loggers with `get_logger()`.
    """

    loggers = {}

    def __init__(self):
        pass

    def get_logger(
        self,
        logger_name: str,
        level=logging.INFO,
        formatted: bool = True,
        out_stream=sys.stdout,
        out_level=logging.INFO,
        err_stream=sys.stderr,
        err_level=logging.WARNING,
    ) -> logging.Logger:
        """Idempotent logging setup."""
        # logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # If we have already initialized this logger, return it
        if logger_name in LoggingManager.loggers:
            return LoggingManager.loggers[logger_name]

        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        LoggingManager.loggers[logger_name] = logger

        stdout_handler = logging.StreamHandler(out_stream)
        stdout_handler.setLevel(out_level)
        stdout_handler.addFilter(lambda x: x.levelno <= out_level)

        stderr_handler = logging.StreamHandler(err_stream)
        stderr_handler.setLevel(err_level)
        stderr_handler.addFilter(lambda x: x.levelno >= err_level)

        if formatted:
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
            stdout_handler.setFormatter(formatter)
            stderr_handler.setFormatter(formatter)

        logger.addHandler(stdout_handler)
        logger.addHandler(stderr_handler)
        return logger

    def split_log(self, log: str) -> List[str]:
        """
        Returns the log, splitting out the prefixed info labels.

        For example, calling `split()` on

        ```
        "2025-06-09 13:16:37 - Leader Entrypoint - INFO - Removing directory /tmp/satcomp25-abc123"
        ```
        gives back
        ```
        ["2025-06-09 13:16:37", "Leader Entrypoint", "INFO", "Removing directory /tmp/satcomp25-abc123"]
        ```

        If the log is really two nested logs, `split_log()` only splits off the first log.
        Call this function again to split off the second one.
        """
        return log.split(" - ", maxsplit=3)
