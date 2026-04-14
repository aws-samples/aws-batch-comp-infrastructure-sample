"""
Thread to periodically track stats about memory usage, etc.
"""

import threading
import time
from pathlib import Path

import common.pathing as pathing
import psutil
from common.misc import str_format_bytes
from common.solver_logging import LoggingManager


class PsStats(threading.Thread):
    """A thread class for logging system CPU/memory/disk statistics."""

    def __init__(self, pid: int, interval_secs=10, also_write_to: str | Path | None = None, should_log: bool = True):
        super().__init__()
        self.pid = pid
        self.sleep_interval = interval_secs
        self.logger = LoggingManager().get_logger("ps_stats")
        self.should_log = should_log
        self.f_path = None if also_write_to is None else pathing.normalize_path(also_write_to)
        self.f = None

    def log(self, s: str):
        if self.should_log:
            self.logger.info(s)

        if self.f is not None:
            self.f.write(s + "\n")

    def get_proc(self, pid: int) -> psutil.Process | None:
        try:
            proc = psutil.Process(pid)
            return proc
        except psutil.NoSuchProcess:
            return None

    def log_proc_info(self, pid: int, recursive: bool = False):
        # Wrap everything in a try-catch, in case the process exits while we are looking at it
        try:
            proc = psutil.Process(pid)

            with proc.oneshot():
                status = proc.status()
                num_threads = proc.num_threads()
                cpu_times = proc.cpu_times()
                memory_info = proc.memory_info()

            self.log(f"[PID {pid}] Process status: {status}")
            self.log(f"[PID {pid}] Num threads: {num_threads}")

            self.log(f"[PID {pid}] Time spent in (user/system), in seconds: {cpu_times.user}/{cpu_times.system}")
            if (
                hasattr(cpu_times, "children_user")
                and hasattr(cpu_times, "children_system")
                and cpu_times.children_user > 0
            ):
                self.log(
                    f"[PID {pid}] Time spent by children processes (user/system), in seconds: {cpu_times.children_user}/{cpu_times.children_system}"
                )
            if hasattr(cpu_times, "iowait"):
                self.log(f"[PID {pid}] Time spent waiting for blocking I/O to complete, in seconds: {cpu_times.iowait}")

            if hasattr(memory_info, "rss"):
                self.log(
                    f"[PID {pid}] Resident set size, non-swapped physical memory: {str_format_bytes(memory_info.rss)}"
                )
            if hasattr(memory_info, "vms"):
                self.log(f"[PID {pid}] Virtual memory size: {str_format_bytes(memory_info.vms)}")
            if hasattr(memory_info, "shared"):
                self.log(f"[PID {pid}] Shared memory size: {str_format_bytes(memory_info.shared)}")
            if hasattr(memory_info, "data"):
                self.log(f"[PID {pid}] Size of data resident set: {str_format_bytes(memory_info.data)}")

            if recursive:
                for child in proc.children(recursive=True):
                    self.log_proc_info(child.pid, recursive=False)

        except psutil.NoSuchProcess:
            self.log(f"[PID {pid}] Doesn't exist")

    def log_cpu_stats(self):
        self.log("---- CPU ----")
        self.log(f"Per-CPU utilization, as a percentage: {psutil.cpu_percent(percpu=True)}")

        load_avg = [x / psutil.cpu_count() * 100 for x in psutil.getloadavg()]
        self.log(f"Average system load over the last 1 minute, as a percentage: \t{load_avg[0]}")
        self.log(f"Average system load over the last 5 minutes, as a percentage: \t{load_avg[1]}")
        self.log(f"Average system load over the last 15 minutes, as a percentage: \t{load_avg[2]}")

    def log_memory_stats(self, devshm: Path):
        self.log("---- MEMORY ----")

        # General memory usage stats
        vmem = psutil.virtual_memory()
        self.log(f"Total memory available (without swap): {str_format_bytes(vmem.available)}")
        self.log(f"Percentage of memory used: {vmem.percent}")

        # System-specific statistics that `virtual_memory()` tracks
        if hasattr(vmem, "active"):
            self.log(f"(Unix) Memory currently in use or very recently used, in RAM: {str_format_bytes(vmem.active)}")
        if hasattr(vmem, "inactive"):
            self.log(f"(Unix) Memory marked as not used (inactive): {str_format_bytes(vmem.inactive)}")
        if hasattr(vmem, "cached"):
            self.log(f"(Linux, BSD) Memory that has been cached: {str_format_bytes(vmem.cached)}")
        if hasattr(vmem, "slab"):
            self.log(f"(Linux) Memory claimed by the in-kernel data structures cache: {str_format_bytes(vmem.slab)}")

        # Swap memory stats
        swap = psutil.swap_memory()
        if swap.total == 0:
            self.log("Swap memory: currently unused")
        else:
            self.log(f"Swap memory total: {str_format_bytes(swap.total)}")
            self.log(f"Swap memory used: {str_format_bytes(swap.used)}")
            self.log(f"Swap memory free: {str_format_bytes(swap.free)}")
            self.log(f"Swap percentage used: {swap.percent}")

        self.log(f"Number of bytes swapped in from disk (cumulative): {str_format_bytes(swap.sin)}")
        self.log(f"Number of bytes swapped out from disk (cumulative): {str_format_bytes(swap.sout)}")

        if devshm.exists():
            sdisk = psutil.disk_usage(str(devshm))
            self.log(f"/dev/shm total space: {str_format_bytes(sdisk.total)}")
            self.log(f"/dev/shm used space: {str_format_bytes(sdisk.used)}")
            self.log(f"/dev/shm free space: {str_format_bytes(sdisk.free)}")
            self.log(f"/dev/shm precentage used: {sdisk.percent}")

    def log_disk_io_stats(self):
        self.log("---- Disk and I/O ----")
        dio = psutil.disk_io_counters()
        if hasattr(dio, "read_time"):
            self.log(f"Time spent reading from disk, in milliseconds: {dio.read_time}")
        if hasattr(dio, "write_time"):
            self.log(f"Time spent writing to disk, in milliseconds: {dio.write_time}")
        if hasattr(dio, "busy_time"):
            self.log(f"(Linux, FreeBSD) Time spent doing actual I/O, in milliseconds: {dio.busy_time}")

    @staticmethod
    def should_loop_again(proc: psutil.Process | None) -> bool:
        return proc is not None and proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE

    def run(self):
        # Open the additional log file, if requested
        if self.f_path is not None:
            self.f = open(self.f_path, "w")

        # On Linux, `/dev/shm` is used as a temp file-system, memory-mapped I/O
        # During logging, we check if this "directory" exists before logging info about it
        devshm = pathing.normalize_path("/dev/shm")

        # First, print some initial system statistics
        self.log(f"Number of logical CPU cores: {psutil.cpu_count(logical=True)}")
        self.log(f"Number of physical CPU cores: {psutil.cpu_count(logical=False)}")
        vmem = psutil.virtual_memory()
        self.log(f"Total physical memory (not including capacity given by swap): {str_format_bytes(vmem.total)}")

        # At the start of tracking, emit info every 0.1 secs for 100 loops (10 secs total),
        # then emit info every second for 100 loops (100 secs total),
        # then switch to slower looping on `interval_secs` seconds
        num_loops = 0
        BACK_OFF_AFTER_LOOPS = 100

        start_time = time.perf_counter()

        proc = self.get_proc(self.pid)
        while self.should_loop_again(proc):
            self.log("---- START PS STATS LOOP ----")
            self.log(f"Time elapsed (secs): {time.perf_counter() - start_time}")

            try:
                self.log("---- PROCESS-GROUP STATS ----")
                self.log_proc_info(self.pid, recursive=True)
            except Exception as e:
                self.logger.error(f"Error: process-group stats error: {e}")

            try:
                self.log_cpu_stats()
            except Exception as e:
                self.logger.error(f"Error: CPU stats error: {e}")

            try:
                self.log_memory_stats(devshm)
            except Exception as e:
                self.logger.error(f"Error: Memory stats error: {e}")

            try:
                self.log_disk_io_stats()
            except Exception as e:
                self.logger.error(f"Error: Disk/I/O stats error: {e}")

            self.log("---- END PS STATS LOOP ----\n")

            # Sleep a bit before looping again
            num_loops += 1
            if num_loops <= BACK_OFF_AFTER_LOOPS:
                time.sleep(0.1)
            elif num_loops <= 2 * BACK_OFF_AFTER_LOOPS:
                time.sleep(1)
            else:
                # Busy wait, in case the proecss exits under us
                # This decreases `.join()` times by the calling subprocess shim
                num_sleeps = round(self.sleep_interval / 2)
                for _ in range(num_sleeps):
                    time.sleep(2)
                    self.log("Done sleeping, checking if process is still alive")
                    proc = self.get_proc(self.pid)
                    if not self.should_loop_again(proc):
                        break

            proc = self.get_proc(self.pid)

        self.log(f"Process {self.pid} seems to have exited, all done looping")

        if self.f is not None:
            self.f.close()
