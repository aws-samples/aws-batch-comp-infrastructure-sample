#!/usr/bin/env python3
"""This file is the main entrypoint for the Leader Node Base Container"""
import logging
import os
import socket
import subprocess
import sys
from time import sleep


sys.path.append('/opt/amazon/lib/python3.8/site-packages/')

from arg_satcomp_solver_base.solver.command_line_solver import CommandLineSolver
from arg_satcomp_solver_base.sqs_queue.sqs_queue import SqsQueue
from arg_satcomp_solver_base.poller.poller import Poller
from arg_satcomp_solver_base.node_manifest.dynamodb_manifest import DynamodbManifest
from arg_satcomp_solver_base.task_end_notification.task_end_notifier import TaskEndNotifier
from arg_satcomp_solver_base.leader.leader import LeaderStatusChecker

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
QUEUE_NAME = os.getenv('SQS_QUEUE_NAME')
OUTPUT_QUEUE_NAME = os.getenv('SQS_OUTPUT_QUEUE_NAME')
SATCOMP_BUCKET_NAME = os.getenv('SATCOMP_BUCKET_NAME')

def run_leader(path):
    cmd = os.path.join(path, "leader")
    stdout = os.path.join(path, "leader_stdout.log")
    stderr = os.path.join(path, "leader_stderr.log")
    with open(stdout, "wb") as out, open(stderr, "wb") as err:
        subprocess.Popen(cmd, stdout=out, stderr=err)


if __name__ == "__main__":
    logger = logging.getLogger("Leader Entrypoint")
    logger.setLevel(logging.DEBUG)

    dir = "/competition"
    logger.info("Running leader healthcheck")
    run_leader(dir)  # Run script to save status to leader_node_status.json
    sleep(1)  # Wait for creation of leader_node_status.json file

    logger.info("Getting input queue: %s", QUEUE_NAME)
    sqs_input_queue = SqsQueue.get_sqs_queue(QUEUE_NAME)

    logger.info("Getting output queue: %s", QUEUE_NAME)
    sqs_output_queue = SqsQueue.get_sqs_queue(OUTPUT_QUEUE_NAME)

    logger.info(f"Bucket name: {SATCOMP_BUCKET_NAME}")

    logger.info("Getting task end notifier")
    task_end_notifier = TaskEndNotifier.get_task_end_notifier()

    logger.info("Getting node manifest")
    node_manifest = DynamodbManifest.get_dynamodb_manifest()

    logger.info("Building command line solver to run solver script /competition/solver")

    solver = CommandLineSolver(f"{dir}/solver")

    logger.info("Getting local IP address")
    local_ip_address = socket.gethostbyname(socket.gethostname())

    logger.info("Starting leader status checker")
    leader_status = LeaderStatusChecker(node_manifest)
    leader_status.start()

    logger.info("starting poller")
    poller = Poller(1, local_ip_address, sqs_input_queue, sqs_output_queue, node_manifest, task_end_notifier, solver, SATCOMP_BUCKET_NAME)
    poller.start()
    poller.join()
