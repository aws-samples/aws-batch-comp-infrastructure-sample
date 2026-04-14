"""Shim for the S3 file system."""

import fnmatch
import logging
import os
from enum import Enum
from pathlib import Path
from typing import List, Tuple

import boto3
import common.pathing as pathing
from botocore.exceptions import ClientError
from common import LoggingManager, SolverEnvironment

################################################################################


class S3FileSystemException(Exception):
    """Exception for S3FileSystem errors"""


class LocalS3FileSystem:
    """An 'implementation' of the `boto3.client('s3')` that treats uploading/downloading as local disk copying."""

    def __init__(self):
        pass

    def ls(self, dir: Path | str, recursive: bool = False) -> List[Path | str]:
        """
        Returns the paths of all files in this directory (or recursively under this directory).

        Unlike the `ls` command, the returned paths are absolute, not relative to `dir`.
        The type of the returned paths matches the type of `dir`.
        """
        is_Path = isinstance(dir, Path)
        dir, is_Path = pathing.normalize_path(dir)

        if not recursive:
            return [file if is_Path else str(file) for file in dir.iterdir()]
        else:
            all_files = []
            for root, _, files in dir.walk():
                all_files += [root / file if is_Path else str(root / file) for file in files]
            return all_files

    def download_file(self, bucket_name: Path | str, file_path: Path | str, download_dest: Path | str) -> None:
        """
        'Downloads' a local file to a destination.

        We don't use the `bucket_name`, but we keep it to maintain compatibility with
        boto3 S3 clients.
        """
        # TODO: Fix the bucket name. Path("") != "", == "."
        # bucket_name, _ = self._normalize_path(bucket_name)
        file_path = pathing.normalize_path(file_path)
        download_dest = pathing.normalize_path(download_dest)

        # Short-circuit, in case the source and destination match
        if file_path == download_dest:
            raise S3FileSystemException(f"Source and destination are the same: {file_path}")

        # Check file permissions
        if not os.path.exists(file_path):
            raise S3FileSystemException(f'"S3 file" {file_path} does not exist')

        if not os.access(file_path, os.R_OK):
            raise S3FileSystemException(f'"S3 file" {file_path} exists but is not readable')

        if os.path.isfile(download_dest) and not os.access(download_dest, os.W_OK):
            raise S3FileSystemException(f"Download destination {download_dest} exists but is not writable")

        # Rather than copy the file, which might be large, create a symlink
        download_dest.symlink_to(file_path)

    def upload_file(self, local_file_path: str, bucket_name: str, object_name: str) -> None:
        if not os.path.exists(local_file_path):
            raise S3FileSystemException(f"Local file {local_file_path} does not exist")

        if not os.access(local_file_path, os.R_OK):
            raise S3FileSystemException(f"Local file {local_file_path} exists but is not readable")

        # TODO: Any actual uploading to do here?
        return


class S3FileSystem:
    """Shim for the value of `boto3.client('s3')`.

    Assumes that the provided s3 client implements the functions
    `download_file()` and `upload_file()`.
    """

    class UriStyle(Enum):
        RELATIVE_PATH = 0
        ABSOLUTE_PATH = 1
        FULL_URI = 2

    def __init__(self, s3_client):
        # For the boto3 reference on S3 clients, see:
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html
        self.s3_client = s3_client

        self.is_aws = not isinstance(s3_client, LocalS3FileSystem)
        self.is_local = not self.is_aws

        lm = LoggingManager()
        self.logger = lm.get_logger("S3FileSystem", formatted=self.is_aws)
        self.logger.setLevel(logging.DEBUG)

    def __split_uri(self, s3_uri: str) -> Tuple[str, str]:
        """Splits an S3 URI into a bucket name and file path.

        @param s3_uri: s3 uri that is in the form `s3://bucket_name/path_to_file`
        @rtype: (str, str)
        @returns: A tuple of the bucket name and the file path
        """

        # Only parse a bucket name and S3 file path if we have an actual S3 client
        if self.is_aws:
            return pathing.split_s3_uri(s3_uri)
        else:
            return ("", s3_uri)

    def ls(
        self,
        bucket: str,
        s3_dir: str | Path,
        recursive: bool = False,
        style: UriStyle = UriStyle.RELATIVE_PATH,
    ) -> List[str]:
        """
        Runs `ls` on an S3 directory. By default, returned paths are relative to `s3_dir`.

        For example, if the file tree looks like
        ```
        my_dir/
          + README.md
          + Makefile
          + sub_dir/
            + hello.txt
        ```
        then `ls("my_dir", recursive=True)`
        returns `["README.md", "Makefile", "sub_dir/hello.txt"]`.

        The `s3_dir` is normally treated like a directory. Behavior is
        undefined if `s3_dir` is a path to an exact file.

        However, `s3_dir` may include a glob on the final segment of the path.
        For example, `~/Desktop/*.txt` is allowed, but `~/Des*op/*.txt` is not.
        In the case of a glob on the last path segment, all prior segments
        are treated as the directory, and the glob is used to filter the
        files that are returned via a normal call to `s3.ls()`.

        When the underlying S3 client is AWS, the `s3_dir` cannot be a `Path`.
        """

        # Just call "ls" directly if we are a local file system
        if self.is_local:
            return self.s3_client.ls(s3_dir, recursive)
        elif isinstance(s3_dir, Path):
            raise ValueError("When using `ls` on an S3 directory, the `s3_dir` cannot be a `Path`.")

        if bucket is None or bucket == "":
            raise ValueError("Error: S3 bucket name is empty")

        # Store a glob pattern if the base has a glob character
        base = os.path.basename(s3_dir)
        glob_pat = None
        if "*" in base or "?" in base or "[" in base:
            # Ideally, we would want to store the base as the glob pattern, i.e.
            #   glob_pat = base
            # However, because we aren't using glob, but `fnmatch.filter()`,
            # and the URIs from `ls()` are full paths, we need to either:
            #   (1) make the URIs relative to s3_dir, filter, then prefix s3_dir again
            #   (2) make the glob have a full path
            # We choose option (2) for simplicity and efficiency
            glob_pat = pathing.normalize_s3_uri(s3_dir)
            s3_dir = os.path.dirname(s3_dir)

        s3_dir = pathing.normalize_s3_dir(s3_dir)

        # Loop until all pages of objects have been gone through
        s3_objects = []
        prefixes = [s3_dir]
        seen_prefixes = [s3_dir]
        try:
            while len(prefixes) > 0:
                prefix = prefixes.pop()
                continuation_token: str = ""
                while continuation_token is not None:
                    if continuation_token == "":
                        response = self.s3_client.list_objects_v2(
                            Bucket=bucket,
                            Delimiter="/",
                            Prefix=prefix,
                        )
                    else:
                        response = self.s3_client.list_objects_v2(
                            Bucket=bucket,
                            ContinuationToken=continuation_token,
                            Delimiter="/",
                            Prefix=prefix,
                        )

                    continuation_token = response.get("NextContinuationToken")

                    # Store the URIs for the S3 objects in this directory
                    # By default, they are returned with `ABSOLUTE_PATH` style
                    files = [obj["Key"] for obj in response.get("Contents", [])]

                    # Keep those that match the glob
                    if glob_pat is not None:
                        files = fnmatch.filter(files, glob_pat)

                    # Format the URIs to be relative to `s3_dir`, if requested
                    if style == S3FileSystem.UriStyle.RELATIVE_PATH:
                        files = [os.path.relpath(file, s3_dir) for file in files]
                    elif style == S3FileSystem.UriStyle.FULL_URI:
                        files = [pathing.bucket_and_path_to_s3_uri(bucket, file) for file in files]

                    s3_objects += files

                    # If recursive, add non-seen prefixes to the list
                    if recursive:
                        new_prefixes = response.get("CommonPrefixes", [])
                        for p_obj in new_prefixes:
                            p = p_obj["Prefix"]
                            if p not in seen_prefixes:
                                prefixes.append(p)
                                seen_prefixes.append(p)

        except ClientError as e:
            self.logger.error("Error: Client error when calling `list_objects` for S3")
            self.logger.error("Are you authorized to access this S3 bucket?")
            self.logger.exception(e, exc_info=False)

        return s3_objects

    def ls_uri(
        self,
        s3_uri: str,
        recursive: bool = False,
        style: UriStyle = UriStyle.RELATIVE_PATH,
    ) -> List[str]:
        bucket, s3_dir = self.__split_uri(s3_uri)
        return self.ls(bucket, s3_dir, recursive, style)

    def download_file(self, bucket: str, s3_file_path: str, download_dest_folder: str | Path) -> Path:
        file_name = os.path.basename(s3_file_path)
        download_dest: Path = pathing.normalize_path(download_dest_folder) / file_name
        try:
            self.logger.info(
                "Downloading file %s from bucket %s to destination %s", s3_file_path, bucket, download_dest
            )
            self.s3_client.download_file(bucket, s3_file_path, str(download_dest))
        except ClientError as e:
            self.logger.error("Failed to download file from s3")
            self.logger.exception(e)
            raise S3FileSystemException(
                f"Failed to download file from s3 with download destination {str(download_dest)}"
            )
        return download_dest

    def download_file_uri(self, problem_uri: str, download_dest_folder: str | Path) -> Path:
        """Function to download file based on user-provided url.

        @param problem_uri: s3 uri that is in the form `s3://bucket_name/path_to_file`
        @param download_dest_folder: folder to download the problem to

        :rtype: str
        :returns: The path to the downloaded file
        """

        bucket, s3_file_path = self.__split_uri(problem_uri)
        return self.download_file(bucket, s3_file_path, download_dest_folder)

    def upload_file(self, src: Path | str, bucket: str, object_name: str) -> None:
        try:
            src = str(pathing.normalize_path(src))
            object_name = object_name.lstrip("/")
            self.logger.info("Uploading file %s to bucket %s and file path %s", src, bucket, object_name)
            self.s3_client.upload_file(src, bucket, object_name)
        except ClientError as e:
            self.logger.error("Failed to upload file to s3")
            self.logger.exception(e)
            raise S3FileSystemException(f"Failed to upload file to s3 with upload destination {bucket}/{object_name}")

    def upload_file_uri(self, src: Path | str, s3_uri: str) -> None:
        """Function to upload file to s3 from local filesystem based on user provided path.

        @param src: path to the file to upload.
        @param s3_uri: s3 uri that is in the form of s3://bucket_name/path_to_file for uploading.
        """
        bucket, object_name = self.__split_uri(s3_uri)
        self.upload_file(src, bucket, object_name)

    def upload_directory_tree(
        self, local_dir: Path | str, bucket: str, s3_dir: str, excluding: List[Path] | None = None
    ) -> None:
        """
        Upload all files rooted at `local_dir` to S3, rooted at `s3_dir`.

        For example, if the file tree looks like this:
        ```
        my_dir/
          + README.md
          + Makefile
          + sub_dir/
            + hello.txt
        ```
        and the function call is `upload_directory_tree("my_dir", <bucket>, "upload_dir")`,
        then the uploaded directory looks like the above, except
        the root directory is `upload_dir`, not `my_dir`.
        """

        local_dir = pathing.normalize_path(local_dir)
        excluding = excluding or []

        # Iterates through all files rooted at `local_dir` and uploads them to S3
        # We take the file paths relative to `local_dir` and append them to `s3_dir`
        # `walk()` recursively descends the file tree for us
        excluding_resolved = {p.resolve() if isinstance(p, Path) else Path(p).resolve() for p in excluding}
        for root, _, files in local_dir.walk():
            for file in files:
                f_full = pathing.normalize_path(root / file)

                if f_full.resolve() in excluding_resolved:
                    self.logger.info(f"Excluding {f_full} from upload")
                    continue

                f = f_full.relative_to(local_dir)

                s3_obj_name = os.path.join(s3_dir, str(f))
                self.upload_file(f_full, bucket, s3_obj_name)

    def upload_directory_tree_uri(self, local_dir: Path | str, s3_uri: str, excluding: List[Path] | None = None):
        bucket, object_base_name = self.__split_uri(s3_uri)
        self.upload_directory_tree(local_dir, bucket, object_base_name, excluding)

    @staticmethod
    def get_s3_file_system():
        s3 = boto3.client("s3")
        return S3FileSystem(s3)

    @staticmethod
    def get_s3_file_system_from_session(session: boto3.Session):
        s3 = session.client("s3")
        return S3FileSystem(s3)

    @staticmethod
    def get_local_s3_file_system():
        local_s3 = LocalS3FileSystem()
        return S3FileSystem(local_s3)

    @staticmethod
    def get_s3_file_system_from_env(senv: SolverEnvironment) -> "S3FileSystem":
        if senv.is_local:
            return S3FileSystem.get_local_s3_file_system()
        else:
            return S3FileSystem.get_s3_file_system()

    @staticmethod
    def get_results_bucket_from_env(senv: SolverEnvironment) -> str:
        if senv.is_local:
            return "/tmp/results/"
        else:
            rn = senv.to_resource_namer()
            return rn.get_bucket_name()
