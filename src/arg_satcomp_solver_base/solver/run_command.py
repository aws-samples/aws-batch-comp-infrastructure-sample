import logging
import os
import subprocess
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

    def run(self, cmd: list, output_directory: str):
        self.logger.info("Running command: %s", str(cmd))
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with open(os.path.join(output_directory, self.stdout_target_loc), "w") as stdout_handle:
            for line in proc.stdout:
                line_str = line.decode("UTF-8")
                self.logger.info(f"STDOUT: {line_str}")
                stdout_handle.write(line_str)
        with open(os.path.join(output_directory, self.stderr_target_loc), "w") as stderr_handle:
            for line in proc.stderr:
                line_str = line.decode("UTF-8")
                self.logger.info(f"STDERR: {line_str}")
                stderr_handle.write(line_str)
        return_code = proc.wait()

        return {
            "stdout": self.stdout_target_loc,
            "stderr": self.stderr_target_loc,
            "return_code": return_code,
            "output_directory": output_directory
        }
