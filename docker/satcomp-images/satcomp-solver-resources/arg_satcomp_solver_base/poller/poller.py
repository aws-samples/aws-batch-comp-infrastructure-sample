"""
This module is a Poller which will run in the background of the satcomp Base Container.
It will poll an SQS queue looking for problems to solve and send them to solver implementations.
"""
import json
import logging
import threading
from enum import Enum
from json import JSONDecodeError
from time import sleep
import os

from arg_satcomp_solver_base.node_manifest.dynamodb_manifest import DynamodbManifest
from arg_satcomp_solver_base.s3_file_system.s3_file_system import S3FileSystem, S3FileSystemException
from arg_satcomp_solver_base.solver.command_line_solver import Solver, SolverException
from arg_satcomp_solver_base.sqs_queue.sqs_queue import SqsQueue, SqsQueueException
from arg_satcomp_solver_base.task_end_notification.task_end_notifier import TaskEndNotifier
from arg_satcomp_solver_base.utils import FileOperations

MOUNT_POINT = '/tmp'


class PollerStatus(Enum):
    HEALTHY = "HEALTHY"


class PollerTimeoutException(Exception):
    pass


class Poller(threading.Thread):
    """Thread that runs in the background trying to pull work off of an SQS
    queue and submitting that work to a solver"""
    worker_poll_timeout = 120
    worker_poll_sleep_time = 5
    queue: SqsQueue
    output_queue: SqsQueue
    node_manifest: DynamodbManifest
    solver: Solver
    thread_id: int
    ip_address: str
    file_operations: FileOperations = FileOperations()
    health_status: PollerStatus
    s3_file_system: S3FileSystem = S3FileSystem.get_s3_file_system()
    s3_bucket: str
    task_end_notifier: TaskEndNotifier

    def __init__(self, thread_id: int,
                 ip_address: str,
                 queue: SqsQueue,
                 output_queue: SqsQueue,
                 node_manifest: DynamodbManifest,
                 task_end_notifier: TaskEndNotifier,
                 solver: Solver, 
                 s3_bucket: str):
        threading.Thread.__init__(self)
        self.queue = queue
        self.output_queue = output_queue
        self.node_manifest = node_manifest
        self.task_end_notifier = task_end_notifier
        self.solver = solver
        self.thread_id = thread_id
        self.ip_address = ip_address
        self.logger = logging.getLogger("Poller")
        self.logger.setLevel(logging.DEBUG)
        self.health_status = PollerStatus.HEALTHY
        self.s3_bucket = s3_bucket

    def _is_valid_solver_request(self, solver_request):
        # TODO improve message validation
        # Expected message structure:
        """{
            "formula" : {
                "value" : <s3 url>,
                "language": "SMTLIB2" | "DIMACS",
            },
            "solverConfig" : {
                "solverName" : "",
                "solverOptions" : [],
                "taskTimeoutSeconds" : 5
            },
            "num_workers": 0
        }"""
        """ {
            "formula": {
                "value": "s3://834251193136-us-east-1-my-project/test.cnf",
                "language": ""
            },
            "solverConfig": {
                "solverName": "",
                "solverOptions": [],
                "taskTimeoutSeconds": 10
            },
            "num_workers": 0
        }
        """
        if solver_request is None:
            return False
        if "formula" not in solver_request:
            return False
        if "language" not in solver_request["formula"]:
            return False
        if "value" not in solver_request["formula"]:
            return False
        if "solverConfig" not in solver_request:
            return False
        if "solverName" not in solver_request["solverConfig"]:
            return False
        if "solverOptions" not in solver_request["solverConfig"]:
            return False
        if "taskTimeoutSeconds" not in solver_request["solverConfig"]:
            return False
        if "num_workers" not in solver_request:
            return False
        return True

    def run(self):
        # TODO: In the future we should make this more testable by separating the while loop
        #  from the thread code itself
        # TODO: How do we want to handle client errors/internal server errors
        while True:
            # TODO: For now we are only handling problems that will fit in SQS message.
            #  In the future this will have to change
            leader_working_directory = None
            efs_shared_directory = None
            try:
                self.logger.info("Trying to get messages from queue: %s", self.queue.queue_name)
                message = self.queue.get_message()
                if message is None:
                    continue 
                
                msg_json = json.loads(message.read())
                message_handle = message.msg.receipt_handle
                self.logger.info("Got problem to solve from message with receipt handle: %s", message_handle)

                message.delete()
                self.logger.info("Deleted message from queue")

                if not self._is_valid_solver_request(msg_json):
                    self.logger.error(f"Message {message.read()} is invalid.  Skipping processing.")
                    continue
                
                s3_uri = msg_json.get("formula").get("value")
                timeout = msg_json.get("solverConfig").get("taskTimeoutSeconds")
                formula_language = msg_json.get("formula").get("language")
                solver_options = msg_json.get("solverConfig").get("solverOptions")
                num_workers = msg_json.get("num_workers", 0)

                self.logger.info("Waiting for worker nodes to come up")
                self.logger.info(f"Task requests {num_workers} worker nodes")
                workers = self.wait_for_worker_nodes(num_workers)
                workers.append({"nodeIp": self.ip_address})

                task_uuid = self.file_operations.generate_uuid()
                efs_uuid_directory = self.file_operations.create_custom_directory(MOUNT_POINT, task_uuid)
                self.logger.info("Created uuid directory in local container %s", efs_uuid_directory)
                download_location = self.s3_file_system.download_file(s3_uri, efs_uuid_directory)
                self.logger.info("Download problem to location: %s", download_location)
                
                solver_response = self.solver.solve(download_location, efs_uuid_directory, workers, task_uuid, timeout, formula_language, solver_options)
                solver_response["driver"]["s3_uri"] = s3_uri
                self.logger.info("Solver response:")
                self.logger.info(solver_response)

                self.logger.info("Writing response to output queue")
                self.output_queue.put_message(json.dumps(solver_response))
                
                self.logger.info(f"Writing all files in request directory path: {efs_uuid_directory} to S3 bucket: {self.s3_bucket}")
                s3_uri = "s3://" + self.s3_bucket + efs_uuid_directory
                self.logger.info(f"S3 URI is: {s3_uri} and S3 bucket is: {self.s3_bucket}")
                self.s3_file_system.upload_directory_tree(efs_uuid_directory, s3_uri)

                self.logger.info(
                    "Cleaning up solver output directory %s",
                    solver_response["solver"].get("request_directory_path")
                )
                self.file_operations.remove_directory(solver_response["solver"].get("request_directory_path"))



                self.logger.info("Cleaning up uuid directory: %s", efs_uuid_directory)
                self.file_operations.remove_directory(efs_uuid_directory)

                self.logger.info("Sending notification that solving is complete")
                self.task_end_notifier.notify_task_end(self.ip_address)

            except SolverException as e:
                self.logger.error("Failed to run solver on message with receipt handle %s", message.msg.receipt_handle)
                self.logger.exception(e)
            except SqsQueueException as e:
                self.logger.error("Failed to read from SQS queue: %s", self.queue.queue_name)
                self.logger.exception(e)
            except JSONDecodeError as e:
                self.logger.error("Failed to run solver on message with receipt handle %s", message.msg.receipt_handle)
                self.logger.error("Message is not valid Json: %s", message.read())
                self.logger.exception(e)
            except S3FileSystemException as e:
                self.logger.error("Failed to download file from s3")
                self.logger.exception(e)


    def wait_for_worker_nodes(self, num_workers):
        worker_nodes = []
        wait_time = 0
        self.logger.info(f"Waiting for {num_workers} worker nodes")
        while len(worker_nodes) < num_workers:
            worker_nodes = self.node_manifest.get_all_ready_worker_nodes()
            sleep(self.worker_poll_sleep_time)
            wait_time += self.worker_poll_sleep_time
            if wait_time > self.worker_poll_timeout:
                raise PollerTimeoutException(f"Timed out waiting for {num_workers} to report. "
                                             f"Only {len(worker_nodes)} reported")
        self.logger.info(f"Workers reported: {worker_nodes}")
        return worker_nodes
