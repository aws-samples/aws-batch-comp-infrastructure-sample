"""
A thread that loops around `update_item()` to continually write timestamps to a database.

According to the boto3 documentation, boto3 clients are generally thread-safe,
but are not necessarily multi-process-safe. Thus, we implement this with a
`threading.Thread` object and not a subprocess.

For more, see:
https://boto3.amazonaws.com/v1/documentation/api/latest/guide/clients.html#multithreading-or-multiprocessing-with-clients
"""

from threading import Lock, Thread
from time import sleep
from typing import Optional

from common.solver_logging import LoggingManager
from dist_consts import DistributedConsts as DConsts
from dynamo_node_objects import NodeStatus, TimestampItem
from harness.aws_shim import DynamoTable

################################################################################

lm = LoggingManager()
logger = lm.get_logger("Heartbeat")


class HeartbeatThread(Thread):
    def __init__(
        self,
        table: DynamoTable,
        ts: TimestampItem,
        interval: int | float = DConsts.HEARTBEAT_SLEEP_INTERVAL,
        lock: Optional[Lock] = None,
    ):
        """
        Initialize a new heartbeat thread, potentially with a `lock` to avoid race conditions.

        The thread `sleep()`s by an `interval` number of seconds between heartbeats.

        In the context of our harness's distributed solver protocol (as of August 2025):
        Worker nodes don't need to provide a lock, but leader do.
        This is because leaders will, by default, broadcast a READY `NodeStatus`,
        but when the leader finishes a job, it broadcasts `CLEANING` for a fixed
        number of seconds. (See `dist_consts.py`.) This modification is performed
        in the main thread, so to prevent the heartbeat thread from overwriting
        the value of the `NodeStatus`, the lock is used to serialize those edits.
        """

        Thread.__init__(self)
        self.table = table
        self.ts = ts
        self.interval = interval
        self.lock = lock
        self.stop_broadcasting_cleaning = None
        self.daemon = True  # If the main thread crashes, crash this thread, too

    def acquire(self):
        if self.lock is not None:
            self.lock.acquire()

    def release(self):
        if self.lock is not None:
            self.lock.release()

    def broadcast_cleaning(self, secs: int | float = DConsts.CLEANUP_TIMEOUT_SECS):
        stop_time = self.ts.get_curr_time() + secs
        logger.info(f"Broadcasting cleaning from {self.ts.get_curr_time()} to {stop_time}")

        self.acquire()
        self.stop_broadcasting_cleaning = stop_time
        self.ts.set_status(NodeStatus.CLEANING)
        self.ts.write_to(self.table)
        self.release()

    def beat(self):
        t = self.ts.get_curr_time()
        self.acquire()
        self.ts.set_time()
        if self.stop_broadcasting_cleaning is not None:
            if t >= self.stop_broadcasting_cleaning:
                self.ts.set_status(NodeStatus.READY)
                self.stop_broadcasting_cleaning = None
            else:
                self.ts.set_status(NodeStatus.CLEANING)
        self.ts.write_to(self.table)
        self.release()

    def run(self):
        while True:
            self.beat()
            sleep(self.interval)
