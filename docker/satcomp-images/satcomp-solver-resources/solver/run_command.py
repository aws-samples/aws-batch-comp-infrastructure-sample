import logging
import os
import time
import subprocess
import threading
import signal
from dataclasses import dataclass

from arg_satcomp_solver_base.utils import FileOperations


@dataclass
class CommandRunner:
    TIMEOUT_RETURNCODE = -100 
    stdout_target_loc: str
    stderr_target_loc: str
    file_operations: FileOperations = FileOperations()

    def __init__(self, stdout_target_loc, stderr_target_loc):
        self.logger = logging.getLogger("RunCommand")
        self.logger.setLevel(logging.DEBUG)
        self.stdout_target_loc = stdout_target_loc
        self.stderr_target_loc = stderr_target_loc
        os.environ['PYTHONUNBUFFERED'] = "1"

    def process_stream(self, stream, str_name, file_handle):
        line = stream.readline()
        while line != "":
            self.logger.info(f"{str_name}: {line}")
            file_handle.write(line)
            line = stream.readline()

    def run(self, cmd: list, output_directory: str, time_out: int):
        self.logger.info("Running command: %s", str(cmd))
        with open(os.path.join(output_directory, self.stdout_target_loc), "w") as stdout_handle:
            with open(os.path.join(output_directory, self.stderr_target_loc), "w") as stderr_handle:
                try:
                    start_time = time.perf_counter()
                    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        universal_newlines=True, start_new_session=True)
                    stdout_t = threading.Thread(target = self.process_stream, args=(proc.stdout, "STDOUT", stdout_handle))
                    stderr_t = threading.Thread(target = self.process_stream, args=(proc.stderr, "STDERR", stderr_handle))
                    stdout_t.start()
                    stderr_t.start()
                    return_code = proc.wait(timeout = time_out)
                    end_time = time.perf_counter()
                    elapsed = end_time - start_time
                    timed_out = False
                except subprocess.TimeoutExpired:
                    timed_out = True
                    elapsed = time_out
                    self.logger.info("Timeout expired for process.  Terminating process group w/sigterm")
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    # wait 10 seconds for a graceful shutdown.
                    try:
                        return_code = proc.wait(timeout = 10)
                    except subprocess.TimeoutExpired:
                        self.logger.info("Process unresponsive.  Terminating process group w/sigkill")
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        return_code = self.TIMEOUT_RETURNCODE
                stdout_t.join()
                stderr_t.join()
        return {
            "stdout": self.stdout_target_loc,
            "stderr": self.stderr_target_loc,
            "return_code": return_code,
            "output_directory": output_directory,
            "elapsed_time": elapsed,
            "timed_out": timed_out
        }
