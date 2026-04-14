"""Global functions for pathing and IO support."""

import os
import sys
from pathlib import Path
from typing import Optional, Tuple, Union
from urllib.parse import urlparse

################################################################################


def normalize_path(path: Union[str, Path, None], relative_to: Union[str, Path, None] = None) -> Optional[Path]:
    """
    Normalizes and resolves a path into a `Path` object.

    For example, `"~/Desktop/folder/.."` gets normalized to `Path("/Users/Desktop")`.

    Environment variables like `$VAR` or `${VAR}` are expanded before resolution.
    For example, `"$SATCOMP_ROOT/examples"` expands to `"/path/to/project/examples"`.

    An optional `relative_to` parameter is used as a current-working directory
    during resolution, in case `path` is a local/relative path.

    If the `relative_to` directory is not `None`, but `path` is an absolute path,
    then `relative_to` has no effect on the returned path.

    If `path is None`, then `None` is returned.
    """
    if path is None:
        return None

    # Convert to string for environment variable expansion
    path_str = str(path)
    path_str = os.path.expandvars(path_str)

    path = Path(path_str)
    path = path.expanduser()

    if relative_to is not None:
        dir = normalize_path(relative_to)
        return (dir / path).resolve()
    else:
        return path.resolve()


# S3 paths cannot start with a leading "/"
def normalize_s3_uri(path: str) -> str:
    return path.lstrip("/")


def normalize_s3_dir(dir: str) -> str:
    dir = dir.lstrip("/")
    if not dir.endswith("/"):
        dir += "/"
    return dir


def path_to_s3_uri(path: Union[str, Path]) -> str:
    if isinstance(path, str):
        if path.startswith("s3://"):
            return path
        else:
            # Note: Be careful when putting `.lstrip()` inside the f-string
            #       Earlier Python versions don't support "" inside an f-string
            #       enclosed by ""
            path = path.lstrip("/")
            return f"s3://{path}"
    else:
        # We assume no drives are specified for Paths
        path = str(path).lstrip("/")
        return f"s3://{path}"


def bucket_and_path_to_s3_uri(bucket: str, path: Union[str, Path]) -> str:
    if isinstance(path, str):
        path = path.lstrip("/")
    else:
        path = str(path).lstrip("/")
    return f"s3://{bucket}/{path}"


def split_s3_uri(s3_uri: str) -> Tuple[str, str]:
    s3_uri = path_to_s3_uri(s3_uri)
    s3_uri_result = urlparse(s3_uri, allow_fragments=False)
    bucket_name = s3_uri_result.netloc
    file_path = s3_uri_result.path.lstrip("/")
    return bucket_name, file_path


def check_path_is_readable_file(
    path: Union[str, Path],
    logger=None,
    error_message: Optional[str] = None,
):
    norm_path: Path = normalize_path(path)
    msg = (lambda s: f"{s}\n{error_message}") if error_message else (lambda s: s)
    log = (lambda s: logger.error(msg(s))) if logger else (lambda s: print(msg(s), file=sys.stderr))

    if not norm_path.exists():
        log(f'Error: Path "{path}" does not exist.')
        exit(1)

    if not norm_path.is_file():
        log(f'Error: Path "{path}" exists, but is not a file.')
        exit(1)

    if not os.access(str(norm_path), os.R_OK):
        log(f'Error: Path "{path}" exists, but is not readable.')
        exit(1)


def check_path_is_dir(
    dir: Union[str, Path],
    logger=None,
    error_message: Optional[str] = None,
):
    norm_dir: Path = normalize_path(dir)
    msg = (lambda s: f"{s}\n{error_message}") if error_message else (lambda s: s)
    log = (lambda s: logger.error(msg(s))) if logger else (lambda s: print(msg(s), file=sys.stderr))

    if not norm_dir.exists():
        log(f'Error: The directory "{dir}" does not exist.')
        exit(1)

    if not norm_dir.is_dir():
        log(f'Error: The path "{dir}" exists and was expected to be a directory, but it wasn\'t.')
