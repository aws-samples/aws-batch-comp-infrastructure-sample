import logging
import os
import subprocess
import time
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

    def process_line(self, stream, str_name, file_handle):
        if stream:
            line = stream.readline().decode("UTF-8")
            if line != "":
                self.logger.info(f"{str_name}: {line}")
                file_handle.write(line)
                return True    
        return False
            
    def run(self, cmd: list, output_directory: str):
        os.environ['PYTHONUNBUFFERED'] = "1"
        self.logger.info("Creating file locatons")
        with open(os.path.join(output_directory, self.stdout_target_loc), "w") as stdout_handle:
            with open(os.path.join(output_directory, self.stderr_target_loc), "w") as stderr_handle:
                self.logger.info("Running command: %s", str(cmd))
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                while True:
                    return_code = proc.poll()
                    while(self.process_line(proc.stdout, "STDOUT", stdout_handle)):
                        pass
                    while(self.process_line(proc.stderr, "STDERR", stderr_handle)):
                        pass
                    if return_code is not None:
                        break
                    else:
                        time.sleep(0.1)  # sleep 100 ms
        return {
            "stdout": self.stdout_target_loc,
            "stderr": self.stderr_target_loc,
            "return_code": return_code,
            "output_directory": output_directory
        }
