"""
This module runs in the background of the Worker Base Container.
It will read worker node status from saved json file and updated manifest.
"""
import json
import logging
import os
import socket
import threading
import uuid
import time

from arg_satcomp_solver_base.node_manifest.dynamodb_manifest import DynamodbManifest, NodeType
from arg_satcomp_solver_base.utils import FileOperations


class WorkerTimeoutException(Exception):
    pass


class WorkerStatusChecker(threading.Thread):
    """Thread that runs in the background trying to get status of worker and
    updates manifest every second. Throws an exception if status is not updated for given expiration time"""

    worker_poll_sleep_time = 1
    file_operations: FileOperations = FileOperations()

    def __init__(self, node_manifest: DynamodbManifest, expiration_time: str, path: str):
        threading.Thread.__init__(self)
        self.node_manifest = node_manifest
        self.logger = logging.getLogger("WorkerPoller")
        self.logger.setLevel(logging.DEBUG)
        self.expiration_time = expiration_time
        self.path = path

    def get_worker_info(self):
        input = os.path.join(self.path, "worker_node_status.json")
        return self.file_operations.read_json_file(input)

    def update_manifest(self, uuid: str, local_ip_address: str, status: str):
        self.logger.info(f"Giving node heartbeat for node {uuid} with ip {local_ip_address}")
        self.node_manifest.register_node(str(uuid), local_ip_address, status, NodeType.WORKER.name)

    def run(self):
        local_ip_address = socket.gethostbyname(socket.gethostname())
        node_uuid = uuid.uuid4()
        self.logger.info(f"Registering node {node_uuid} with ip {local_ip_address}")
        while True:
            try:
                current_timestamp = int(time.time())
                self.logger.info("Trying to get worker node status")
                worker_status_info = self.get_worker_info()

                status = worker_status_info.get("status")
                self.logger.info(f"Worker status is {status}")

                worker_timestamp = worker_status_info.get("timestamp")
                self.logger.info(f"Worker status updated time:  {worker_timestamp}")

                if worker_timestamp < current_timestamp - self.expiration_time:
                    raise WorkerTimeoutException("Timed out waiting for worker node status to update")

                self.update_manifest(node_uuid, local_ip_address, status)

                self.logger.info("#######################")
                time.sleep(self.worker_poll_sleep_time)

            except FileNotFoundError:
                self.logger.error("worker_node_status file is not generated")
            except json.JSONDecodeError as e:
                self.logger.error("Worker status file is not valid Json")
                self.logger.exception(e)
