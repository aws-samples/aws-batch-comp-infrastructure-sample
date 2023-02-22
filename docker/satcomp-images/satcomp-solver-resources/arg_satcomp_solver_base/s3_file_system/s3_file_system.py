"""Implementation of classes for interacting with S3"""
import logging
import ntpath
import os
from urllib.parse import urlparse

from botocore.exceptions import ClientError


class S3FileSystemException(Exception):
    """Exception for S3FileSystem errors"""


class S3FileSystem:
    """Class to represent an S3 storage"""

    def __init__(self, s3_client):
        self.s3_client = s3_client
        self.logger = logging.getLogger("S3FileSystem")

    def download_file(self, problem_uri: str, download_dest_folder: str):
        """
        Function to download file based on user provided url
        @param download_dest_folder: folder to download the problem to
        @type problem_uri: s3 uri that is in the form of s3://bucket_name/path_to_file
        """
        if problem_uri is None:
            raise S3FileSystemException('s3 uri is empty')

        problem_uri = urlparse(problem_uri, allow_fragments=False)
        bucket_name = problem_uri.netloc
        file_path = problem_uri.path.lstrip('/')

        # Get the file name
        file_name = ntpath.basename(file_path)
        download_dest = os.path.join(download_dest_folder, file_name)

        try:
            self.logger.debug('Downloading file %s from bucket %s to destination %s', file_path, bucket_name, download_dest)
            self.s3_client.download_file(bucket_name, file_path, download_dest)
        except ClientError as e:
            self.logger.error("Failed to download file from s3")
            self.logger.exception(e)
            raise S3FileSystemException(f"Failed to download file from s3 with download destination {download_dest}")

        return download_dest

    @staticmethod
    def get_s3_file_system():
        import boto3
        s3 = boto3.client('s3')
        return S3FileSystem(s3)
