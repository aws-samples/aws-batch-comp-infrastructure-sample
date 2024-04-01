#!/usr/bin/env python3
"""This file is the main entrypoint for the Worker Node Base Container"""
import logging
import os
import subprocess
import sys
from time import sleep

sys.path.append('/opt/amazon/lib/python3.8/site-packages/')

from arg_satcomp_solver_base.node_manifest.dynamodb_manifest import DynamodbManifest
from arg_satcomp_solver_base.worker.worker import WorkerStatusChecker
from arg_satcomp_solver_base.task_end_notification.task_end_notification_poller import TaskEndNotificationPoller
from arg_satcomp_solver_base.utils import FileOperations

logging.getLogger("botocore").setLevel(logging.CRITICAL)
logging.getLogger("boto3").setLevel(logging.CRITICAL)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)

class PollerTimeoutException(Exception):
    pass

def run_worker(path):
    cmd = os.path.join(path, "worker")
    stdout = os.path.join(path, "worker_stdout.log")
    stderr = os.path.join(path, "worker_stderr.log")
    with open(stdout, "wb") as out, open(stderr, "wb") as err:
        subprocess.Popen(cmd, stdout=out, stderr=err)

def write_leader_node_json(leader_nodes, dir): 
    file_operations: FileOperations = FileOperations()
    output = os.path.join(dir, "leader_node_status.json")
    
    ## write most recently reporting leader
    leader_nodes.sort(key = lambda a: a['lastModified'], reverse=True)
    node_to_write = leader_nodes[0]

    ## get rid of decimal; incompatible with json writer
    node_to_write['lastModified'] = int(node_to_write['lastModified'])
    return file_operations.write_json_file(output, node_to_write)
    

## Small hack to support getting leader IP node by workers.
## Waits up to 10 minutes.
def get_current_leader_nodes(node_manifest, logger):
    poll_sleep_time = 1
    poll_timeout = 600
    leader_nodes = []
    wait_time = 0
    logger.info(f"Waiting for 1 leader node")
    while True:
        leader_nodes = node_manifest.get_all_ready_leader_nodes()
        if len(leader_nodes) >= 1:
            break
        sleep(poll_sleep_time)
        wait_time += poll_sleep_time
        if wait_time > poll_timeout:
            raise PollerTimeoutException("Timed out waiting for leader to report. "
                                            "Zero leaders reported")

    logger.info(f"Leaders reported: {leader_nodes}")
    return leader_nodes


if __name__ == "__main__":
    logger = logging.getLogger("Worker Entrypoint")
    dir = "/competition"

    logger.info("Getting node manifest")
    node_manifest = DynamodbManifest.get_dynamodb_manifest()

    logger.info("Writing leader IP to json file")
    leaders = get_current_leader_nodes(node_manifest, logger)
    write_leader_node_json(leaders, dir)

    logger.info("Running worker script from participant")
    run_worker(dir)  # Run script to save status to work_node_status.json
    sleep(1)  # Wait for creation of work_node_status.json file
 
 
    logger.info("Starting worker status checker")
    worker_status = WorkerStatusChecker(node_manifest, 5, dir)
    worker_status.start()

    task_end_notification_poller = TaskEndNotificationPoller.get_task_end_notification_poller()
    task_end_notification_poller.start()

