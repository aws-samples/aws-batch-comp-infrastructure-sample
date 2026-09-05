# Key Abstractions

This page documents the main classes and patterns used throughout the codebase.

## Configuration Classes

**Location:** `scripting/runner/runner_config.py`

### ProjectConfig

Parses the top-level project configuration:

```python
from runner.runner_config import ProjectConfig

config = ProjectConfig.from_yaml("config.yml")
print(config.project)        # Project name
print(config.region)         # AWS region
print(config.solver_type)    # "sat" or "smt"
print(config.solvers)        # List of SolverConfig
```

### SolverConfig

Configuration for individual solvers:

```python
solver = config.solvers[0]
print(solver.name)                         # Solver name
print(solver.docker_dir)                   # Docker build context
print(solver.dockerfile)                   # Dockerfile path
print(solver.is_distributed)               # True/False
print(solver.num_worker_nodes_per_leader)  # Worker count
print(solver.ec2_instance_type)            # e.g., "m6i.xlarge"
print(solver.disk_size)                    # Disk size in GB
```

## Resource Naming

**Location:** `scripting/common/resource_namer.py`

All AWS resources created by this project are named by the `ResourceNamer` class
in `scripting/common/resource_namer.py`. This document describes the naming
convention and how to use it to identify which project owns a given resource.

```python
from common.resource_namer import ResourceNamer

namer = ResourceNamer(project="satcomp25", solver="mallob")
namer.solver_stack()      # "satcomp--solver--satcomp25--mallobStack"
namer.container_name()    # "satcomp--container--satcomp25--mallob"
```

### The `--` Field Separator

Resource names use `--` (double hyphen) as a field separator.
Because `--` is the separator, **project names and solver names must not contain `--`**.
Single hyphens are fine (e.g., `my-solver`, `sat-comp-25`).

The config parser enforces this rule at startup. If a project or solver name
contains `--`, the tool logs an error and exits immediately.

### Naming Pattern

Resources include the solver name and the project name 
so that two projects sharing the same AWS account and region never collide.

The general pattern is:

```
satcomp--{resource-type}--{project}--{solver}
```

For global (non-solver-specific) resources, the solver field is omitted:

```
satcomp--{resource-type}--{project}
```

Because `--` never appears inside a project or solver name, you can always split
on `--` to recover each field unambiguously.

### Resource Types

| Resource | Pattern | Example (`project=satcomp25`, `solver=mallob`) |
|---|---|---|
| Solver stack | `satcomp--solver--{project}--{solver}Stack` | `satcomp--solver--satcomp25--mallobStack` |
| Log group stack | `satcomp--loggroup--{project}--{solver}Stack` | `satcomp--loggroup--satcomp25--mallobStack` |
| Task definition | `satcomp--taskdef--{project}--{solver}Leader` | `satcomp--taskdef--satcomp25--mallobLeader` |
| Container name | `satcomp--container--{project}--{solver}` | `satcomp--container--satcomp25--mallob` |
| ECR image tag | `satcomp--image--{project}--{solver}` | `satcomp--image--satcomp25--mallob` |
| S3 bucket stack | `satcomp--s3--{project}` | `satcomp--s3--satcomp25` |
| ECR repo stack | `satcomp--ecr--{project}` | `satcomp--ecr--satcomp25` |
| VPC stack | `satcomp--vpc--{project}` | `satcomp--vpc--satcomp25` |

### Exceptions

TODO: should all be prefixed with `satcomp--`, but must test that functionality doesn't break.

- **S3 bucket name**: `{account}-{region}-{project}-solver-results`
- **ECR repo name**: `{project}-{region}-ecr`
- **ECS cluster name**: `{project}-{region}-{solver}-ecs-cluster`
- **SQS queue names**: `{account}-{region}-{project}-{solver}-InputQueue`
- **DynamoDB table names**: `{project}-{region}-{solver}-NodeIpTable`
- **Log group path**: `/ecs/{project}-{region}-{solver}`
- **ASG name**: `{project}-{region}-{solver}-Asg`

### Identifying Project Resources

To find all resources belonging to a specific project, look for names that start
with `satcomp--` and contain your project name in the third `--`-delimited field.

For example, to find all resources for project `satcomp25`:

```bash
# List CloudFormation stacks for a project
aws cloudformation list-stacks \
  --query "StackSummaries[?starts_with(StackName, 'satcomp--') && contains(StackName, '--satcomp25')]"
```

## SolverDockerClient

**Location:** `scripting/runner/runner_docker.py`

Handles Docker image building and pushing:

```python
from runner.runner_docker import SolverDockerClient

client = SolverDockerClient(config)
client.build_base_image()
client.build_solver_images()
client.push_solver_images()
```

## SolverJobManager

**Location:** `scripting/runner/runner_jobs.py`

Manages job submission and result processing:

```python
from runner.runner_jobs import SolverJobManager

manager = SolverJobManager(config, jobs_config)
manager.submit_jobs()
manager.process_results()
manager.purge_queues()
```

## SolverEnvironment

**Location:** `scripting/common/solver_env.py`

Encapsulates environment variables passed to solver containers:

```python
from common.solver_env import SolverEnvironment

env = SolverEnvironment.from_env()  # Read from environment
print(env.solver)           # Solver name
print(env.is_distributed)   # True/False
print(env.num_workers)      # Worker count
print(env.is_aws)           # True if running on AWS
print(env.is_local)         # True if running locally
```

Key environment variables:
- `SOLVER_NAME` - Name of the solver
- `PROJECT_NAME` - Name of the project/competition
- `SOLVER_NODE_TYPE` - "parallel" for parallel, "distributed-leader" and "distributed-worker" for different node types
- `NUM_WORKERS` - Number of worker nodes, including the leader node
- `AWS_ACCOUNT_ID` - [AWS only] Account ID
- `AWS_DEFAULT_REGION` - [AWS only] Region name
- `LOCAL_TEST_FILES` - [Local testing only] Path to local test files, in the Docker image
- `LOCAL_TIMEOUT` - [Local testing only] Number of seconds for timeout

## AWS Shim Classes

**Location:** `scripting/harness/aws_shim/`

Wrappers for AWS services with local testing support:

### S3FileSystem

```python
from harness.aws_shim import S3FileSystem

s3 = S3FileSystem.get_s3_file_system_from_env(env)
s3.download_file_uri("s3://bucket/path/file.cnf", local_dir)
s3.upload_directory_tree_uri(local_dir, "s3://bucket/results/")
```

### SqsQueue

```python
from harness.aws_shim import SqsQueue

q_in, q_out = SqsQueue.get_queues_from_env(env)
message = q_in.get_message(wait_time_secs=20)
if message:
    body = message.read()
    message.delete()
q_out.put_message(result_json)
```

### DynamoTable

```python
from harness.aws_shim import DynamoTable

ip_table, ts_table = DynamoTable.get_tables_from_env(env)
```

## Solver I/O Classes

**Location:** `scripting/common/solver_io.py`

### SolverInput

Input parameters passed to `get_run_command()`:

```python
from common.solver_io import SolverInput

s_input = SolverInput(
    formula_file=Path("/tmp/formula.cnf"),
    run_dir=Path("/tmp/run"),
    timeout_seconds=1000,
    solver_options=[],
    node_ip="10.0.0.1",
    worker_node_ips=["10.0.0.2", "10.0.0.3"]
)
```

### SolverOutput

Result from solver execution:

```python
from common.solver_io import SolverOutput, SolverResultCode

s_out = SolverOutput(
    result_code=SolverResultCode.SAT,
    return_code=0,
    elapsed_time=42.5,
    stdout_path=Path("/tmp/stdout.txt"),
    stderr_path=Path("/tmp/stderr.txt")
)
```

### SolverResultCode

Enum for solver results:

```python
from common.solver_io import SolverResultCode

SolverResultCode.SAT            # Satisfiable
SolverResultCode.UNSAT          # Unsatisfiable
SolverResultCode.UNKNOWN        # Unknown/indeterminate
SolverResultCode.TIMEOUT        # Timed out
SolverResultCode.INDETERMINATE  # Could not parse result
```

## DynamoDB Objects (Distributed)

**Location:** `scripting/harness/entrypoints/dynamo_node_objects.py`

### IpItem

Represents a node in the IP table:

```python
from dynamo_node_objects import IpItem

ip = IpItem(is_leader=True)
ip.write_to(ip_table)
ip.claim_workers(ip_table, num_workers=5)
```

### TimestampItem

Heartbeat tracking:

```python
from dynamo_node_objects import TimestampItem

ts = TimestampItem(uuid="node-uuid")
ts.write_to(timestamp_table)
ts.is_alive()
```

## Patterns and Conventions

### Configuration Merging

Solver configs inherit from `global_solver_options`, with per-solver values taking
precedence:

```python
# In runner_config.py
def get_effective_value(solver, field, global_opts):
    return getattr(solver, field, None) or getattr(global_opts, field, None)
```

### Error Handling

Most operations raise exceptions on failure. The CLI catches and reports these
with appropriate exit codes.

### Logging

Use `LoggingManager` for consistent logging:

```python
from common import LoggingManager

lm = LoggingManager()
logger = lm.get_logger("MyComponent")
logger.info("Processing job")
```

## Further Reading

- [Architecture](01-architecture.md) - System overview
- [Testing](03-testing.md) - Test approach and conventions
- [Developer Guide README](README.md) - Detailed codebase guidance
