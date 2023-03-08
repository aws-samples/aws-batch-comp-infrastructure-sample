"""General utils package"""
import json
import logging
import os
import shutil
import uuid
from datetime import datetime

import pytz


class TimeProvider:

    def get_current_time(self):
        return datetime.now(pytz.utc)


class FileOperations:
    def __init__(self):
        self.logger = logging.getLogger("FileOperations")

    def save_to_file(self, path: str, body: str):
        """Save a string to a file
        Raises OSError if unable to open
        """
        with open(path, "w", encoding="UTF-8") as file_handle:
            file_handle.write(body)

    def create_directory(self, task_uuid: str):
        return self.create_custom_directory("/tmp/", task_uuid)

    def create_custom_directory(self, directory_name, task_uuid: str):
        request_directory_path = os.path.join(directory_name, task_uuid)
        os.mkdir(request_directory_path)
        return request_directory_path

    def read_json_file(self, path: str):
        with open(path) as solver_out_handle:
            return json.loads(solver_out_handle.read())

    def write_json_file(self, path: str, item: dict):
        return self.save_to_file(path, json.dumps(item))

    def read_log_file(self, file_path, max_file_length=None):
        try:
            with open(file_path, 'rb') as f:
                if max_file_length is not None:
                    return f.read(max_file_length).decode("UTF-8")
                return f.read().decode("UTF-8")
        except FileNotFoundError as e:
            self.logger.error("Could not open log file %s", file_path)
            self.logger.exception(e)
            return None

    def generate_uuid(self):
        return str(uuid.uuid4())

    def remove_directory(self, path: str):
        if os.path.exists(path):
            shutil.rmtree(path)
