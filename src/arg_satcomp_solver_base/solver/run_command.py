import logging
import os
import subprocess
import threading
from dataclasses import dataclass

from arg_satcomp_solver_base.utils import FileOperations


@dataclass
class CommandRunner:
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

    def run(self, cmd: list, output_directory: str):
        self.logger.info("Running command: %s", str(cmd))
        with open(os.path.join(output_directory, self.stdout_target_loc), "w") as stdout_handle:
            with open(os.path.join(output_directory, self.stderr_target_loc), "w") as stderr_handle:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    universal_newlines=True)
                stdout_t = threading.Thread(target = self.process_stream, args=(proc.stdout, "STDOUT", stdout_handle))
                stderr_t = threading.Thread(target = self.process_stream, args=(proc.stderr, "STDERR", stderr_handle))
                stdout_t.start()
                stderr_t.start()
                return_code = proc.wait()
                stdout_t.join()
                stderr_t.join()
        return {
            "stdout": self.stdout_target_loc,
            "stderr": self.stderr_target_loc,
            "return_code": return_code,
            "output_directory": output_directory
        }
