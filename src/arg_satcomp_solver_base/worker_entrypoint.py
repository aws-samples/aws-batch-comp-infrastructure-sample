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

logging.getLogger("botocore").setLevel(logging.CRITICAL)
logging.getLogger("boto3").setLevel(logging.CRITICAL)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)


def run_worker(path):
    cmd = os.path.join(path, "worker")
    stdout = os.path.join(path, "worker_stdout.log")
    stderr = os.path.join(path, "worker_stderr.log")
    with open(stdout, "wb") as out, open(stderr, "wb") as err:
        subprocess.Popen(cmd, stdout=out, stderr=err)


if __name__ == "__main__":
    logger = logging.getLogger("Worker Entrypoint")
    dir = "/competition"

    logger.info("Running worker script from participant")
    run_worker(dir)  # Run script to save status to work_node_status.json
    sleep(1)  # Wait for creation of work_node_status.json file
 
    logger.info("Getting node manifest")
    node_manifest = DynamodbManifest.get_dynamodb_manifest()

    logger.info("Starting worker status checker")
    worker_status = WorkerStatusChecker(node_manifest, 5, dir)
    worker_status.start()

    task_end_notification_poller = TaskEndNotificationPoller.get_task_end_notification_poller()
    task_end_notification_poller.start()

