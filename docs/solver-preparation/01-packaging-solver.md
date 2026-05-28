# Packaging Your Solver

Preparing your solver for the competition is much simpler than in previous years, and requires only two files:

1. **Dockerfile** - Tells Docker how to clone and build your solver into an image
2. **solver_cmd.py** - Tells the competition infrastructure how to invoke your solver and interpret results

This page explains how to prepare both files. We provide examples for several solvers in [/examples/solvers](/examples/solvers/). The [Cadical example](/examples/solvers/sat/sequential/cadical/) is well documented.

The examples are good starting points, and we hope you can get your solver running without consulting the details in this guide.

## Preparing your `Dockerfile`

All solvers are run in Docker containers. Docker helps reduce problems when
running code on one system that was developed on another. It standardizes how solver
code is compiled, making it easier for competitors to submit solvers and for organizers
to run them consistently.

For more details on how Docker is used, see the [Architecture section](/docs/architecture/README.md).

Your Dockerfile needs to:

1. Extend our Dockerfile (`FROM satcomp-infrastructure`)
2. Install the software dependencies required by your solver
3. Import, compile, and make your solver executable
4. Copy your customized `solver_cmd.py` to `/opt/amazon/scripting/harness/entrypoints/`

### Example

```dockerfile
FROM satcomp-infrastructure
USER root

# Install dependencies
RUN apt-get update && apt-get install -y cmake build-essential

# Clone and build solver from source (recommended)
RUN git clone https://github.com/your/solver.git && \
    cd solver && \
    mkdir build && cd build && \
    cmake .. && make -j

# Copy your solver_cmd.py
COPY solver_cmd.py /opt/amazon/scripting/harness/entrypoints/
```

### Getting Your Source Code into the Image

There are two approaches:

1. **Clone from repository** (required for the competition submission):
   ```dockerfile
   RUN git clone https://github.com/your/solver.git
   ```

2. **Copy from local directory** (useful for development and testing):
   ```dockerfile
   COPY src /solver
   ```
   Note: When using `COPY`, files must be within the Docker build context (the directory
   specified by `docker_dir` in your config.yml).

### Notes

- The base image runs Ubuntu Noble (v24.04). *Software must be configured for Linux*.
- Your solver runs as `ecs-user`, not root. Files and directories your solver writes to
  at runtime must be owned by `ecs-user`:
  ```dockerfile
  COPY --chown=ecs-user src /solver
  RUN mkdir /mydir && chown ecs-user:ecs-user /mydir
  ```
- Your docker containers will not have internet access when running on AWS.
- **Everything must build from source** - Copying/installing pre-compiled binaries into your docker container is not allowed for security reasons. We will check.
- **Do not edit the competition infrastructure** - We are using the same codebase to run the competition. Your solver risks disqualification if it doesn't build and run for us. If you find issues or bugs, please contact us.

## Preparing `solver_cmd.py`

The `solver_cmd.py` file is a shim between the competition infrastructure and your solver. You must implement three functions:

### `get_run_command()`

Returns a list of command-line tokens to invoke your solver:

```python
from pathlib import Path
from typing import List
from common.solver_io import SolverInput, SolverResultCode

def get_run_command(s_input: SolverInput) -> List[str]:
    return [
        "/solver/build/mysolver",
        str(s_input.formula_file),
        "-t", str(s_input.timeout_seconds)
    ]
```

The `SolverInput` object provides:
- `formula_file` - Path to the formula file (already downloaded)
- `run_dir` - Working directory for this run
- `timeout_seconds` - Time limit for solving
- `solver_options` - Any options from jobs.yml
- `node_ip` - IP address of this node (for distributed)
- `worker_node_ips` - List of worker IPs (for distributed)

### `get_solver_result()`

Parses your solver's stdout to determine the result. For example, for most SAT solvers:

```python
def get_solver_result(stdout_path: Path) -> SolverResultCode:
    if stdout_path.exists():
        with open(stdout_path, 'r') as f:
            content = f.read()

        if "s SATISFIABLE" in content:
            return SolverResultCode.SAT
        elif "s UNSATISFIABLE" in content:
            return SolverResultCode.UNSAT
        elif "s UNKNOWN" in content:
            return SolverResultCode.UNKNOWN

    return SolverResultCode.INDETERMINATE
```

### `get_cleanup_command()` (Distributed Solvers Only)

For distributed solvers, implement cleanup logic that runs after each job:

```python
def get_cleanup_command() -> List[str]:
    return ["pkill", "-f", "mysolver"]
```

This command is called on all nodes (leader and workers) after each job completes.

## Next Step

After preparing your Dockerfile and solver_cmd.py, register your solver in a [config.yml](02-configuration.md) file.
