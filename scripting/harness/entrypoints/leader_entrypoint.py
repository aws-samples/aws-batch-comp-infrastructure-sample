"""
Entrypoint script to send problem instances to the leader solver.

First thing called after setting up the SSH daemon upon running the Docker container.

Note: The imports below assume that this script is being called inside the Docker container,
      modeled after the satcomp-infrastructure:common.
"""

import glob
import os
import shutil
import uuid
from logging import Logger
from pathlib import Path
from threading import Lock
from time import sleep
from typing import List, Optional

import common.misc as misc
import common.pathing as pathing
from common import LoggingManager, SolverEnvironment, SubprocessShim
from common.constants import COMPRESSION_EXTENSIONS, SQS_MAX_WAIT_TIME_SECS
from common.solver_io import CompetitionQueueOutput, SolverInput, SolverOutput, SolverQueueInput, SolverResultCode
from dist_consts import DistributedConsts as DConsts
from dynamo_node_objects import (
    IpItem,
    TimestampItem,
)
from harness.aws_shim import DynamoTable, S3FileSystem, SqsQueue
from harness.entrypoints.solver_cmd import get_cleanup_command, get_run_command, get_solver_result
from heartbeat import HeartbeatThread
from utils import SolverRequester

################################################################################

lm = LoggingManager()
logger = lm.get_logger("Leader Entrypoint")

# Currently-supported compression extensions (imported from constants)
COMPRESSION_EXTS = COMPRESSION_EXTENSIONS

################################################################################


def make_work_dir(solver_name: str, is_distributed: bool) -> Path:
    """
    Makes a working directory at `/tmp/{year}-{solver_type}-{mode}-{solver}`.

    The returned `Path` is an absolute path to the newly-created directory.
    Does nothing if the directory already exists.

    We create the directory at this location to reflect the URI of the files
    uploaded to S3 at the end of a solving run.
    """
    year = misc.get_curr_year()
    solver_mode = "dist" if is_distributed else "parallel"
    work_dir = Path("/tmp") / f"{year}-{solver_mode}-{solver_name}"
    logger.info(f"Working directory for leader: {work_dir}")
    work_dir.mkdir(mode=0o755, exist_ok=True)
    return work_dir


def make_run_dir(work_dir: Path, formula_uri: str) -> Path:
    """
    Makes a run directory at `<work_dir>/{formula}/{time}-{UUID}`.

    Since the work directory is indexed by solver, the super-directory on
    S3 will also be indexed by solver. So we index by formula here.
    """

    # Construct a truncated name for the formula by discarding extensions
    formula = os.path.basename(formula_uri)
    if os.path.splitext(formula)[1] in COMPRESSION_EXTS:
        formula = os.path.splitext(formula)[0]
    formula = os.path.splitext(formula)[0]  # Discards ".cnf"/".smtlib2"

    timestamp = misc.get_curr_date_str(include_year=False)
    run_dir = work_dir / formula / f"{timestamp}-{uuid.uuid4()}"
    logger.info(f"Run directory for leader: {run_dir}")
    run_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
    return run_dir


def get_run_dir_to_remove(run_dir: Path) -> Path:
    return run_dir.parent


def add_local_jobs_to_queue(senv: SolverEnvironment, queue: SqsQueue):
    """
    Adds jobs to the local queue. Should only be called when testing locally.

    For each file in `senv.local_test_files` (which can be a glob),
    add it as a job to the provided queue.
    """
    if not senv.is_local:
        return

    requester = SolverRequester.from_env(senv)
    local_test_files = pathing.normalize_path(senv.local_test_files)

    # Glob for files
    files = glob.glob(str(local_test_files), recursive=True)
    for f in files:
        logger.debug(f"Adding file to queue: {str(f)}")
        input_json_str = requester.make_request_json(str(f))
        queue.send_message(input_json_str)


def download_formula(s3: S3FileSystem, formula_url: str, dir: Path) -> Path:
    """
    Downloads a formula to `dir` and returns its `Path`.

    If the formula has an extension indicating it is a compressed file,
    (one of ".bz2", ".xz", ),
    then this function decompresses it to a new file without the extension
    and then deletes the compressed file.
    """
    formula_path = s3.download_file_uri(formula_url, dir)
    logger.info(f"Download successful to {str(formula_path)}")

    # Uncompress the file, if it matches a valid file extension
    suffix = formula_path.suffix
    if suffix in COMPRESSION_EXTS:
        new_formula_path = formula_path.parent / formula_path.stem

        # Lazily import functionality for the specific compression type
        # TODO: Handle broader classes of compression
        # Note: tarfile.is_tarfile() returns 'False' for ".xz" files
        if suffix == ".bz2":
            from bz2 import BZ2File

            f = BZ2File(formula_path, "rb")
        elif suffix == ".xz":
            from lzma import LZMAFile

            f = LZMAFile(formula_path, "rb")

        # Decompress the file over, 100KB at a time
        with open(new_formula_path, "wb") as new_f:
            for data in iter(lambda: f.read(100 * 1024), b""):
                new_f.write(data)

        # Remove the compressed file, since we won't need it anymore
        f.close()
        os.remove(formula_path)
        formula_path = new_formula_path
    return formula_path


def clean_up_crashed_nodes(
    ip_table: DynamoTable,
    timestamp_table: DynamoTable,
):
    deleted_ts = TimestampItem.delete_expired_items(timestamp_table)
    deleted_uuids = [t.uuid for t in deleted_ts]
    deleted_uuid_strs = [str(t.uuid.value) for t in deleted_ts]

    if len(deleted_uuids) == 0:
        logger.info("No crashed/dead nodes to clean up")
        return

    logger.info(f"Deleting the following crashed nodes from the tables: {deleted_uuid_strs}")
    IpItem.batch_delete_item(ip_table, deleted_uuids)

    # In addition to deleting the IP entries for expired nodes,
    # we also need to unclaim any (alive) workers if their leader has crashed.
    # (This happens if the leader crashes, but none of the workers do.)
    all_leaders = IpItem.scan(ip_table, is_leader=True)
    dead_leaders = filter(lambda x: x.uuid.value in deleted_uuid_strs, all_leaders)
    for leader in dead_leaders:
        logger.info(f"Unclaiming workers for dead leader {leader.uuid.value}")
        leader.unclaim_workers(ip_table)


def claim_workers(
    ip_table: DynamoTable,
    timestamp_table: DynamoTable,
    ip: IpItem | None,
    num_workers: int,
) -> List[str]:
    """Claims workers and checks that they're healthy."""
    if ip is None or num_workers == 0:
        return []

    clean_up_crashed_nodes(ip_table, timestamp_table)

    # Scan for any worker nodes that we have already claimed
    workers = IpItem.scan(ip_table, is_leader=False, led_by=ip.uuid.value)
    logger.info(f"Found {len(workers)} workers already claimed by me (out of {num_workers} needed workers)")

    # If we don't have enough workers, claim some extras until we hit our quota
    if len(workers) < num_workers:
        logger.info("We don't have enough workers. Claiming more...")
        num_left_to_claim = num_workers - len(workers)
        newly_claimed = ip.claim_workers(ip_table, num_left_to_claim)
        workers.extend(newly_claimed)

    assert len(workers) == num_workers

    # Now that we've claimed workers, check that their heartbeats are active
    logger.info(f"Claimed the following {len(workers)} workers: {workers}.")
    logger.info("Checking that all workers are healthy")
    curr_time = TimestampItem.get_curr_time()
    worker_uuids = [w.uuid for w in workers]
    tss = TimestampItem.batch_get(timestamp_table, worker_uuids)
    for t in tss:
        if not t.is_alive(time=curr_time):
            logger.info(f"Worker with ID {t.uuid.value} is dead, cleaning up...")
            claim_workers(ip_table, timestamp_table, ip, num_workers)

    return [w.ip_address.value for w in workers]


def clean_up_self(logger: Logger, run_dir: Path) -> None:
    cleanup_stdout_path = run_dir / "cleanup_stdout.txt"
    cleanup_stderr_path = run_dir / "cleanup_stderr.txt"
    cleanup_subproc = SubprocessShim(logger, cleanup_stdout_path, cleanup_stderr_path)
    cleanup_cmd = get_cleanup_command()
    clean_out = cleanup_subproc.run(cleanup_cmd, timeout_secs=DConsts.CLEANUP_TIMEOUT_SECS)
    if clean_out.return_code != 0:
        logger.info(f"Cleanup script returned with code {clean_out.return_code}")
        logger.info(f"Examine cleanup_stdout/stderr.txt for more information")
    else:
        logger.info(f"Cleanup script completed successfully, in {clean_out.elapsed_time} seconds")
        # Sleep for the remaining allotted time for cleanup, in case cleanup was pretty quick
        # This gives worker nodes the chance to clean up as well
        sleep(max(0, DConsts.CLEANUP_TIMEOUT_SECS - clean_out.elapsed_time))


def run_job(
    s3: S3FileSystem,
    s3_bucket: str,
    q_input: SolverQueueInput,
    senv: SolverEnvironment,
    node_ip: str,
    worker_ips: List[str],
    heartbeat: Optional[HeartbeatThread] = None,
) -> CompetitionQueueOutput:

    # Generate a run directory (and a work super-directory)
    work_dir: Path = make_work_dir(senv.solver, senv.is_distributed)
    run_dir: Path = make_run_dir(work_dir, q_input.formula_url)
    formula_path: Path = download_formula(s3, q_input.formula_url, run_dir)

    # Alias various file paths we generate during solving
    input_path = run_dir / "input.json"
    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"
    solver_out_path = run_dir / "solver_out.json"
    ps_stats_path = run_dir / "ps_stats.txt"

    # Create the `input.json file` in the run directory
    s_input: SolverInput = SolverInput.from_queue_input(formula_path, run_dir, q_input, node_ip, worker_ips)
    s_input.write_to_json_file(input_path)

    # Run the solver in a new process by invoking the user-provided command
    shim_logger = lm.get_logger("Leader shim")
    subproc_shim = SubprocessShim(
        shim_logger,
        stdout_path,
        stderr_path,
        ps_stats_path,
    )

    start_time = misc.get_curr_date_str()
    cmd = get_run_command(s_input)
    subproc_output = subproc_shim.run(cmd, q_input.timeout_secs)

    # Distributed leader needs to announce to all workers that they need to clean up
    # The heartbeat thread will announce this fact and then switch back to READY for us automatically
    # We also lead by example and clean up ourselves
    if senv.is_distributed and heartbeat is not None:
        heartbeat.broadcast_cleaning()
        clean_up_self(shim_logger, run_dir)

    # Get the solver's result and write the info to `solver_out.json`
    # TODO replace with just exit codes later
    solver_result_code = get_solver_result(stdout_path)
    s_out = SolverOutput(
        solver_result_code,
        subproc_output.return_code,
        subproc_output.elapsed_time,
        stdout_path,
        stderr_path,
    )

    # Write the `solver_out.json` file to disk
    # We must wrap the write-to-disk in a try because the disk might have no space left
    # This was encountered by a solver during SATCOMP-2025 due to high use of swap memory,
    # so this try/catch-block isn't merely a theoretical risk
    try:
        s_out.write_to_json_file(solver_out_path)
    except OSError as e:
        logger.error(f"Failed to write solver output to {solver_out_path}: {e}")
        logger.error("This likely happened because we ran out of disk space.")
        logger.error(f"Solver output: {s_out.to_dict()}")
        # TODO Ajust return/error code for this
        # Able to store multiple failing reasons?

    # Upload the run directory to s3 (relative to "/tmp")
    s3_dir = run_dir.relative_to("/tmp")
    full_s3_dir = pathing.bucket_and_path_to_s3_uri(s3_bucket, s3_dir)
    logger.info(f"Uploading {run_dir} to {full_s3_dir}")
    s3.upload_directory_tree_uri(run_dir, full_s3_dir, excluding=[formula_path])

    # Remove the run directory, now that we've uploaded everything
    if s3.is_aws:
        dir_to_remove = get_run_dir_to_remove(run_dir)
        logger.info(f"Removing directory {dir_to_remove}")
        shutil.rmtree(dir_to_remove)

    # Create the queue message for the output queue
    elapsed_time = s_out.elapsed_time
    runtime_millisecs = round(elapsed_time * 1000)
    if elapsed_time >= q_input.timeout_secs:
        solver_result_code = SolverResultCode.TIMEOUT

    return CompetitionQueueOutput(
        solver=senv.solver,
        process_return_code=subproc_output.return_code,
        solver_result_code=solver_result_code,
        solver_runtime_millis=runtime_millisecs,
        job_time_start=start_time,
        formula_s3_uri=q_input.formula_url,
        upload_dir_uri=full_s3_dir,
    )


################################################################################


def run(senv: SolverEnvironment):
    logger.info("Started leader entrypoint")

    # Collect the relevant set of (shimmed) AWS resources
    q_in, q_out = SqsQueue.get_queues_from_env(senv)
    s3 = S3FileSystem.get_s3_file_system_from_env(senv)
    s3_results_bucket = S3FileSystem.get_results_bucket_from_env(senv)

    ip = IpItem(is_leader=senv.is_leader)
    worker_ips = []

    # If distributed, register the leader node with Dynamo DB
    ip_table = timestamp_table = ts = lock = hb = None
    if senv.is_distributed and senv.num_workers > 0:
        ip_table, timestamp_table = DynamoTable.get_tables_from_env(senv)
        ip.write_to(ip_table)

        # Start up a heartbeat thread to tell the leader we're alive
        # This thread runs forever, and we never wait on it
        ts = TimestampItem(ip.uuid.value)
        lock = Lock()
        hb = HeartbeatThread(timestamp_table, ts, lock=lock)
        hb.start()

    if senv.is_local:
        add_local_jobs_to_queue(senv, q_in)

    # Start pulling jobs off the job queue
    # If local, stop polling the job queue when it comes back empty 3 times
    # If on AWS, poll continuously
    MAX_EMPTY_QUEUE_ATTEMPTS = 3 if senv.is_local else None
    QUEUE_WAIT_TIME = SQS_MAX_WAIT_TIME_SECS
    num_times_empty_queue = 0
    need_to_claim_workers = senv.is_distributed
    while MAX_EMPTY_QUEUE_ATTEMPTS is None or num_times_empty_queue < MAX_EMPTY_QUEUE_ATTEMPTS:
        # If distributed, claim the desired number of worker nodes
        # This protocol is somewhat complicated, see the docs in `/docs/design`
        if need_to_claim_workers:
            worker_ips = claim_workers(ip_table, timestamp_table, ip, senv.num_workers)
            need_to_claim_workers = False

        # Get a message from the queue. If no message, loop again
        message = q_in.get_message(wait_time_secs=QUEUE_WAIT_TIME)
        if message is None:
            logger.info("No message on the queue, trying again")
            num_times_empty_queue += 1
            continue

        # Read the job message and delete the job from queue
        message_body = message.read()
        logger.info(f"Received message: {message_body}")
        q_input: SolverQueueInput = SolverQueueInput.from_json(message_body)
        message.delete()

        q_output_msg = run_job(
            s3,
            s3_results_bucket,
            q_input,
            senv,
            node_ip=ip.ip_address.value,
            worker_ips=worker_ips,
            heartbeat=hb,
        )

        q_out.put_message(q_output_msg.to_json())
        need_to_claim_workers = senv.is_distributed

    # If we are on AWS, we never get to this point
    if senv.is_aws:
        exit(0)

    # If local, log the output messages on our queue
    logger.info("Exiting the leader entrypoint")
    logger.info("Here are the output queue messages:")

    message = q_out.get_message(wait_time_secs=0)
    while message is not None:
        logger.info(message.read())
        message = q_out.get_message(wait_time_secs=0)
