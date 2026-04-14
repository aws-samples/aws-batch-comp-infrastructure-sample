"""Common miscellaneous functions."""

import sys
from datetime import date, datetime
from typing import Any, List


def str_format_bytes(bytes: int, suffix="B") -> str:
    """
    Returns a string formatted into a human-readable label for the number of bytes.

    ```
    str_format_bytes(1024)          # "1.0 KiB"
    str_format_bytes(1048576)       # "1.0 MiB"
    ```
    """
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(bytes) < 1024.0:
            return f"{bytes:3.1f} {unit}{suffix}"
        bytes /= 1024.0
    return f"{bytes:.1f} Yi{suffix}"


def check_not_none(d: dict, key: str, logger=None, error_msg: str | None = None, should_exit: bool = True):
    """
    Check that a value under `key` in dictionary `d` is not `None`.

    If it is, print an optional `error_msg`.

    Exits with `exit(1)` if `should_exit=True` (which it is by default).
    """
    log = lambda s: logger.error(s) if logger is not None else print(s, file=sys.stderr)

    if d.get(key) is None:
        log(f'Value for key "{key}" was None, when a non-None value was expected.')
        if error_msg is not None:
            log(error_msg)

        if should_exit:
            exit(1)


def get_curr_date_str(include_year: bool = True) -> str:
    if include_year:
        return datetime.today().strftime("%Y-%m-%d-%H-%M-%S")
    else:
        return datetime.today().strftime("%Y-%m-%d-%H-%M-%S")


# Numeric helper functions


def get_curr_year() -> int:
    return date.today().year


def intn(x: Any | None) -> int | None:
    """Applies `int()` to any non-`None` value. Otherwise returns `None`."""
    return None if x is None else int(x)


def floatn(x: Any | None) -> float | None:
    """Applies `float()` to any non-`None` value. Otherwise returns `None`."""
    return None if x is None else float(x)


def strn(x: Any | None) -> str | None:
    """Applies `str()` to any non-`None` value. Otherwise returns `None`."""
    return None if x is None else str(x)


def union_overwrite_none(d1: dict, d2: dict, keys: List[str]) -> dict:
    """
    Modifies in place `d1[k]` with `d2.get(k)` if `d1.get(k) is None`.

    Also returns `d1`. Useful for when `d1` is the literal value `{}`.
    """
    for key in keys:
        d1[key] = d1.get(key, d2.get(key))
    return d1


def get_local_ip_address() -> str:
    import socket

    try:
        return socket.gethostbyname(socket.gethostname())
    except socket.gaierror:
        return socket.gethostbyname("localhost")
