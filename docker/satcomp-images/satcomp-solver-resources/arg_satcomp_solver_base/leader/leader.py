"""
This module runs in the background of the Leader Base Container.
It updates the manifest periodically.
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


class LeaderTimeoutException(Exception):
    pass


class LeaderStatusChecker(threading.Thread):
    """Thread that runs in the background publishing leader READY status & IP address by
    updating manifest every second"""

    leader_poll_sleep_time = 1
    file_operations: FileOperations = FileOperations()

    def __init__(self, node_manifest: DynamodbManifest):
        threading.Thread.__init__(self)
        self.node_manifest = node_manifest
        self.logger = logging.getLogger("LeaderPoller")
        self.logger.setLevel(logging.DEBUG)
        self.setDaemon(True)

    def update_manifest(self, uuid: str, local_ip_address: str, status: str):
        self.logger.info(f"Giving node heartbeat for node {uuid} with ip {local_ip_address}")
        self.node_manifest.register_node(str(uuid), local_ip_address, status, NodeType.LEADER.name)

    # TODO: This should be updated so that the leader emits its status (just like the workers)
    # Perhaps for SAT-Comp 2023
    def run(self):
        local_ip_address = socket.gethostbyname(socket.gethostname())
        node_uuid = uuid.uuid4()
        self.logger.info(f"Registering leader node {node_uuid} with ip {local_ip_address}")
        while True:
            current_timestamp = int(time.time())
            
            self.update_manifest(node_uuid, local_ip_address, "READY")

            self.logger.info("Leader updated status")
            time.sleep(self.leader_poll_sleep_time)
