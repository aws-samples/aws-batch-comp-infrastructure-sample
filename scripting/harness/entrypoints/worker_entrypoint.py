from time import sleep

from common import LoggingManager
from common.solver_env import SolverEnvironment
from common.subprocess_shim import SubprocessShim
from dist_consts import DistributedConsts as DConsts
from dynamo_node_objects import (
    IpItem,
    NodeStatus,
    TimestampItem,
)
from harness.aws_shim import DynamoTable
from heartbeat import HeartbeatThread
from solver_cmd import get_cleanup_command

################################################################################

lm = LoggingManager()
logger = lm.get_logger("Worker entrypoint")


def ensure_registered(ip: IpItem, ip_table: DynamoTable, ts: TimestampItem, timestamp_table: DynamoTable):
    """Re-register this worker if its IP entry was deleted from DynamoDB.

    This can happen when clean_up_crashed_nodes deletes our IP entry because
    our heartbeat timestamp expired — e.g., due to a transient credential
    failure. The worker process is still alive, but it's become invisible to
    the leader's get_unclaimed_workers() scan. Without re-registration, the
    leader sees 0 available workers and the workers wait forever to be claimed,
    creating a permanent deadlock.

    If re-registration fails (credentials still dead), we exit so ECS can
    restart the worker with fresh credentials.
    """
    entry = ip_table.get_item(Key=ip.uuid)
    if entry is None:
        logger.info("My IP entry was deleted from DynamoDB — re-registering")
        try:
            ip.write_to(ip_table)
            ts.set_time()
            ts.write_to(timestamp_table)
            logger.info("Re-registration successful")
        except Exception as e:
            logger.error(f"Failed to re-register: {type(e).__name__}: {e}. Exiting so ECS can restart.")
            exit(1)


def get_leader(ip: IpItem, ip_table: DynamoTable, timestamp_table: DynamoTable, ts: TimestampItem) -> TimestampItem:
    old_leader = None
    while True:
        # Sleep until we are assigned a (new) leader
        ensure_registered(ip, ip_table, ts, timestamp_table)
        ip.read_from(ip_table)
        while ip.led_by.value == ip.UNOWNED_UUID or ip.led_by.value == old_leader:
            logger.info("My IP node has not been claimed yet, waiting for a bit before checking again")
            sleep(DConsts.LED_BY_SLEEP_INTERVAL)
            ensure_registered(ip, ip_table, ts, timestamp_table)
            ip.read_from(ip_table)

        logger.info(f"Provisionally assigned leader with id {ip.led_by.value}")

        # We have a leader - check that the leader is alive and well
        try:
            ts = TimestampItem(ip.led_by.value)
            ts.read_from(timestamp_table, raise_not_exists_error=True)
            ts.check_is_alive()
            logger.info(f"Now led by node with id {ip.led_by.value}")
            return ts
        except Exception as e:
            if isinstance(e, ValueError):
                logger.info("Leader is not in the timestamp table")
            else:
                logger.info("Leader is not alive, or there was some other error")

            logger.info(f"My leader {ip.led_by.value} was dead, waiting for a fresh leader")
            old_leader = ip.led_by.value


def clean_up():
    subproc_shim = SubprocessShim(logger, stdout_path=None, stderr_path=None)
    cmd = get_cleanup_command()
    subproc_out = subproc_shim.run(cmd, timeout_secs=DConsts.CLEANUP_TIMEOUT_SECS)

    # Wait for the remaining allotted cleanup time, so the leader can swap back to "READY"
    sleep(max(0, DConsts.CLEANUP_TIMEOUT_SECS - subproc_out.elapsed_time))


def wait_for_cleanup_signal(ts: TimestampItem, table: DynamoTable):
    logger.info(f"Now polling for CLEANUP signal from leader with id {ts.uuid.value}")

    # Poll the database until the status is CLEANING, or until the leader is dead
    try:
        ts.read_from(table, raise_not_exists_error=True)
        while NodeStatus.from_val(ts.status.value) != NodeStatus.CLEANING:
            ts.check_is_alive()
            sleep(DConsts.CLEAN_SLEEP_INTERVAL)
            ts.read_from(table, raise_not_exists_error=True)
    except Exception:
        logger.info("Leader is dead, cleaning up immediately")
        return


def run(senv: SolverEnvironment):
    logger.info("Started worker entrypoint")
    assert senv.is_distributed

    ip_table, timestamp_table = DynamoTable.get_tables_from_env(senv)

    # When we wake up, register ourselves in the IP table
    ip = IpItem(is_leader=False)
    ip.write_to(ip_table)

    # Start up a heartbeat thread to tell the leader we're alive
    # This thread runs forever, and we never wait on it
    ts = TimestampItem(ip.uuid.value)
    hb = HeartbeatThread(timestamp_table, ts)
    hb.start()

    # The distributed protocol for coordinating leaders and workers is complicated
    # Read the documentation at `docs/design`
    # Basically, workers are dumb: they see who their current leader is,
    # and if the leader ever says to clean up, the worker invokes the cleanup command
    while True:
        logger.info("Getting a leader")
        leader_ts = get_leader(ip, ip_table, timestamp_table, ts)

        logger.info("Waiting for cleanup signal")
        wait_for_cleanup_signal(leader_ts, timestamp_table)

        logger.info("Cleaning up")
        clean_up()
